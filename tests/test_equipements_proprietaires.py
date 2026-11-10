from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from gestion import services
from gestion.models import Bien, Contrat, Equipement, Proprietaire
from gestion.utils import normaliser_telephone

pytestmark = pytest.mark.django_db


@pytest.fixture
def proprio_a(gestionnaire):
    return Proprietaire.objects.create(gestionnaire=gestionnaire, prenom='Ibrahima', nom='Sow',
                                       telephone='77 123 45 67', commission_pct=10)


@pytest.fixture
def proprio_b(gestionnaire):
    return Proprietaire.objects.create(gestionnaire=gestionnaire, prenom='Fatou', nom='Ndiaye',
                                       telephone='+221781234567', commission_pct=8)


# ── Équipements ──────────────────────────────────────────────────────────────

def test_catalogue_equipements_precharge():
    assert Equipement.objects.count() >= 30
    assert Equipement.objects.filter(nom='Climatisation').exists()


def test_associer_des_equipements_a_un_bien_libre_ou_loue(client_gestion, bien, contrat):
    ids = list(Equipement.objects.filter(nom__in=['Climatisation', 'Groupe électrogène']).values_list('id', flat=True))
    r = client_gestion.patch(f'/api/v1/biens/{bien.pk}/', {'equipements': ids, 'nb_chambres': 2, 'meuble': True},
                             format='json')
    assert r.status_code == 200, r.content
    assert sorted(e['nom'] for e in r.json()['equipements_detail']) == ['Climatisation', 'Groupe électrogène']
    assert bien.statut == 'loue' or Bien.objects.get(pk=bien.pk).statut == 'loue'   # bien loué : même chose
    r = client_gestion.patch(f'/api/v1/biens/{bien.pk}/', {'equipements': []}, format='json')
    assert r.json()['equipements'] == []


def test_equipements_vides_en_envoi_multipart(client_gestion, bien):
    bien.equipements.set(Equipement.objects.all()[:2])
    r = client_gestion.patch(f'/api/v1/biens/{bien.pk}/', {'equipements__present': '1', 'nom': 'Studio'},
                             format='multipart')
    assert r.status_code == 200, r.content
    assert r.json()['equipements'] == []


def test_filtrer_les_biens_par_equipements(client_gestion, bien, gestionnaire):
    clim, eau = Equipement.objects.get(nom='Climatisation'), Equipement.objects.get(nom='Citerne / réservoir')
    autre = Bien.objects.create(proprietaire=gestionnaire, nom='Villa', ville='Saly', adresse='x', code_postal='1',
                                surface=100, loyer_charges=500000)
    bien.equipements.set([clim, eau])
    autre.equipements.set([clim])
    r = client_gestion.get(f'/api/v1/biens/?equipements={clim.pk}&equipements={eau.pk}')
    assert [b['nom'] for b in r.json()['results']] == [bien.nom]
    assert r.json()['count'] == 1
    assert client_gestion.get(f'/api/v1/biens/?equipements={clim.pk}').json()['count'] == 2


def test_ajout_et_suppression_d_equipement_du_catalogue(client_gestion, bien):
    r = client_gestion.post('/api/v1/equipements/', {'nom': 'Salle de sport', 'categorie': 'confort'}, format='json')
    assert r.status_code == 201
    doublon = client_gestion.post('/api/v1/equipements/', {'nom': 'salle de SPORT', 'categorie': 'confort'},
                                  format='json')
    assert doublon.status_code == 400
    clim = Equipement.objects.get(nom='Climatisation')
    bien.equipements.add(clim)
    assert client_gestion.delete(f'/api/v1/equipements/{clim.pk}/').status_code == 400   # utilisé par un bien
    assert client_gestion.delete(f'/api/v1/equipements/{r.json()["id"]}/').status_code == 204


def test_api_publique_expose_les_equipements(bien):
    from rest_framework.test import APIClient
    bien.equipements.set(Equipement.objects.filter(nom__in=['Wifi / fibre optique', 'Parking / garage']))
    r = APIClient().get(f'/api/v1/public/biens/{bien.pk}/')
    assert sorted(r.json()['equipements']) == ['Parking / garage', 'Wifi / fibre optique']
    clim = Equipement.objects.get(nom='Climatisation')
    assert APIClient().get(f'/api/v1/public/biens/?equipements={clim.pk}').json()['count'] == 0


# ── Propriétaires multiples ──────────────────────────────────────────────────

def test_telephone_normalise_au_format_senegalais(proprio_a, locataire):
    assert proprio_a.telephone == '+221771234567'
    assert normaliser_telephone('00221 77 123 45 67') == '+221771234567'
    assert normaliser_telephone('221771234567') == '+221771234567'
    assert normaliser_telephone('+33 6 12 34 56 78') == '+33612345678'
    assert normaliser_telephone('') == ''


def test_plusieurs_proprietaires_dont_les_parts_font_100(client_gestion, bien, proprio_a, proprio_b):
    r = client_gestion.put(f'/api/v1/biens/{bien.pk}/proprietaires/', {'parts': [
        {'proprietaire': proprio_a.pk, 'quote_part': '60'}, {'proprietaire': proprio_b.pk, 'quote_part': '40'}]},
        format='json')
    assert r.status_code == 200, r.content
    assert r.json()['total'] == 100.0
    assert [p['nom'] for p in r.json()['parts']] == ['Ibrahima Sow', 'Fatou Ndiaye']
    fiche = client_gestion.get(f'/api/v1/proprietaires/{proprio_b.pk}/').json()
    assert fiche['nb_biens'] == 1 and fiche['biens_detail'][0]['nom'] == bien.nom


@pytest.mark.parametrize('parts', [[('a', 60)], [('a', 60), ('b', 50)], [('a', 50), ('a', 50)]])
def test_quotes_parts_incorrectes_refusees(client_gestion, bien, proprio_a, proprio_b, parts):
    ids = {'a': proprio_a.pk, 'b': proprio_b.pk}
    r = client_gestion.put(f'/api/v1/biens/{bien.pk}/proprietaires/', {'parts': [
        {'proprietaire': ids[k], 'quote_part': q} for k, q in parts]}, format='json')
    assert r.status_code == 400
    assert bien.parts.count() == 0          # rien n'est enregistré à moitié


def test_proprietaire_principal_a_la_creation(client_gestion, proprio_a):
    r = client_gestion.post('/api/v1/biens/', {
        'nom': 'Villa', 'adresse': 'Rue 1', 'ville': 'Dakar', 'code_postal': '11000', 'surface': 120,
        'loyer_charges': 450000, 'proprietaire_principal': proprio_a.pk}, format='json')
    assert r.status_code == 201, r.content
    assert r.json()['quotes_parts_total'] == 100.0


def test_releve_de_reversement_avec_quotes_parts(client_gestion, contrat, proprio_a, proprio_b):
    services.definir_proprietaires_bien(contrat.bien, [(proprio_a, 70), (proprio_b, 30)])
    services.generer_loyers_du_mois()
    p = contrat.paiements.get()
    services.enregistrer_versement(p, p.solde)            # 150 000 encaissés
    from gestion.models import Depense
    Depense.objects.create(bien=contrat.bien, libelle='Plomberie', montant=Decimal('10000'), date=date.today())
    a = client_gestion.get(f'/api/v1/proprietaires/{proprio_a.pk}/releve/').json()
    assert a['totaux']['encaisse_part'] == 105000       # 70 %
    assert a['totaux']['commission'] == 10500           # 10 % de 105 000
    assert a['totaux']['depenses_part'] == 7000
    assert a['totaux']['net'] == 87500
    b = client_gestion.get(f'/api/v1/proprietaires/{proprio_b.pk}/releve/').json()
    assert b['totaux']['net'] == 45000 - 3600 - 3000  # 30 % - 8 % de commission - 30 % des dépenses


def test_on_ne_supprime_pas_un_proprietaire_qui_possede_un_bien(client_gestion, bien, proprio_a):
    services.definir_proprietaires_bien(bien, [(proprio_a, 100)])
    assert client_gestion.delete(f'/api/v1/proprietaires/{proprio_a.pk}/').status_code == 400
    services.definir_proprietaires_bien(bien, [])
    assert client_gestion.delete(f'/api/v1/proprietaires/{proprio_a.pk}/').status_code == 204


def test_un_gestionnaire_ne_voit_pas_les_proprietaires_d_un_autre(settings, proprio_a):
    settings.DONNEES_PARTAGEES = False
    from rest_framework.test import APIClient
    autre = User.objects.create_user('autre', 'autre@example.com', 'Motdepasse-Solide-1')
    c = APIClient()
    c.force_authenticate(autre)
    assert c.get('/api/v1/proprietaires/').json()['count'] == 0
    assert c.get(f'/api/v1/proprietaires/{proprio_a.pk}/').status_code == 404


# ── Cohérence ────────────────────────────────────────────────────────────────

def test_bien_ne_peut_pas_etre_loue_sans_contrat(client_gestion, bien):
    r = client_gestion.patch(f'/api/v1/biens/{bien.pk}/', {'statut': 'loue'}, format='json')
    assert r.status_code == 400
    r = client_gestion.post('/api/v1/biens/', {'nom': 'X', 'adresse': 'a', 'ville': 'b', 'code_postal': '1',
                                               'surface': 10, 'loyer_charges': 1000, 'statut': 'loue'}, format='json')
    assert r.status_code == 400


def test_bien_sous_contrat_ne_peut_pas_changer_de_statut_a_la_main(client_gestion, contrat):
    assert client_gestion.patch(f'/api/v1/biens/{contrat.bien.pk}/', {'statut': 'libre'}, format='json').status_code == 400
    assert client_gestion.patch(f'/api/v1/biens/{contrat.bien.pk}/', {'nom': 'Renommé'}, format='json').status_code == 200


def test_suppression_bloquee_avec_contrat_actif(client_gestion, contrat, locataire):
    assert client_gestion.delete(f'/api/v1/biens/{contrat.bien.pk}/').status_code == 400
    assert client_gestion.delete(f'/api/v1/locataires/{locataire.pk}/').status_code == 400
    services.resilier_contrat(contrat)
    assert client_gestion.delete(f'/api/v1/locataires/{locataire.pk}/').status_code == 204
    assert client_gestion.delete(f'/api/v1/biens/{contrat.bien.pk}/').status_code == 204


def test_contrat_sur_bien_en_travaux_refuse(bien, locataire):
    bien.statut = 'travaux'
    bien.save()
    c = Contrat(bien=bien, locataire=locataire, date_debut=date.today(), loyer_mensuel=1000)
    with pytest.raises(ValidationError):
        c.full_clean()


def test_paiement_depassant_le_du_ou_hors_contrat_refuse(client_gestion, contrat):
    mois = date.today().replace(day=1)
    r = client_gestion.post('/api/v1/paiements/', {'contrat': contrat.pk, 'mois': mois.isoformat(),
                                                   'montant_du': 1000, 'montant_paye': 5000}, format='json')
    assert r.status_code == 400
    avant = (contrat.date_debut - timedelta(days=90)).replace(day=1)
    r = client_gestion.post('/api/v1/paiements/', {'contrat': contrat.pk, 'mois': avant.isoformat(),
                                                   'montant_du': 1000}, format='json')
    assert r.status_code == 400


def test_intervention_terminee_recoit_sa_date_de_resolution(client_gestion, bien):
    r = client_gestion.post('/api/v1/interventions/', {'bien': bien.pk, 'titre': 'Fuite', 'description': 'x'}, format='json')
    iid = r.json()['id']
    r = client_gestion.patch(f'/api/v1/interventions/{iid}/', {'statut': 'terminee'}, format='json')
    assert r.json()['date_resolution'] == date.today().isoformat()
    r = client_gestion.patch(f'/api/v1/interventions/{iid}/', {'statut': 'en_cours'}, format='json')
    assert r.json()['date_resolution'] is None
    r = client_gestion.patch(f'/api/v1/interventions/{iid}/', {'date_resolution': '2000-01-01'}, format='json')
    assert r.status_code == 400


def test_reservation_manager_passe_par_les_memes_regles_que_le_site(client_gestion, bien):
    bien.capacite = 2
    bien.save()
    arrivee = date.today() + timedelta(days=5)
    base = {'bien': bien.pk, 'nom': 'Client', 'telephone': '+221771112233', 'date_arrivee': arrivee.isoformat(),
            'date_depart': (arrivee + timedelta(days=2)).isoformat(), 'mode_paiement': 'wave'}
    assert client_gestion.post('/api/v1/reservations/', {**base, 'nb_personnes': 4}, format='json').status_code == 400
    ok = client_gestion.post('/api/v1/reservations/', {**base, 'nb_personnes': 2}, format='json')
    assert ok.status_code == 201 and ok.json()['montant_total'] == '40000.00'
    assert client_gestion.post('/api/v1/reservations/', {**base, 'nb_personnes': 1}, format='json').status_code == 400


def test_reservation_annulee_ne_peut_pas_etre_retablie_sur_des_dates_reprises(client_gestion, bien):
    arrivee = date.today() + timedelta(days=5)
    kw = dict(telephone='+221771112233', date_arrivee=arrivee, date_depart=arrivee + timedelta(days=2),
              nb_personnes=1, mode_paiement='wave')
    r1 = services.creer_reservation(bien, nom='Premier', **kw)
    client_gestion.post(f'/api/v1/reservations/{r1.pk}/statut/', {'statut': 'annulee'}, format='json')
    services.creer_reservation(bien, nom='Second', **kw)
    r = client_gestion.post(f'/api/v1/reservations/{r1.pk}/statut/', {'statut': 'confirmee'}, format='json')
    assert r.status_code == 400


def test_verification_de_coherence_detecte_et_corrige(client_gestion, bien, contrat, proprio_a, gestionnaire):
    Bien.objects.filter(pk=bien.pk).update(statut='libre')        # incohérence introduite hors règles
    services.definir_proprietaires_bien(bien, [(proprio_a, 100)])
    Proprietaire.objects.get(pk=proprio_a.pk)
    from gestion.models import BienProprietaire
    BienProprietaire.objects.filter(bien=bien).update(quote_part=Decimal('80'))
    codes = {a['code'] for a in client_gestion.get('/api/v1/coherence/').json()['anomalies']}
    assert {'bien_libre_avec_contrat', 'quotes_parts_incorrectes'} <= codes
    assert client_gestion.post('/api/v1/coherence/').json()['biens_corriges'] == 1
    codes = {a['code'] for a in client_gestion.get('/api/v1/coherence/').json()['anomalies']}
    assert 'bien_libre_avec_contrat' not in codes


def test_fiche_publique_du_bien_affiche_les_equipements(client, bien):
    bien.equipements.set(Equipement.objects.filter(nom__in=['Climatisation', 'Piscine']))
    bien.meuble, bien.nb_chambres, bien.capacite = True, 2, 4
    bien.save()
    reponse = client.get(f'/nos-biens/{bien.pk}/')
    assert reponse.status_code == 200
    page = reponse.content.decode()
    assert 'Climatisation' in page and 'Piscine' in page and 'Meublé' in page and 'Personnes max.' in page


# ── Intégration avec la version de l'utilisateur ─────────────────────────────

def test_pages_historiques_django_ne_plantent_pas(client, gestionnaire, bien, contrat):
    """/gestion/loyers/ n'avait pas de gabarit, biens_list.html référençait une image inexistante."""
    client.force_login(gestionnaire)
    for url in ('/gestion/loyers/', '/gestion/biens/', f'/gestion/biens/{bien.pk}/', '/gestion/biens/ajouter/'):
        r = client.get(url)
        assert r.status_code == 200, url
    page = client.get(f'/gestion/biens/{bien.pk}/').content.decode()
    assert 'Équipements' in page and 'Propriétaires' in page


def test_un_seul_email_par_reservation_et_adresse_de_secours(bien, gestionnaire, settings):
    """L'ancien signal et le circuit unifié envoyaient deux emails ; le compte SMTP sert désormais de secours."""
    from django.core import mail
    from gestion.models import Reservation
    gestionnaire.email = ''
    gestionnaire.save()
    settings.NOTIFICATIONS_EMAIL_DEFAUT = 'boite-smtp@example.com'
    arrivee = date.today() + timedelta(days=9)
    services.creer_reservation(bien, nom='C', telephone='+221771112233', date_arrivee=arrivee, nb_personnes=1,
                               mode_paiement='wave')
    assert [m.to for m in mail.outbox] == [['boite-smtp@example.com']]
    assert Reservation.objects.count() == 1


def test_les_nouveaux_types_de_bien_sont_acceptes_par_l_api(client_gestion):
    for type_bien in ('chambre', 'piscine', 'Hotel'):
        r = client_gestion.post('/api/v1/biens/', {'nom': type_bien, 'type_bien': type_bien, 'adresse': 'a',
                                                    'ville': 'b', 'code_postal': '1', 'surface': 10,
                                                    'loyer_charges': 1000}, format='json')
        assert r.status_code == 201, r.content


def test_la_preuve_de_paiement_n_est_pas_modifiable_par_l_api(client_gestion, bien):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from gestion.models import Reservation
    r = Reservation.objects.create(bien=bien, nom='X', telephone='+221771112233', date_arrivee=date.today() + timedelta(days=3),
                                   nb_personnes=1, mode_paiement='wave')
    client_gestion.patch(f'/api/v1/reservations/{r.pk}/', {'preuve_paiement': SimpleUploadedFile('p.png', b'x')},
                         format='multipart')
    r.refresh_from_db()
    assert not r.preuve_paiement
