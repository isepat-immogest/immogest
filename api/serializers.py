from django.core.exceptions import ValidationError as DjangoValidationError  # type: ignore
from rest_framework import serializers  # type: ignore

from gestion.models import (Bien, Contrat, DemandeContact, Depense, Document, Intervention, Locataire,
                            Notification, Paiement, Reservation)
from gestion.scope import proprietaires_visibles


class CleanedModelSerializer(serializers.ModelSerializer):
    """Applique `Model.clean()` (règles métier) lors de la validation DRF."""

    def validate(self, attrs):
        attrs = super().validate(attrs)
        modele = self.Meta.model
        if self.instance is not None:
            instance = modele.objects.get(pk=self.instance.pk)
            for k, v in attrs.items():
                setattr(instance, k, v)
        else:
            instance = modele(**{k: v for k, v in attrs.items() if k in {f.name for f in modele._meta.fields}})
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

class BienSerializer(serializers.ModelSerializer):
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)
    type_display = serializers.CharField(source='get_type_bien_display', read_only=True)
    locataire_actuel = serializers.SerializerMethodField()

    class Meta:
        model = Bien
        exclude = ['proprietaire']
        read_only_fields = ['created_at']

    def get_locataire_actuel(self, obj):
        # `_contrats_actifs` est pré-chargé par la vue (évite 2 requêtes par ligne)
        actifs = getattr(obj, '_contrats_actifs', None)
        contrat = actifs[0] if actifs else (obj.contrat_actif if actifs is None else None)
        return {'id': contrat.locataire.pk, 'nom': str(contrat.locataire)} if contrat else None


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

    def get_a_un_acces(self, obj):
        return obj.compte_id is not None

    def get_acces_actif(self, obj):
        return bool(obj.compte_id and obj.compte.is_active)

    def get_contrat_actif(self, obj):
        actifs = getattr(obj, '_contrats_actifs', None)
        c = actifs[0] if actifs else (obj.contrat_actif if actifs is None else None)
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


class GenererMoisSerializer(serializers.Serializer):
    mois = serializers.DateField(required=False, help_text="Un jour du mois visé (défaut : mois courant)")


# ── Interventions ────────────────────────────────────────────────────────────

class InterventionSerializer(serializers.ModelSerializer):
    bien_nom = serializers.CharField(source='bien.nom', read_only=True)
    signale_par_nom = serializers.SerializerMethodField()
    priorite_display = serializers.CharField(source='get_priorite_display', read_only=True)
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)

    class Meta:
        model = Intervention
        exclude = ['signale_par']
        read_only_fields = ['created_at']

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
        read_only_fields = ['created_at', 'montant_total']

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


# ── Public ───────────────────────────────────────────────────────────────────

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


class DocumentSerializer(serializers.ModelSerializer):
    """Le fichier est en écriture seule : il se télécharge via /documents/{id}/telecharger/ (authentifié)."""
    type_display = serializers.CharField(source='get_type_document_display', read_only=True)
    nom_fichier = serializers.SerializerMethodField()
    taille = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ['id', 'type_document', 'type_display', 'titre', 'fichier', 'locataire', 'bien',
                  'date_expiration', 'created_at', 'nom_fichier', 'taille']
        read_only_fields = ['created_at']
        extra_kwargs = {'fichier': {'write_only': True}}

    def get_nom_fichier(self, obj) -> str:
        return obj.fichier.name.rsplit('/', 1)[-1]

    def get_taille(self, obj) -> int:
        try:
            return obj.fichier.size
        except (OSError, ValueError):
            return 0

    def validate_locataire(self, locataire):
        if locataire is not None:
            _verifier_perimetre(self.context['request'], locataire.proprietaire_id)
        return locataire

    def validate_bien(self, bien):
        if bien is not None:
            _verifier_perimetre(self.context['request'], bien.proprietaire_id)
        return bien

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if not attrs.get('locataire') and not attrs.get('bien'):
            raise serializers.ValidationError('Rattachez le document à un locataire ou à un bien.')
        return attrs


# ── Public ───────────────────────────────────────────────────────────────────

class PublicBienSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source='get_type_bien_display', read_only=True)

    class Meta:
        model = Bien
        fields = ['id', 'nom', 'type_bien', 'type_display', 'adresse', 'ville', 'surface', 'nb_pieces',
                  'etage', 'loyer_charges', 'prix_nuit', 'description', 'photo']


class PublicReservationCreateSerializer(serializers.ModelSerializer):
    website = serializers.CharField(required=False, allow_blank=True, write_only=True)  # honeypot anti-spam

    class Meta:
        model = Reservation
        fields = ['bien', 'nom', 'telephone', 'email', 'date_arrivee', 'date_depart', 'nb_personnes',
                  'mode_paiement', 'message', 'website']

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

    def validate_website(self, value):
        if value:
            raise serializers.ValidationError('Spam détecté.')
        return value
