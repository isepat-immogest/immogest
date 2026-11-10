"""API publique (site vitrine et applications mobiles) : sans authentification, limitée en débit."""
from django.core.exceptions import ValidationError as DjangoValidationError  # type: ignore
from django.shortcuts import get_object_or_404  # type: ignore
from django.urls import reverse  # type: ignore
from drf_spectacular.utils import extend_schema  # type: ignore
from rest_framework import generics, serializers, status  # type: ignore
from rest_framework.permissions import AllowAny  # type: ignore
from rest_framework.response import Response  # type: ignore
from rest_framework.throttling import ScopedRateThrottle  # type: ignore
from rest_framework.views import APIView  # type: ignore

from gestion import services
from gestion.emails import envoyer_accuse_demande, envoyer_accuse_reservation
from gestion.models import Bien, DemandeContact, Reservation

from . import serializers as sz


class PublicMixin:
    permission_classes = [AllowAny]
    authentication_classes = []


class PublicBienList(PublicMixin, generics.ListAPIView):
    serializer_class = sz.PublicBienSerializer
    search_fields = ['nom', 'adresse', 'ville']
    ordering_fields = ['loyer_charges', 'created_at', 'surface']
    filterset_fields = ['type_bien', 'nb_pieces', 'meuble']

    def get_queryset(self):
        qs = Bien.objects.filter(statut='libre', offre='location').prefetch_related('equipements').order_by('-created_at')
        p = self.request.query_params
        for eq in p.getlist('equipements'):           # ?equipements=3&equipements=7 : il faut TOUS les équipements
            if eq.isdigit():
                qs = qs.filter(equipements=int(eq))
        if p.get('ville'):
            qs = qs.filter(ville__iexact=p['ville'])
        try:
            if p.get('prix_max'):
                qs = qs.filter(loyer_charges__lte=float(p['prix_max']))
            if p.get('prix_min'):
                qs = qs.filter(loyer_charges__gte=float(p['prix_min']))
        except ValueError:
            pass
        return qs


class PublicBienDetail(PublicMixin, generics.RetrieveAPIView):
    serializer_class = sz.PublicBienSerializer
    queryset = Bien.objects.filter(statut='libre', offre='location').prefetch_related('equipements')


class PublicDisponibilites(PublicMixin, APIView):
    @extend_schema(responses={200: dict})
    def get(self, request, pk):
        bien = get_object_or_404(Bien, pk=pk, statut='libre', offre='location')
        return Response({'occupees': services.dates_occupees(bien)})


class PublicReservationCreate(PublicMixin, APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'public_write'

    @extend_schema(request=sz.PublicReservationCreateSerializer, responses={201: sz.PublicReservationSerializer})
    def post(self, request):
        data = sz.PublicReservationCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        donnees = dict(data.validated_data)
        donnees.pop('website', None)
        bien = donnees.pop('bien')
        try:
            reservation = services.creer_reservation(bien, **donnees)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, 'error_dict') else exc.messages)
        DemandeContact.objects.create(
            bien=bien, nom=reservation.nom, email=reservation.email, telephone=reservation.telephone,
            message=f'Nouvelle réservation {reservation.reference} ({reservation.get_mode_paiement_display()}).')
        envoyer_accuse_reservation(reservation, lien=request.build_absolute_uri(
            reverse('reservation_confirmation', args=[reservation.token])))
        return Response(sz.PublicReservationSerializer(reservation).data, status=status.HTTP_201_CREATED)


class PublicReservationDetail(PublicMixin, generics.RetrieveAPIView):
    """Suivi d'une réservation par jeton secret (non devinable, contrairement à un identifiant séquentiel)."""
    serializer_class = sz.PublicReservationSerializer
    queryset = Reservation.objects.select_related('bien')
    lookup_field = 'token'


class PublicContact(PublicMixin, APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'public_write'

    @extend_schema(request=sz.PublicContactSerializer, responses={201: dict})
    def post(self, request):
        data = sz.PublicContactSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        valides = dict(data.validated_data)
        valides.pop('website', None)
        demande = DemandeContact.objects.create(**valides)
        envoyer_accuse_demande(demande)
        services.notifier_nouvelle_demande(demande)
        return Response({'detail': 'Message envoyé. Nous vous répondrons rapidement.'},
                        status=status.HTTP_201_CREATED)
