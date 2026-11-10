"""Ajoute en une commande toutes les photos d'un dossier à la galerie d'un bien.

Exemples :
    python manage.py importer_photos 7 "C:\\Users\\bmd\\Pictures\\villa"
    python manage.py importer_photos "Villa F3 neuve" "C:\\Users\\bmd\\Pictures\\villa" --principale
"""
from pathlib import Path

from django.core.files import File  # type: ignore
from django.core.management.base import BaseCommand, CommandError  # type: ignore

from gestion.models import Bien, BienPhoto

EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}


class Command(BaseCommand):
    help = 'Importe les images d\'un dossier dans la galerie photo d\'un bien (numéro ou nom du bien).'

    def add_arguments(self, parser):
        parser.add_argument('bien', help='Numéro (id) ou nom exact du bien')
        parser.add_argument('dossier', help='Dossier contenant les images')
        parser.add_argument('--principale', action='store_true',
                            help='Utiliser la première image comme photo principale si le bien n\'en a pas')

    def handle(self, *args, **options):
        ref = options['bien']
        bien = Bien.objects.filter(pk=ref).first() if ref.isdigit() else Bien.objects.filter(nom=ref).first()
        if bien is None:
            raise CommandError(f'Bien introuvable : {ref}')
        dossier = Path(options['dossier'])
        if not dossier.is_dir():
            raise CommandError(f'Dossier introuvable : {dossier}')
        fichiers = sorted(f for f in dossier.iterdir() if f.suffix.lower() in EXTENSIONS)
        if not fichiers:
            raise CommandError('Aucune image (jpg, png, webp, gif) dans ce dossier.')

        ordre = (bien.photos.order_by('-ordre').values_list('ordre', flat=True).first() or 0)
        for i, fichier in enumerate(fichiers, start=1):
            with fichier.open('rb') as f:
                if i == 1 and options['principale'] and not bien.photo:
                    bien.photo.save(fichier.name, File(f), save=True)
                else:
                    BienPhoto.objects.create(bien=bien, image=File(f, name=fichier.name),
                                             legende=fichier.stem.replace('_', ' ').replace('-', ' ')[:120],
                                             ordre=ordre + i)
        self.stdout.write(self.style.SUCCESS(f'{len(fichiers)} photo(s) importée(s) pour « {bien.nom} ».'))
