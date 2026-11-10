"""Catalogue d'équipements de départ (adapté au contexte sénégalais) ; modifiable ensuite dans l'application."""
from django.db import migrations

CATALOGUE = {
    'confort': ['Climatisation', 'Ventilateur de plafond', 'Chauffe-eau', 'Balcon', 'Terrasse', 'Ascenseur'],
    'eau_energie': [
        "Eau courante (SEN'EAU)", 'Citerne / réservoir', 'Surpresseur', 'Groupe électrogène',
        'Panneaux solaires', 'Compteur électrique individuel (Senelec)', "Compteur d'eau individuel",
    ],
    'cuisine': [
        'Cuisine équipée', 'Réfrigérateur', 'Cuisinière / plaques', 'Machine à laver', 'Literie fournie',
        'Salon / canapé', 'Télévision', 'Placards intégrés',
    ],
    'connectivite': ['Wifi / fibre optique', 'Antenne TV / bouquet satellite'],
    'securite': [
        'Gardien / sécurité 24h/24', 'Porte blindée', 'Portail sécurisé', 'Vidéosurveillance',
        'Interphone / digicode', 'Clôture murée', 'Alarme',
    ],
    'exterieur': ['Parking / garage', 'Jardin', 'Piscine', 'Cour', 'Toit-terrasse', 'Accès personnes à mobilité réduite'],
}


def creer_catalogue(apps, schema_editor):
    Equipement = apps.get_model('gestion', 'Equipement')
    for categorie, noms in CATALOGUE.items():
        for nom in noms:
            eq, cree = Equipement.objects.get_or_create(nom=nom, defaults={'categorie': categorie})
            if not cree and eq.categorie == 'autre':
                eq.categorie = categorie          # un équipement déjà saisi à la main reçoit sa catégorie
                eq.save(update_fields=['categorie'])


class Migration(migrations.Migration):

    dependencies = [
        ('gestion', '0012_equipements_proprietaires_notifications'),
    ]

    operations = [
        migrations.RunPython(creer_catalogue, migrations.RunPython.noop),
    ]
