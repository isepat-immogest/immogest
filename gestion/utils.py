"""Petits utilitaires partagés par l'application."""

MOIS_FR = [
    'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
    'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre',
]
MOIS_FR_ABREGE = [
    'jan.', 'fév.', 'mars', 'avr.', 'mai', 'juin',
    'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.',
]


def mois_annee_fr(d):
    """Formate une date en 'mois année' français (ex : 'septembre 2026'), sans
    dépendre de la locale système — souvent indisponible sur les hébergeurs,
    ce qui ferait planter tout code utilisant locale.setlocale('fr_FR.UTF-8')."""
    return f"{MOIS_FR[d.month - 1]} {d.year}"


def mois_annee_fr_abrege(d):
    """Version courte, ex : 'sept. 2026' (utile pour les libellés de graphique)."""
    return f"{MOIS_FR_ABREGE[d.month - 1]} {d.year}"


def normaliser_telephone(valeur, indicatif='221'):
    """Met un numéro au format international « +221771234567 » (Sénégal par défaut).

    - « 77 123 45 67 », « 77.123.45.67 » → « +221771234567 »
    - « 00221771234567 » ou « 221771234567 » → « +221771234567 »
    - un numéro déjà international (« +33612345678 ») est conservé tel quel, sans espaces.
    Une valeur vide reste vide ; une valeur inexploitable est renvoyée nettoyée (la validation la refusera).
    """
    if not valeur:
        return ''
    brut = str(valeur).strip()
    chiffres = ''.join(c for c in brut if c.isdigit())
    if not chiffres:
        return brut
    if brut.startswith('+'):
        return '+' + chiffres
    if chiffres.startswith('00'):
        return '+' + chiffres[2:]
    if chiffres.startswith(indicatif) and len(chiffres) == len(indicatif) + 9:
        return '+' + chiffres
    if len(chiffres) == 9:          # numéro local sénégalais (7X XXX XX XX ou 33 XXX XX XX)
        return '+' + indicatif + chiffres
    return chiffres
