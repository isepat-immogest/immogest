import uuid
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User  # type: ignore
from django.core.exceptions import ValidationError  # type: ignore
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator  # type: ignore
from django.db import models  # type: ignore

from .utils import mois_annee_fr, normaliser_telephone

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
        ('chambre', 'Chambre'),
        ('piscine', 'Piscine'),
        ('Hotel', 'Hotel'),
        ('terrain', 'Terrain'),
        ('villa', 'Villa'),
    ]
    OFFRE_CHOICES = [
        ('location', 'À louer'),
        ('vente', 'À vendre'),
    ]
    STATUT_JURIDIQUE_CHOICES = [
        ('titre_foncier', 'Titre foncier'),
        ('bail', 'Bail'),
        ('deliberation', 'Délibération'),
        ('autre', 'Autre'),
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
    offre = models.CharField(
        max_length=10, choices=OFFRE_CHOICES, default='location',
        help_text='Annonce publique : bien à louer ou à vendre')
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='libre')
    adresse = models.CharField(max_length=200)
    ville = models.CharField(max_length=100)
    code_postal = models.CharField(max_length=10)
    surface = models.DecimalField(max_digits=7, decimal_places=2, help_text='Surface en m²')
    nb_pieces = models.PositiveIntegerField(default=1)
    etage = models.IntegerField(null=True, blank=True)
    loyer_charges = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)],
        help_text='Loyer charges comprises (laisser à 0 pour un bien à vendre)')
    prix_vente = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)],
        help_text="Prix de vente en FCFA (obligatoire si le bien est « à vendre »)")
    statut_juridique = models.CharField(
        max_length=20, choices=STATUT_JURIDIQUE_CHOICES, blank=True,
        help_text='Situation foncière affichée sur l’annonce (titre foncier, bail…)')
    prix_nuit = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)],
        help_text='Tarif par nuit pour les réservations (optionnel)')
    depot_garantie = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    nb_chambres = models.PositiveIntegerField(default=0)
    nb_salles_bain = models.PositiveIntegerField(default=1)
    meuble = models.BooleanField(default=False, help_text='Le bien est loué meublé')
    capacite = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)],
        help_text='Nombre maximum de personnes (réservations)')
    equipements = models.ManyToManyField('Equipement', blank=True, related_name='biens')
    proprietaires = models.ManyToManyField(
        'Proprietaire', through='BienProprietaire', blank=True, related_name='biens',
        help_text='Propriétaires du bien (indivision : plusieurs possibles, quotes-parts = 100 %)')
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

    def clean(self):
        """Le statut « loué » ne se pose pas à la main : il découle des contrats (voir synchroniser_statut)."""
        if self.offre == 'vente' and not self.prix_vente:
            raise ValidationError({'prix_vente': 'Indiquez le prix de vente d’un bien à vendre.'})
        if not self.pk:
            if self.statut == 'loue':
                raise ValidationError({'statut': "Un bien ne peut être « loué » que s'il a un contrat actif : "
                                                 "créez d'abord le contrat."})
            return
        actif = self.contrats.filter(statut='actif').exists()
        if self.statut == 'loue' and not actif:
            raise ValidationError({'statut': "Ce bien n'a aucun contrat actif : il ne peut pas être « loué »."})
        if actif and self.statut != 'loue':
            raise ValidationError({'statut': 'Ce bien a un contrat actif : résiliez-le avant de changer son statut.'})

    @property
    def galerie(self):
        """Toutes les photos du bien : la photo principale d'abord, puis la galerie (dans l'ordre choisi)."""
        images = [{'url': self.photo.url, 'legende': self.nom}] if self.photo else []
        images += [{'url': p.image.url, 'legende': p.legende or self.nom} for p in self.photos.all()]
        return images

    @property
    def photo_principale(self):
        if self.photo:
            return self.photo
        premiere = next(iter(self.photos.all()), None)
        return premiere.image if premiere else None

    @property
    def est_a_vendre(self):
        return self.offre == 'vente'

    @property
    def prix_affiche(self):
        """Prix de l'annonce : prix de vente pour une vente, loyer mensuel pour une location."""
        return self.prix_vente if self.est_a_vendre else self.loyer_charges

    @classmethod
    def annonces_publiques(cls):
        """Biens visibles sur le site public : locations libres + ventes (libre ou « en vente »)."""
        from django.db.models import Q  # type: ignore
        return cls.objects.filter(
            Q(offre='location', statut='libre') | Q(offre='vente', statut__in=['libre', 'vente']))

    @property
    def locataire_actuel(self):
        contrat = self.contrat_actif
        return contrat.locataire if contrat else None

    @property
    def total_quotes_parts(self):
        from django.db.models import Sum  # type: ignore
        return self.parts.aggregate(t=Sum('quote_part'))['t'] or 0

    @property
    def contrat_actif(self):
        prefetch = getattr(self, '_contrats_actifs', None)  # rempli par les viewsets (évite le N+1)
        if prefetch is not None:
            return prefetch[0] if prefetch else None
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


class BienPhoto(models.Model):
    """Photo supplémentaire d'un bien (galerie), en plus de la photo principale."""
    bien = models.ForeignKey(Bien, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='biens/galerie/')
    legende = models.CharField(max_length=120, blank=True, help_text='Ex. : Salon, Façade, Vue du terrain')
    ordre = models.PositiveIntegerField(default=0, help_text='Plus petit = affiché en premier')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Photo du bien'
        verbose_name_plural = 'Photos du bien'
        ordering = ['ordre', 'id']

    def __str__(self):
        return f'{self.bien.nom} — {self.legende or self.image.name}'


class Equipement(models.Model):
    """Catalogue d'équipements (climatisation, citerne, groupe électrogène, wifi…) associables à un bien."""
    CATEGORIE_CHOICES = [
        ('confort', 'Confort'),
        ('eau_energie', 'Eau et énergie'),
        ('cuisine', 'Cuisine et mobilier'),
        ('connectivite', 'Connectivité'),
        ('securite', 'Sécurité'),
        ('exterieur', 'Extérieur et stationnement'),
        ('autre', 'Autre'),
    ]

    nom = models.CharField(max_length=100, unique=True)
    icone = models.CharField(max_length=50, blank=True, help_text="Nom d'icône (optionnel)")
    categorie = models.CharField(max_length=20, choices=CATEGORIE_CHOICES, default='autre')

    class Meta:
        verbose_name = 'Équipement'
        ordering = ['categorie', 'nom']

    def __str__(self):
        return self.nom

    def clean(self):
        self.nom = (self.nom or '').strip()
        if self.nom and Equipement.objects.filter(nom__iexact=self.nom).exclude(pk=self.pk).exists():
            raise ValidationError({'nom': 'Cet équipement existe déjà.'})


class Proprietaire(models.Model):
    """Propriétaire (mandant) d'un ou plusieurs biens : distinct du compte de connexion du gestionnaire.

    Un bien peut avoir plusieurs propriétaires (indivision, héritiers, couple…) via `BienProprietaire`,
    et un propriétaire peut posséder plusieurs biens.
    """
    TYPE_CHOICES = [('personne', 'Personne physique'), ('societe', 'Société / SCI')]

    gestionnaire = models.ForeignKey(User, on_delete=models.CASCADE, related_name='proprietaires_geres',
                                     help_text='Compte de gestion qui administre ce propriétaire.')
    type_proprietaire = models.CharField(max_length=10, choices=TYPE_CHOICES, default='personne')
    prenom = models.CharField(max_length=100, blank=True)
    nom = models.CharField(max_length=150, help_text='Nom, ou raison sociale pour une société')
    email = models.EmailField(blank=True)
    telephone = models.CharField(max_length=20, validators=[telephone_validator])
    whatsapp = models.CharField(max_length=20, blank=True, validators=[telephone_validator],
                                help_text='Laisser vide si identique au téléphone')
    adresse = models.CharField(max_length=200, blank=True)
    commission_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=10, validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Commission de gestion prélevée sur les loyers encaissés (%)')
    compte_reversement = models.CharField(max_length=100, blank=True,
                                          help_text='Wave / Orange Money / IBAN pour le reversement')
    notif_email = models.BooleanField(default=True, help_text='Recevoir ses relevés et alertes par email')
    notif_whatsapp = models.BooleanField(default=False, help_text='Recevoir ses relevés et alertes par WhatsApp')
    notes = models.TextField(blank=True)
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Propriétaire'
        ordering = ['nom', 'prenom']

    def __str__(self):
        return f'{self.prenom} {self.nom}'.strip()

    @property
    def numero_whatsapp(self):
        return self.whatsapp or self.telephone

    def save(self, *args, **kwargs):
        self.telephone = normaliser_telephone(self.telephone)
        self.whatsapp = normaliser_telephone(self.whatsapp)
        super().save(*args, **kwargs)


class BienProprietaire(models.Model):
    """Quote-part d'un propriétaire sur un bien (la somme des quotes-parts d'un bien doit valoir 100 %)."""
    bien = models.ForeignKey(Bien, on_delete=models.CASCADE, related_name='parts')
    proprietaire = models.ForeignKey(Proprietaire, on_delete=models.PROTECT, related_name='parts')
    quote_part = models.DecimalField(
        max_digits=5, decimal_places=2, default=100,
        validators=[MinValueValidator(Decimal('0.01')), MaxValueValidator(100)],
        help_text='Part détenue, en %')

    class Meta:
        verbose_name = 'Quote-part de propriété'
        unique_together = ['bien', 'proprietaire']
        ordering = ['-quote_part', 'proprietaire__nom']

    def __str__(self):
        return f'{self.proprietaire} — {self.quote_part} % de {self.bien}'


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
    notif_whatsapp = models.BooleanField(
        default=False, help_text='Le locataire accepte de recevoir des messages WhatsApp (rappels de loyer, reçus)')
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

    def save(self, *args, **kwargs):
        self.telephone = normaliser_telephone(self.telephone)
        super().save(*args, **kwargs)

    @property
    def contrat_actif(self):
        prefetch = getattr(self, '_contrats_actifs', None)  # rempli par les viewsets (évite le N+1)
        if prefetch is not None:
            return prefetch[0] if prefetch else None
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
            if self.bien.statut == 'travaux':
                raise ValidationError({'bien': "Ce bien est en travaux : repassez-le « libre » avant de le louer."})
        if self.statut == 'actif' and self.date_fin and self.date_fin < date.today() and self._state.adding:
            raise ValidationError({'date_fin': 'Un nouveau contrat actif ne peut pas être déjà expiré.'})
        if self.depot_garantie is not None and self.depot_garantie < 0:
            raise ValidationError({'depot_garantie': 'Le dépôt de garantie ne peut pas être négatif.'})

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

    def clean(self):
        if self.mois:
            self.mois = self.mois.replace(day=1)
        if self.montant_du is not None and self.montant_paye is not None and self.montant_paye > self.montant_du:
            raise ValidationError({'montant_paye': 'Le montant payé ne peut pas dépasser le montant dû.'})
        if self.contrat_id and self.mois:
            c = self.contrat
            if self.mois < c.date_debut.replace(day=1) or (c.date_fin and self.mois > c.date_fin):
                raise ValidationError({'mois': "Ce mois est en dehors de la durée du contrat."})

    def calculer_statut(self):
        """Statut déduit des montants et de l'échéance (plus de saisie incohérente)."""
        if self.montant_du is not None and self.montant_paye >= self.montant_du:
            return 'paye'
        if self.montant_paye and self.montant_paye > 0:
            return 'partiel'
        return 'retard' if self.date_echeance < date.today() else 'en_attente'

    def save(self, *args, **kwargs):
        if self.mois:
            self.mois = self.mois.replace(day=1)   # un loyer est toujours rattaché au 1er du mois
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

    def clean(self):
        if self.date_resolution and self.date_signalement and self.date_resolution < self.date_signalement:
            raise ValidationError({'date_resolution': 'La résolution ne peut pas précéder le signalement.'})
        if self.date_intervention and self.date_signalement and self.date_intervention < self.date_signalement:
            raise ValidationError({'date_intervention': "L'intervention ne peut pas précéder le signalement."})
        if self.cout is not None and self.cout < 0:
            raise ValidationError({'cout': 'Le coût ne peut pas être négatif.'})

    def save(self, *args, **kwargs):
        if self.statut == 'terminee' and not self.date_resolution:
            self.date_resolution = date.today()
        elif self.statut in ('ouverte', 'en_cours') and self.date_resolution:
            self.date_resolution = None        # une intervention rouverte n'est plus « résolue »
        super().save(*args, **kwargs)


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
    preuve_paiement = models.FileField(upload_to='preuves/', blank=True, null=True)

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
        if self.bien_id and self.bien.capacite and self.nb_personnes and self.nb_personnes > self.bien.capacite:
            erreurs['nb_personnes'] = f'Ce bien accueille {self.bien.capacite} personne(s) au maximum.'
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


class ProfilGestionnaire(models.Model):
    """Coordonnées et préférences de notification d'un compte de gestion (email + WhatsApp)."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profil_gestion')
    numero_whatsapp = models.CharField(
        max_length=20, blank=True, validators=[telephone_validator],
        help_text='Numéro qui reçoit les alertes WhatsApp (ex : +221 77 123 45 67)')
    notif_email = models.BooleanField(default=True, help_text='Recevoir les alertes par email')
    notif_whatsapp = models.BooleanField(default=True, help_text='Recevoir les alertes par WhatsApp')
    evenements_desactives = models.JSONField(
        default=list, blank=True, help_text="Codes d'événements dont on ne veut plus être prévenu hors application")

    class Meta:
        verbose_name = 'Profil gestionnaire'

    def __str__(self):
        return f'Profil de {self.user}'

    def save(self, *args, **kwargs):
        self.numero_whatsapp = normaliser_telephone(self.numero_whatsapp)
        super().save(*args, **kwargs)


class EnvoiNotification(models.Model):
    """Journal de chaque envoi externe (email / WhatsApp) : plus aucun échec n'est silencieux."""
    CANAL_CHOICES = [('email', 'Email'), ('whatsapp', 'WhatsApp')]
    STATUT_CHOICES = [('envoye', 'Envoyé'), ('echec', 'Échec'), ('ignore', 'Ignoré')]

    destinataire = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True,
                                     related_name='envois_notifications')
    gestionnaire = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True,
                                     related_name='envois_de_ses_contacts',
                                     help_text='Gestionnaire responsable quand le destinataire est un propriétaire ou un locataire')
    libelle_destinataire = models.CharField(max_length=150, blank=True)
    notification = models.ForeignKey(Notification, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='envois')
    evenement = models.CharField(max_length=40, blank=True)
    canal = models.CharField(max_length=10, choices=CANAL_CHOICES)
    adresse = models.CharField(max_length=254, blank=True, help_text='Email ou numéro utilisé')
    sujet = models.CharField(max_length=200, blank=True)
    message = models.TextField(blank=True)
    statut = models.CharField(max_length=10, choices=STATUT_CHOICES)
    erreur = models.TextField(blank=True)
    tentatives = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Envoi de notification"
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['statut', 'tentatives'], name='envoi_statut_tent_idx')]

    def __str__(self):
        return f'{self.get_canal_display()} → {self.adresse or self.destinataire or self.libelle_destinataire} ({self.get_statut_display()})'
