from django.contrib import admin
from django.urls import path, re_path, include
from django.conf import settings
from django.views.static import serve
from django.contrib.auth import views as auth_views
from api import spa
from api.urls import docs_urlpatterns

urlpatterns = [
    path('admin/', admin.site.urls),

    # Réinitialisation de mot de passe (comptes propriétaires ET locataires)
    path('gestion/mot-de-passe-oublie/', auth_views.PasswordResetView.as_view(
        template_name='gestion/password_reset.html'), name='password_reset'),
    path('gestion/mot-de-passe-oublie/envoye/', auth_views.PasswordResetDoneView.as_view(
        template_name='gestion/password_reset_done.html'), name='password_reset_done'),
    path('gestion/reinitialiser/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='gestion/password_reset_confirm.html'), name='password_reset_confirm'),
    path('gestion/reinitialiser/termine/', auth_views.PasswordResetCompleteView.as_view(
        template_name='gestion/password_reset_complete.html'), name='password_reset_complete'),

    path('api/v1/', include('api.urls')),
    path('api/', include(docs_urlpatterns)),
    path('api/health/', spa.health),

    # Application React (back-office + espace locataire)
    path('app/assets/<path:path>', spa.assets),
    path('app/', spa.index),
    path('app/<path:path>', spa.index),

    path('gestion/', include('gestion.urls')),
    path('', include('site_public.urls')),
]

# Photos téléversées : servies par Django tant qu'aucun stockage externe (S3) n'est utilisé.
# (static() ne fonctionne qu'avec DEBUG=True ; serve() fonctionne aussi en production.)
if settings.SERVE_MEDIA:
    urlpatterns += [
        re_path(r'^%s(?P<path>.*)$' % settings.MEDIA_URL.lstrip('/'), serve,
                {'document_root': settings.MEDIA_ROOT}),
    ]
