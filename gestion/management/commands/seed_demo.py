"""Charge un petit jeu de données de démonstration (remplace les anciens dumps data.json).

    python manage.py seed_demo [--user agent --password ...]
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from gestion import services
from gestion.models import Bien, Contrat, Intervention, Locataire, Paiement


class Command(BaseCommand):
    help = "Crée des biens, locataires, contrats et loyers de démonstration."

    def add_arguments(self, parser):
        parser.add_argument('--user', default='demo')
        parser.add_argument('--password', default='Demo-ImmoGest-2026')

    def handle(self, *args, **options):
        user, cree = User.objects.get_or_create(username=options['user'], defaults={'email': 'demo@immogest.local'})
        if cree:
            user.set_password(options['password'])
            user.save()
        biens = []
        for nom, ville, typ, loyer, nuit in [
            ('Appartement Almadies', 'Dakar', 'appartement', 350000, 45000),
            ('Studio Plateau', 'Dakar', 'studio', 150000, 22000),
            ('Villa Saly', 'Mbour', 'maison', 600000, 80000),
            ('Local Sandaga', 'Dakar', 'commerce', 400000, None),
        ]:
            b, _ = Bien.objects.get_or_create(
                proprietaire=user, nom=nom,
                defaults=dict(ville=ville, adresse='Adresse démo', code_postal='10000', type_bien=typ, surface=60,
                              nb_pieces=3, loyer_charges=Decimal(loyer), prix_nuit=nuit))
            biens.append(b)
        for i, (prenom, nom, tel) in enumerate([('Awa', 'Diop', '+221771110001'), ('Moussa', 'Fall', '+221771110002')]):
            loc, _ = Locataire.objects.get_or_create(proprietaire=user, prenom=prenom, nom=nom,
                                                     defaults=dict(telephone=tel, email=f'{prenom.lower()}@example.com'))
            if not loc.contrats.exists():
                c = Contrat(bien=biens[i], locataire=loc, date_debut=date.today() - timedelta(days=150),
                            loyer_mensuel=biens[i].loyer_charges - 20000, charges_mensuelles=20000, jour_paiement=5)
                c.full_clean()
                c.save()
                debut = date.today().replace(day=1)
                for k in range(5, -1, -1):
                    total = (debut.year * 12 + debut.month - 1) - k
                    mois = date(total // 12, total % 12 + 1, 1)
                    paye = k > 0 and not (i == 1 and k == 1)
                    p = Paiement(contrat=c, mois=mois, montant_du=c.loyer_total,
                                 montant_paye=c.loyer_total if paye else 0)
                    if paye:  # payé à l'échéance : sinon la date du jour serait utilisée (paiement « en retard »)
                        p.date_paiement = p.date_echeance
                    p.save()
        Intervention.objects.get_or_create(bien=biens[0], titre='Fuite robinet cuisine',
                                           defaults=dict(description='Fuite sous l\'évier.', priorite='haute'))
        services.generer_loyers_du_mois()
        self._seed_depenses(user, biens)
        self.stdout.write(self.style.SUCCESS(
            f"Données de démo prêtes. Connexion : {options['user']} / {options['password']}"))

    def _seed_depenses(self, user, biens):
        from gestion.models import Depense
        if Depense.objects.filter(bien__proprietaire=user).exists():
            return
        aujourd_hui = date.today()
        lignes = [
            (0, 'taxe', 'Taxe foncière', 85000, 40), (0, 'assurance', 'Assurance habitation', 45000, 75),
            (0, 'travaux', 'Peinture du salon', 120000, 20), (1, 'entretien', 'Nettoyage citerne', 30000, 12),
            (2, 'travaux', 'Réparation toiture', 250000, 55), (2, 'syndic', 'Charges de copropriété', 60000, 8),
        ]
        for i, cat, libelle, montant, jours in lignes:
            Depense.objects.create(bien=biens[i], categorie=cat, libelle=libelle, montant=Decimal(montant),
                                   date=aujourd_hui - timedelta(days=jours))
        biens[0].prix_acquisition = Decimal('45000000')
        biens[0].save(update_fields=['prix_acquisition'])
