"""Choix des propriétaires directement dans le formulaire d'ajout / modification d'un bien (interface /gestion/)."""
from decimal import Decimal

import pytest
from django.urls import reverse

from gestion.models import Bien, Proprietaire


@pytest.fixture
def awa(gestionnaire):
    return Proprietaire.objects.create(gestionnaire=gestionnaire, prenom='Awa', nom='Diop',
                                       telephone='+221771234567', commission_pct=10)


@pytest.fixture
def moussa(gestionnaire):
    return Proprietaire.objects.create(gestionnaire=gestionnaire, prenom='Moussa', nom='Fall',
                                       telephone='+221781234567', commission_pct=8)


def _donnees(**extra):
    donnees = {'nom': 'Villa test', 'type_bien': 'villa', 'offre': 'location', 'statut': 'libre', 'ville': 'Dakar',
               'adresse': 'Rue 1', 'code_postal': '11000', 'surface': '120', 'nb_pieces': '4', 'nb_chambres': '3',
               'nb_salles_bain': '2', 'loyer_charges': '300000', 'depot_garantie': '0'}
    donnees.update(extra)
    return donnees


def _parts(bien):
    return {p.proprietaire_id: p.quote_part for p in bien.parts.all()}


def test_ajout_d_un_bien_avec_un_proprietaire(client, gestionnaire, awa):
    client.force_login(gestionnaire)
    reponse = client.post(reverse('bien_create'), _donnees(proprietaire_1=awa.pk))
    assert reponse.status_code == 302, getattr(reponse, 'context', None) and reponse.context['form'].errors
    bien = Bien.objects.get(nom='Villa test')
    assert _parts(bien) == {awa.pk: Decimal('100')}


def test_ajout_d_un_bien_en_copropriete(client, gestionnaire, awa, moussa):
    client.force_login(gestionnaire)
    client.post(reverse('bien_create'), _donnees(
        proprietaire_1=awa.pk, quote_1='60', proprietaire_2=moussa.pk, quote_2='40'))
    assert _parts(Bien.objects.get(nom='Villa test')) == {awa.pk: Decimal('60'), moussa.pk: Decimal('40')}


def test_parts_qui_ne_font_pas_100_refusees(client, gestionnaire, awa, moussa):
    client.force_login(gestionnaire)
    reponse = client.post(reverse('bien_create'), _donnees(
        proprietaire_1=awa.pk, quote_1='60', proprietaire_2=moussa.pk, quote_2='30'))
    assert reponse.status_code == 200 and not Bien.objects.filter(nom='Villa test').exists()


def test_modification_remplace_les_proprietaires(client, gestionnaire, bien, awa, moussa):
    client.force_login(gestionnaire)
    client.post(reverse('bien_edit', args=[bien.pk]), _donnees(nom=bien.nom, proprietaire_1=awa.pk))
    client.post(reverse('bien_edit', args=[bien.pk]), _donnees(nom=bien.nom, proprietaire_1=moussa.pk))
    assert _parts(bien) == {moussa.pk: Decimal('100')}


def test_sans_choix_la_liste_actuelle_est_conservee(client, gestionnaire, bien, awa):
    client.force_login(gestionnaire)
    client.post(reverse('bien_edit', args=[bien.pk]), _donnees(nom=bien.nom, proprietaire_1=awa.pk))
    client.post(reverse('bien_edit', args=[bien.pk]), _donnees(nom=bien.nom))
    assert _parts(bien) == {awa.pk: Decimal('100')}
