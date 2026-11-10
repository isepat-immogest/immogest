"""
Envoie à chaque propriétaire son relevé de reversement (email et/ou WhatsApp, selon ses choix).

    python manage.py envoyer_releves [--mois AAAA-MM] [--dry-run]

Sans --mois : le mois qui vient de se terminer. `taches_quotidiennes` le lance automatiquement le 1er de chaque mois.
"""
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from gestion import alertes


class Command(BaseCommand):
    help = "Envoie les relevés de reversement mensuels aux propriétaires."

    def add_arguments(self, parser):
        parser.add_argument('--mois', help='Mois concerné, au format AAAA-MM (défaut : le mois précédent).')
        parser.add_argument('--dry-run', action='store_true', help='Affiche les relevés sans rien envoyer.')

    def handle(self, *args, **options):
        mois = None
        if options['mois']:
            try:
                annee, m = options['mois'].split('-')
                mois = date(int(annee), int(m), 1)
            except ValueError:
                raise CommandError('Mois attendu au format AAAA-MM (ex. 2026-10).')
        nb = alertes.envoyer_releves_proprietaires(mois, options['dry_run'], ecrire=self.stdout.write)
        self.stdout.write(self.style.SUCCESS(f'{nb} relevé(s) {"préparé(s) (dry-run)" if options["dry_run"] else "envoyé(s)"}.'))
