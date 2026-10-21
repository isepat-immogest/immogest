from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from gestion import services
from gestion.models import Bien, Contrat, Depense, Document, Locataire, Notification, Paiement

pytestmark = pytest.mark.django_db
API = '/api/v1'


def test_rentabilite_du_bien(client_gestion, bien, contrat):
    bien.prix_acquisition = Decimal('10000000')
    bien.save()
    p = Paiement.objects.create(contrat=contrat, mois=date.today().replace(day=1), montant_du=150000,
                                montant_paye=150000)
    Depense.objects.create(bien=bien, categorie='travaux', libelle='Peinture', montant=Decimal('50000'))
    r = client_gestion.get(f'{API}/biens/{bien.pk}/rentabilite/').data
    assert p.statut == 'paye'
    assert r['revenus_12m'] == 150000 and r['depenses_12m'] == 50000 and r['net_12m'] == 100000
    assert r['rendement_net_pct'] == 1.0
    assert 'travaux' in r['depenses_par_categorie']


def test_crud_depense_et_resume(client_gestion, bien):
    r = client_gestion.post(f'{API}/depenses/', {'bien': bien.pk, 'categorie': 'taxe', 'libelle': 'Taxe 2026',
                                                 'montant': '25000', 'date': str(date.today())}, format='json')
    assert r.status_code == 201 and r.data['bien_nom'] == bien.nom
    resume = client_gestion.get(f'{API}/depenses/resume/').data
    assert resume['depenses_12m'] == 25000 and resume['par_categorie'][0]['categorie'] == 'taxe'


def test_depense_sur_bien_dun_autre_compte_refusee(settings, bien):
    from django.contrib.auth.models import User
    settings.DONNEES_PARTAGEES = False
    autre = User.objects.create_user('autre', password='Motdepasse-Solide-1')
    c = APIClient()
    c.force_authenticate(autre)
    r = c.post(f'{API}/depenses/', {'bien': bien.pk, 'libelle': 'x', 'montant': '1'}, format='json')
    assert r.status_code == 400


def test_score_locataire_bon_puis_risque(locataire, contrat):
    assert services.score_locataire(locataire)['niveau'] == 'inconnu'
    for k in (1, 2, 3):
        mois = (date.today().replace(day=1) - timedelta(days=31 * k)).replace(day=1)
        Paiement.objects.create(contrat=contrat, mois=mois, montant_du=100, montant_paye=100,
                                date_paiement=mois.replace(day=2))
    assert services.score_locataire(locataire)['score'] == 100
    mois = (date.today().replace(day=1) - timedelta(days=31 * 4)).replace(day=1)
    Paiement.objects.create(contrat=contrat, mois=mois, montant_du=100, montant_paye=0)
    s = services.score_locataire(locataire)
    assert s['score'] == 75 and s['nb_retards'] == 1 and s['niveau'] == 'moyen'


def test_score_penalise_le_taux_deffort_eleve(locataire, contrat):
    locataire.revenu_mensuel = Decimal('200000')  # loyer 150 000 => 75 %
    locataire.save()
    mois = (date.today().replace(day=1) - timedelta(days=31)).replace(day=1)
    Paiement.objects.create(contrat=contrat, mois=mois, montant_du=100, montant_paye=100, date_paiement=mois)
    s = services.score_locataire(locataire)
    assert s['taux_effort'] == 75 and s['score'] == 85


def test_calendrier_regroupe_les_evenements(client_gestion, bien, contrat):
    from gestion.models import Reservation
    debut = date.today()
    Reservation.objects.create(bien=bien, nom='Client', telephone='+221771234567', date_arrivee=debut + timedelta(days=2),
                               date_depart=debut + timedelta(days=4), mode_paiement='wave')
    r = client_gestion.get(f'{API}/calendrier/', {'debut': str(debut), 'fin': str(debut + timedelta(days=30))})
    assert r.status_code == 200
    assert 'reservation' in {e['type'] for e in r.data['evenements']}
    assert client_gestion.get(f'{API}/calendrier/', {'debut': 'x', 'fin': 'y'}).status_code == 400
    assert client_gestion.get(f'{API}/calendrier/', {'debut': str(debut), 'fin': str(debut + timedelta(days=400))}).status_code == 400


def test_upload_document_valide_et_telechargement_prive(client_gestion, locataire, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    f = SimpleUploadedFile('cni.pdf', b'%PDF-1.4 test', content_type='application/pdf')
    r = client_gestion.post(f'{API}/documents/', {'titre': 'CNI', 'type_document': 'identite',
                                                  'locataire': locataire.pk, 'fichier': f}, format='multipart')
    assert r.status_code == 201 and 'fichier' not in r.data and r.data['nom_fichier'] == 'cni.pdf'
    dl = client_gestion.get(f"{API}/documents/{r.data['id']}/telecharger/")
    assert dl.status_code == 200 and b''.join(dl.streaming_content).startswith(b'%PDF')
    assert APIClient().get(f"{API}/documents/{r.data['id']}/telecharger/").status_code in (401, 403)


def test_document_refuse_extension_dangereuse(client_gestion, locataire, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    f = SimpleUploadedFile('virus.exe', b'MZ', content_type='application/octet-stream')
    r = client_gestion.post(f'{API}/documents/', {'titre': 'x', 'locataire': locataire.pk, 'fichier': f},
                            format='multipart')
    assert r.status_code == 400 and Document.objects.count() == 0


def test_document_sans_rattachement_refuse(client_gestion, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    f = SimpleUploadedFile('a.pdf', b'%PDF', content_type='application/pdf')
    assert client_gestion.post(f'{API}/documents/', {'titre': 'x', 'fichier': f}, format='multipart').status_code == 400


def test_rappels_decheance_notifient_le_locataire(contrat, compte_locataire):
    cible = date.today() + timedelta(days=3)
    contrat.jour_paiement = min(cible.day, 28)
    contrat.save()
    if cible.day > 28:
        pytest.skip('jour hors plage de paiement (1-28)')
    Paiement.objects.create(contrat=contrat, mois=cible.replace(day=1), montant_du=150000)
    assert services.envoyer_rappels_echeance() == 1
    assert Notification.objects.filter(destinataire=compte_locataire, titre__contains='3 jour').exists()


def test_listes_sans_requetes_en_n_plus_un(client_gestion, gestionnaire):
    """Le nombre de requêtes d'une liste ne dépend pas du nombre de lignes (pas de N+1)."""
    def creer(n):
        for i in range(n):
            b = Bien.objects.create(proprietaire=gestionnaire, nom=f'B{n}-{i}', ville='Dakar', adresse='x',
                                    code_postal='1', surface=10, loyer_charges=100)
            loc = Locataire.objects.create(proprietaire=gestionnaire, prenom='A', nom=f'L{n}-{i}',
                                           telephone='+221770000000')
            c = Contrat.objects.create(bien=b, locataire=loc, date_debut=date.today(), loyer_mensuel=100)
            Paiement.objects.create(contrat=c, mois=date.today().replace(day=1), montant_du=100)

    def compter(url):
        with CaptureQueriesContext(connection) as ctx:
            assert client_gestion.get(url).status_code == 200
        return len(ctx)

    creer(2)
    client_gestion.get(f'{API}/biens/')  # chauffe : le profil de l'utilisateur est mis en cache une fois
    avant ={u: compter(f'{API}/{u}/') for u in ('biens', 'locataires', 'contrats', 'paiements')}
    creer(8)
    apres = {u: compter(f'{API}/{u}/') for u in ('biens', 'locataires', 'contrats', 'paiements')}
    assert avant == apres, f'requêtes avant/après : {avant} / {apres}'


def test_reponses_compressees_gzip(client_gestion, bien):
    r = client_gestion.get(f'{API}/biens/', HTTP_ACCEPT_ENCODING='gzip')
    assert r.status_code == 200
