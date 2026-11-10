"""Annonces de démonstration (terrains, villas, appartements à Diamniadio…) pour tester le site public."""
from decimal import Decimal

from django.contrib.auth.models import User  # type: ignore
from django.core.management.base import BaseCommand, CommandError  # type: ignore

from gestion.models import Bien

ANNONCES = [
    dict(nom='Terrain 150 m² – Sébi Ponti', type_bien='terrain', offre='vente', surface=150,
         prix_vente=Decimal('10000000'), statut_juridique='titre_foncier', adresse='Sébi Ponti',
         description='Terrain avec titre foncier, emplacement stratégique pour un projet immobilier.'),
    dict(nom='Parcelles viabilisées 150 à 273 m²', type_bien='terrain', offre='vente', surface=150,
         prix_vente=Decimal('11000000'), statut_juridique='titre_foncier', adresse='Près de la gare TER',
         description='Terrains viabilisés avec accès à l’eau et à l’électricité, titres fonciers individuels.'),
    dict(nom='Terrain en bail – Pôle urbain', type_bien='terrain', offre='vente', surface=180,
         prix_vente=Decimal('13000000'), statut_juridique='bail', adresse='Sortie 11 de l’autoroute à péage',
         description='Lotissement avec possibilité de jumeler des parcelles.'),
    dict(nom='Villa F3 neuve', type_bien='villa', offre='vente', surface=150, nb_pieces=4, nb_chambres=2,
         nb_salles_bain=2, prix_vente=Decimal('23000000'), statut_juridique='bail', adresse='Diamniadio centre',
         description='2 chambres, salon, cuisine, 2 salles de bain, courette avant et arrière.'),
    dict(nom='Appartement 2 chambres – SD City', type_bien='appartement', offre='vente', surface=81, nb_pieces=3,
         nb_chambres=2, nb_salles_bain=2, prix_vente=Decimal('32000000'), statut_juridique='titre_foncier',
         adresse='SD City', description='Proche de l’autoroute à péage et du nouvel aéroport.'),
    dict(nom='Villa 3 pièces à louer', type_bien='villa', offre='location', surface=150, nb_pieces=3,
         nb_chambres=2, loyer_charges=Decimal('150000'), adresse='Diamniadio',
         description='Villa dans le pôle urbain de Diamniadio.'),
]


class Command(BaseCommand):
    help = 'Crée quelques annonces de démonstration à Diamniadio (ventes et location).'

    def handle(self, *args, **options):
        proprietaire = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if proprietaire is None:
            raise CommandError('Créez d’abord un utilisateur (python manage.py createsuperuser).')
        crees = 0
        for donnees in ANNONCES:
            _, cree = Bien.objects.get_or_create(
                proprietaire=proprietaire, nom=donnees['nom'],
                defaults={'ville': 'Diamniadio', 'code_postal': '00000', 'statut': 'libre', **donnees})
            crees += cree
        self.stdout.write(self.style.SUCCESS(f'{crees} annonce(s) créée(s), {len(ANNONCES) - crees} déjà présente(s).'))
