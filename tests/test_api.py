from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from gestion.models import Bien, Locataire, Paiement, Reservation

pytestmark = pytest.mark.django_db
API = '/api/v1'


def test_api_exige_authentification():
    assert APIClient().get(f'{API}/biens/').status_code in (401, 403)


def test_login_session_et_me(gestionnaire):
    c = APIClient()
    assert c.post(f'{API}/auth/login/', {'username': 'agent', 'password': 'faux'}, format='json').status_code == 400
    r = c.post(f'{API}/auth/login/', {'username': 'agent', 'password': 'Motdepasse-Solide-1'}, format='json')
    assert r.status_code == 200 and r.data['role'] == 'gestionnaire'
    assert c.get(f'{API}/me/').data['username'] == 'agent'


def test_erreur_de_validation_au_format_uniforme(client_gestion):
    r = client_gestion.post(f'{API}/biens/', {'nom': 'X'}, format='json')
    assert r.status_code == 400
    assert r.data['code'] == 'validation_error' and 'adresse' in r.data['details']


def test_crud_bien_et_recherche(client_gestion, bien):
    assert client_gestion.get(f'{API}/biens/?search=almadies').data['count'] == 1
    assert client_gestion.get(f'{API}/biens/?statut=vente').data['count'] == 0
    r = client_gestion.patch(f'{API}/biens/{bien.pk}/', {'nom': 'Renommé'}, format='json')
    assert r.status_code == 200 and r.data['nom'] == 'Renommé'
    assert client_gestion.delete(f'{API}/biens/{bien.pk}/').status_code == 204


def test_isolation_entre_comptes(settings, client_gestion, bien):
    settings.DONNEES_PARTAGEES = False
    autre = User.objects.create_user('autre', password='Motdepasse-Solide-1')
    c = APIClient()
    c.force_authenticate(autre)
    assert c.get(f'{API}/biens/').data['count'] == 0
    assert c.get(f'{API}/biens/{bien.pk}/').status_code == 404


def test_contrat_double_actif_refuse(client_gestion, contrat, locataire):
    payload = {'bien': contrat.bien.pk, 'locataire': locataire.pk, 'date_debut': str(date.today()),
               'loyer_mensuel': '1000', 'type_bail': 'vide'}
    r = client_gestion.post(f'{API}/contrats/', payload, format='json')
    assert r.status_code == 400 and 'bien' in r.data['details']


def test_resilier_contrat_libere_le_bien(client_gestion, contrat):
    r = client_gestion.post(f'{API}/contrats/{contrat.pk}/resilier/', {}, format='json')
    assert r.status_code == 200 and r.data['statut'] == 'resilie'
    contrat.bien.refresh_from_db()
    assert contrat.bien.statut == 'libre'


def test_generer_loyers_et_versement(client_gestion, contrat):
    r = client_gestion.post(f'{API}/paiements/generer-mois/', {}, format='json')
    assert r.data['crees'] == 1
    p = Paiement.objects.get()
    r = client_gestion.post(f'{API}/paiements/{p.pk}/versement/', {'montant': '50000', 'mode_paiement': 'wave'},
                            format='json')
    assert r.status_code == 200 and r.data['statut'] == 'partiel'
    r = client_gestion.post(f'{API}/paiements/{p.pk}/versement/', {'montant': '999999999'}, format='json')
    assert r.status_code == 400
    lst = client_gestion.get(f'{API}/paiements/')
    assert lst.data['totaux']['encaisse'] == 50000


def test_quittance_pdf(client_gestion, contrat):
    client_gestion.post(f'{API}/paiements/generer-mois/', {}, format='json')
    p = Paiement.objects.get()
    r = client_gestion.get(f'{API}/paiements/{p.pk}/quittance/')
    assert r.status_code == 200 and r['Content-Type'] == 'application/pdf' and r.content[:4] == b'%PDF'


def test_dashboard_et_recherche_et_export(client_gestion, contrat):
    client_gestion.post(f'{API}/paiements/generer-mois/', {}, format='json')
    d = client_gestion.get(f'{API}/dashboard/').data
    assert d['kpis']['total_biens'] == 1 and d['kpis']['taux_occupation'] == 100 and len(d['revenus']) == 6
    assert client_gestion.get(f'{API}/recherche/?q=awa').data['resultats'][0]['type'] == 'locataire'
    assert client_gestion.get(f'{API}/rapports/financier/?export=csv')['Content-Type'].startswith('text/csv')
    assert client_gestion.get(f'{API}/rapports/financier/?export=xlsx').status_code == 200


def test_inviter_locataire_donne_un_lien_sans_mot_de_passe(client_gestion, locataire):
    r = client_gestion.post(f'{API}/locataires/{locataire.pk}/inviter/')
    assert r.status_code == 200 and '/app/activer/' in r.data['lien_activation']
    locataire.refresh_from_db()
    assert not locataire.compte.has_usable_password()
    uid, token = r.data['lien_activation'].rstrip('/').split('/')[-2:]
    ok = APIClient().post(f'{API}/auth/password/confirm/',
                          {'uid': uid, 'token': token, 'password': 'Un-Mot-De-Passe-Fort-9'}, format='json')
    assert ok.status_code == 200
    locataire.compte.refresh_from_db()
    assert locataire.compte.check_password('Un-Mot-De-Passe-Fort-9')
    # le lien est à usage unique
    assert APIClient().post(f'{API}/auth/password/confirm/',
                            {'uid': uid, 'token': token, 'password': 'Autre-Mot-De-Passe-8'},
                            format='json').status_code == 400


def test_locataire_nacces_pas_a_la_gestion(client_locataire):
    assert client_locataire.get(f'{API}/biens/').status_code == 403


def test_espace_locataire_ne_montre_que_ses_donnees(client_locataire, contrat, gestionnaire):
    autre_loc = Locataire.objects.create(proprietaire=gestionnaire, prenom='B', nom='C', telephone='+221770000000')
    autre_bien = Bien.objects.create(proprietaire=gestionnaire, nom='Autre', ville='Thiès', adresse='x',
                                     code_postal='1', surface=10, loyer_charges=1)
    from gestion.models import Contrat
    autre_contrat = Contrat.objects.create(bien=autre_bien, locataire=autre_loc, date_debut=date.today(),
                                           loyer_mensuel=1)
    Paiement.objects.create(contrat=autre_contrat, mois=date.today().replace(day=1), montant_du=1)
    Paiement.objects.create(contrat=contrat, mois=date.today().replace(day=1), montant_du=5)
    r = client_locataire.get(f'{API}/espace/paiements/')
    assert r.data['count'] == 1
    autre_id = Paiement.objects.get(contrat=autre_contrat).pk
    assert client_locataire.get(f'{API}/espace/paiements/{autre_id}/').status_code == 404
    assert client_locataire.get(f'{API}/espace/').data['contrat']['bien'] == contrat.bien.pk


def test_signalement_locataire_notifie_le_gestionnaire(client_locataire, contrat, gestionnaire):
    r = client_locataire.post(f'{API}/espace/interventions/',
                              {'titre': 'Fuite', 'description': "Robinet qui fuit"}, format='json')
    assert r.status_code == 201
    from gestion.models import Notification
    assert Notification.objects.filter(destinataire=gestionnaire, titre__contains='Fuite').exists()


def test_public_catalogue_et_reservation(bien):
    c = APIClient()
    assert c.get(f'{API}/public/biens/?ville=dakar').data['count'] == 1
    arrivee = date.today() + timedelta(days=5)
    payload = {'bien': bien.pk, 'nom': 'Client Test', 'telephone': '+221771234567',
               'email': 'client@example.com', 'date_arrivee': str(arrivee), 'date_depart': str(arrivee + timedelta(days=2)),
               'nb_personnes': 2, 'mode_paiement': 'orange_money'}
    r = c.post(f'{API}/public/reservations/', payload, format='json')
    assert r.status_code == 201 and r.data['montant_total'] == '40000.00'
    # suivi par jeton secret
    assert c.get(f"{API}/public/reservations/{r.data['token']}/").status_code == 200
    # double réservation refusée
    assert c.post(f'{API}/public/reservations/', payload, format='json').status_code == 400
    # indisponibilités publiées
    assert len(c.get(f'{API}/public/biens/{bien.pk}/disponibilites/').data['occupees']) == 1


def test_public_honeypot_bloque_le_spam(bien):
    r = APIClient().post(f'{API}/public/contact/', {'nom': 'Bot', 'message': 'x', 'website': 'http://spam'},
                         format='json')
    assert r.status_code == 400


def test_public_ne_montre_pas_les_biens_non_libres(bien):
    bien.statut = 'loue'
    bien.save()
    assert APIClient().get(f'{API}/public/biens/').data['count'] == 0


def test_convertir_reservation_en_contrat(client_gestion, bien):
    arrivee = date.today() + timedelta(days=3)
    r = Reservation.objects.create(
        bien=bien, nom='Moussa Fall', telephone='+221771234567', date_arrivee=arrivee,
        date_depart=arrivee + timedelta(days=4), mode_paiement='wave', montant_total=80000, statut='payee')
    resp = client_gestion.post(f'{API}/reservations/{r.pk}/convertir-en-contrat/')
    assert resp.status_code == 201 and resp.data['type_bail'] == 'saisonnier'
    r.refresh_from_db()
    assert r.statut == 'confirmee'


def test_confirmation_site_public_protegee_par_jeton(bien):
    arrivee = date.today() + timedelta(days=3)
    r = Reservation.objects.create(bien=bien, nom='X', telephone='+221771234567', date_arrivee=arrivee,
                                   mode_paiement='wave')
    from django.urls import Resolver404, resolve
    with pytest.raises(Resolver404):  # l'ancien identifiant séquentiel ne mène plus nulle part
        resolve(f'/reservation/{r.pk}/confirmation/')
    # RequestFactory : le client de test de Django 5.1 est incompatible avec Python 3.14 pour le rendu de gabarits
    from django.test import RequestFactory
    from site_public.views import reservation_confirmation
    reponse = reservation_confirmation(RequestFactory().get('/'), token=r.token)
    assert reponse.status_code == 200 and r.reference in reponse.content.decode()


def test_health_et_schema():
    c = APIClient()
    assert c.get('/api/health/').status_code == 200
    assert c.get('/api/schema/').status_code == 200
