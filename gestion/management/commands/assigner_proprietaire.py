"""
Rattache un ou plusieurs propriétaires à des biens, avec leurs quotes-parts (la somme doit valoir 100 %).

Exemples :
    python manage.py assigner_proprietaire --lister
    python manage.py assigner_proprietaire --bien 3 --proprietaire 1
    python manage.py assigner_proprietaire --bien 3 --proprietaire 1:60 --proprietaire Ndiaye:40
    python manage.py assigner_proprietaire --sans-proprietaire --proprietaire 1
    (ajoutez --dry-run pour voir sans rien modifier)

Tout est fait en une seule transaction : si une quote-part est incorrecte, rien n'est modifié.
Attention : pour un bien indiqué par --bien, la liste des propriétaires est REMPLACÉE.
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from gestion import services
from gestion.models import Bien, Proprietaire


class Command(BaseCommand):
    help = "Rattache des propriétaires (avec quotes-parts) à des biens."

    def add_arguments(self, parser):
        parser.add_argument('--bien', type=int, action='append', default=[], metavar='ID',
                            help='Numéro du bien (répétable).')
        parser.add_argument('--sans-proprietaire', action='store_true',
                            help="Cible tous les biens qui n'ont encore aucun propriétaire.")
        parser.add_argument('--proprietaire', action='append', default=[], metavar='ID_OU_NOM[:PART]',
                            help='Propriétaire (numéro ou nom) et sa part en %%. Répétable. '
                                 'La part est facultative s\'il n\'y a qu\'un propriétaire (100 %%).')
        parser.add_argument('--dry-run', action='store_true', help='Affiche sans rien modifier.')
        parser.add_argument('--lister', action='store_true', help='Liste les propriétaires et les biens, puis quitte.')

    def trouver_proprietaire(self, texte):
        if texte.isdigit():
            try:
                return Proprietaire.objects.get(pk=int(texte))
            except Proprietaire.DoesNotExist:
                raise CommandError(f"Propriétaire n° {texte} introuvable (utilisez --lister).")
        trouves = list(Proprietaire.objects.filter(Q(nom__icontains=texte) | Q(prenom__icontains=texte)))
        if not trouves:
            raise CommandError(f"Aucun propriétaire ne correspond à « {texte} » (utilisez --lister).")
        if len(trouves) > 1:
            noms = ', '.join(f'{p.pk}={p}' for p in trouves)
            raise CommandError(f"« {texte} » correspond à plusieurs propriétaires ({noms}) : utilisez le numéro.")
        return trouves[0]

    def lister(self):
        self.stdout.write(self.style.MIGRATE_HEADING('Propriétaires'))
        for p in Proprietaire.objects.order_by('nom'):
            self.stdout.write(f'  {p.pk:>4}  {p}  ({p.telephone})  — {p.parts.count()} bien(s)')
        self.stdout.write(self.style.MIGRATE_HEADING('Biens'))
        for b in Bien.objects.order_by('id').prefetch_related('parts__proprietaire'):
            parts = ', '.join(f'{x.proprietaire} {x.quote_part:g} %' for x in b.parts.all()) or 'AUCUN PROPRIÉTAIRE'
            self.stdout.write(f'  {b.pk:>4}  {b.nom}  →  {parts}')

    def handle(self, *args, **options):
        if options['lister']:
            return self.lister()
        if not options['proprietaire']:
            raise CommandError('Indiquez au moins un --proprietaire (ou --lister pour voir les numéros).')
        if not options['bien'] and not options['sans_proprietaire']:
            raise CommandError('Indiquez les biens : --bien ID (répétable) ou --sans-proprietaire.')

        parts = []
        for brut in options['proprietaire']:
            texte, _, part = brut.partition(':')
            prop = self.trouver_proprietaire(texte.strip())
            if part:
                try:
                    part = Decimal(part.replace(',', '.'))
                except InvalidOperation:
                    raise CommandError(f"Part invalide « {part} » (ex : 60 ou 33.33).")
            elif len(options['proprietaire']) == 1:
                part = Decimal(100)
            else:
                raise CommandError(f"Indiquez la part de « {prop} » : --proprietaire {prop.pk}:60")
            parts.append((prop, part))

        biens = {}
        for pk in options['bien']:
            try:
                biens[pk] = Bien.objects.get(pk=pk)
            except Bien.DoesNotExist:
                raise CommandError(f'Bien n° {pk} introuvable (utilisez --lister).')
        if options['sans_proprietaire']:
            for b in Bien.objects.filter(parts__isnull=True):
                biens.setdefault(b.pk, b)
        if not biens:
            self.stdout.write('Aucun bien à traiter.')
            return

        resume = ', '.join(f'{p} {q:g} %' for p, q in parts)
        try:
            with transaction.atomic():
                for b in biens.values():
                    services.definir_proprietaires_bien(b, parts)
                    self.stdout.write(f'  bien {b.pk} « {b.nom} » → {resume}')
                if options['dry_run']:
                    transaction.set_rollback(True)
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages) + ' Rien n\'a été modifié.')
        etat = "à modifier (dry-run : rien n'a été enregistré)" if options['dry_run'] else 'mis à jour'
        self.stdout.write(self.style.SUCCESS(f'{len(biens)} bien(s) {etat}.'))