"""
Alertes et relances automatiques (cloche + email + WhatsApp).

    python manage.py envoyer_alertes [--dry-run]

À planifier une fois par jour (cron ou planificateur de l'hébergeur) :
    0 8 * * *  cd /chemin/vers/le/projet && /chemin/vers/venv/bin/python manage.py envoyer_alertes

- Chaque gestionnaire reçoit UN récapitulatif : loyers en retard, contrats à échéance sous 30 jours,
  documents expirés ou expirant, anomalies de données (selon ses préférences de notification).
- Les locataires ayant un accès en ligne reçoivent une relance graduée (J+1, J+7, puis chaque semaine).
"""
from django.core.management.base import BaseCommand

from gestion import alertes


class Command(BaseCommand):
    help = "Envoie le récapitulatif quotidien aux gestionnaires et les relances aux locataires en retard."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help="Affiche ce qui serait envoyé sans rien envoyer.")

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        gestionnaires = alertes.envoyer_recapitulatifs(dry_run, ecrire=self.stdout.write)
        locataires = alertes.relancer_locataires(dry_run, ecrire=self.stdout.write)
        self.stdout.write(self.style.SUCCESS(
            f"Terminé. {gestionnaires} récapitulatif(s) gestionnaire, {locataires} relance(s) locataire"
            f"{' (dry-run, rien envoyé)' if dry_run else ''}."))
