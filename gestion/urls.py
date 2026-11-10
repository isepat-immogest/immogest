from django.urls import path # type: ignore
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.dashboard, name='dashboard'),
    path('loyers/', views.etat_loyers, name='etat_loyers'),

    # Biens
    path('biens/', views.biens_list, name='biens_list'),
    path('biens/ajouter/', views.bien_create, name='bien_create'),
    path('biens/<int:pk>/', views.bien_detail, name='bien_detail'),
    path('biens/<int:pk>/modifier/', views.bien_edit, name='bien_edit'),
    path('biens/<int:pk>/photos/ajouter/', views.bien_photos_ajouter, name='bien_photos_ajouter'),
    path('biens/<int:pk>/photos/<int:photo_pk>/supprimer/', views.bien_photo_supprimer, name='bien_photo_supprimer'),
    path('biens/<int:pk>/photos/<int:photo_pk>/principale/', views.bien_photo_principale, name='bien_photo_principale'),
    path('biens/<int:pk>/supprimer/', views.bien_delete, name='bien_delete'),

    # Locataires
    path('locataires/', views.locataires_list, name='locataires_list'),
    path('locataires/ajouter/', views.locataire_create, name='locataire_create'),
    path('locataires/<int:pk>/', views.locataire_detail, name='locataire_detail'),
    path('locataires/<int:pk>/modifier/', views.locataire_edit, name='locataire_edit'),
    path('locataires/<int:pk>/supprimer/', views.locataire_delete, name='locataire_delete'),
    path('locataires/<int:pk>/acces/creer/', views.locataire_creer_acces, name='locataire_creer_acces'),
    path('locataires/<int:pk>/acces/revoquer/', views.locataire_revoquer_acces, name='locataire_revoquer_acces'),

    # Contrats
    path('contrats/', views.contrats_list, name='contrats_list'),
    path('contrats/ajouter/', views.contrat_create, name='contrat_create'),
    path('contrats/<int:pk>/modifier/', views.contrat_edit, name='contrat_edit'),

    # Paiements
    path('paiements/', views.paiements_list, name='paiements_list'),
    path('paiements/ajouter/', views.paiement_create, name='paiement_create'),
    path('paiements/<int:pk>/modifier/', views.paiement_edit, name='paiement_edit'),
    path('paiements/<int:pk>/quittance/', views.paiement_quittance_pdf, name='paiement_quittance_pdf'),
    path('rapport-financier/', views.rapport_financier, name='rapport_financier'),

    # Interventions
    path('interventions/', views.interventions_list, name='interventions_list'),
    path('interventions/ajouter/', views.intervention_create, name='intervention_create'),
    path('interventions/<int:pk>/modifier/', views.intervention_edit, name='intervention_edit'),

    # Demandes de contact (site public)
    path('demandes/', views.demandes_list, name='demandes_list'),
    path('demandes/<int:pk>/toggle/', views.demande_toggle_traite, name='demande_toggle_traite'),

    # Réservations (site public)
    path('reservations/', views.reservations_list, name='reservations_list'),
    path('reservations/ajouter/', views.reservation_create_manual, name='reservation_create_manual'),
    path('reservations/<int:pk>/statut/', views.reservation_update_statut, name='reservation_update_statut'),

    # Espace locataire
    path('mon-espace/', views.espace_locataire_dashboard, name='espace_locataire'),
    path('mon-espace/paiements/', views.espace_locataire_paiements, name='espace_locataire_paiements'),
    path('mon-espace/paiements/<int:pk>/quittance/', views.espace_locataire_quittance_pdf, name='espace_locataire_quittance_pdf'),
    path('mon-espace/interventions/', views.espace_locataire_interventions, name='espace_locataire_interventions'),
    path('mon-espace/interventions/signaler/', views.espace_locataire_intervention_create, name='espace_locataire_intervention_create'),
    path('mon-espace/mot-de-passe/', views.espace_locataire_mot_de_passe, name='espace_locataire_mot_de_passe'),
]
