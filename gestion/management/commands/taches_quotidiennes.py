"""
Tâches quotidiennes (à planifier une fois par jour, ex. 08:00) :
  - génère les loyers du mois pour les contrats actifs ;
  - passe en « retard » les loyers dont l'échéance est dépassée ;
  - annule les réservations impayées depuis plus de 48 h ;
  - envoie les alertes email (voir envoyer_alertes).

    python manage.py taches_quotidiennes [--dry-run]
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand

from gestion import services


class Command(BaseCommand):
    help = "Génération des loyers, détection des retards, expiration des réservations, alertes."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help="N'envoie aucun email.")

    def handle(self, *args, **options):
        crees = services.generer_loyers_du_mois()
        retards = services.actualiser_statuts_retard()
        expirees = services.expirer_reservations_impayees()
        rappels = services.envoyer_rappels_echeance()
        self.stdout.write(f'{crees} loyer(s) généré(s), {retards} passé(s) en retard, '
                          f'{expirees} réservation(s) expirée(s), {rappels} rappel(s) envoyé(s).')
        call_command('envoyer_alertes', dry_run=options['dry_run'])
