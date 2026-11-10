"""Logique métier d'ImmoGest, indépendante des vues (utilisée par l'API, le site public et les commandes)."""
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings  # type: ignore
from django.contrib.auth.models import User  # type: ignore
from django.contrib.auth.tokens import default_token_generator  # type: ignore
from django.core.exceptions import ValidationError  # type: ignore
from django.core.mail import send_mail  # type: ignore
from django.db import transaction  # type: ignore
from django.db.models import F, Q  # type: ignore
from django.db.models.functions import TruncMonth  # type: ignore
from django.utils.encoding import force_bytes  # type: ignore
from django.utils.http import urlsafe_base64_encode  # type: ignore

from .models import (Bien, BienProprietaire, Contrat, Depense, Document, Intervention, Locataire, Notification,
                     Paiement, Proprietaire, Reservation)
from .scope import proprietaires_visibles


# ── Notifications ────────────────────────────────────────────────────────────
# Implémentées dans gestion/notifications.py (cloche + email + WhatsApp, préférences, journal d'envoi).
# Réexportées ici pour que les vues et l'API continuent d'appeler `services.notifier(...)`.
from .notifications import (gestionnaires_a_notifier, notifier, notifier_contact,  # noqa: E402,F401
                            notifier_gestionnaires)


# ── Contrats ─────────────────────────────────────────────────────────────────

@transaction.atomic
def resilier_contrat(contrat, date_fin=None, statut='resilie', par=None):
    """Termine un contrat : le bien redevient libre et les loyers futurs non payés sont supprimés.
    `par` : compte qui effectue l'action (il n'est pas notifié de sa propre action)."""
    if contrat.statut != 'actif':
        raise ValidationError('Ce contrat n\'est pas actif.')
    fin = date_fin or date.today()
    if fin < contrat.date_debut:
        raise ValidationError({'date_fin': 'La date de fin ne peut pas précéder le début du contrat.'})
    contrat.statut = statut
    contrat.date_fin = fin
    contrat.save()
    contrat.paiements.filter(mois__gt=fin, montant_paye=0).delete()
    notifier_gestionnaires(
        contrat.bien, f'Contrat {"résilié" if statut == "resilie" else "terminé"} : {contrat.bien.nom}',
        f'{contrat.locataire} — fin le {fin:%d/%m/%Y}. Le bien est de nouveau disponible.',
        lien=f'/biens/{contrat.bien_id}', evenement='contrat_resilie', exclure=par)
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


def enregistrer_versement(paiement, montant, mode='', date_versement=None, par=None):
    """Ajoute un versement (total ou partiel) à un loyer ; le statut est recalculé automatiquement.
    `par` : compte qui saisit le versement (les autres gestionnaires sont prévenus, pas lui)."""
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
    contrat = paiement.contrat
    reste = f'Reste à payer : {paiement.solde:.0f} FCFA.' if paiement.solde > 0 else 'Loyer soldé.'
    notifier_gestionnaires(
        contrat.bien, f'Paiement reçu : {contrat.locataire}',
        f'{montant:.0f} FCFA pour {contrat.bien.nom} ({paiement.mois:%m/%Y}). {reste}',
        lien='/paiements', evenement='paiement_recu', exclure=par)
    _prevenir_locataire_et_proprietaires(paiement, Decimal(str(montant)))
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
def creer_reservation(bien, notifier_gestion=True, **donnees):
    """Crée une réservation après contrôle de disponibilité (verrou sur le bien contre le double-booking).
    `notifier_gestion=False` quand la réservation est saisie par le gestionnaire lui-même."""
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
    if notifier_gestion:
        notifier_gestionnaires(
            bien, f'Nouvelle réservation {reservation.reference}',
            f'{reservation.nom} ({reservation.telephone}) — {bien.nom} du {arrivee:%d/%m/%Y}'
            f'{f" au {depart:%d/%m/%Y}" if depart else ""} : {reservation.montant_total:.0f} FCFA '
            f'à régler par {reservation.get_mode_paiement_display()}.',
            lien='/reservations', evenement='reservation_nouvelle')
    return reservation


def changer_statut_reservation(reservation, statut):
    """Change le statut d'une réservation sans ressusciter une réservation annulée sur des dates déjà reprises."""
    if statut == reservation.statut:
        return reservation
    if reservation.statut == 'annulee' and statut in Reservation.STATUTS_BLOQUANTS:
        if reservations_en_conflit(reservation.bien, reservation.date_arrivee, reservation.date_depart,
                                   exclure_pk=reservation.pk):
            raise ValidationError({'statut': 'Ces dates ont été réservées par un autre client entre-temps : '
                                             'impossible de rétablir cette réservation.'})
    reservation.statut = statut
    reservation.save(update_fields=['statut'])
    return reservation


def expirer_reservations_impayees(heures=48):
    """Annule les réservations en attente de paiement depuis plus de `heures` heures."""
    from django.utils import timezone  # type: ignore
    limite = timezone.now() - timedelta(hours=heures)
    expirees = list(Reservation.objects.filter(statut='en_attente', created_at__lt=limite).select_related('bien'))
    for r in expirees:
        r.statut = 'annulee'
        r.save(update_fields=['statut'])
        notifier_gestionnaires(
            r.bien, f'Réservation {r.reference} expirée',
            f'{r.nom} n\'a pas payé sous {heures} h : les dates du {r.date_arrivee:%d/%m/%Y} sont libérées.',
            lien='/reservations', evenement='reservation_expiree')
    return len(expirees)


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
            locataire = p.contrat.locataire
            texte = f'{p.solde:.0f} FCFA pour {p.contrat.bien.nom}, échéance le {cible:%d/%m/%Y}.'
            compte = locataire.compte
            if compte and compte.is_active:
                notifier([compte], f'Loyer à payer dans {delta} jour(s)', texte,
                         lien='/espace/paiements', email=True, whatsapp=False)
                nb += 1
            if locataire.notif_whatsapp:
                notifier_contact(locataire, p.contrat.bien.proprietaire, f'Loyer à payer dans {delta} jour(s)',
                                 f'Bonjour {locataire.prenom}, {texte}', evenement='rappel_locataire', par_email=False)
                nb += int(not (compte and compte.is_active))
    return nb


# ── Propriétaires multiples, quotes-parts et reversements ────────────────────

TOLERANCE_QUOTE_PART = Decimal('0.01')


@transaction.atomic
def definir_proprietaires_bien(bien, parts):
    """Remplace la liste des propriétaires d'un bien. `parts` : liste de (Proprietaire, quote_part en %).

    Règles : pas de doublon, chaque part > 0, et la somme des parts vaut exactement 100 %
    (une liste vide est acceptée : le bien est alors signalé « sans propriétaire » par la vérification de cohérence).
    """
    parts = [(p, Decimal(str(q))) for p, q in parts]
    if not parts:
        BienProprietaire.objects.filter(bien=bien).delete()
        return []
    ids = [p.pk for p, _ in parts]
    if len(ids) != len(set(ids)):
        raise ValidationError({'proprietaires': 'Un même propriétaire ne peut apparaître qu\'une fois.'})
    if any(q <= 0 or q > 100 for _, q in parts):
        raise ValidationError({'proprietaires': 'Chaque quote-part doit être comprise entre 0,01 et 100 %.'})
    total = sum(q for _, q in parts)
    if abs(total - 100) > TOLERANCE_QUOTE_PART:
        raise ValidationError({'proprietaires': f'Les quotes-parts doivent totaliser 100 % (actuellement {total} %).'})
    BienProprietaire.objects.filter(bien=bien).delete()
    return BienProprietaire.objects.bulk_create(
        [BienProprietaire(bien=bien, proprietaire=p, quote_part=q) for p, q in parts])


def _prevenir_locataire_et_proprietaires(paiement, montant):
    """Accusé de réception au locataire (s'il l'accepte par WhatsApp) et, pour chaque propriétaire qui le souhaite,
    sa part du montant encaissé."""
    contrat = paiement.contrat
    bien, gestionnaire = contrat.bien, contrat.bien.proprietaire
    reste = f'Il reste {paiement.solde:.0f} FCFA à régler.' if paiement.solde > 0 else 'Votre loyer est soldé, merci !'
    notifier_contact(
        contrat.locataire, gestionnaire, 'Paiement reçu',
        f'Bonjour {contrat.locataire.prenom}, nous avons bien reçu {montant:.0f} FCFA pour « {bien.nom} » '
        f'({paiement.mois:%m/%Y}). {reste}', evenement='recu_locataire', par_email=False)
    for part in bien.parts.select_related('proprietaire'):
        sa_part = (montant * part.quote_part / 100).quantize(Decimal('1'))
        notifier_contact(
            part.proprietaire, gestionnaire, f'Loyer encaissé : {bien.nom}',
            f'Bonjour {part.proprietaire.prenom or part.proprietaire.nom}, {montant:.0f} FCFA de loyer ont été '
            f'encaissés pour « {bien.nom} » ({paiement.mois:%m/%Y}). Votre part ({part.quote_part:.0f} %) : '
            f'{sa_part:.0f} FCFA, avant commission de gestion.', evenement='paiement_proprietaire')


def mois_suivant(d):
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def releve_proprietaire(proprietaire, mois=None):
    """Décompte de reversement d'un propriétaire pour un mois : sa part des loyers encaissés,
    la commission de gestion, sa part des dépenses, et le net à lui reverser."""
    from django.db.models import Sum  # type: ignore
    debut = premier_jour_du_mois(mois or date.today())
    fin = mois_suivant(debut)
    zero = Decimal('0')
    lignes, tot = [], {'encaisse_part': zero, 'commission': zero, 'depenses_part': zero, 'net': zero}
    for part in proprietaire.parts.select_related('bien'):
        bien, quote = part.bien, part.quote_part / 100
        encaisse = Paiement.objects.filter(contrat__bien=bien, mois=debut).aggregate(
            t=Sum('montant_paye'))['t'] or zero
        depenses = Depense.objects.filter(bien=bien, date__gte=debut, date__lt=fin).aggregate(
            t=Sum('montant'))['t'] or zero
        encaisse_part = (encaisse * quote).quantize(Decimal('1'))
        commission = (encaisse_part * proprietaire.commission_pct / 100).quantize(Decimal('1'))
        depenses_part = (depenses * quote).quantize(Decimal('1'))
        net = encaisse_part - commission - depenses_part
        lignes.append({'bien': bien.pk, 'bien_nom': bien.nom, 'quote_part': part.quote_part,
                       'encaisse_total': encaisse, 'encaisse_part': encaisse_part, 'commission': commission,
                       'depenses_part': depenses_part, 'net': net})
        for cle, val in (('encaisse_part', encaisse_part), ('commission', commission),
                         ('depenses_part', depenses_part), ('net', net)):
            tot[cle] += val
    return {'proprietaire': proprietaire.pk, 'mois': debut, 'commission_pct': proprietaire.commission_pct,
            'lignes': lignes, 'totaux': tot}


# ── Garde-fous de suppression (plus de CASCADE silencieux sur des données vivantes) ──

def verifier_suppression_bien(bien):
    if bien.contrats.filter(statut='actif').exists():
        raise ValidationError("Ce bien a un contrat actif : résiliez-le avant de supprimer le bien.")
    if bien.reservations.filter(statut__in=Reservation.STATUTS_BLOQUANTS, date_arrivee__gte=date.today()).exists():
        raise ValidationError("Ce bien a des réservations à venir : annulez-les avant de le supprimer.")


def verifier_suppression_locataire(locataire):
    if locataire.contrats.filter(statut='actif').exists():
        raise ValidationError("Ce locataire a un contrat actif : résiliez-le avant de supprimer sa fiche.")


def verifier_suppression_proprietaire(proprietaire):
    if proprietaire.parts.exists():
        raise ValidationError("Ce propriétaire possède encore des biens : retirez-le de chaque bien "
                              "(ou désactivez-le) avant de le supprimer.")


# ── Messages des visiteurs ───────────────────────────────────────────────────

def notifier_nouvelle_demande(demande):
    """Prévient les gestionnaires (cloche + email + WhatsApp) d'un message reçu via le site public ou l'API."""
    coordonnees = ' · '.join(x for x in (demande.telephone, demande.email) if x)
    notifier_gestionnaires(
        demande.bien, f'Nouveau message de {demande.nom}',
        f'{demande.message[:200]}' + (f'\nContact : {coordonnees}' if coordonnees else ''),
        lien='/demandes', evenement='message_nouveau')


# ── Vérification de cohérence des données ────────────────────────────────────

def _anomalie(code, gravite, message, url=''):
    return {'code': code, 'gravite': gravite, 'message': message, 'url': url}


def verifier_coherence(proprietaires, utilisateur=None):
    """Liste les incohérences de données du périmètre : chaque anomalie a un code, une gravité
    (« erreur » ou « avertissement »), un message lisible et le lien de la page où la corriger."""
    aujourd_hui = date.today()
    anomalies = []
    biens = list(Bien.objects.filter(proprietaire__in=proprietaires).prefetch_related('parts', 'contrats'))
    for b in biens:
        actifs = [c for c in b.contrats.all() if c.statut == 'actif']
        lien = f'/biens/{b.pk}'
        if b.statut == 'loue' and not actifs:
            anomalies.append(_anomalie('bien_loue_sans_contrat', 'erreur',
                                       f'« {b.nom} » est marqué loué mais n\'a aucun contrat actif.', lien))
        if actifs and b.statut != 'loue':
            anomalies.append(_anomalie('bien_libre_avec_contrat', 'erreur',
                                       f'« {b.nom} » a un contrat actif mais son statut est « {b.get_statut_display()} ».', lien))
        if len(actifs) > 1:
            anomalies.append(_anomalie('contrats_actifs_multiples', 'erreur',
                                       f'« {b.nom} » a {len(actifs)} contrats actifs en même temps.', '/contrats'))
        parts = list(b.parts.all())
        if not parts:
            anomalies.append(_anomalie('bien_sans_proprietaire', 'avertissement',
                                       f'« {b.nom} » n\'a aucun propriétaire renseigné.', lien))
        else:
            total = sum(p.quote_part for p in parts)
            if abs(total - 100) > TOLERANCE_QUOTE_PART:
                anomalies.append(_anomalie('quotes_parts_incorrectes', 'erreur',
                                           f'Les quotes-parts de « {b.nom} » totalisent {total} % au lieu de 100 %.', lien))
    for c in Contrat.objects.filter(bien__proprietaire__in=proprietaires, statut='actif',
                                    date_fin__lt=aujourd_hui).select_related('bien', 'locataire'):
        anomalies.append(_anomalie('contrat_expire_actif', 'avertissement',
                                   f'Le contrat de {c.locataire} ({c.bien.nom}) a expiré le {c.date_fin:%d/%m/%Y} '
                                   f'mais est toujours actif : terminez-le ou prolongez-le.', '/contrats'))
    suspects = (Paiement.objects.filter(contrat__bien__proprietaire__in=proprietaires)
                .annotate(debut_mois=TruncMonth('contrat__date_debut'))
                .filter(Q(montant_paye__gt=F('montant_du')) | Q(mois__lt=F('debut_mois'))
                        | Q(mois__gt=F('contrat__date_fin')))
                .select_related('contrat__bien', 'contrat__locataire'))
    for p in suspects:
        if p.montant_paye > p.montant_du:
            anomalies.append(_anomalie('paiement_excedentaire', 'erreur',
                                       f'Loyer {p.mois:%m/%Y} de {p.contrat.locataire} : payé {p.montant_paye:.0f} '
                                       f'pour {p.montant_du:.0f} dû.', '/paiements'))
        c = p.contrat
        if p.mois < c.date_debut.replace(day=1) or (c.date_fin and p.mois > c.date_fin):
            anomalies.append(_anomalie('paiement_hors_contrat', 'avertissement',
                                       f'Loyer {p.mois:%m/%Y} de {c.locataire} en dehors de la durée du contrat.', '/paiements'))
    resas = list(Reservation.objects.filter(
        Q(date_arrivee__gte=aujourd_hui - timedelta(days=1)) | Q(date_depart__gte=aujourd_hui),
        bien__proprietaire__in=proprietaires, statut__in=Reservation.STATUTS_BLOQUANTS).select_related('bien'))
    for i, r in enumerate(resas):
        if r.bien.capacite and r.nb_personnes > r.bien.capacite:
            anomalies.append(_anomalie('reservation_capacite', 'avertissement',
                                       f'{r.reference} : {r.nb_personnes} personnes pour {r.bien.capacite} places.', '/reservations'))
        for autre in resas[i + 1:]:
            if autre.bien_id == r.bien_id and r.date_arrivee < (autre.date_depart or autre.date_arrivee + timedelta(days=1)) \
                    and autre.date_arrivee < (r.date_depart or r.date_arrivee + timedelta(days=1)):
                anomalies.append(_anomalie('reservations_en_conflit', 'erreur',
                                           f'{r.reference} et {autre.reference} se chevauchent sur « {r.bien.nom} ».', '/reservations'))
    for d in Document.objects.filter(date_expiration__lt=aujourd_hui).filter(
            Q(bien__proprietaire__in=proprietaires) | Q(locataire__proprietaire__in=proprietaires)):
        anomalies.append(_anomalie('document_expire', 'avertissement',
                                   f'Document « {d.titre} » expiré le {d.date_expiration:%d/%m/%Y}.',
                                   f'/biens/{d.bien_id}' if d.bien_id else f'/locataires/{d.locataire_id}'))
    if utilisateur is not None:
        profil = getattr(utilisateur, 'profil_gestion', None)
        if not utilisateur.email and not getattr(settings, 'NOTIFICATIONS_EMAIL_DEFAUT', '') \
                and not (profil and profil.numero_whatsapp):
            anomalies.append(_anomalie('gestionnaire_sans_canal', 'avertissement',
                                       "Aucun email ni numéro WhatsApp : vous ne recevrez aucune alerte hors de l'application.",
                                       '/parametres'))
    return anomalies


def corriger_statuts_biens(proprietaires):
    """Réaligne le statut des biens sur leurs contrats (seule correction automatique sans risque). Renvoie le nombre corrigé."""
    nb = 0
    for b in Bien.objects.filter(proprietaire__in=proprietaires):
        avant = b.statut
        b.synchroniser_statut()
        nb += int(b.statut != avant)
    return nb
