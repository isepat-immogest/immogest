from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from gestion import services
from gestion.models import Contrat, Paiement, Reservation

pytestmark = pytest.mark.django_db


def test_contrat_actif_met_le_bien_en_loue_puis_libre_a_la_resiliation(contrat):
    contrat.bien.refresh_from_db()
    assert contrat.bien.statut == 'loue'
    services.resilier_contrat(contrat)
    contrat.bien.refresh_from_db()
    assert contrat.bien.statut == 'libre'
    assert contrat.statut == 'resilie'


def test_deux_contrats_actifs_sur_le_meme_bien_sont_refuses(contrat, locataire):
    autre = Contrat(bien=contrat.bien, locataire=locataire, date_debut=date.today(), loyer_mensuel=1000)
    with pytest.raises(ValidationError):
        autre.full_clean()


def test_date_fin_avant_debut_refusee(bien, locataire):
    c = Contrat(bien=bien, locataire=locataire, date_debut=date(2026, 5, 1), date_fin=date(2026, 4, 1),
                loyer_mensuel=1000)
    with pytest.raises(ValidationError):
        c.full_clean()


def test_statut_paiement_calcule_automatiquement(contrat):
    mois = date.today().replace(day=1)
    p = Paiement.objects.create(contrat=contrat, mois=mois, montant_du=Decimal('150000'), montant_paye=0)
    assert p.statut in ('en_attente', 'retard')
    p.montant_paye = Decimal('50000')
    p.save()
    assert p.statut == 'partiel'
    p.montant_paye = Decimal('150000')
    p.save()
    assert p.statut == 'paye'
    assert p.date_paiement is not None


def test_paiement_ancien_non_solde_est_en_retard(contrat):
    ancien = (date.today().replace(day=1) - timedelta(days=40)).replace(day=1)
    p = Paiement.objects.create(contrat=contrat, mois=ancien, montant_du=1000)
    assert p.statut == 'retard'


def test_generer_loyers_est_idempotent(contrat):
    mois = date.today()
    assert services.generer_loyers_du_mois(mois) == 1
    assert services.generer_loyers_du_mois(mois) == 0
    assert Paiement.objects.get(contrat=contrat).montant_du == contrat.loyer_total


def test_versement_partiel_puis_solde(contrat):
    services.generer_loyers_du_mois()
    p = Paiement.objects.get(contrat=contrat)
    services.enregistrer_versement(p, 50000, 'wave')
    assert p.statut == 'partiel'
    services.enregistrer_versement(p, p.solde, 'wave')
    assert p.statut == 'paye'
    with pytest.raises(ValidationError):
        services.enregistrer_versement(p, 1)


def test_reservation_calcule_le_montant_et_bloque_les_dates(bien):
    arrivee = date.today() + timedelta(days=10)
    r = services.creer_reservation(
        bien, nom='Client', telephone='+221771112233', date_arrivee=arrivee,
        date_depart=arrivee + timedelta(days=3), nb_personnes=2, mode_paiement='wave')
    assert r.montant_total == Decimal('60000')
    with pytest.raises(ValidationError):
        services.creer_reservation(
            bien, nom='Autre', telephone='+221771112244', date_arrivee=arrivee + timedelta(days=1),
            date_depart=arrivee + timedelta(days=2), nb_personnes=1, mode_paiement='wave')


def test_reservation_dates_incoherentes_refusees(bien):
    arrivee = date.today() + timedelta(days=10)
    with pytest.raises(ValidationError):
        services.creer_reservation(
            bien, nom='X', telephone='+221771112233', date_arrivee=arrivee, date_depart=arrivee - timedelta(days=1),
            nb_personnes=1, mode_paiement='wave')


def test_expiration_des_reservations_impayees(bien):
    arrivee = date.today() + timedelta(days=10)
    r = services.creer_reservation(bien, nom='X', telephone='+221771112233', date_arrivee=arrivee,
                                   nb_personnes=1, mode_paiement='wave')
    Reservation.objects.filter(pk=r.pk).update(created_at=r.created_at - timedelta(hours=72))
    assert services.expirer_reservations_impayees(48) == 1


def test_locataire_ne_voit_pas_lhistorique_des_anciens_occupants(contrat, locataire, compte_locataire):
    from gestion.models import Intervention
    Intervention.objects.create(bien=contrat.bien, titre='Avant', description='x',
                                date_signalement=contrat.date_debut - timedelta(days=100))
    Intervention.objects.create(bien=contrat.bien, titre='Pendant', description='x')
    titres = [i.titre for i in services.interventions_du_locataire(locataire)]
    assert titres == ['Pendant']
