"""Notifications du gestionnaire : cloche de l'application + email + WhatsApp.

Point d'entrée unique : `notifier(...)`. Pour chaque destinataire :
  1. une notification interne (cloche) est toujours créée ;
  2. si demandé, un email et/ou un WhatsApp part ensuite (une fois la transaction validée), en respectant les
     préférences du destinataire (`ProfilGestionnaire`) ;
  3. chaque envoi externe, réussi ou non, est tracé dans `EnvoiNotification` (consultable dans l'application) ;
     les échecs sont rejoués par `renvoyer_echecs()` (commande `taches_quotidiennes`).

À ne pas confondre avec `gestion/emails.py`, qui écrit aux CLIENTS du site public.
"""
import logging
from datetime import timedelta
from functools import partial

from django.conf import settings  # type: ignore
from django.contrib.auth.models import User  # type: ignore
from django.core.mail import send_mail  # type: ignore
from django.db import transaction  # type: ignore
from django.utils import timezone  # type: ignore

from . import whatsapp
from .models import EnvoiNotification, Notification

logger = logging.getLogger(__name__)

# Événements pour lesquels le gestionnaire peut choisir de ne plus être prévenu par email / WhatsApp.
EVENEMENTS = {
    'reservation_nouvelle': 'Nouvelle réservation',
    'reservation_expiree': 'Réservation expirée (non payée)',
    'message_nouveau': 'Nouveau message d\'un visiteur',
    'signalement': "Signalement d'un locataire",
    'paiement_recu': 'Paiement de loyer reçu',
    'loyer_retard': 'Loyers en retard (récapitulatif quotidien)',
    'contrat_echeance': 'Contrats arrivant à échéance',
    'contrat_resilie': 'Contrat résilié',
    'document_expire': 'Documents expirant bientôt',
    'coherence': 'Anomalies détectées dans les données',
}

# Messages à des tiers (propriétaires, locataires) : tracés dans le journal, non désactivables par le gestionnaire.
EVENEMENTS_TIERS = {
    'recu_locataire': 'Reçu de paiement au locataire',
    'rappel_locataire': 'Rappel de loyer au locataire',
    'relance_locataire': 'Relance de loyer en retard',
    'paiement_proprietaire': 'Loyer encaissé, part du propriétaire',
    'releve_proprietaire': 'Relevé mensuel au propriétaire',
}

MAX_TENTATIVES = 3
SIGNATURE = "— ImmoGest"


# ── Destinataires et préférences ─────────────────────────────────────────────

def gestionnaires_a_notifier(bien=None, exclure=None):
    """Comptes de gestion à prévenir : propriétaire du bien (mode isolé), sinon tous les comptes de gestion.
    `exclure` : compte à ne pas prévenir (celui qui vient lui-même de faire l'action)."""
    if bien is not None and not getattr(settings, 'DONNEES_PARTAGEES', False):
        qs = User.objects.filter(pk=bien.proprietaire_id, is_active=True)
    else:
        qs = User.objects.filter(locataire_profile__isnull=True, is_active=True)
    if exclure is not None:
        qs = qs.exclude(pk=getattr(exclure, 'pk', exclure))
    return qs.select_related('profil_gestion')


class Preferences:
    """Canaux effectivement utilisables pour un utilisateur donné."""

    def __init__(self, user):
        profil = getattr(user, 'profil_gestion', None)
        est_locataire = hasattr(user, 'locataire_profile')
        # Un compte de gestion sans email reçoit les alertes sur l'adresse de secours (compte SMTP), comme l'ancien
        # signal de réservation ; un locataire n'a jamais d'adresse de secours.
        self.email = user.email or ('' if est_locataire else getattr(settings, 'NOTIFICATIONS_EMAIL_DEFAUT', ''))
        self.email_actif = profil.notif_email if profil else True
        self.numero = profil.numero_whatsapp if profil else ''
        # Les locataires ne reçoivent pas de WhatsApp : seuls les comptes de gestion ont un profil de notification.
        self.whatsapp_actif = bool(profil and profil.notif_whatsapp) and not est_locataire
        self.desactives = set(profil.evenements_desactives) if profil else set()


# ── Liens et mise en forme ───────────────────────────────────────────────────

def normaliser_lien(lien):
    """Les liens sont relatifs à l'application React (routeur en `/app`) : « /app/reservations » → « /reservations »."""
    lien = (lien or '').strip()
    if lien.startswith('/app/') or lien == '/app':
        lien = lien[4:] or '/'
    return lien


def lien_absolu(lien):
    base = (getattr(settings, 'SITE_URL', '') or '').rstrip('/')
    if not lien or not base:
        return ''
    return f'{base}/app{lien if lien.startswith("/") else "/" + lien}'


def _corps_email(message, lien):
    ouvrir = f'\n\nOuvrir dans ImmoGest : {lien_absolu(lien)}' if lien_absolu(lien) else ''
    return f'{message}{ouvrir}\n\n{SIGNATURE}'


def _texte_whatsapp(titre, message, lien):
    lignes = [f'*ImmoGest* — {titre}']
    if message:
        lignes.append(message)
    if lien_absolu(lien):
        lignes.append(lien_absolu(lien))
    return '\n'.join(lignes)


# ── Envoi par canal (chaque tentative est journalisée) ───────────────────────

def _enregistrer(envoi, statut, erreur=''):
    envoi.statut = statut
    envoi.erreur = erreur[:1000]
    envoi.save(update_fields=['statut', 'erreur', 'tentatives'])
    if statut == 'echec':
        logger.warning('Envoi %s à %s échoué : %s', envoi.canal, envoi.adresse, erreur)
    return envoi


def _tenter(envoi):
    """Exécute l'envoi décrit par `envoi` et met à jour son statut."""
    try:
        if envoi.canal == 'email':
            send_mail(envoi.sujet, envoi.message, None, [envoi.adresse], fail_silently=False)
        else:
            whatsapp.envoyer_whatsapp(envoi.adresse, envoi.message)
    except Exception as exc:  # noqa: BLE001 — un fournisseur qui plante ne doit jamais casser l'action de l'utilisateur
        return _enregistrer(envoi, 'echec', str(exc) or exc.__class__.__name__)
    return _enregistrer(envoi, 'envoye')


def _envoyer_canal(user, notification, canal, adresse, sujet, message, evenement, gestionnaire=None, libelle=''):
    envoi = EnvoiNotification.objects.create(
        destinataire=user, gestionnaire=gestionnaire, libelle_destinataire=libelle, notification=notification,
        evenement=evenement, canal=canal, adresse=adresse, sujet=sujet, message=message, statut='echec',
        tentatives=1)
    return _tenter(envoi)


def _ignorer(user, notification, canal, evenement, raison, sujet='', gestionnaire=None, libelle=''):
    return EnvoiNotification.objects.create(
        destinataire=user, gestionnaire=gestionnaire, libelle_destinataire=libelle, notification=notification,
        evenement=evenement, canal=canal, sujet=sujet, statut='ignore', erreur=raison, tentatives=0)


def _diffuser(user, notification, titre, message, lien, evenement, par_email, par_whatsapp, forcer=False):
    """Envoie les canaux externes d'un destinataire. Renvoie la liste des EnvoiNotification créés."""
    prefs = Preferences(user)
    if not forcer and evenement in prefs.desactives:
        return []
    envois = []
    if par_email and prefs.email_actif:
        if prefs.email:
            envois.append(_envoyer_canal(user, notification, 'email', prefs.email, titre,
                                         _corps_email(message or titre, lien), evenement))
        else:
            envois.append(_ignorer(user, notification, 'email', evenement,
                                   "Aucune adresse email sur ce compte.", titre))
    if par_whatsapp and prefs.whatsapp_actif:
        if not prefs.numero:
            envois.append(_ignorer(user, notification, 'whatsapp', evenement,
                                   "Aucun numéro WhatsApp renseigné dans vos paramètres.", titre))
        elif not whatsapp.whatsapp_configure():
            envois.append(_ignorer(user, notification, 'whatsapp', evenement,
                                   "WhatsApp n'est pas configuré sur le serveur (WHATSAPP_PROVIDER).", titre))
        else:
            envois.append(_envoyer_canal(user, notification, 'whatsapp', prefs.numero, titre,
                                         _texte_whatsapp(titre, message, lien), evenement))
    return envois


# ── API publique ─────────────────────────────────────────────────────────────

def notifier(destinataires, titre, message='', lien='', email=False, evenement='', whatsapp=None):
    """Crée une notification interne pour chaque destinataire, puis envoie email / WhatsApp si demandé.

    `email=True` demande l'email ET le WhatsApp (chacun soumis aux préférences du destinataire) ;
    `whatsapp=False` permet de n'envoyer que l'email. Les envois partent après validation de la transaction
    en cours : une action annulée ne déclenche jamais de message.
    """
    par_whatsapp = email if whatsapp is None else whatsapp
    lien = normaliser_lien(lien)
    for user in list(destinataires):
        notification = Notification.objects.create(destinataire=user, titre=titre, message=message, lien=lien)
        if email or par_whatsapp:
            transaction.on_commit(partial(
                _diffuser, user, notification, titre, message, lien, evenement, email, par_whatsapp))


def notifier_gestionnaires(bien, titre, message='', lien='', evenement='', exclure=None):
    """Prévient les gestionnaires concernés par `bien` (None = tous) par cloche + email + WhatsApp."""
    notifier(gestionnaires_a_notifier(bien, exclure=exclure), titre, message, lien, email=True,
             evenement=evenement)


def _diffuser_contact(contact, gestionnaire, titre, message, lien, evenement, par_email, par_whatsapp):
    """Écrit à un propriétaire ou à un locataire (qui n'a pas forcément de compte), dans le respect de ses choix.

    - Propriétaire : email si `notif_email`, WhatsApp si `notif_whatsapp`.
    - Locataire    : WhatsApp seulement et seulement s'il a donné son accord (`notif_whatsapp`) ; ses emails passent
      par son compte de connexion (voir `notifier`).
    Chaque envoi est tracé au nom du gestionnaire responsable ; un canal refusé par la personne n'est pas tracé."""
    est_proprietaire = hasattr(contact, 'commission_pct')
    libelle = str(contact)
    envois = []
    pour = dict(gestionnaire=gestionnaire, libelle=libelle)
    if est_proprietaire and par_email and contact.notif_email and contact.email:
        envois.append(_envoyer_canal(None, None, 'email', contact.email, titre,
                                     _corps_email(message, lien) if lien else f'{message}\n\n{SIGNATURE}',
                                     evenement, **pour))
    if par_whatsapp and contact.notif_whatsapp:
        numero = getattr(contact, 'numero_whatsapp', '') or contact.telephone
        if not numero:
            envois.append(_ignorer(None, None, 'whatsapp', evenement, 'Aucun numéro renseigné.', titre, **pour))
        elif not whatsapp.whatsapp_configure():
            envois.append(_ignorer(None, None, 'whatsapp', evenement,
                                   "WhatsApp n'est pas configuré sur le serveur (WHATSAPP_PROVIDER).", titre, **pour))
        else:
            envois.append(_envoyer_canal(None, None, 'whatsapp', numero, titre,
                                         _texte_whatsapp(titre, message, ''), evenement, **pour))
    return envois


def notifier_contact(contact, gestionnaire, titre, message, evenement='', par_email=True, par_whatsapp=True):
    """Message à un propriétaire ou un locataire, envoyé après validation de la transaction en cours."""
    transaction.on_commit(partial(
        _diffuser_contact, contact, gestionnaire, titre, message, '', evenement, par_email, par_whatsapp))


def envoyer_test(user):
    """Envoie un message de test sur les canaux actifs de `user` (ignore les préférences par événement).
    Renvoie la liste des EnvoiNotification, pour que l'interface montre ce qui a réussi ou échoué."""
    titre = 'Message de test'
    message = "Si vous recevez ce message, les notifications ImmoGest fonctionnent."
    notification = Notification.objects.create(destinataire=user, titre=titre, message=message)
    return _diffuser(user, notification, titre, message, '', 'test', True, True, forcer=True)


def renvoyer_echecs(max_tentatives=MAX_TENTATIVES, heures=24):
    """Rejoue les envois en échec récents (3 tentatives maximum). Renvoie (réussis, encore_en_échec)."""
    limite = timezone.now() - timedelta(hours=heures)
    reussis = restants = 0
    for envoi in EnvoiNotification.objects.filter(statut='echec', tentatives__lt=max_tentatives,
                                                  created_at__gte=limite):
        envoi.tentatives += 1
        _tenter(envoi)
        if envoi.statut == 'envoye':
            reussis += 1
        else:
            restants += 1
    return reussis, restants
