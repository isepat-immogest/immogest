import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Galerie photo : plusieurs photos par bien."""

    dependencies = [
        ('gestion', '0014_annonces_vente'),
    ]

    operations = [
        migrations.CreateModel(
            name='BienPhoto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(upload_to='biens/galerie/')),
                ('legende', models.CharField(blank=True, help_text='Ex. : Salon, Façade, Vue du terrain', max_length=120)),
                ('ordre', models.PositiveIntegerField(default=0, help_text='Plus petit = affiché en premier')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('bien', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='photos', to='gestion.bien')),
            ],
            options={
                'verbose_name': 'Photo du bien',
                'verbose_name_plural': 'Photos du bien',
                'ordering': ['ordre', 'id'],
            },
        ),
    ]
