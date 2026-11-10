from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError  # type: ignore
from drf_spectacular.utils import extend_schema_field  # type: ignore
from rest_framework import serializers  # type: ignore

from gestion import notifications
from gestion.models import (Bien, BienProprietaire, Contrat, DemandeContact, Depense, Document, EnvoiNotification,
                            Equipement, Intervention, Locataire, Notification, Paiement, ProfilGestionnaire,
                            Proprietaire, Reservation)
from gestion.scope import proprietaires_visibles


class CleanedModelSerializer(serializers.ModelSerializer):
    """Applique `Model.clean()` (règles métier) lors de la validation DRF."""

    def validate(self, attrs):
        attrs = super().validate(attrs)
        modele = self.Meta.model
        champs = {f.name for f in modele._meta.fields}   # exclut les relations plusieurs-à-plusieurs (équipements…)
        if self.instance is not None:
            instance = modele.objects.get(pk=self.instance.pk)
            for k, v in attrs.items():
                if k in champs:
                    setattr(instance, k, v)
        else:
            instance = modele(**{k: v for k, v in attrs.items() if k in champs})
        try:
            instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, 'error_dict') else exc.messages)
        return attrs


def _verifier_perimetre(request, chemin_proprietaire_obj):
    """Lève une erreur si l'objet n'appartient pas au périmètre de l'utilisateur."""
    if chemin_proprietaire_obj not in proprietaires_visibles(request.user).values_list('pk', flat=True):
        raise serializers.ValidationError("Objet introuvable.")


# ── Biens ────────────────────────────────────────────────────────────────────

class EquipementSerializer(CleanedModelSerializer):
    categorie_display = serializers.CharField(source='get_categorie_display', read_only=True)
    nb_biens = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Equipement
        fields = ['id', 'nom', 'icone', 'categorie', 'categorie_display', 'nb_biens']


class BienSerializer(CleanedModelSerializer):
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)
    type_display = serializers.CharField(source='get_type_bien_display', read_only=True)
    locataire_actuel = serializers.SerializerMethodField()
    equipements = serializers.PrimaryKeyRelatedField(many=True, queryset=Equipement.objects.all(), required=False)
    equipements_detail = serializers.SerializerMethodField()
    proprietaires_detail = serializers.SerializerMethodField()
    quotes_parts_total = serializers.SerializerMethodField()
    # À la création : propriétaire unique à 100 % (pour plusieurs propriétaires : /biens/{id}/proprietaires/).
    proprietaire_principal = serializers.PrimaryKeyRelatedField(
        queryset=Proprietaire.objects.all(), write_only=True, required=False, allow_null=True)

    class Meta:
        model = Bien
        exclude = ['proprietaire', 'proprietaires']
        read_only_fields = ['created_at']

    def to_internal_value(self, data):
        # Envoi multipart (photo) : une liste vide ne peut pas s'écrire en formulaire, d'où un marqueur explicite.
        if hasattr(data, 'getlist') and data.get('equipements__present') and 'equipements' not in data:
            data = data.copy()
            data.setlist('equipements', [])
        return super().to_internal_value(data)

    def validate_proprietaire_principal(self, proprietaire):
        if proprietaire is not None:
            _verifier_perimetre(self.context['request'], proprietaire.gestionnaire_id)
        return proprietaire

    @extend_schema_field(dict)
    def get_locataire_actuel(self, obj):
        loc = obj.locataire_actuel
        return {'id': loc.pk, 'nom': str(loc)} if loc else None

    @extend_schema_field(list)
    def get_equipements_detail(self, obj):
        return [{'id': e.pk, 'nom': e.nom, 'categorie': e.categorie} for e in obj.equipements.all()]

    @extend_schema_field(list)
    def get_proprietaires_detail(self, obj):
        return [{'proprietaire': p.proprietaire_id, 'nom': str(p.proprietaire), 'quote_part': p.quote_part,
                 'telephone': p.proprietaire.telephone} for p in obj.parts.all()]

    @extend_schema_field(float)
    def get_quotes_parts_total(self, obj):
        return float(sum(p.quote_part for p in obj.parts.all()))


# ── Propriétaires ────────────────────────────────────────────────────────────

class ProprietaireSerializer(serializers.ModelSerializer):
    nom_complet = serializers.CharField(source='__str__', read_only=True)
    type_display = serializers.CharField(source='get_type_proprietaire_display', read_only=True)
    nb_biens = serializers.IntegerField(read_only=True, default=0)
    biens_detail = serializers.SerializerMethodField()

    class Meta:
        model = Proprietaire
        exclude = ['gestionnaire']
        read_only_fields = ['created_at']

    @extend_schema_field(list)
    def get_biens_detail(self, obj):
        return [{'id': p.bien_id, 'nom': p.bien.nom, 'quote_part': p.quote_part} for p in obj.parts.all()]


class PartProprietaireSerializer(serializers.Serializer):
    proprietaire = serializers.PrimaryKeyRelatedField(queryset=Proprietaire.objects.all())
    quote_part = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal('0.01'), max_value=100)


class DefinirProprietairesSerializer(serializers.Serializer):
    parts = PartProprietaireSerializer(many=True)

    def validate_parts(self, parts):
        for p in parts:
            _verifier_perimetre(self.context['request'], p['proprietaire'].gestionnaire_id)
        return parts


# ── Locataires ───────────────────────────────────────────────────────────────

class LocataireSerializer(serializers.ModelSerializer):
    nom_complet = serializers.CharField(source='__str__', read_only=True)
    initiales = serializers.CharField(read_only=True)
    a_un_acces = serializers.SerializerMethodField()
    acces_actif = serializers.SerializerMethodField()
    contrat_actif = serializers.SerializerMethodField()

    

    class Meta:
        model = Locataire
        exclude = ['proprietaire', 'compte']
        read_only_fields = ['created_at']

    @extend_schema_field(bool)
    def get_a_un_acces(self, obj):
        return obj.compte_id is not None

    @extend_schema_field(bool)
    def get_acces_actif(self, obj):
        return bool(obj.compte_id and obj.compte.is_active)

    @extend_schema_field(dict)
    def get_contrat_actif(self, obj):
        c = obj.contrat_actif
        return {'id': c.pk, 'bien': c.bien.nom, 'loyer_total': c.loyer_total} if c else None


# ── Contrats ─────────────────────────────────────────────────────────────────

class ContratSerializer(CleanedModelSerializer):
    bien_nom = serializers.CharField(source='bien.nom', read_only=True)
    locataire_nom = serializers.CharField(source='locataire.__str__', read_only=True)
    loyer_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    duree_mois = serializers.IntegerField(read_only=True)
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)

    class Meta:
        model = Contrat
        fields = '__all__'
        read_only_fields = ['created_at']

    def validate_bien(self, bien):
        _verifier_perimetre(self.context['request'], bien.proprietaire_id)
        return bien

    def validate_locataire(self, locataire):
        _verifier_perimetre(self.context['request'], locataire.proprietaire_id)
        return locataire


class ResiliationSerializer(serializers.Serializer):
    date_fin = serializers.DateField(required=False)
    statut = serializers.ChoiceField(choices=['resilie', 'termine'], default='resilie')


# ── Paiements ────────────────────────────────────────────────────────────────

class PaiementSerializer(CleanedModelSerializer):
    locataire_nom = serializers.CharField(source='contrat.locataire.__str__', read_only=True)
    bien_nom = serializers.CharField(source='contrat.bien.nom', read_only=True)
    solde = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    date_echeance = serializers.DateField(read_only=True)
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)
    montant_du = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)

    class Meta:
        model = Paiement
        fields = '__all__'
        read_only_fields = ['created_at', 'statut']

    def validate_contrat(self, contrat):
        _verifier_perimetre(self.context['request'], contrat.bien.proprietaire_id)
        return contrat

    def validate(self, attrs):
        if 'montant_du' not in attrs and self.instance is None:
            attrs['montant_du'] = attrs['contrat'].loyer_total
        return super().validate(attrs)


class VersementSerializer(serializers.Serializer):
    montant = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=1)
    mode_paiement = serializers.ChoiceField(choices=Paiement.MODE_CHOICES, required=False, allow_blank=True)
    date_versement = serializers.DateField(required=False)


class DepenseSerializer(serializers.ModelSerializer):
    bien_nom = serializers.CharField(source='bien.nom', read_only=True)
    categorie_display = serializers.CharField(source='get_categorie_display', read_only=True)

    class Meta:
        model = Depense
        fields = '__all__'
        read_only_fields = ['created_at']

    def validate_bien(self, bien):
        _verifier_perimetre(self.context['request'], bien.proprietaire_id)
        return bien


class DocumentSerializer(CleanedModelSerializer):
    """Le fichier est en écriture seule : il n'est jamais exposé par URL, mais via `/telecharger/`."""
    type_display = serializers.CharField(source='get_type_document_display', read_only=True)
    nom_fichier = serializers.SerializerMethodField()
    taille = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ['id', 'type_document', 'type_display', 'titre', 'fichier', 'nom_fichier', 'taille',
                  'locataire', 'bien', 'date_expiration', 'created_at']
        read_only_fields = ['created_at']
        extra_kwargs = {'fichier': {'write_only': True}}

    @extend_schema_field(str)
    def get_nom_fichier(self, obj):
        return obj.fichier.name.rsplit('/', 1)[-1] if obj.fichier else ''

    @extend_schema_field(int)
    def get_taille(self, obj):
        try:
            return obj.fichier.size
        except (OSError, ValueError):
            return None

    def validate_locataire(self, locataire):
        if locataire is not None:
            _verifier_perimetre(self.context['request'], locataire.proprietaire_id)
        return locataire

    def validate_bien(self, bien):
        if bien is not None:
            _verifier_perimetre(self.context['request'], bien.proprietaire_id)
        return bien


class GenererMoisSerializer(serializers.Serializer):
    mois = serializers.DateField(required=False, help_text="Un jour du mois visé (défaut : mois courant)")


# ── Interventions ────────────────────────────────────────────────────────────

class InterventionSerializer(CleanedModelSerializer):
    bien_nom = serializers.CharField(source='bien.nom', read_only=True)
    signale_par_nom = serializers.SerializerMethodField()
    priorite_display = serializers.CharField(source='get_priorite_display', read_only=True)
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)

    class Meta:
        model = Intervention
        exclude = ['signale_par']
        read_only_fields = ['created_at']

    @extend_schema_field(str)
    def get_signale_par_nom(self, obj):
        return obj.signale_par.get_full_name() or obj.signale_par.username if obj.signale_par else None

    def validate_bien(self, bien):
        _verifier_perimetre(self.context['request'], bien.proprietaire_id)
        return bien


class SignalementLocataireSerializer(serializers.Serializer):
    titre = serializers.CharField(max_length=200)
    description = serializers.CharField()
    priorite = serializers.ChoiceField(choices=Intervention.PRIORITE_CHOICES, default='normale')


# ── Réservations / demandes ─────────────────────────────────────────────────

class ReservationSerializer(CleanedModelSerializer):
    reference = serializers.CharField(read_only=True)
    bien_nom = serializers.CharField(source='bien.nom', read_only=True)
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)
    nb_nuits = serializers.IntegerField(read_only=True)

    class Meta:
        model = Reservation
        exclude = ['token']
        read_only_fields = ['created_at', 'montant_total', 'preuve_paiement']

    def validate_bien(self, bien):
        _verifier_perimetre(self.context['request'], bien.proprietaire_id)
        return bien


class StatutSerializer(serializers.Serializer):
    statut = serializers.ChoiceField(choices=Reservation.STATUT_CHOICES)


class DemandeSerializer(serializers.ModelSerializer):
    bien_nom = serializers.CharField(source='bien.nom', read_only=True, default=None)

    class Meta:
        model = DemandeContact
        fields = '__all__'
        read_only_fields = ['created_at', 'nom', 'email', 'telephone', 'message', 'bien']


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        exclude = ['destinataire']


class EnvoiNotificationSerializer(serializers.ModelSerializer):
    canal_display = serializers.CharField(source='get_canal_display', read_only=True)
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)
    evenement_label = serializers.SerializerMethodField()

    class Meta:
        model = EnvoiNotification
        fields = ['id', 'canal', 'canal_display', 'adresse', 'libelle_destinataire', 'sujet', 'evenement',
                  'evenement_label', 'statut', 'statut_display', 'erreur', 'tentatives', 'created_at']

    @extend_schema_field(str)
    def get_evenement_label(self, obj):
        return {**notifications.EVENEMENTS, **notifications.EVENEMENTS_TIERS}.get(obj.evenement, obj.evenement)


class PreferencesNotificationSerializer(serializers.Serializer):
    """Préférences de notification du gestionnaire connecté (email, WhatsApp, événements)."""
    email = serializers.EmailField(allow_blank=True, required=False)
    numero_whatsapp = serializers.CharField(allow_blank=True, required=False, max_length=20)
    notif_email = serializers.BooleanField(required=False)
    notif_whatsapp = serializers.BooleanField(required=False)
    evenements_desactives = serializers.ListField(child=serializers.CharField(), required=False)

    def validate_numero_whatsapp(self, valeur):
        from django.core.exceptions import ValidationError as DjangoError  # type: ignore
        from gestion.models import telephone_validator
        from gestion.utils import normaliser_telephone
        valeur = normaliser_telephone(valeur)
        if valeur:
            try:
                telephone_validator(valeur)
            except DjangoError as exc:
                raise serializers.ValidationError(exc.messages)
        return valeur

    def validate_evenements_desactives(self, codes):
        inconnus = sorted(set(codes) - set(notifications.EVENEMENTS))
        if inconnus:
            raise serializers.ValidationError(f'Événement(s) inconnu(s) : {", ".join(inconnus)}.')
        return sorted(set(codes))


# ── Public ───────────────────────────────────────────────────────────────────

class PublicBienSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source='get_type_bien_display', read_only=True)
    equipements = serializers.SlugRelatedField(many=True, read_only=True, slug_field='nom')

    class Meta:
        model = Bien
        fields = ['id', 'nom', 'type_bien', 'type_display', 'adresse', 'ville', 'surface', 'nb_pieces',
                  'nb_chambres', 'nb_salles_bain', 'meuble', 'capacite', 'equipements', 'etage', 'loyer_charges',
                  'prix_nuit', 'description', 'photo']


class PublicReservationCreateSerializer(serializers.ModelSerializer):
    website = serializers.CharField(required=False, allow_blank=True, write_only=True)  # honeypot anti-spam

    class Meta:
        model = Reservation
        fields = ['bien', 'nom', 'telephone', 'email', 'date_arrivee', 'date_depart', 'nb_personnes',
                  'mode_paiement', 'message', 'website']
        # L'email est obligatoire : c'est là que le client reçoit sa confirmation.
        extra_kwargs = {'email': {'required': True, 'allow_blank': False}}

    def validate_website(self, value):
        if value:
            raise serializers.ValidationError('Spam détecté.')
        return value


class PublicReservationSerializer(serializers.ModelSerializer):
    reference = serializers.CharField(read_only=True)
    bien_nom = serializers.CharField(source='bien.nom', read_only=True)
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)

    class Meta:
        model = Reservation
        fields = ['reference', 'token', 'bien_nom', 'nom', 'date_arrivee', 'date_depart', 'nb_personnes',
                  'mode_paiement', 'statut', 'statut_display', 'montant_total']


class PublicContactSerializer(serializers.ModelSerializer):
    website = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = DemandeContact
        fields = ['bien', 'nom', 'email', 'telephone', 'message', 'website']
        extra_kwargs = {'email': {'required': True, 'allow_blank': False}}

    def validate_website(self, value):
        if value:
            raise serializers.ValidationError('Spam détecté.')
        return value
