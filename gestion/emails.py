"""
Emails de confirmation envoyés automatiquement au CLIENT (visiteur du site public).

- envoyer_accuse_demande      : après un message (formulaire de contact, fiche d'un bien, API publique)
- envoyer_accuse_reservation  : après une réservation (site public ou API publique)

À ne pas confondre avec `services.notifier`, qui prévient les GESTIONNAIRES.

L'envoi ne doit jamais empêcher l'enregistrement de la demande : en cas de problème
(SMTP mal configuré, adresse refusée...), l'erreur est écrite dans les journaux du
serveur et la fonction renvoie False.

Choix volontaire : le texte libre saisi par le client n'est PAS recopié dans l'email.
Les formulaires étant publics, cela éviterait qu'ils servent à envoyer du contenu
arbitraire à n'importe quelle adresse.
"""
import logging

from django.core.mail import send_mail

logger = logging.getLogger(__name__)

SIGNATURE = "Cordialement,\nL'équipe ImmoGest"


def _montant(valeur):
    return f"{valeur:,.0f}".replace(',', ' ')


def _envoyer(destinataire, sujet, corps):
    if not destinataire:
        return False
    try:
        # from_email=None : utilise DEFAULT_FROM_EMAIL (réglages / fichier .env)
        send_mail(sujet, corps, None, [destinataire], fail_silently=False)
        return True
    except Exception:
        logger.warning("Échec d'envoi de l'email de confirmation à %s", destinataire, exc_info=True)
        return False


def envoyer_accuse_demande(demande):
    """Confirme au client que sa demande de contact a bien été reçue."""
    sujet_bien = f" concernant « {demande.bien.nom} »" if demande.bien else ""
    corps = (
        f"Bonjour {demande.nom},\n\n"
        f"Nous avons bien reçu votre demande{sujet_bien}.\n"
        f"Notre équipe vous répondra dans les meilleurs délais, "
        f"par email ou par téléphone.\n\n"
        f"Si vous n'êtes pas à l'origine de cette demande, vous pouvez ignorer ce message.\n\n"
        f"{SIGNATURE}"
    )
    return _envoyer(demande.email, "Nous avons bien reçu votre demande", corps)


def envoyer_accuse_reservation(reservation, lien=None):
    """Envoie au client le récapitulatif de sa réservation.

    `lien` : adresse complète de la page de suivi (protégée par un jeton secret),
    où le client retrouve les consignes de paiement.
    """
    bien = reservation.bien
    depart = (f"Départ : {reservation.date_depart:%d/%m/%Y}\n"
              if reservation.date_depart else "")
    montant = (f"Montant : {_montant(reservation.montant_total)} F CFA\n"
               if reservation.montant_total else "")
    suivi = (f"Retrouvez les consignes de paiement et le suivi de votre réservation ici :\n{lien}\n\n"
             if lien else
             "Retrouvez les consignes de paiement sur la page de confirmation de votre réservation.\n\n")
    corps = (
        f"Bonjour {reservation.nom},\n\n"
        f"Nous avons bien enregistré votre réservation {reservation.reference}.\n\n"
        f"Bien : {bien.nom} — {bien.adresse}, {bien.ville}\n"
        f"Arrivée : {reservation.date_arrivee:%d/%m/%Y}\n"
        f"{depart}"
        f"Nombre de personnes : {reservation.nb_personnes}\n"
        f"Mode de paiement choisi : {reservation.get_mode_paiement_display()}\n"
        f"{montant}\n"
        f"{suivi}"
        f"Notre équipe confirmera votre réservation dès réception du paiement.\n\n"
        f"Si vous n'êtes pas à l'origine de cette réservation, vous pouvez ignorer ce message.\n\n"
        f"{SIGNATURE}"
    )
    return _envoyer(reservation.email, f"Votre réservation {reservation.reference}", corps)
