"""Logique métier d'ImmoGest, indépendante des vues (utilisée par l'API, le site public et les commandes)."""
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings  # type: ignore
from django.contrib.auth.models import User  # type: ignore
from django.contrib.auth.tokens import default_token_generator  # type: ignore
from django.core.exceptions import ValidationError  # type: ignore
from django.core.mail import send_mail  # type: ignore
from django.db import transaction  # type: ignore
from django.utils.encoding import force_bytes  # type: ignore
from django.utils.http import urlsafe_base64_encode  # type: ignore

from .models import Bien, Contrat, Locataire, Notification, Paiement, Reservation
from .scope import proprietaires_visibles


# ── Notifications ────────────────────────────────────────────────────────────

def gestionnaires_a_notifier(bien=None):
    """Comptes de gestion à prévenir : propriétaire du bien, sinon tous les comptes de gestion."""
    if bien is not None and not getattr(settings, 'DONNEES_PARTAGEES', False):
        return User.objects.filter(pk=bien.proprietaire_id)
    return User.objects.filter(locataire_profile__isnull=True, is_active=True)


def notifier(destinataires, titre, message='', lien='', email=False):
    """Crée une notification interne pour chaque destinataire (et un email si demandé)."""
    destinataires = list(destinataires)
    Notification.objects.bulk_create([
        Notification(destinataire=u, titre=titre, message=message, lien=lien) for u in destinataires
    ])
    if email:
        adresses = [u.email for u in destinataires if u.email]
        if adresses:
            send_mail(titre, message or titre, None, adresses, fail_silently=True)


# ── Contrats ─────────────────────────────────────────────────────────────────

@transaction.atomic
def resilier_contrat(contrat, date_fin=None, statut='resilie'):
    """Termine un contrat : le bien redevient libre et les loyers futurs non payés sont supprimés."""
    if contrat.statut != 'actif':
        raise ValidationError('Ce contrat n\'est pas actif.')
    fin = date_fin or date.today()
    contrat.statut = statut
    contrat.date_fin = fin
    contrat.save()
    contrat.paiements.filter(mois__gt=fin, montant_paye=0).delete()
    return contrat


# ── Loyers ───────────────────────────────────────────────────────────────────

def premier_jour_du_mois(d):
    return d.replace(day=1)


def generer_loyers_du_mois(mois=None, proprietaires=None):
    """Crée les loyers manquants du mois pour tous les contrats actifs. Renvoie le nombre créé."""
    mois = premier_jour_du_mois(mois or date.today())
    contrats = Contrat.objects.filter(statut='actif', date_debut__lte=mois.replace(day=28))
    if proprietaires is not None:
        contrats = contrats.filter(bien__proprietaire__in=proprietaires)
    crees = 0
    for contrat in contrats:
        if contrat.date_fin and contrat.date_fin < mois:
            continue
        _, created = Paiement.objects.get_or_create(
            contrat=contrat, mois=mois, defaults={'montant_du': contrat.loyer_total})
        crees += int(created)
    return crees


def enregistrer_versement(paiement, montant, mode='', date_versement=None):
    """Ajoute un versement (total ou partiel) à un loyer ; le statut est recalculé automatiquement."""
    montant = Decimal(montant)
    if montant <= 0:
        raise ValidationError({'montant': 'Le montant doit être positif.'})
    if montant > paiement.solde:
        raise ValidationError({'montant': f'Le versement dépasse le solde restant ({paiement.solde}).'})
    paiement.montant_paye += montant
    if mode:
        paiement.mode_paiement = mode
    paiement.date_paiement = date_versement or date.today()
    paiement.save()
    return paiement


def actualiser_statuts_retard():
    """Passe en « retard » les loyers non soldés dont l'échéance est dépassée. Renvoie le nombre mis à jour."""
    nb = 0
    for p in Paiement.objects.filter(statut='en_attente').select_related('contrat'):
        if p.calculer_statut() == 'retard':
            p.save()
            nb += 1
    return nb


# ── Réservations ─────────────────────────────────────────────────────────────

def reservations_en_conflit(bien, arrivee, depart, exclure_pk=None):
    depart = depart or (arrivee + timedelta(days=1))
    qs = Reservation.objects.filter(bien=bien, statut__in=Reservation.STATUTS_BLOQUANTS)
    if exclure_pk:
        qs = qs.exclude(pk=exclure_pk)
    # Une réservation sans date de départ occupe une nuit.
    return [r for r in qs if arrivee < (r.date_depart or r.date_arrivee + timedelta(days=1))
            and depart > r.date_arrivee]


def dates_occupees(bien):
    """Périodes déjà réservées d'un bien (pour le calendrier public)."""
    return [
        {'debut': r.date_arrivee, 'fin': r.date_depart or r.date_arrivee + timedelta(days=1)}
        for r in Reservation.objects.filter(bien=bien, statut__in=Reservation.STATUTS_BLOQUANTS,
                                            date_arrivee__gte=date.today() - timedelta(days=1))
    ]


def calculer_montant_reservation(bien, arrivee, depart):
    nuits = max(((depart - arrivee).days if depart else 1), 1)
    tarif = bien.prix_nuit if bien.prix_nuit else (bien.loyer_charges / 30)
    return (Decimal(tarif) * nuits).quantize(Decimal('1'))


@transaction.atomic
def creer_reservation(bien, **donnees):
    """Crée une réservation après contrôle de disponibilité (verrou sur le bien contre le double-booking)."""
    bien = Bien.objects.select_for_update().get(pk=bien.pk)
    if bien.statut != 'libre':
        raise ValidationError("Ce bien n'est plus disponible.")
    arrivee, depart = donnees['date_arrivee'], donnees.get('date_depart')
    if reservations_en_conflit(bien, arrivee, depart):
        raise ValidationError({'date_arrivee': 'Ces dates sont déjà réservées pour ce bien.'})
    reservation = Reservation(bien=bien, **donnees)
    reservation.montant_total = calculer_montant_reservation(bien, arrivee, depart)
    reservation.full_clean(exclude=['bien'])
    reservation.save()
    notifier(
        gestionnaires_a_notifier(bien),
        f'Nouvelle réservation {reservation.reference}',
        f'{reservation.nom} — {bien.nom} du {arrivee:%d/%m/%Y}'
        f'{f" au {depart:%d/%m/%Y}" if depart else ""} ({reservation.montant_total:.0f} FCFA).',
        lien='/app/reservations', email=True)
    return reservation


def expirer_reservations_impayees(heures=48):
    """Annule les réservations en attente de paiement depuis plus de `heures` heures."""
    from django.utils import timezone  # type: ignore
    limite = timezone.now() - timedelta(hours=heures)
    return Reservation.objects.filter(statut='en_attente', created_at__lt=limite).update(statut='annulee')


@transaction.atomic
def convertir_reservation_en_contrat(reservation, proprietaire):
    """Crée le locataire et un contrat saisonnier à partir d'une réservation confirmée."""
    parties = reservation.nom.strip().split(' ', 1)
    locataire = Locataire.objects.create(
        proprietaire=proprietaire, prenom=parties[0], nom=parties[1] if len(parties) > 1 else parties[0],
        email=reservation.email, telephone=reservation.telephone)
    contrat = Contrat(
        bien=reservation.bien, locataire=locataire, type_bail='saisonnier',
        date_debut=reservation.date_arrivee, date_fin=reservation.date_depart,
        loyer_mensuel=reservation.montant_total or reservation.bien.loyer_charges, charges_mensuelles=0)
    contrat.full_clean()
    contrat.save()
    reservation.statut = 'confirmee'
    reservation.save(update_fields=['statut'])
    return contrat


# ── Accès locataire ──────────────────────────────────────────────────────────

def lien_activation(user, base_url):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    return f'{base_url}/app/activer/{uid}/{default_token_generator.make_token(user)}'


@transaction.atomic
def inviter_locataire(locataire, base_url):
    """Crée (ou réactive) le compte du locataire et renvoie un lien d'activation à usage unique."""
    user = locataire.compte
    if user is None:
        base = f'{locataire.prenom}.{locataire.nom}'.lower().replace(' ', '')
        username, i = base, 1
        while User.objects.filter(username=username).exists():
            i += 1
            username = f'{base}{i}'
        user = User(username=username, email=locataire.email, first_name=locataire.prenom,
                    last_name=locataire.nom)
        user.set_unusable_password()
        user.save()
        locataire.compte = user
        locataire.save(update_fields=['compte'])
    else:
        user.is_active = True
        user.set_unusable_password()
        user.save()
    lien = lien_activation(user, base_url)
    if locataire.email:
        send_mail(
            "Activez votre espace locataire ImmoGest",
            f"Bonjour {locataire.prenom},\n\nVotre espace locataire est prêt (identifiant : {user.username}).\n"
            f"Choisissez votre mot de passe via ce lien personnel :\n{lien}\n",
            None, [locataire.email], fail_silently=True)
    return user, lien


def perimetre(user):
    return proprietaires_visibles(user)


def interventions_du_locataire(locataire):
    """Interventions visibles par un locataire : celles qu'il a signalées et celles du bien pendant ses contrats
    (un locataire ne voit jamais l'historique des précédents occupants)."""
    from django.db.models import Q  # type: ignore
    from .models import Intervention
    filtre = Q(pk__in=[])
    if locataire.compte_id:
        filtre |= Q(signale_par_id=locataire.compte_id)
    for contrat in locataire.contrats.all():
        fin = contrat.date_fin or date.today()
        filtre |= Q(bien_id=contrat.bien_id, date_signalement__gte=contrat.date_debut,
                    date_signalement__lte=fin)
    return Intervention.objects.filter(filtre).distinct().order_by('-date_signalement')


# ── Rentabilité, score, calendrier, rappels ──────────────────────────────────

def il_y_a_12_mois(d=None):
    d = d or date.today()
    return date(d.year - 1, d.month, 1)


def rentabilite_bien(bien):
    """Revenus encaissés, dépenses et rendement d'un bien sur les 12 derniers mois."""
    from django.db.models import Sum  # type: ignore
    debut = il_y_a_12_mois()
    revenus = Paiement.objects.filter(contrat__bien=bien, mois__gte=debut).aggregate(
        t=Sum('montant_paye'))['t'] or Decimal('0')
    depenses_qs = bien.depenses.filter(date__gte=debut)
    depenses = depenses_qs.aggregate(t=Sum('montant'))['t'] or Decimal('0')
    net = revenus - depenses
    rendement = None
    if bien.prix_acquisition:
        rendement = round(float(net) / float(bien.prix_acquisition) * 100, 2)
    par_categorie = {c['categorie']: c['t'] for c in depenses_qs.values('categorie').annotate(t=Sum('montant'))}
    return {'revenus_12m': revenus, 'depenses_12m': depenses, 'net_12m': net,
            'rendement_net_pct': rendement, 'depenses_par_categorie': par_categorie}


def score_locataire(locataire):
    """Score de fiabilité (0-100) : ponctualité des paiements + taux d'effort (loyer / revenu)."""
    paiements = list(Paiement.objects.filter(contrat__locataire=locataire).select_related('contrat'))
    echus = [p for p in paiements if p.date_echeance <= date.today()]
    if not echus:
        return {'score': None, 'niveau': 'inconnu', 'nb_paiements': 0, 'nb_retards': 0, 'taux_effort': None}
    retards = 0
    for p in echus:
        paye_en_retard = p.statut == 'paye' and p.date_paiement and p.date_paiement > p.date_echeance
        if p.statut in ('retard', 'partiel') or paye_en_retard:
            retards += 1
    score = round(100 * (1 - retards / len(echus)))
    taux_effort = None
    contrat = locataire.contrat_actif
    if locataire.revenu_mensuel and contrat:
        taux_effort = round(float(contrat.loyer_total) / float(locataire.revenu_mensuel) * 100)
        if taux_effort > 40:
            score = max(score - 15, 0)
    niveau = 'bon' if score >= 80 else 'moyen' if score >= 50 else 'risque'
    return {'score': score, 'niveau': niveau, 'nb_paiements': len(echus), 'nb_retards': retards,
            'taux_effort': taux_effort}


def evenements_calendrier(proprietaires, debut, fin):
    """Événements du calendrier entre deux dates : séjours, échéances de loyer, fins de contrat, interventions."""
    evts = []
    for r in Reservation.objects.filter(bien__proprietaire__in=proprietaires, date_arrivee__lte=fin).exclude(
            statut='annulee').select_related('bien'):
        sortie = r.date_depart or r.date_arrivee
        if sortie >= debut:
            evts.append({'id': f'res-{r.pk}', 'type': 'reservation', 'titre': f'{r.nom} — {r.bien.nom}',
                         'debut': r.date_arrivee, 'fin': sortie, 'statut': r.statut, 'url': '/reservations'})
    for p in Paiement.objects.filter(contrat__bien__proprietaire__in=proprietaires, mois__gte=debut.replace(day=1) - timedelta(days=31),
                                     mois__lte=fin).exclude(statut='paye').select_related('contrat__locataire',
                                                                                         'contrat__bien'):
        if debut <= p.date_echeance <= fin:
            evts.append({'id': f'loyer-{p.pk}', 'type': 'loyer', 'titre': f'Loyer {p.contrat.locataire}',
                         'debut': p.date_echeance, 'fin': p.date_echeance, 'statut': p.statut, 'url': '/paiements'})
    for c in Contrat.objects.filter(bien__proprietaire__in=proprietaires, statut='actif', date_fin__gte=debut,
                                    date_fin__lte=fin).select_related('bien', 'locataire'):
        evts.append({'id': f'fin-{c.pk}', 'type': 'contrat', 'titre': f'Fin de bail — {c.locataire}',
                     'debut': c.date_fin, 'fin': c.date_fin, 'statut': c.statut, 'url': '/contrats'})
    from .models import Intervention
    for i in Intervention.objects.filter(bien__proprietaire__in=proprietaires, date_intervention__gte=debut,
                                         date_intervention__lte=fin).exclude(statut='annulee').select_related('bien'):
        evts.append({'id': f'int-{i.pk}', 'type': 'intervention', 'titre': f'{i.titre} — {i.bien.nom}',
                     'debut': i.date_intervention, 'fin': i.date_intervention, 'statut': i.statut,
                     'url': '/interventions'})
    return sorted(evts, key=lambda e: e['debut'])


def envoyer_rappels_echeance(jours=(3, 1)):
    """Rappels d'échéance (J-3, J-1) aux locataires ayant un compte, et récapitulatif aux gestionnaires."""
    aujourd_hui = date.today()
    nb = 0
    for delta in jours:
        cible = aujourd_hui + timedelta(days=delta)
        paiements = Paiement.objects.filter(
            statut__in=['en_attente', 'partiel'], mois=cible.replace(day=1)).select_related(
            'contrat__locataire__compte', 'contrat__bien')
        for p in paiements:
            if p.date_echeance != cible:
                continue
            compte = p.contrat.locataire.compte
            if compte and compte.is_active:
                notifier([compte], f'Loyer à payer dans {delta} jour(s)',
                         f'{p.solde:.0f} FCFA pour {p.contrat.bien.nom}, échéance le {cible:%d/%m/%Y}.',
                         lien='/espace/paiements', email=True)
                nb += 1
    return nb
