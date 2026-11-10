"""Annonces publiques : biens à vendre (terrains, villas…) à côté des locations."""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from gestion.models import Bien


def _vente(gestionnaire, **extra):
    donnees = dict(
        proprietaire=gestionnaire, nom='Terrain Sébi Ponti', type_bien='terrain', offre='vente', ville='Diamniadio',
        adresse='Sébi Ponti', code_postal='00000', surface=150, prix_vente=Decimal('10000000'),
        statut_juridique='titre_foncier')
    donnees.update(extra)
    return Bien.objects.create(**donnees)


def test_un_bien_a_vendre_exige_un_prix(gestionnaire):
    bien = Bien(proprietaire=gestionnaire, nom='Terrain', type_bien='terrain', offre='vente', ville='Diamniadio',
                adresse='x', code_postal='0', surface=150)
    with pytest.raises(ValidationError) as erreur:
        bien.full_clean()
    assert 'prix_vente' in erreur.value.message_dict


def test_un_terrain_a_vendre_n_a_pas_besoin_de_loyer(gestionnaire):
    bien = _vente(gestionnaire)
    bien.full_clean()
    assert bien.loyer_charges == 0 and bien.prix_affiche == Decimal('10000000')


def test_annonces_publiques_melangent_locations_et_ventes(gestionnaire, bien):
    vente = _vente(gestionnaire)
    en_vente = _vente(gestionnaire, nom='Villa F3', type_bien='villa', statut='vente')
    retire = _vente(gestionnaire, nom='Terrain retiré', statut='travaux')
    visibles = set(Bien.annonces_publiques())
    assert {bien, vente, en_vente} <= visibles
    assert retire not in visibles


def test_les_biens_existants_restent_des_locations(bien):
    assert bien.offre == 'location' and not bien.est_a_vendre


def test_api_publique_de_reservation_ignore_les_ventes(gestionnaire, bien):
    vente = _vente(gestionnaire)
    reponse = APIClient().get('/api/v1/public/biens/')
    assert reponse.status_code == 200
    ids = [b['id'] for b in (reponse.json().get('results', reponse.json()))]
    assert bien.id in ids and vente.id not in ids
    assert APIClient().get(f'/api/v1/public/biens/{vente.id}/').status_code == 404


def test_creation_d_une_vente_par_l_api_de_gestion(client_gestion):
    reponse = client_gestion.post('/api/v1/biens/', {
        'nom': 'Parcelle 150 m²', 'type_bien': 'terrain', 'offre': 'vente', 'ville': 'Diamniadio',
        'adresse': 'Zone Sébi Ponti', 'code_postal': '00000', 'surface': '150',
        'prix_vente': '11000000', 'statut_juridique': 'titre_foncier'}, format='json')
    assert reponse.status_code == 201, reponse.content
    assert reponse.json()['prix_vente'] == '11000000.00'


def test_creation_d_une_vente_sans_prix_refusee(client_gestion):
    reponse = client_gestion.post('/api/v1/biens/', {
        'nom': 'Parcelle', 'type_bien': 'terrain', 'offre': 'vente', 'ville': 'Diamniadio',
        'adresse': 'Zone', 'code_postal': '00000', 'surface': '150'}, format='json')
    assert reponse.status_code == 400


def _image(nom='a.png'):
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image
    tampon = io.BytesIO()
    Image.new('RGB', (4, 4), 'red').save(tampon, 'PNG')
    return SimpleUploadedFile(nom, tampon.getvalue(), content_type='image/png')


def test_galerie_photo_ordonnee(settings, tmp_path, bien):
    from gestion.models import BienPhoto
    settings.MEDIA_ROOT = tmp_path
    assert bien.galerie == [] and bien.photo_principale is None
    BienPhoto.objects.create(bien=bien, image=_image('b.png'), legende='Salon', ordre=2)
    BienPhoto.objects.create(bien=bien, image=_image('c.png'), legende='Façade', ordre=1)
    bien.refresh_from_db()
    assert [p['legende'] for p in bien.galerie] == ['Façade', 'Salon']
    assert bien.photo_principale.name.startswith('biens/galerie/')


def test_galerie_gestion_ajout_principale_et_suppression(client, settings, tmp_path, gestionnaire, bien):
    from django.urls import reverse
    settings.MEDIA_ROOT = tmp_path
    client.force_login(gestionnaire)
    reponse = client.post(reverse('bien_photos_ajouter', args=[bien.pk]),
                          {'photos': [_image('a.png'), _image('b.png')]})
    assert reponse.status_code == 302 and bien.photos.count() == 2
    premiere, seconde = list(bien.photos.all())
    client.post(reverse('bien_photo_principale', args=[bien.pk, seconde.pk]))
    assert list(bien.photos.all())[0] == seconde
    client.post(reverse('bien_photo_supprimer', args=[bien.pk, premiere.pk]))
    assert bien.photos.count() == 1


def test_galerie_gestion_refuse_un_faux_fichier_image(client, settings, tmp_path, gestionnaire, bien):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.urls import reverse
    settings.MEDIA_ROOT = tmp_path
    client.force_login(gestionnaire)
    faux = SimpleUploadedFile('virus.png', b'ceci n est pas une image', content_type='image/png')
    client.post(reverse('bien_photos_ajouter', args=[bien.pk]), {'photos': [faux]})
    assert bien.photos.count() == 0
