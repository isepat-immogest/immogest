from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APIClient

from gestion.models import Bien, Contrat, Locataire


@pytest.fixture(autouse=True)
def vider_cache():
    cache.clear()


@pytest.fixture
def gestionnaire(db):
    return User.objects.create_user('agent', 'agent@example.com', 'Motdepasse-Solide-1')


@pytest.fixture
def client_gestion(gestionnaire):
    c = APIClient()
    c.force_authenticate(gestionnaire)
    return c


@pytest.fixture
def bien(gestionnaire):
    return Bien.objects.create(
        proprietaire=gestionnaire, nom='Studio Almadies', ville='Dakar', adresse='Rue 10', code_postal='11000',
        surface=30, loyer_charges=Decimal('150000'), prix_nuit=Decimal('20000'))


@pytest.fixture
def locataire(gestionnaire):
    return Locataire.objects.create(
        proprietaire=gestionnaire, prenom='Awa', nom='Diop', email='awa@example.com', telephone='+221771234567')


@pytest.fixture
def contrat(bien, locataire):
    return Contrat.objects.create(
        bien=bien, locataire=locataire, date_debut=date.today() - timedelta(days=60),
        loyer_mensuel=Decimal('140000'), charges_mensuelles=Decimal('10000'), jour_paiement=5)


@pytest.fixture
def compte_locataire(locataire):
    user = User.objects.create_user('awa.diop', 'awa@example.com', 'Motdepasse-Solide-1')
    locataire.compte = user
    locataire.save()
    return user


@pytest.fixture
def client_locataire(compte_locataire):
    c = APIClient()
    c.force_authenticate(compte_locataire)
    return c


@pytest.fixture(autouse=True)
def hash_rapide(settings):
    """Hachage MD5 en test : les créations de comptes passent de ~0,3 s à quelques ms."""
    settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
