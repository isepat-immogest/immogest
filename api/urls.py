from django.urls import include, path  # type: ignore
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView  # type: ignore
from rest_framework.routers import DefaultRouter  # type: ignore
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView  # type: ignore

from . import auth_views, espace_views, public_views, views

router = DefaultRouter()
router.register('biens', views.BienViewSet, basename='bien')
router.register('locataires', views.LocataireViewSet, basename='locataire')
router.register('contrats', views.ContratViewSet, basename='contrat')
router.register('paiements', views.PaiementViewSet, basename='paiement')
router.register('interventions', views.InterventionViewSet, basename='intervention')
router.register('reservations', views.ReservationViewSet, basename='reservation')
router.register('demandes', views.DemandeViewSet, basename='demande')
router.register('depenses', views.DepenseViewSet, basename='depense')
router.register('documents', views.DocumentViewSet, basename='document')
router.register('notifications', views.NotificationViewSet, basename='notification')

espace = DefaultRouter()
espace.register('paiements', espace_views.EspacePaiementViewSet, basename='espace-paiement')
espace.register('interventions', espace_views.EspaceInterventionViewSet, basename='espace-intervention')

urlpatterns = [
    # Authentification
    path('auth/csrf/', auth_views.CsrfView.as_view()),
    path('auth/login/', auth_views.LoginView.as_view()),
    path('auth/logout/', auth_views.LogoutView.as_view()),
    path('auth/password/reset/', auth_views.PasswordResetRequestView.as_view()),
    path('auth/password/confirm/', auth_views.PasswordConfirmView.as_view()),
    path('auth/password/change/', auth_views.PasswordChangeView.as_view()),
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', auth_views.MeView.as_view()),

    # Gestion
    path('dashboard/', views.DashboardView.as_view()),
    path('recherche/', views.SearchView.as_view()),
    path('calendrier/', views.CalendrierView.as_view()),
    path('rapports/financier/', views.RapportFinancierView.as_view()),
    path('', include(router.urls)),

    # Espace locataire
    path('espace/', espace_views.EspaceAccueilView.as_view()),
    path('espace/', include(espace.urls)),

    # Public
    path('public/biens/', public_views.PublicBienList.as_view()),
    path('public/biens/<int:pk>/', public_views.PublicBienDetail.as_view()),
    path('public/biens/<int:pk>/disponibilites/', public_views.PublicDisponibilites.as_view()),
    path('public/reservations/', public_views.PublicReservationCreate.as_view()),
    path('public/reservations/<uuid:token>/', public_views.PublicReservationDetail.as_view()),
    path('public/contact/', public_views.PublicContact.as_view()),
]

docs_urlpatterns = [
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='docs'),
]
