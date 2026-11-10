"""API de l'espace locataire : un locataire ne voit que ses propres données."""
from django.db.models import Sum  # type: ignore
from django.http import HttpResponse  # type: ignore
from drf_spectacular.utils import extend_schema  # type: ignore
from rest_framework import mixins, status, viewsets  # type: ignore
from rest_framework.decorators import action  # type: ignore
from rest_framework.response import Response  # type: ignore
from rest_framework.views import APIView  # type: ignore

from gestion import services
from gestion.models import Intervention, Paiement
from gestion.pdf_utils import generer_quittance_pdf

from . import serializers as sz
from .permissions import IsLocataire


class EspaceAccueilView(APIView):
    permission_classes = [IsLocataire]

    @extend_schema(responses={200: dict})
    def get(self, request):
        locataire = request.user.locataire_profile
        contrat = locataire.contrat_actif
        paiements = Paiement.objects.filter(contrat__locataire=locataire).select_related(
            'contrat__bien', 'contrat__locataire')
        a_payer = paiements.exclude(statut='paye')
        agrege = a_payer.aggregate(du=Sum('montant_du'), paye=Sum('montant_paye'))
        return Response({
            'locataire': sz.LocataireSerializer(locataire).data,
            'contrat': sz.ContratSerializer(contrat, context={'request': request}).data if contrat else None,
            'bien': sz.BienSerializer(contrat.bien).data if contrat else None,
            'montant_du': (agrege['du'] or 0) - (agrege['paye'] or 0),
            'paiements_recents': sz.PaiementSerializer(
                paiements.order_by('-mois')[:6], many=True, context={'request': request}).data,
            'interventions': sz.InterventionSerializer(
                services.interventions_du_locataire(locataire)[:5], many=True, context={'request': request}).data,
        })


class EspacePaiementViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsLocataire]
    serializer_class = sz.PaiementSerializer
    filterset_fields = ['statut']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Paiement.objects.none()
        return (Paiement.objects.filter(contrat__locataire=self.request.user.locataire_profile)
                .select_related('contrat__bien', 'contrat__locataire').order_by('-mois'))

    @extend_schema(responses={(200, 'application/pdf'): bytes})
    @action(detail=True, methods=['get'])
    def quittance(self, request, pk=None):
        paiement = self.get_object()
        rep = HttpResponse(generer_quittance_pdf(paiement), content_type='application/pdf')
        rep['Content-Disposition'] = f'attachment; filename="quittance_{paiement.mois:%Y_%m}.pdf"'
        return rep


class EspaceInterventionViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsLocataire]
    serializer_class = sz.InterventionSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Intervention.objects.none()
        return services.interventions_du_locataire(self.request.user.locataire_profile).select_related('bien')

    @extend_schema(request=sz.SignalementLocataireSerializer, responses={201: sz.InterventionSerializer})
    def create(self, request):
        locataire = request.user.locataire_profile
        contrat = locataire.contrat_actif
        if not contrat:
            return Response({'code': 'no_contract',
                             'message': 'Aucun contrat actif : impossible de signaler un problème.',
                             'details': {}}, status=status.HTTP_400_BAD_REQUEST)
        data = sz.SignalementLocataireSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        inter = Intervention.objects.create(bien=contrat.bien, signale_par=request.user, **data.validated_data)
        services.notifier_gestionnaires(
            contrat.bien, f'Signalement : {inter.titre}',
            f'{locataire} ({locataire.telephone}) — {contrat.bien.nom} — priorité {inter.get_priorite_display().lower()}.'
            f'\n{inter.description[:200]}', lien='/interventions', evenement='signalement')
        return Response(sz.InterventionSerializer(inter, context={'request': request}).data,
                        status=status.HTTP_201_CREATED)
