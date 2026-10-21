"""
Envoie un email de test pour vérifier que l'envoi réel (Gmail...) fonctionne.

Usage :
    python manage.py tester_email votre.adresse@gmail.com

Contrairement à l'envoi automatique aux clients (qui ne bloque jamais la page),
cette commande affiche clairement la cause d'un échec (mot de passe refusé,
serveur injoignable...).
"""
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Envoie un email de test pour vérifier la configuration d'envoi."

    def add_arguments(self, parser):
        parser.add_argument('destinataire', help="Adresse qui recevra l'email de test.")

    def handle(self, *args, **options):
        destinataire = options['destinataire']
        backend = settings.EMAIL_BACKEND
        self.stdout.write(f"Moteur d'envoi : {backend}")

        if 'console' in backend:
            self.stdout.write(self.style.WARNING(
                "L'envoi réel n'est PAS activé (EMAIL_USE_SMTP n'est pas à True dans .env).\n"
                "L'email va s'afficher ci-dessous mais personne ne le recevra."
            ))
        else:
            self.stdout.write(
                f"Serveur : {settings.EMAIL_HOST}:{settings.EMAIL_PORT} | "
                f"compte : {settings.EMAIL_HOST_USER or '(vide)'} | "
                f"expéditeur : {settings.DEFAULT_FROM_EMAIL or '(vide)'}"
            )

        try:
            send_mail(
                subject="ImmoGest — email de test",
                message="Si vous lisez ce message, l'envoi d'emails d'ImmoGest fonctionne.",
                from_email=None,
                recipient_list=[destinataire],
                fail_silently=False,
            )
        except Exception as erreur:
            raise CommandError(f"Échec de l'envoi : {type(erreur).__name__} : {erreur}")

        if 'console' in backend:
            self.stdout.write(self.style.WARNING("Terminé (affichage console uniquement, rien d'envoyé)."))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Email envoyé à {destinataire}. Vérifiez la boîte de réception et les spams."
            ))
