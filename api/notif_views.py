"""Préférences de notification du gestionnaire (email, WhatsApp, événements) et journal des envois."""
from django.db.models import Q  # type: ignore
from drf_spectacular.utils import extend_schema  # type: ignore
from rest_framework import generics  # type: ignore
from rest_framework.response import Response  # type: ignore
from rest_framework.views import APIView  # type: ignore

from gestion import notifications, whatsapp
from gestion.models import EnvoiNotification, ProfilGestionnaire

from . import serializers as sz
from .permissions import IsGestionnaire


def _etat(user):
    profil = getattr(user, 'profil_gestion', None)
    desactives = set(profil.evenements_desactives) if profil else set()
    return {
        'email': user.email,
        'numero_whatsapp': profil.numero_whatsapp if profil else '',
        'notif_email': profil.notif_email if profil else True,
        'notif_whatsapp': profil.notif_whatsapp if profil else True,
        'evenements_desactives': sorted(desactives),
        'evenements': [{'code': c, 'label': l, 'actif': c not in desactives}
                       for c, l in notifications.EVENEMENTS.items()],
        'whatsapp_disponible': whatsapp.whatsapp_configure(),
        'whatsapp_fournisseur': whatsapp.fournisseur(),
    }


class PreferencesNotificationView(APIView):
    permission_classes = [IsGestionnaire]

    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response(_etat(request.user))

    @extend_schema(request=sz.PreferencesNotificationSerializer, responses={200: dict})
    def patch(self, request):
        data = sz.PreferencesNotificationSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        if 'email' in v:
            request.user.email = v['email']
            request.user.save(update_fields=['email'])
        profil, _ = ProfilGestionnaire.objects.get_or_create(user=request.user)
        for champ in ('numero_whatsapp', 'notif_email', 'notif_whatsapp', 'evenements_desactives'):
            if champ in v:
                setattr(profil, champ, v[champ])
        profil.save()
        request.user.refresh_from_db()
        return Response(_etat(request.user))


class TestNotificationView(APIView):
    """Envoie un message de test sur les canaux actifs et dit précisément ce qui a marché ou non."""
    permission_classes = [IsGestionnaire]

    @extend_schema(request=None, responses={200: dict})
    def post(self, request):
        envois = notifications.envoyer_test(request.user)
        return Response({'resultats': [
            {'canal': e.canal, 'adresse': e.adresse, 'statut': e.statut, 'erreur': e.erreur} for e in envois]})


class EnvoisNotificationList(generics.ListAPIView):
    """Journal des derniers envois (email / WhatsApp) du gestionnaire connecté."""
    permission_classes = [IsGestionnaire]
    serializer_class = sz.EnvoiNotificationSerializer
    filterset_fields = ['canal', 'statut']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return EnvoiNotification.objects.none()
        u = self.request.user      # ses propres alertes + ce qui a été envoyé à ses propriétaires et locataires
        return EnvoiNotification.objects.filter(Q(destinataire=u) | Q(gestionnaire=u))
