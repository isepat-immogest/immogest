import json
from datetime import date, timedelta
from urllib.parse import parse_qs

import pytest
from django.core import mail
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from gestion import alertes, notifications, services, whatsapp
from gestion.models import EnvoiNotification, Notification, ProfilGestionnaire

pytestmark = pytest.mark.django_db


@pytest.fixture
def envoyes(monkeypatch):
    """Capture les requêtes HTTP vers les fournisseurs WhatsApp."""
    appels = []

    def faux_post(url, corps, entetes, timeout=8):
        appels.append({'url': url, 'corps': corps, 'entetes': entetes})
        return 200, '{"ok": true}'
    monkeypatch.setattr(whatsapp, '_post', faux_post)
    return appels


@pytest.fixture
def cloud(settings):
    settings.WHATSAPP_PROVIDER = 'cloud'
    settings.WHATSAPP_TOKEN = 'jeton'
    settings.WHATSAPP_PHONE_NUMBER_ID = '123456'


@pytest.fixture
def profil(gestionnaire):
    return ProfilGestionnaire.objects.create(user=gestionnaire, numero_whatsapp='77 123 45 67')


def reservation_publique(bien):
    arrivee = date.today() + timedelta(days=10)
    return services.creer_reservation(
        bien, nom='Client Test', telephone='+221771112233', email='c@example.com', date_arrivee=arrivee,
        date_depart=arrivee + timedelta(days=2), nb_personnes=2, mode_paiement='wave')


def test_nouvelle_reservation_previent_le_gestionnaire_par_cloche_email_et_whatsapp(bien, profil, cloud, envoyes):
    r = reservation_publique(bien)
    assert Notification.objects.filter(destinataire=profil.user, titre__contains=r.reference).exists()
    assert [m.to for m in mail.outbox] == [['agent@example.com']]
    assert 'https://immogest.test/app/reservations' in mail.outbox[0].body
    assert len(envoyes) == 1
    appel = envoyes[0]
    assert appel['url'] == 'https://graph.facebook.com/v20.0/123456/messages'
    assert appel['entetes']['Authorization'] == 'Bearer jeton'
    corps = json.loads(appel['corps'])
    assert corps['to'] == '221771234567' and corps['type'] == 'text'
    assert 'Client Test' in corps['text']['body'] and 'https://immogest.test/app/reservations' in corps['text']['body']
    assert set(EnvoiNotification.objects.values_list('statut', flat=True)) == {'envoye'}


def test_lien_de_la_cloche_ne_contient_plus_le_prefixe_app(bien, gestionnaire):
    reservation_publique(bien)
    assert Notification.objects.get(destinataire=gestionnaire).lien == '/reservations'


def test_modele_whatsapp_meta_pour_les_messages_hors_fenetre_24h(bien, profil, cloud, envoyes, settings):
    settings.WHATSAPP_TEMPLATE_NAME = 'alerte_immogest'
    reservation_publique(bien)
    corps = json.loads(envoyes[0]['corps'])
    assert corps['type'] == 'template' and corps['template']['name'] == 'alerte_immogest'
    variable = corps['template']['components'][0]['parameters'][0]['text']
    assert '\n' not in variable and 'Client Test' in variable


def test_twilio(bien, profil, settings, envoyes):
    settings.WHATSAPP_PROVIDER = 'twilio'
    settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN = 'ACxxx', 'secret'
    settings.TWILIO_WHATSAPP_FROM = '+14155238886'
    reservation_publique(bien)
    assert envoyes[0]['url'].endswith('/Accounts/ACxxx/Messages.json')
    champs = parse_qs(envoyes[0]['corps'].decode())
    assert champs['To'] == ['whatsapp:+221771234567'] and champs['From'] == ['whatsapp:+14155238886']


def test_echec_whatsapp_n_empeche_ni_l_email_ni_la_reservation_et_est_journalise(bien, profil, cloud, monkeypatch):
    def panne(*a, **k):
        raise whatsapp.WhatsAppError('Fournisseur injoignable')
    monkeypatch.setattr(whatsapp, '_post', panne)
    r = reservation_publique(bien)
    assert r.pk and len(mail.outbox) == 1
    echec = EnvoiNotification.objects.get(canal='whatsapp')
    assert echec.statut == 'echec' and 'injoignable' in echec.erreur


def test_renvoi_automatique_des_echecs(bien, profil, cloud, monkeypatch):
    monkeypatch.setattr(whatsapp, '_post', lambda *a, **k: (500, 'erreur'))
    reservation_publique(bien)
    assert EnvoiNotification.objects.get(canal='whatsapp').statut == 'echec'
    monkeypatch.setattr(whatsapp, '_post', lambda *a, **k: (200, 'ok'))
    assert notifications.renvoyer_echecs() == (1, 0)
    envoi = EnvoiNotification.objects.get(canal='whatsapp')
    assert envoi.statut == 'envoye' and envoi.tentatives == 2


def test_pas_de_numero_ou_whatsapp_non_configure_est_signale_pas_silencieux(bien, gestionnaire, settings):
    reservation_publique(bien)                    # pas de profil, WhatsApp désactivé : email seulement
    assert len(mail.outbox) == 1
    assert not EnvoiNotification.objects.filter(canal='whatsapp').exists()   # pas de profil = pas de WhatsApp voulu
    ProfilGestionnaire.objects.create(user=gestionnaire)          # profil sans numéro
    settings.WHATSAPP_PROVIDER = 'cloud'
    envois = notifications._diffuser(gestionnaire, None, 'T', 'm', '', 'test', True, True)
    assert any(e.canal == 'whatsapp' and e.statut == 'ignore' and 'numéro' in e.erreur for e in envois)
    ProfilGestionnaire.objects.filter(user=gestionnaire).update(numero_whatsapp='+221771234567')
    settings.WHATSAPP_PROVIDER = ''                                # numéro OK mais serveur non configuré
    gestionnaire.refresh_from_db()
    envois = notifications._diffuser(User.objects.get(pk=gestionnaire.pk), None, 'T', 'm', '', 'test', True, True)
    assert any(e.canal == 'whatsapp' and e.statut == 'ignore' and 'configuré' in e.erreur for e in envois)


def test_preferences_canaux_et_evenements(bien, profil, cloud, envoyes):
    profil.notif_whatsapp = False
    profil.save()
    reservation_publique(bien)
    assert len(mail.outbox) == 1 and envoyes == []
    profil.notif_whatsapp, profil.notif_email = True, True
    profil.evenements_desactives = ['reservation_nouvelle']
    profil.save()
    mail.outbox.clear()
    arrivee = date.today() + timedelta(days=40)
    services.creer_reservation(bien, nom='Autre', telephone='+221771112244', email='a@example.com',
                               date_arrivee=arrivee, nb_personnes=1, mode_paiement='wave')
    assert mail.outbox == [] and envoyes == []                       # événement coupé : plus ni email ni WhatsApp
    assert Notification.objects.filter(titre__contains='Nouvelle réservation').count() == 2   # la cloche reste


def test_gestionnaire_sans_email_est_signale(bien, gestionnaire):
    gestionnaire.email = ''
    gestionnaire.save()
    reservation_publique(bien)
    ign = EnvoiNotification.objects.get(canal='email')
    assert ign.statut == 'ignore' and 'email' in ign.erreur.lower()


def test_les_evenements_metier_notifient_les_autres_gestionnaires_pas_l_acteur(contrat, gestionnaire, settings):
    collegue = User.objects.create_user('collegue', 'collegue@example.com', 'Motdepasse-Solide-1')
    services.generer_loyers_du_mois()
    p = contrat.paiements.get()
    services.enregistrer_versement(p, 50000, 'wave', par=gestionnaire)
    assert [m.to for m in mail.outbox] == [['collegue@example.com']]
    assert 'Reste à payer : 100000' in mail.outbox[0].body
    assert not Notification.objects.filter(destinataire=gestionnaire, titre__contains='Paiement reçu').exists()
    assert Notification.objects.filter(destinataire=collegue, titre__contains='Paiement reçu').exists()
    mail.outbox.clear()
    services.resilier_contrat(contrat, par=gestionnaire)
    assert 'résilié' in mail.outbox[0].subject


def test_message_du_site_public_django_previent_enfin_le_gestionnaire(bien, profil, cloud, envoyes):
    from django.test import RequestFactory
    from django.contrib.messages.storage.fallback import FallbackStorage
    from site_public import views
    rf = RequestFactory()
    req = rf.post('/contact/', {'nom': 'Visiteur', 'email': 'v@example.com', 'telephone': '771234567',
                                'message': 'Le studio est-il libre ?'})
    req.session = {}
    req._messages = FallbackStorage(req)
    views.contact(req)
    assert Notification.objects.filter(destinataire=profil.user, titre='Nouveau message de Visiteur').exists()
    assert json.loads(envoyes[0]['corps'])['text']['body'].count('Le studio est-il libre ?') == 1


def test_expiration_de_reservation_previent_le_gestionnaire(bien, profil, cloud, envoyes):
    from gestion.models import Reservation
    r = reservation_publique(bien)
    Reservation.objects.filter(pk=r.pk).update(created_at=r.created_at - timedelta(hours=72))
    envoyes.clear()
    assert services.expirer_reservations_impayees(48) == 1
    assert 'expirée' in json.loads(envoyes[0]['corps'])['text']['body']


def test_recapitulatif_quotidien_unique_avec_retards_et_anomalies(contrat, profil, cloud, envoyes):
    ancien = (date.today().replace(day=1) - timedelta(days=40)).replace(day=1)
    from gestion.models import Paiement
    Paiement.objects.create(contrat=contrat, mois=ancien, montant_du=150000)
    contrat.bien.__class__.objects.filter(pk=contrat.bien.pk).update(statut='libre')    # anomalie volontaire
    assert alertes.envoyer_recapitulatifs() == 1
    texte = json.loads(envoyes[0]['corps'])['text']['body']
    assert '1 loyer(s) en retard' in texte and 'Awa Diop' in texte and 'anomalie' in texte
    assert len(envoyes) == 1 and len(mail.outbox) == 1
    profil.evenements_desactives = ['loyer_retard', 'coherence']
    profil.save()
    assert alertes.construire_recapitulatif(profil.user) == ''


def test_relance_graduee_des_locataires(contrat, compte_locataire):
    from gestion.models import Paiement
    mois = date.today().replace(day=1)
    p = Paiement.objects.create(contrat=contrat, mois=mois, montant_du=150000)
    echeance = p.date_echeance
    assert alertes.relancer_locataires(aujourd_hui=echeance + timedelta(days=1)) == 1
    assert alertes.relancer_locataires(aujourd_hui=echeance + timedelta(days=2)) == 0
    assert alertes.relancer_locataires(aujourd_hui=echeance + timedelta(days=7)) == 1
    assert alertes.relancer_locataires(aujourd_hui=echeance + timedelta(days=14)) == 1


# ── API des préférences ──────────────────────────────────────────────────────

def test_api_preferences_et_test_d_envoi(client_gestion, gestionnaire, cloud, envoyes):
    r = client_gestion.get('/api/v1/me/notifications/')
    assert r.status_code == 200 and r.json()['whatsapp_disponible'] is True
    r = client_gestion.patch('/api/v1/me/notifications/', {
        'numero_whatsapp': '78 111 22 33', 'email': 'nouveau@example.com',
        'evenements_desactives': ['signalement']}, format='json')
    assert r.status_code == 200 and r.json()['numero_whatsapp'] == '+221781112233'
    assert r.json()['email'] == 'nouveau@example.com'
    assert [e['actif'] for e in r.json()['evenements'] if e['code'] == 'signalement'] == [False]
    r = client_gestion.post('/api/v1/me/notifications/test/')
    assert {x['canal']: x['statut'] for x in r.json()['resultats']} == {'email': 'envoye', 'whatsapp': 'envoye'}
    assert mail.outbox[-1].to == ['nouveau@example.com']
    journal = client_gestion.get('/api/v1/me/notifications/envois/').json()
    assert journal['count'] == 2


def test_api_preferences_refuse_numero_et_evenement_invalides(client_gestion):
    assert client_gestion.patch('/api/v1/me/notifications/', {'numero_whatsapp': 'abc'}, format='json').status_code == 400
    assert client_gestion.patch('/api/v1/me/notifications/', {'evenements_desactives': ['nimporte']},
                                format='json').status_code == 400


def test_un_locataire_n_a_pas_acces_aux_preferences_de_gestion(client_locataire):
    assert client_locataire.get('/api/v1/me/notifications/').status_code == 403
    assert client_locataire.get('/api/v1/coherence/').status_code == 403
    assert client_locataire.get('/api/v1/proprietaires/').status_code == 403


def test_numero_whatsapp_normalise_et_numero_invalide_refuse(settings):
    assert whatsapp.numero_international('+221 77 123 45 67') == '221771234567'
    settings.WHATSAPP_PROVIDER = 'console'
    with pytest.raises(whatsapp.WhatsAppError):
        whatsapp.envoyer_whatsapp('12', 'x')
    settings.WHATSAPP_PROVIDER = ''
    with pytest.raises(whatsapp.WhatsAppError):
        whatsapp.envoyer_whatsapp('+221771234567', 'x')
