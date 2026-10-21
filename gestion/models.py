import uuid
from datetime import date

from django.contrib.auth.models import User  # type: ignore
from django.core.exceptions import ValidationError  # type: ignore
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator  # type: ignore
from django.db import models  # type: ignore

from .utils import mois_annee_fr

telephone_validator = RegexValidator(
    r'^\+?[0-9 .\-]{7,20}$',
    'Numéro de téléphone invalide (ex : +221 77 123 45 67).',
)


class Bien(models.Model):
    TYPE_CHOICES = [
        ('appartement', 'Appartement'),
        ('maison', 'Maison'),
        ('studio', 'Studio'),
        ('commerce', 'Local commercial'),
        ('garage', 'Garage'),
    ]
    STATUT_CHOICES = [
        ('libre', 'Libre'),
        ('loue', 'Loué'),
        ('travaux', 'En travaux'),
        ('vente', 'En vente'),
    ]

    proprietaire = models.ForeignKey(User, on_delete=models.CASCADE, related_name='biens')
    nom = models.CharField(max_length=100)
    type_bien = models.CharField(max_length=20, choices=TYPE_CHOICES, default='appartement')
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='libre')
    adresse = models.CharField(max_length=200)
    ville = models.CharField(max_length=100)
    code_postal = models.CharField(max_length=10)
    surface = models.DecimalField(max_digits=7, decimal_places=2, help_text='Surface en m²')
    nb_pieces = models.PositiveIntegerField(default=1)
    etage = models.IntegerField(null=True, blank=True)
    loyer_charges = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)],
        help_text='Loyer charges comprises')
    prix_nuit = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)],
        help_text='Tarif par nuit pour les réservations (optionnel)')
    depot_garantie = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    description = models.TextField(blank=True)
    date_acquisition = models.DateField(null=True, blank=True)
    prix_acquisition = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    photo = models.ImageField(upload_to='biens/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Bien immobilier'
        verbose_name_plural = 'Biens immobiliers'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.nom} — {self.ville}'

    @property
    def locataire_actuel(self):
        contrat = self.contrat_actif
        return contrat.locataire if contrat else None

    @property
    def contrat_actif(self):
        return self.contrats.filter(statut='actif').first()

    def synchroniser_statut(self):
        """Aligne le statut du bien sur ses contrats (loué s'il y a un contrat actif, sinon libre).
        Les statuts « travaux » et « vente » sont posés à la main et ne sont pas écrasés."""
        if self.contrats.filter(statut='actif').exists():
            nouveau = 'loue'
        elif self.statut == 'loue':
            nouveau = 'libre'
        else:
            return
        if nouveau != self.statut:
            self.statut = nouveau
            self.save(update_fields=['statut'])


class Locataire(models.Model):
    proprietaire = models.ForeignKey(User, on_delete=models.CASCADE, related_name='locataires')
    compte = models.OneToOneField(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='locataire_profile',
        help_text="Compte de connexion donnant accès à l'espace locataire (optionnel)."
    )
    prenom = models.CharField(max_length=100)
    nom = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    telephone = models.CharField(max_length=20, validators=[telephone_validator])
    date_naissance = models.DateField(null=True, blank=True)
    profession = models.CharField(max_length=100, blank=True)
    revenu_mensuel = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    adresse_precedente = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Locataire'
        ordering = ['nom', 'prenom']

    def __str__(self):
        return f'{self.prenom} {self.nom}'

    @property
    def initiales(self):
        return f'{self.prenom[:1]}{self.nom[:1]}'.upper()

    @property
    def contrat_actif(self):
        return self.contrats.filter(statut='actif').first()


class Contrat(models.Model):
    STATUT_CHOICES = [
        ('actif', 'Actif'),
        ('termine', 'Terminé'),
        ('resilie', 'Résilié'),
    ]
    TYPE_CHOICES = [
        ('vide', 'Location vide'),
        ('meuble', 'Location meublée'),
        ('commercial', 'Bail commercial'),
        ('saisonnier', 'Saisonnier'),
    ]

    bien = models.ForeignKey(Bien, on_delete=models.CASCADE, related_name='contrats')
    locataire = models.ForeignKey(Locataire, on_delete=models.CASCADE, related_name='contrats')
    type_bail = models.CharField(max_length=20, choices=TYPE_CHOICES, default='vide')
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='actif')
    date_debut = models.DateField()
    date_fin = models.DateField(null=True, blank=True)
    loyer_mensuel = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    charges_mensuelles = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                             validators=[MinValueValidator(0)])
    depot_garantie = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    jour_paiement = models.PositiveIntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(28)], help_text='Jour du mois (1 à 28)')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Contrat de location'
        ordering = ['-date_debut']
        indexes = [models.Index(fields=['statut', 'date_fin'], name='contrat_statut_fin_idx')]

    def __str__(self):
        return f'{self.bien} → {self.locataire}'

    def clean(self):
        if self.date_fin and self.date_debut and self.date_fin < self.date_debut:
            raise ValidationError({'date_fin': 'La date de fin doit être postérieure à la date de début.'})
        if self.statut == 'actif' and self.bien_id:
            autres = Contrat.objects.filter(bien_id=self.bien_id, statut='actif').exclude(pk=self.pk)
            if autres.exists():
                raise ValidationError(
                    {'bien': "Ce bien a déjà un contrat actif. Résiliez-le avant d'en créer un autre."})

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.bien.synchroniser_statut()

    def delete(self, *args, **kwargs):
        bien = self.bien
        super().delete(*args, **kwargs)
        bien.synchroniser_statut()

    @property
    def loyer_total(self):
        return self.loyer_mensuel + self.charges_mensuelles

    @property
    def duree_mois(self):
        fin = self.date_fin or date.today()
        delta = (fin.year - self.date_debut.year) * 12 + (fin.month - self.date_debut.month)
        return max(delta, 0)


class Paiement(models.Model):
    STATUT_CHOICES = [
        ('paye', 'Payé'),
        ('en_attente', 'En attente'),
        ('retard', 'En retard'),
        ('partiel', 'Partiel'),
    ]
    MODE_CHOICES = [
        ('wave', 'Wave'),
        ('orange_money', 'Orange Money'),
        ('free_money', 'Free Money'),
        ('virement', 'Virement'),
        ('cheque', 'Chèque'),
        ('especes', 'Espèces'),
        ('prelevement', 'Prélèvement'),
    ]

    contrat = models.ForeignKey(Contrat, on_delete=models.CASCADE, related_name='paiements')
    mois = models.DateField(help_text='Premier jour du mois concerné')
    montant_du = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    montant_paye = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                       validators=[MinValueValidator(0)])
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='en_attente')
    mode_paiement = models.CharField(max_length=20, choices=MODE_CHOICES, blank=True)
    date_paiement = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Paiement'
        ordering = ['-mois']
        unique_together = ['contrat', 'mois']
        indexes = [models.Index(fields=['statut', 'mois'], name='paiement_statut_mois_idx')]

    def __str__(self):
        return f'{self.contrat.locataire} — {mois_annee_fr(self.mois)}'

    @property
    def solde(self):
        return self.montant_du - self.montant_paye

    @property
    def date_echeance(self):
        return self.mois.replace(day=min(self.contrat.jour_paiement, 28))

    def calculer_statut(self):
        """Statut déduit des montants et de l'échéance (plus de saisie incohérente)."""
        if self.montant_du is not None and self.montant_paye >= self.montant_du:
            return 'paye'
        if self.montant_paye and self.montant_paye > 0:
            return 'partiel'
        return 'retard' if self.date_echeance < date.today() else 'en_attente'

    def save(self, *args, **kwargs):
        self.statut = self.calculer_statut()
        if self.statut == 'paye' and not self.date_paiement:
            self.date_paiement = date.today()
        super().save(*args, **kwargs)


class Intervention(models.Model):
    PRIORITE_CHOICES = [
        ('basse', 'Basse'),
        ('normale', 'Normale'),
        ('haute', 'Haute'),
        ('urgente', 'Urgente'),
    ]
    STATUT_CHOICES = [
        ('ouverte', 'Ouverte'),
        ('en_cours', 'En cours'),
        ('terminee', 'Terminée'),
        ('annulee', 'Annulée'),
    ]

    bien = models.ForeignKey(Bien, on_delete=models.CASCADE, related_name='interventions')
    titre = models.CharField(max_length=200)
    description = models.TextField()
    priorite = models.CharField(max_length=10, choices=PRIORITE_CHOICES, default='normale')
    statut = models.CharField(max_length=10, choices=STATUT_CHOICES, default='ouverte')
    date_signalement = models.DateField(default=date.today)
    date_intervention = models.DateField(null=True, blank=True)
    date_resolution = models.DateField(null=True, blank=True)
    prestataire = models.CharField(max_length=100, blank=True)
    cout = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    signale_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='interventions_signalees')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Intervention'
        ordering = ['-date_signalement']

    def __str__(self):
        return f'{self.titre} — {self.bien}'


class DemandeContact(models.Model):
    """Demande envoyée par un visiteur du site public (formulaire de contact)."""
    bien = models.ForeignKey(Bien, on_delete=models.SET_NULL, null=True, blank=True, related_name='demandes')
    nom = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    telephone = models.CharField(max_length=20, blank=True)
    message = models.TextField()
    traite = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Demande de contact'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.nom} — {self.bien if self.bien else "Contact général"}'


class Reservation(models.Model):
    """Commande / réservation d'une chambre par un client, payée via Wave, Orange Money ou Free Money."""
    MODE_PAIEMENT_CHOICES = [
        ('wave', 'Wave'),
        ('orange_money', 'Orange Money'),
        ('free_money', 'Free Money'),
    ]
    STATUT_CHOICES = [
        ('en_attente', 'En attente de paiement'),
        ('payee', 'Payée'),
        ('confirmee', 'Confirmée'),
        ('annulee', 'Annulée'),
    ]
    STATUTS_BLOQUANTS = ['en_attente', 'payee', 'confirmee']

    bien = models.ForeignKey(Bien, on_delete=models.CASCADE, related_name='reservations')
    token = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    nom = models.CharField(max_length=150)
    telephone = models.CharField(max_length=20, validators=[telephone_validator])
    email = models.EmailField(blank=True)
    date_arrivee = models.DateField()
    date_depart = models.DateField(null=True, blank=True)
    nb_personnes = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    mode_paiement = models.CharField(max_length=20, choices=MODE_PAIEMENT_CHOICES)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='en_attente')
    montant_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Réservation'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['statut', 'date_arrivee'], name='resa_statut_arrivee_idx')]

    def __str__(self):
        return f'{self.nom} — {self.bien} ({self.get_statut_display()})'

    @property
    def reference(self):
        return f'RES-{self.pk:05d}'

    @property
    def nb_nuits(self):
        if self.date_depart and self.date_arrivee:
            return max((self.date_depart - self.date_arrivee).days, 1)
        return 1

    def clean(self):
        erreurs = {}
        if self.date_arrivee and self.pk is None and self.date_arrivee < date.today():
            erreurs['date_arrivee'] = "La date d'arrivée ne peut pas être dans le passé."
        if self.date_depart and self.date_arrivee and self.date_depart <= self.date_arrivee:
            erreurs['date_depart'] = "Le départ doit être postérieur à l'arrivée."
        if erreurs:
            raise ValidationError(erreurs)


class Notification(models.Model):
    """Notification interne (cloche de l'application)."""
    destinataire = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    titre = models.CharField(max_length=150)
    message = models.TextField(blank=True)
    lien = models.CharField(max_length=200, blank=True)
    lue = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.titre} → {self.destinataire}'


class Depense(models.Model):
    """Dépense liée à un bien (taxe, assurance, travaux…) pour calculer la rentabilité nette."""
    CATEGORIE_CHOICES = [
        ('taxe', 'Taxes et impôts'),
        ('assurance', 'Assurance'),
        ('travaux', 'Travaux'),
        ('entretien', 'Entretien'),
        ('syndic', 'Syndic / charges'),
        ('autre', 'Autre'),
    ]

    bien = models.ForeignKey(Bien, on_delete=models.CASCADE, related_name='depenses')
    categorie = models.CharField(max_length=20, choices=CATEGORIE_CHOICES, default='autre')
    libelle = models.CharField(max_length=200)
    montant = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    date = models.DateField(default=date.today)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Dépense'
        ordering = ['-date', '-id']
        indexes = [models.Index(fields=['date'], name='depense_date_idx')]

    def __str__(self):
        return f'{self.libelle} — {self.bien}'


TAILLE_MAX_DOCUMENT = 5 * 1024 * 1024
EXTENSIONS_DOCUMENT = ('pdf', 'jpg', 'jpeg', 'png')


def valider_document(fichier):
    ext = fichier.name.rsplit('.', 1)[-1].lower() if '.' in fichier.name else ''
    if ext not in EXTENSIONS_DOCUMENT:
        raise ValidationError('Format non autorisé (PDF, JPG ou PNG uniquement).')
    if fichier.size > TAILLE_MAX_DOCUMENT:
        raise ValidationError('Fichier trop volumineux (5 Mo maximum).')


class Document(models.Model):
    """Pièce jointe (pièce d'identité, bail signé, assurance…) rattachée à un locataire ou à un bien.
    Le fichier n'est jamais exposé par une URL publique : il est servi par un endpoint authentifié."""
    TYPE_CHOICES = [
        ('identite', "Pièce d'identité"),
        ('bail', 'Bail signé'),
        ('assurance', 'Assurance'),
        ('justificatif', 'Justificatif de revenu'),
        ('etat_lieux', 'État des lieux'),
        ('autre', 'Autre'),
    ]

    type_document = models.CharField(max_length=20, choices=TYPE_CHOICES, default='autre')
    titre = models.CharField(max_length=150)
    fichier = models.FileField(upload_to='documents/%Y/%m/', validators=[valider_document])
    locataire = models.ForeignKey(Locataire, on_delete=models.CASCADE, null=True, blank=True,
                                  related_name='documents')
    bien = models.ForeignKey(Bien, on_delete=models.CASCADE, null=True, blank=True, related_name='documents')
    date_expiration = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.titre

    def clean(self):
        if not self.locataire_id and not self.bien_id:
            raise ValidationError('Un document doit être rattaché à un locataire ou à un bien.')
