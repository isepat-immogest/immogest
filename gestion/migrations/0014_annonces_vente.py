import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    """Annonces publiques : biens à vendre (prix de vente, situation foncière) et nouveaux types (terrain, villa)."""

    dependencies = [
        ('gestion', '0013_catalogue_equipements'),
    ]

    operations = [
        migrations.AddField(
            model_name='bien',
            name='offre',
            field=models.CharField(
                choices=[('location', 'À louer'), ('vente', 'À vendre')], default='location',
                help_text='Annonce publique : bien à louer ou à vendre', max_length=10),
        ),
        migrations.AddField(
            model_name='bien',
            name='prix_vente',
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=14, null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                help_text='Prix de vente en FCFA (obligatoire si le bien est « à vendre »)'),
        ),
        migrations.AddField(
            model_name='bien',
            name='statut_juridique',
            field=models.CharField(
                blank=True, max_length=20,
                choices=[('titre_foncier', 'Titre foncier'), ('bail', 'Bail'),
                         ('deliberation', 'Délibération'), ('autre', 'Autre')],
                help_text='Situation foncière affichée sur l’annonce (titre foncier, bail…)'),
        ),
        migrations.AlterField(
            model_name='bien',
            name='loyer_charges',
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=10,
                validators=[django.core.validators.MinValueValidator(0)],
                help_text='Loyer charges comprises (laisser à 0 pour un bien à vendre)'),
        ),
        migrations.AlterField(
            model_name='bien',
            name='type_bien',
            field=models.CharField(
                choices=[('appartement', 'Appartement'), ('maison', 'Maison'), ('studio', 'Studio'),
                         ('commerce', 'Local commercial'), ('garage', 'Garage'), ('chambre', 'Chambre'),
                         ('piscine', 'Piscine'), ('Hotel', 'Hotel'), ('terrain', 'Terrain'),
                         ('villa', 'Villa')],
                default='appartement', max_length=20),
        ),
    ]
