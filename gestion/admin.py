from django.contrib import admin  # type: ignore
from django.utils.html import format_html

from .models import (
    Bien, BienPhoto, BienProprietaire, Contrat, DemandeContact, EnvoiNotification, Equipement, Intervention, Locataire,
    Paiement, ProfilGestionnaire, Proprietaire, Reservation,
)


@admin.register(Equipement)
class EquipementAdmin(admin.ModelAdmin):
    list_display = ['nom', 'categorie', 'icone']
    list_filter = ['categorie']
    search_fields = ['nom']


class BienProprietaireInline(admin.TabularInline):
    model = BienProprietaire
    extra = 1


class BienPhotoInline(admin.TabularInline):
    model = BienPhoto
    extra = 3
    fields = ['image', 'legende', 'ordre']


@admin.register(Bien)
class BienAdmin(admin.ModelAdmin):
    list_display = ['nom', 'offre', 'type_bien', 'statut', 'ville', 'loyer_charges', 'prix_vente', 'proprietaire']
    list_filter = ['offre', 'statut', 'type_bien', 'ville']
    search_fields = ['nom', 'adresse', 'ville']
    filter_horizontal = ['equipements']
    inlines = [BienPhotoInline, BienProprietaireInline]


@admin.register(Proprietaire)
class ProprietaireAdmin(admin.ModelAdmin):
    list_display = ['nom', 'prenom', 'telephone', 'email', 'commission_pct', 'actif', 'gestionnaire']
    list_filter = ['actif', 'type_proprietaire']
    search_fields = ['nom', 'prenom', 'email', 'telephone']


@admin.register(Locataire)
class LocataireAdmin(admin.ModelAdmin):
    list_display = ['nom', 'prenom', 'email', 'telephone', 'proprietaire']
    search_fields = ['nom', 'prenom', 'email']


@admin.register(Contrat)
class ContratAdmin(admin.ModelAdmin):
    list_display = ['bien', 'locataire', 'type_bail', 'statut', 'date_debut', 'loyer_mensuel']
    list_filter = ['statut', 'type_bail']


@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    list_display = ['contrat', 'mois', 'montant_du', 'montant_paye', 'statut']
    list_filter = ['statut', 'mois']


@admin.register(Intervention)
class InterventionAdmin(admin.ModelAdmin):
    list_display = ['titre', 'bien', 'priorite', 'statut', 'date_signalement', 'cout']
    list_filter = ['statut', 'priorite']


@admin.register(DemandeContact)
class DemandeContactAdmin(admin.ModelAdmin):
    list_display = ['nom', 'email', 'telephone', 'bien', 'traite', 'created_at']
    list_filter = ['traite', 'created_at']
    search_fields = ['nom', 'email', 'message']


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    # `voir_preuve` figurait dans une liste écrasée par la suivante : la colonne ne s'affichait jamais.
    list_display = ['reference', 'nom', 'telephone', 'bien', 'date_arrivee', 'mode_paiement', 'statut',
                    'voir_preuve', 'created_at']
    list_filter = ['statut', 'mode_paiement', 'created_at']
    search_fields = ['nom', 'telephone', 'email']
    readonly_fields = ['voir_preuve']

    @admin.display(description='Preuve de paiement')
    def voir_preuve(self, obj):
        if obj.preuve_paiement:
            return format_html('<a href="{}" target="_blank" rel="noopener">Voir la preuve</a>', obj.preuve_paiement.url)
        return 'Aucune preuve'


@admin.register(ProfilGestionnaire)
class ProfilGestionnaireAdmin(admin.ModelAdmin):
    list_display = ['user', 'numero_whatsapp', 'notif_email', 'notif_whatsapp']


@admin.register(EnvoiNotification)
class EnvoiNotificationAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'canal', 'adresse', 'sujet', 'statut', 'tentatives']
    list_filter = ['canal', 'statut']
    search_fields = ['adresse', 'sujet', 'erreur']
    readonly_fields = [f.name for f in EnvoiNotification._meta.fields]
