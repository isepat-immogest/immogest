import io
import os

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from gestion.models import BienPhoto

pytestmark = pytest.mark.django_db

AVIF = b'\x00\x00\x00\x1cftypavif\x00\x00\x00\x00avifmif1miaf' + b'\x00' * 40


@pytest.fixture(autouse=True)
def media_temporaire(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def image(nom='p.png', couleur='red'):
    tampon = io.BytesIO()
    Image.new('RGB', (40, 30), couleur).save(tampon, 'PNG')
    return SimpleUploadedFile(nom, tampon.getvalue(), content_type='image/png')


def envoyer(client, bien, *fichiers, **extra):
    return client.post(f'/api/v1/biens/{bien.pk}/galerie/', {'images': list(fichiers), **extra}, format='multipart')


def test_la_galerie_existante_d_un_bien_est_lue_par_l_api(client_gestion, bien):
    """Cas réel : photos enregistrées dans BienPhoto, sans photo principale."""
    for n in (2, 1, 3):
        BienPhoto.objects.create(bien=bien, image=f'biens/galerie/1_{n}.avif', ordre=n)
    g = client_gestion.get(f'/api/v1/biens/{bien.pk}/galerie/').json()
    assert [p['url'].rsplit('/', 1)[-1] for p in g] == ['1_1.avif', '1_2.avif', '1_3.avif']
    assert [p['couverture'] for p in g] == [True, False, False]          # sans photo principale : la 1re est la couverture
    assert all(p['url'].startswith('http') for p in g)


def test_la_photo_principale_passe_avant_la_galerie(client_gestion, bien):
    bien.photo = image('principale.png')
    bien.save()
    BienPhoto.objects.create(bien=bien, image=image('a.png'), ordre=1)
    g = client_gestion.get(f'/api/v1/biens/{bien.pk}/galerie/').json()
    assert [p['principale'] for p in g] == [True, False] and [p['couverture'] for p in g] == [True, False]


def test_la_liste_des_biens_donne_une_vignette_meme_sans_photo_principale(client_gestion, bien):
    assert client_gestion.get(f'/api/v1/biens/{bien.pk}/').json()['vignette'] is None
    BienPhoto.objects.create(bien=bien, image='biens/galerie/1_1.avif', ordre=1)
    v = client_gestion.get(f'/api/v1/biens/{bien.pk}/').json()['vignette']
    assert v.endswith('/biens/galerie/1_1.avif')


def test_ajout_multiple_avec_ordre_et_legende(client_gestion, bien):
    r = envoyer(client_gestion, bien, image('a.png'), image('b.png', 'blue'), legende='Salon')
    assert r.status_code == 200, r.content
    assert [p['legende'] for p in r.json()] == ['Salon', 'Salon']
    assert [p.ordre for p in bien.photos.all()] == [1, 2]
    envoyer(client_gestion, bien, image('c.png'))
    assert [p.ordre for p in bien.photos.all()] == [1, 2, 3]


def test_avif_accepte_et_faux_fichier_refuse(client_gestion, bien):
    ok = envoyer(client_gestion, bien, SimpleUploadedFile('a.avif', AVIF, content_type='image/avif'))
    assert ok.status_code == 200 and ok.json()[0]['url'].endswith('.avif')
    faux = SimpleUploadedFile('x.png', b'pas une image', content_type='image/png')
    assert envoyer(client_gestion, bien, image('b.png'), faux).status_code == 400
    assert bien.photos.count() == 1                                   # rien d'enregistré à moitié


def test_limite_et_taille(client_gestion, bien, monkeypatch):
    from api import galerie_views
    monkeypatch.setattr(galerie_views, 'photos_max', lambda: 2)
    assert envoyer(client_gestion, bien, image('1.png'), image('2.png')).status_code == 200
    r = envoyer(client_gestion, bien, image('3.png'))
    assert r.status_code == 400 and '2 photos' in str(r.json())
    monkeypatch.setattr(galerie_views, 'photos_max', lambda: 20)
    monkeypatch.setattr(galerie_views, 'TAILLE_MAX', 10)
    assert envoyer(client_gestion, bien, image('4.png')).status_code == 400


def test_mettre_en_tete_legender_et_supprimer(client_gestion, bien):
    envoyer(client_gestion, bien, image('a.png'), image('b.png'), image('c.png'))
    a, b, c = list(bien.photos.all())
    r = client_gestion.post(f'/api/v1/biens/{bien.pk}/galerie/{c.pk}/en-tete/')
    assert r.status_code == 200 and [p['id'] for p in r.json()] == [c.pk, a.pk, b.pk]
    r = client_gestion.patch(f'/api/v1/biens/{bien.pk}/galerie/{b.pk}/', {'legende': 'Chambre'}, format='json')
    assert [p['legende'] for p in r.json() if p['id'] == b.pk] == ['Chambre']
    assert client_gestion.patch(f'/api/v1/biens/{bien.pk}/galerie/{b.pk}/', {'legende': 'x' * 121}, format='json').status_code == 400
    chemin = a.image.path
    assert os.path.exists(chemin)
    assert client_gestion.delete(f'/api/v1/biens/{bien.pk}/galerie/{a.pk}/').status_code == 200
    assert not os.path.exists(chemin) and bien.photos.count() == 2


def test_supprimer_la_photo_principale(client_gestion, bien):
    bien.photo = image('principale.png')
    bien.save()
    assert client_gestion.delete(f'/api/v1/biens/{bien.pk}/galerie/principale/').status_code == 200
    bien.refresh_from_db()
    assert not bien.photo
    assert client_gestion.delete(f'/api/v1/biens/{bien.pk}/galerie/principale/').status_code == 404
    assert client_gestion.delete(f'/api/v1/biens/{bien.pk}/galerie/abc/').status_code == 404


def test_cloisonnement_et_droits(settings, bien, client_locataire):
    from django.contrib.auth.models import User
    from rest_framework.test import APIClient
    settings.DONNEES_PARTAGEES = False
    autre = APIClient()
    autre.force_authenticate(User.objects.create_user('autre', 'a@example.com', 'Motdepasse-Solide-1'))
    assert autre.get(f'/api/v1/biens/{bien.pk}/galerie/').status_code == 404
    assert envoyer(autre, bien, image()).status_code == 404
    assert client_locataire.get(f'/api/v1/biens/{bien.pk}/galerie/').status_code == 403


def test_liste_des_biens_sans_requete_par_bien(client_gestion, bien, gestionnaire, django_assert_max_num_queries):
    from gestion.models import Bien
    for i in range(5):
        b = Bien.objects.create(proprietaire=gestionnaire, nom=f'B{i}', adresse='a', ville='v', code_postal='1',
                                surface=10, loyer_charges=1000)
        BienPhoto.objects.create(bien=b, image=f'biens/galerie/{i}_1.avif', ordre=1)
    with django_assert_max_num_queries(12):
        assert client_gestion.get('/api/v1/biens/').status_code == 200
