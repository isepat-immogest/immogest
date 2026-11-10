"""Alertes automatiques quotidiennes envoyées au gestionnaire (cloche + email + WhatsApp).

Un seul récapitulatif par gestionnaire et par jour, regroupant (selon ses préférences) :
loyers en retard, contrats qui arrivent à échéance, documents qui expirent, anomalies de données.
Les locataires ayant un compte reçoivent une relance graduée (J+1, J+7, puis chaque semaine).
"""
from datetime import date, timedelta

from django.db.models import Q  # type: ignore

from . import services
from .models import Contrat, Document, Locataire, Paiement, Proprietaire
from .notifications import Preferences, gestionnaires_a_notifier, notifier, notifier_contact
from .scope import proprietaires_visibles

MAX_LIGNES = 5          # lignes détaillées par rubrique (le reste est résumé : « … et 3 autres »)
JOURS_ECHEANCE = 30     # contrats / documents surveillés à l'avance


def _lignes(titre, lignes):
    """Section de message : titre + 5 lignes maximum."""
    if not lignes:
        return []
    visibles = lignes[:MAX_LIGNES]
    reste = len(lignes) - len(visibles)
    out = [titre] + [f'  - {ligne}' for ligne in visibles]
    if reste > 0:
        out.append(f'  … et {reste} autre(s)')
    return out + ['']


def loyers_en_retard(proprietaires, aujourd_hui=None):
    """Loyers non soldés dont l'échéance est dépassée (statut « retard », ou « partiel » après l'échéance)."""
    aujourd_hui = aujourd_hui or date.today()
    qs = Paiement.objects.filter(contrat__bien__proprietaire__in=proprietaires, statut__in=['retard', 'partiel']
                                 ).select_related('contrat__bien', 'contrat__locataire')
    return [p for p in qs if p.date_echeance < aujourd_hui]


def construire_recapitulatif(user, aujourd_hui=None):
    """Texte du récapitulatif quotidien de `user` (chaîne vide s'il n'y a rien à signaler)."""
    aujourd_hui = aujourd_hui or date.today()
    prefs = Preferences(user)
    perimetre = proprietaires_visibles(user)
    limite = aujourd_hui + timedelta(days=JOURS_ECHEANCE)
    out = []

    if 'loyer_retard' not in prefs.desactives:
        retards = loyers_en_retard(perimetre, aujourd_hui)
        if retards:
            total = sum(p.solde for p in retards)
            out += _lignes(
                f'⚠ {len(retards)} loyer(s) en retard — {total:.0f} FCFA à recouvrer :',
                [f'{p.contrat.locataire} ({p.contrat.bien.nom}) — {p.mois:%m/%Y} — {p.solde:.0f} FCFA'
                 for p in sorted(retards, key=lambda p: p.date_echeance)])

    if 'contrat_echeance' not in prefs.desactives:
        contrats = Contrat.objects.filter(bien__proprietaire__in=perimetre, statut='actif', date_fin__gte=aujourd_hui,
                                          date_fin__lte=limite).select_related('bien', 'locataire').order_by('date_fin')
        out += _lignes(f'📅 {contrats.count()} contrat(s) à échéance sous {JOURS_ECHEANCE} jours :',
                       [f'{c.locataire} ({c.bien.nom}) — fin le {c.date_fin:%d/%m/%Y}' for c in contrats])

    if 'document_expire' not in prefs.desactives:
        docs = Document.objects.filter(date_expiration__lte=limite).filter(
            Q(bien__proprietaire__in=perimetre) | Q(locataire__proprietaire__in=perimetre)).order_by('date_expiration')
        out += _lignes(f'📄 {docs.count()} document(s) expiré(s) ou expirant bientôt :',
                       [f'{d.titre} — {"expiré" if d.date_expiration < aujourd_hui else "expire"} '
                        f'le {d.date_expiration:%d/%m/%Y}' for d in docs])

    if 'coherence' not in prefs.desactives:
        anomalies = [a for a in services.verifier_coherence(perimetre) if a['gravite'] == 'erreur']
        out += _lignes(f'🔧 {len(anomalies)} anomalie(s) de données à corriger :', [a['message'] for a in anomalies])

    return '\n'.join(out).strip()


def envoyer_recapitulatifs(dry_run=False, ecrire=print):
    """Envoie le récapitulatif quotidien à chaque gestionnaire. Renvoie le nombre de gestionnaires concernés."""
    nb = 0
    for user in gestionnaires_a_notifier(None):
        corps = construire_recapitulatif(user)
        if not corps:
            continue
        nb += 1
        if dry_run:
            ecrire(f'[dry-run] Récapitulatif pour {user.username} :\n{corps}\n')
        else:
            notifier([user], 'Récapitulatif du jour', corps, lien='/', email=True, evenement='recapitulatif')
    return nb


def relancer_locataires(dry_run=False, ecrire=print, aujourd_hui=None):
    """Relance graduée des locataires (avec compte et email) : à J+1, J+7 puis chaque semaine de retard."""
    aujourd_hui = aujourd_hui or date.today()
    nb = 0
    locataires = Locataire.objects.filter(
        Q(compte__isnull=False, compte__is_active=True) & ~Q(email='') | Q(notif_whatsapp=True)
    ).select_related('compte', 'proprietaire')
    for loc in locataires:
        retards = [p for p in Paiement.objects.filter(contrat__locataire=loc, statut__in=['retard', 'partiel']
                                                      ).select_related('contrat__bien')
                   if p.date_echeance < aujourd_hui]
        if not retards:
            continue
        jours = (aujourd_hui - min(p.date_echeance for p in retards)).days
        if not (jours in (1, 7) or (jours > 7 and jours % 7 == 0)):
            continue
        nb += 1
        total = sum(p.solde for p in retards)
        message = (f'Bonjour {loc.prenom}, il reste {total:.0f} FCFA à régler pour « {retards[0].contrat.bien.nom} » '
                   f'(retard de {jours} jour(s)). Merci de régulariser ou de contacter votre bailleur en cas de difficulté.')
        if dry_run:
            ecrire(f'[dry-run] Relance à {loc.email or loc.telephone} :\n{message}\n')
            continue
        if loc.compte and loc.compte.is_active and loc.email:
            notifier([loc.compte], 'Rappel : loyer en retard', message, lien='/espace/paiements',
                     email=True, whatsapp=False, evenement='relance_locataire')
        notifier_contact(loc, loc.proprietaire, 'Rappel : loyer en retard', message,
                         evenement='relance_locataire', par_email=False)
    return nb


def texte_releve(releve, proprietaire):
    """Message de relevé de reversement (court : il part aussi par WhatsApp)."""
    lignes = [f'Bonjour {proprietaire.prenom or proprietaire.nom}, votre relevé de {releve["mois"]:%m/%Y} :']
    for l in releve['lignes']:
        lignes.append(f'- {l["bien_nom"]} ({l["quote_part"]:.0f} %) : loyers {l["encaisse_part"]:.0f}, '
                      f'commission -{l["commission"]:.0f}, dépenses -{l["depenses_part"]:.0f} = {l["net"]:.0f} FCFA')
    t = releve['totaux']
    lignes.append(f'Net à vous reverser : {t["net"]:.0f} FCFA'
                  f'{" sur " + proprietaire.compte_reversement if proprietaire.compte_reversement else ""}.')
    return '\n'.join(lignes)


def envoyer_releve_a(prop, mois=None):
    """Envoie tout de suite le relevé d'UN propriétaire et renvoie le détail des envois (pour l'afficher)."""
    from .notifications import _diffuser_contact
    mois = mois or (date.today().replace(day=1) - timedelta(days=1)).replace(day=1)
    releve = services.releve_proprietaire(prop, mois)
    if not releve['lignes']:
        return []
    return _diffuser_contact(prop, prop.gestionnaire, f'Relevé {mois:%m/%Y}', texte_releve(releve, prop), '',
                             'releve_proprietaire', True, True)


def envoyer_releves_proprietaires(mois=None, dry_run=False, ecrire=print):
    """Envoie à chaque propriétaire actif (qui a au moins un bien et un canal accepté) son relevé du mois.
    Par défaut : le mois qui vient de se terminer. Renvoie le nombre de relevés préparés."""
    mois = mois or (date.today().replace(day=1) - timedelta(days=1)).replace(day=1)
    nb = 0
    for prop in Proprietaire.objects.filter(actif=True).select_related('gestionnaire'):
        if not (prop.notif_email and prop.email) and not prop.notif_whatsapp:
            continue
        releve = services.releve_proprietaire(prop, mois)
        if not releve['lignes']:
            continue
        nb += 1
        texte = texte_releve(releve, prop)
        if dry_run:
            ecrire(f'[dry-run] Relevé pour {prop} :\n{texte}\n')
        else:
            notifier_contact(prop, prop.gestionnaire, f'Relevé {mois:%m/%Y}', texte, evenement='releve_proprietaire')
    return nb
