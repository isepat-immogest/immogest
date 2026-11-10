import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core import mail

from gestion import alertes, services, whatsapp
from gestion.models import EnvoiNotification, Paiement, Proprietaire

pytestmark = pytest.mark.django_db


@pytest.fixture
def envoyes(monkeypatch):
    appels = []
    monkeypatch.setattr(whatsapp, '_post', lambda url, corps, entetes, timeout=8: (appels.append(json.loads(corps)) or (200, 'ok')))
    return appels


@pytest.fixture(autouse=True)
def cloud(settings):
    settings.WHATSAPP_PROVIDER = 'cloud'
    settings.WHATSAPP_TOKEN, settings.WHATSAPP_PHONE_NUMBER_ID = 'jeton', '123'


@pytest.fixture
def proprio(gestionnaire):
    return Proprietaire.objects.create(gestionnaire=gestionnaire, prenom='Ibrahima', nom='Sow', email='ib@example.com',
                                       telephone='77 123 45 67', notif_email=True, notif_whatsapp=True,
                                       commission_pct=10, compte_reversement='Wave 77 123 45 67')


def textes(envoyes):
    return [m['text']['body'] for m in envoyes]


def test_recu_au_locataire_seulement_avec_son_accord(contrat, locataire, envoyes):
    services.generer_loyers_du_mois()
    p = contrat.paiements.get()
    services.enregistrer_versement(p, 50000)
    assert envoyes == []                                       # pas de consentement : aucun WhatsApp
    locataire.notif_whatsapp = True
    locataire.save()
    p.refresh_from_db()
    services.enregistrer_versement(p, 100000)
    assert len(envoyes) == 1 and envoyes[0]['to'] == whatsapp.numero_international(locataire.telephone)
    assert 'Votre loyer est soldé' in textes(envoyes)[0]
    envoi = EnvoiNotification.objects.get(canal='whatsapp')
    assert envoi.destinataire is None and envoi.libelle_destinataire == str(locataire)
    assert envoi.gestionnaire == contrat.bien.proprietaire


def test_chaque_proprietaire_recoit_sa_part_du_loyer(contrat, proprio, gestionnaire, envoyes):
    autre = Proprietaire.objects.create(gestionnaire=gestionnaire, nom='Ndiaye', telephone='78 111 22 33',
                                        notif_whatsapp=True, notif_email=False)
    services.definir_proprietaires_bien(contrat.bien, [(proprio, 60), (autre, 40)])
    services.generer_loyers_du_mois()
    services.enregistrer_versement(contrat.paiements.get(), 150000)
    corps = textes(envoyes)
    assert any('90000 FCFA' in t for t in corps) and any('60000 FCFA' in t for t in corps)    # 60 % / 40 % de 150 000
    assert [m.to for m in mail.outbox if 'ib@example.com' in m.to] == [['ib@example.com']]   # email seulement si accepté
    assert not any('78 111' in str(m.body) for m in mail.outbox)


def test_proprietaire_sans_canal_ne_recoit_rien(contrat, proprio, envoyes):
    proprio.notif_email = proprio.notif_whatsapp = False
    proprio.save()
    services.definir_proprietaires_bien(contrat.bien, [(proprio, 100)])
    services.generer_loyers_du_mois()
    mail.outbox.clear()
    services.enregistrer_versement(contrat.paiements.get(), 150000)
    assert envoyes == [] and not [m for m in mail.outbox if 'ib@example.com' in m.to]


def test_releve_mensuel_aux_proprietaires(contrat, proprio, envoyes):
    services.definir_proprietaires_bien(contrat.bien, [(proprio, 100)])
    mois = date.today().replace(day=1)
    services.generer_loyers_du_mois()
    services.enregistrer_versement(contrat.paiements.get(), 150000)
    envoyes.clear()
    mail.outbox.clear()
    assert alertes.envoyer_releves_proprietaires(mois) == 1
    texte = textes(envoyes)[0]
    assert 'net' in texte.lower() and '135000' in texte and 'Wave 77 123 45 67' in texte      # 150 000 - 10 %
    assert any('ib@example.com' in m.to for m in mail.outbox)
    assert alertes.envoyer_releves_proprietaires(mois, dry_run=True, ecrire=lambda *_: None) == 1


def test_api_envoyer_releve_et_journal(client_gestion, contrat, proprio, envoyes):
    services.definir_proprietaires_bien(contrat.bien, [(proprio, 100)])
    mois = date.today().replace(day=1).isoformat()
    r = client_gestion.post(f'/api/v1/proprietaires/{proprio.pk}/envoyer-releve/?mois={mois}')
    assert r.status_code == 200
    assert {x['canal']: x['statut'] for x in r.json()['resultats']} == {'email': 'envoye', 'whatsapp': 'envoye'}
    journal = client_gestion.get('/api/v1/me/notifications/envois/').json()['results']
    assert {j['libelle_destinataire'] for j in journal} == {'Ibrahima Sow'}
    proprio.notif_email = proprio.notif_whatsapp = False
    proprio.save()
    assert client_gestion.post(f'/api/v1/proprietaires/{proprio.pk}/envoyer-releve/').status_code == 400


def test_relance_whatsapp_graduee_des_locataires_consentants(contrat, locataire, envoyes):
    locataire.notif_whatsapp = True                             # sans compte de connexion : WhatsApp seulement
    locataire.save()
    p = Paiement.objects.create(contrat=contrat, mois=date.today().replace(day=1), montant_du=150000)
    assert alertes.relancer_locataires(aujourd_hui=p.date_echeance + timedelta(days=1)) == 1
    assert len(envoyes) == 1 and 'retard' in textes(envoyes)[0]
    assert alertes.relancer_locataires(aujourd_hui=p.date_echeance + timedelta(days=3)) == 0
    assert len(envoyes) == 1


def test_rappel_d_echeance_whatsapp(contrat, locataire, envoyes):
    locataire.notif_whatsapp = True
    locataire.save()
    services.generer_loyers_du_mois()
    p = contrat.paiements.get()
    Paiement.objects.filter(pk=p.pk).update(statut='en_attente')   # le test simule un jour AVANT l'échéance
    cible = p.date_echeance
    from unittest import mock
    with mock.patch('gestion.services.date') as faux:
        faux.today.return_value = cible - timedelta(days=3)
        faux.side_effect = lambda *a, **k: date(*a, **k)
        assert services.envoyer_rappels_echeance(jours=(3,)) == 1
    assert 'Loyer à payer dans 3 jour' in textes(envoyes)[0]
