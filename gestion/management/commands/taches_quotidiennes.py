"""
Tâches quotidiennes (à planifier une fois par jour, ex. 08:00) :
  - génère les loyers du mois pour les contrats actifs ;
  - passe en « retard » les loyers dont l'échéance est dépassée ;
  - annule les réservations impayées depuis plus de 48 h (et prévient le gestionnaire) ;
  - réaligne le statut des biens sur leurs contrats ;
  - rejoue les envois email / WhatsApp en échec ;
  - envoie les rappels d'échéance, le récapitulatif au gestionnaire et les relances aux locataires.

    python manage.py taches_quotidiennes [--dry-run]
"""
from datetime import date

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand

from gestion import notifications, services


class Command(BaseCommand):
    help = "Génération des loyers, détection des retards, expiration des réservations, alertes."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help="N'envoie aucun message.")

    def handle(self, *args, **options):
        crees = services.generer_loyers_du_mois()
        retards = services.actualiser_statuts_retard()
        expirees = services.expirer_reservations_impayees()
        biens_corriges = services.corriger_statuts_biens(User.objects.filter(locataire_profile__isnull=True))
        rejoues, encore_en_echec = notifications.renvoyer_echecs()
        rappels = services.envoyer_rappels_echeance()
        self.stdout.write(
            f'{crees} loyer(s) généré(s), {retards} passé(s) en retard, {expirees} réservation(s) expirée(s), '
            f'{biens_corriges} bien(s) resynchronisé(s), {rejoues} envoi(s) rejoué(s) '
            f'({encore_en_echec} toujours en échec), {rappels} rappel(s) envoyé(s).')
        call_command('envoyer_alertes', dry_run=options['dry_run'])
        if date.today().day == 1:                    # relevés de reversement : une fois par mois
            call_command('envoyer_releves', dry_run=options['dry_run'])
