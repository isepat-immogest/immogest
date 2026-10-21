"""Emails de confirmation envoyés au client (réservation et demande de contact)."""
from datetime import date, timedelta

from django.core import mail
from rest_framework.test import APIClient

from gestion import emails
from gestion.forms import ContactPublicForm, ReservationForm, ReservationPublicForm
from gestion.models import Reservation

API = '/api/v1'


def _payload(bien, **extra):
    arrivee = date.today() + timedelta(days=5)
    data = {'bien': bien.pk, 'nom': 'Aminata Fall', 'telephone': '+221771234567',
            'email': 'aminata@gmail.com', 'date_arrivee': str(arrivee),
            'date_depart': str(arrivee + timedelta(days=2)), 'nb_personnes': 2,
            'mode_paiement': 'wave'}
    data.update(extra)
    return data


def _mails_pour(adresse):
    """Emails destinés au client (les gestionnaires reçoivent leurs propres notifications)."""
    return [m for m in mail.outbox if adresse in m.to]


def test_reservation_api_envoie_un_email_au_client(bien):
    r = APIClient().post(f'{API}/public/reservations/', _payload(bien), format='json')
    assert r.status_code == 201
    envoyes = _mails_pour('aminata@gmail.com')
    assert len(envoyes) == 1
    reservation = Reservation.objects.get()
    assert reservation.reference in envoyes[0].subject
    corps = envoyes[0].body
    assert 'Studio Almadies' in corps
    assert '40 000 F CFA' in corps                 # 2 nuits x 20 000
    assert str(reservation.token) in corps         # lien de suivi sécurisé


def test_reservation_api_refuse_sans_email(bien):
    donnees = _payload(bien)
    donnees.pop('email')
    r = APIClient().post(f'{API}/public/reservations/', donnees, format='json')
    assert r.status_code == 400
    assert not Reservation.objects.exists()


def test_contact_api_envoie_un_accuse_sans_recopier_le_texte_libre(bien):
    r = APIClient().post(f'{API}/public/contact/', {
        'bien': bien.pk, 'nom': 'Moussa', 'email': 'moussa@gmail.com',
        'message': 'Bonjour SPAMSPAM http://spam.example'}, format='json')
    assert r.status_code == 201
    envoyes = _mails_pour('moussa@gmail.com')
    assert len(envoyes) == 1
    assert 'SPAMSPAM' not in envoyes[0].body       # le texte libre n'est jamais recopié
    assert 'Studio Almadies' in envoyes[0].body


def test_contact_api_refuse_sans_email(bien):
    r = APIClient().post(f'{API}/public/contact/', {'nom': 'Moussa', 'message': 'Bonjour'}, format='json')
    assert r.status_code == 400


def test_un_email_en_panne_ne_bloque_pas_la_reservation(bien, monkeypatch):
    def panne(*args, **kwargs):
        raise ConnectionRefusedError('SMTP injoignable')
    monkeypatch.setattr(emails, 'send_mail', panne)
    r = APIClient().post(f'{API}/public/reservations/', _payload(bien), format='json')
    assert r.status_code == 201
    assert Reservation.objects.count() == 1


def test_pas_d_adresse_pas_d_email(bien):
    reservation = Reservation.objects.create(
        bien=bien, nom='X', telephone='+221771234567', email='',
        date_arrivee=date.today() + timedelta(days=3), mode_paiement='wave')
    assert emails.envoyer_accuse_reservation(reservation) is False
    assert mail.outbox == []


def test_reservation_site_public_envoie_un_email_au_client(bien):
    # RequestFactory : le client de test de Django 5.1 est incompatible avec Python 3.14 pour le rendu de gabarits
    from django.test import RequestFactory
    from site_public.views import reservation_create
    reponse = reservation_create(RequestFactory().post('/', _payload(bien)), pk=bien.pk)
    assert reponse.status_code == 302
    assert len(_mails_pour('aminata@gmail.com')) == 1


def test_formulaires_publics_exigent_l_email_mais_pas_la_saisie_manuelle(bien):
    donnees = _payload(bien)
    donnees.pop('email')
    assert 'email' in ReservationPublicForm(data=donnees).errors
    assert 'email' not in ReservationForm(data=donnees).errors      # saisie manuelle : facultatif
    assert 'email' in ContactPublicForm(data={'nom': 'A', 'message': 'B'}).errors
