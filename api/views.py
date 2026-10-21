"""Vues de l'API de gestion (réservées aux comptes de gestion)."""
import csv
from datetime import date, timedelta

from django.db.models import Case, Count, IntegerField, Prefetch, Q, Sum, When  # type: ignore
from django.http import FileResponse, HttpResponse  # type: ignore
from drf_spectacular.utils import extend_schema  # type: ignore
from rest_framework import mixins, status, viewsets  # type: ignore
from rest_framework.decorators import action  # type: ignore
from rest_framework.exceptions import ValidationError  # type: ignore
from rest_framework.response import Response  # type: ignore
from rest_framework.views import APIView  # type: ignore

from gestion import services
from gestion.models import (Bien, Contrat, DemandeContact, Depense, Document, Intervention, Locataire,
                            Notification, Paiement, Reservation)
from gestion.pdf_utils import generer_quittance_pdf, generer_rapport_financier_pdf
from gestion.scope import proprietaires_visibles
from gestion.utils import mois_annee_fr_abrege

from . import filters, serializers as sz
from .permissions import IsGestionnaire


class ScopedViewSet(viewsets.ModelViewSet):
    """ViewSet limité au périmètre de l'utilisateur (voir gestion/scope.py)."""
    permission_classes = [IsGestionnaire]
    scope_path = 'proprietaire'
    select = ()

    def get_queryset(self):
        qs = super().get_queryset().filter(**{f'{self.scope_path}__in': proprietaires_visibles(self.request.user)})
        return qs.select_related(*self.select) if self.select else qs


class BienViewSet(ScopedViewSet):
    queryset = Bien.objects.all()
    serializer_class = sz.BienSerializer
    filterset_class = filters.BienFilter
    search_fields = ['nom', 'adresse', 'ville']
    ordering_fields = ['nom', 'loyer_charges', 'created_at', 'surface']

    def get_queryset(self):
        return super().get_queryset().prefetch_related(Prefetch(
            'contrats', queryset=Contrat.objects.filter(statut='actif').select_related('locataire'),
            to_attr='_contrats_actifs'))

    def perform_create(self, serializer):
        serializer.save(proprietaire=self.request.user)

    @extend_schema(responses={200: dict})
    @action(detail=True, methods=['get'])
    def rentabilite(self, request, pk=None):
        """Revenus, dépenses et rendement net du bien sur 12 mois."""
        return Response(services.rentabilite_bien(self.get_object()))


class LocataireViewSet(ScopedViewSet):
    queryset = Locataire.objects.all()
    serializer_class = sz.LocataireSerializer
    search_fields = ['nom', 'prenom', 'email', 'telephone']
    ordering_fields = ['nom', 'created_at']
    select = ('compte',)

    def get_queryset(self):
        return super().get_queryset().prefetch_related(Prefetch(
            'contrats', queryset=Contrat.objects.filter(statut='actif').select_related('bien'),
            to_attr='_contrats_actifs'))

    def perform_create(self, serializer):
        serializer.save(proprietaire=self.request.user)

    @extend_schema(responses={200: dict})
    @action(detail=True, methods=['get'])
    def score(self, request, pk=None):
        """Score de fiabilité du locataire (ponctualité des paiements + taux d'effort)."""
        return Response(services.score_locataire(self.get_object()))

    @extend_schema(request=None, responses={200: dict})
    @action(detail=True, methods=['post'])
    def inviter(self, request, pk=None):
        """Crée/réactive l'accès du locataire et renvoie un lien d'activation à usage unique."""
        locataire = self.get_object()
        user, lien = services.inviter_locataire(locataire, request.build_absolute_uri('/').rstrip('/'))
        return Response({'identifiant': user.username, 'lien_activation': lien,
                         'email_envoye': bool(locataire.email)})

    @extend_schema(request=None, responses={200: dict})
    @action(detail=True, methods=['post'])
    def revoquer(self, request, pk=None):
        locataire = self.get_object()
        if locataire.compte:
            locataire.compte.is_active = False
            locataire.compte.save(update_fields=['is_active'])
        return Response({'detail': 'Accès désactivé.'})


class ContratViewSet(ScopedViewSet):
    queryset = Contrat.objects.all()
    serializer_class = sz.ContratSerializer
    filterset_class = filters.ContratFilter
    scope_path = 'bien__proprietaire'
    select = ('bien', 'locataire')
    search_fields = ['bien__nom', 'locataire__nom', 'locataire__prenom']
    ordering_fields = ['date_debut', 'date_fin', 'loyer_mensuel']

    @extend_schema(request=sz.ResiliationSerializer, responses=sz.ContratSerializer)
    @action(detail=True, methods=['post'])
    def resilier(self, request, pk=None):
        contrat = self.get_object()
        data = sz.ResiliationSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.resilier_contrat(contrat, data.validated_data.get('date_fin'), data.validated_data['statut'])
        return Response(self.get_serializer(contrat).data)


class PaiementViewSet(ScopedViewSet):
    queryset = Paiement.objects.all()
    serializer_class = sz.PaiementSerializer
    filterset_class = filters.PaiementFilter
    scope_path = 'contrat__bien__proprietaire'
    select = ('contrat__bien', 'contrat__locataire')
    search_fields = ['contrat__locataire__nom', 'contrat__locataire__prenom', 'contrat__bien__nom']
    ordering_fields = ['mois', 'montant_du', 'montant_paye', 'statut']

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        qs = self.filter_queryset(self.get_queryset())
        response.data['totaux'] = {
            'encaisse': qs.aggregate(t=Sum('montant_paye'))['t'] or 0,
            'reste_a_payer': (qs.aggregate(t=Sum('montant_du'))['t'] or 0) - (qs.aggregate(t=Sum('montant_paye'))['t'] or 0),
            'nb_retard': qs.filter(statut='retard').count(),
        }
        return response

    @extend_schema(request=sz.VersementSerializer, responses=sz.PaiementSerializer)
    @action(detail=True, methods=['post'])
    def versement(self, request, pk=None):
        """Enregistre un versement (total ou partiel) ; le statut est recalculé."""
        paiement = self.get_object()
        data = sz.VersementSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.enregistrer_versement(
            paiement, data.validated_data['montant'], data.validated_data.get('mode_paiement', ''),
            data.validated_data.get('date_versement'))
        return Response(self.get_serializer(paiement).data)

    @extend_schema(request=sz.GenererMoisSerializer, responses={200: dict})
    @action(detail=False, methods=['post'], url_path='generer-mois')
    def generer_mois(self, request):
        """Crée les loyers manquants du mois pour tous les contrats actifs."""
        data = sz.GenererMoisSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        mois = data.validated_data.get('mois') or date.today()
        crees = services.generer_loyers_du_mois(mois, proprietaires_visibles(request.user))
        return Response({'crees': crees, 'mois': services.premier_jour_du_mois(mois)})

    @extend_schema(responses={(200, 'application/pdf'): bytes})
    @action(detail=True, methods=['get'])
    def quittance(self, request, pk=None):
        paiement = self.get_object()
        reponse = HttpResponse(generer_quittance_pdf(paiement), content_type='application/pdf')
        reponse['Content-Disposition'] = (
            f'attachment; filename="quittance_{paiement.contrat.locataire.nom}_{paiement.mois:%Y_%m}.pdf"')
        return reponse


class InterventionViewSet(ScopedViewSet):
    queryset = Intervention.objects.all()
    serializer_class = sz.InterventionSerializer
    filterset_class = filters.InterventionFilter
    scope_path = 'bien__proprietaire'
    select = ('bien', 'signale_par')
    search_fields = ['titre', 'description', 'bien__nom', 'prestataire']
    ordering_fields = ['date_signalement', 'poids', 'cout']

    def get_queryset(self):
        return super().get_queryset().annotate(poids=Case(
            When(priorite='urgente', then=4), When(priorite='haute', then=3),
            When(priorite='normale', then=2), default=1, output_field=IntegerField()))

    def perform_create(self, serializer):
        serializer.save(signale_par=self.request.user)


class ReservationViewSet(ScopedViewSet):
    queryset = Reservation.objects.all()
    serializer_class = sz.ReservationSerializer
    filterset_class = filters.ReservationFilter
    scope_path = 'bien__proprietaire'
    select = ('bien',)
    search_fields = ['nom', 'telephone', 'email', 'bien__nom']
    ordering_fields = ['created_at', 'date_arrivee', 'montant_total']

    def perform_create(self, serializer):
        d = serializer.validated_data
        conflits = services.reservations_en_conflit(d['bien'], d['date_arrivee'], d.get('date_depart'))
        if conflits:
            raise ValidationError({'date_arrivee': 'Ces dates sont déjà réservées pour ce bien.'})
        serializer.save(montant_total=services.calculer_montant_reservation(
            d['bien'], d['date_arrivee'], d.get('date_depart')))

    @extend_schema(request=sz.StatutSerializer, responses=sz.ReservationSerializer)
    @action(detail=True, methods=['post'])
    def statut(self, request, pk=None):
        reservation = self.get_object()
        data = sz.StatutSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        reservation.statut = data.validated_data['statut']
        reservation.save(update_fields=['statut'])
        return Response(self.get_serializer(reservation).data)

    @extend_schema(request=None, responses=sz.ContratSerializer)
    @action(detail=True, methods=['post'], url_path='convertir-en-contrat')
    def convertir(self, request, pk=None):
        reservation = self.get_object()
        contrat = services.convertir_reservation_en_contrat(reservation, request.user)
        return Response(sz.ContratSerializer(contrat, context={'request': request}).data,
                        status=status.HTTP_201_CREATED)


class DemandeViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin,
                     viewsets.GenericViewSet):
    queryset = DemandeContact.objects.select_related('bien')
    serializer_class = sz.DemandeSerializer
    permission_classes = [IsGestionnaire]
    filterset_class = filters.DemandeFilter
    search_fields = ['nom', 'email', 'message']
    ordering_fields = ['created_at']

    def get_queryset(self):
        return super().get_queryset().filter(
            Q(bien__proprietaire__in=proprietaires_visibles(self.request.user)) | Q(bien__isnull=True))

    @extend_schema(request=None, responses=sz.DemandeSerializer)
    @action(detail=True, methods=['post'])
    def basculer(self, request, pk=None):
        demande = self.get_object()
        demande.traite = not demande.traite
        demande.save(update_fields=['traite'])
        return Response(self.get_serializer(demande).data)


class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = sz.NotificationSerializer
    filterset_fields = ['lue']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Notification.objects.none()
        return Notification.objects.filter(destinataire=self.request.user)

    @extend_schema(request=None, responses={200: dict})
    @action(detail=True, methods=['post'])
    def lue(self, request, pk=None):
        self.get_queryset().filter(pk=pk).update(lue=True)
        return Response({'detail': 'ok'})

    @extend_schema(request=None, responses={200: dict})
    @action(detail=False, methods=['post'], url_path='tout-lire')
    def tout_lire(self, request):
        self.get_queryset().filter(lue=False).update(lue=True)
        return Response({'detail': 'ok'})


# ── Tableau de bord, recherche, rapports ───────────────────────────────────────

def _mois_moins(d, n):
    total = (d.year * 12 + d.month - 1) - n
    annee, mois = divmod(total, 12)
    return date(annee, mois + 1, 1)


class DashboardView(APIView):
    permission_classes = [IsGestionnaire]

    @extend_schema(responses={200: dict})
    def get(self, request):
        prop = proprietaires_visibles(request.user)
        biens = Bien.objects.filter(proprietaire__in=prop)
        paiements = Paiement.objects.filter(contrat__bien__proprietaire__in=prop)
        aujourd_hui = date.today()
        debut_mois = aujourd_hui.replace(day=1)

        par_statut = dict(biens.values_list('statut').annotate(n=Count('id')))
        total = biens.count()
        loues = par_statut.get('loue', 0)

        du_mois = paiements.filter(mois=debut_mois)
        retards = paiements.filter(statut='retard')
        prevu = du_mois.aggregate(t=Sum('montant_du'))['t'] or 0
        encaisse = du_mois.aggregate(t=Sum('montant_paye'))['t'] or 0

        serie = []
        agreges = {r['mois']: r for r in paiements.filter(mois__gte=_mois_moins(debut_mois, 5), mois__lte=debut_mois)
                   .values('mois').annotate(prevu=Sum('montant_du'), encaisse=Sum('montant_paye'))}
        for i in range(5, -1, -1):
            m = _mois_moins(debut_mois, i)
            ligne = agreges.get(m, {})
            serie.append({'mois': mois_annee_fr_abrege(m), 'prevu': ligne.get('prevu') or 0,
                          'encaisse': ligne.get('encaisse') or 0})

        interventions = (Intervention.objects.filter(bien__proprietaire__in=prop, statut__in=['ouverte', 'en_cours'])
                         .select_related('bien').annotate(poids=Case(
                             When(priorite='urgente', then=4), When(priorite='haute', then=3),
                             When(priorite='normale', then=2), default=1, output_field=IntegerField()))
                         .order_by('-poids', '-date_signalement')[:5])
        contrats_fin = (Contrat.objects.filter(bien__proprietaire__in=prop, statut='actif',
                                               date_fin__gte=aujourd_hui, date_fin__lte=aujourd_hui + timedelta(days=90))
                        .select_related('bien', 'locataire').order_by('date_fin')[:5])
        demandes = DemandeContact.objects.filter(
            Q(bien__proprietaire__in=prop) | Q(bien__isnull=True), traite=False)
        reservations = Reservation.objects.filter(bien__proprietaire__in=prop, statut__in=['en_attente', 'payee'])

        return Response({
            'kpis': {
                'total_biens': total, 'biens_loues': loues, 'biens_libres': par_statut.get('libre', 0),
                'biens_travaux': par_statut.get('travaux', 0),
                'taux_occupation': round(loues / total * 100) if total else 0,
                'revenus_mois': encaisse, 'prevu_mois': prevu,
                'taux_recouvrement': round(encaisse / prevu * 100) if prevu else 0,
                'nb_retard': retards.count(),
                'montant_retard': (retards.aggregate(t=Sum('montant_du'))['t'] or 0)
                                  - (retards.aggregate(t=Sum('montant_paye'))['t'] or 0),
                'demandes_non_traitees': demandes.count(), 'reservations_a_traiter': reservations.count(),
            },
            'revenus': serie,
            'repartition_biens': [{'statut': k, 'nombre': v} for k, v in par_statut.items()],
            'interventions': [{'id': i.pk, 'titre': i.titre, 'bien': i.bien.nom, 'priorite': i.priorite,
                               'statut': i.statut} for i in interventions],
            'contrats_fin': [{'id': c.pk, 'bien': c.bien.nom, 'locataire': str(c.locataire),
                              'date_fin': c.date_fin} for c in contrats_fin],
            'paiements_recents': sz.PaiementSerializer(
                paiements.select_related('contrat__bien', 'contrat__locataire').order_by('-created_at')[:6],
                many=True, context={'request': request}).data,
        })


class SearchView(APIView):
    permission_classes = [IsGestionnaire]

    @extend_schema(responses={200: dict})
    def get(self, request):
        q = request.query_params.get('q', '').strip()
        if len(q) < 2:
            return Response({'resultats': []})
        prop = proprietaires_visibles(request.user)
        resultats = []
        for b in Bien.objects.filter(proprietaire__in=prop).filter(
                Q(nom__icontains=q) | Q(adresse__icontains=q) | Q(ville__icontains=q))[:5]:
            resultats.append({'type': 'bien', 'id': b.pk, 'titre': b.nom, 'detail': f'{b.ville} · {b.adresse}',
                              'url': f'/biens/{b.pk}'})
        for loc in Locataire.objects.filter(proprietaire__in=prop).filter(
                Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(telephone__icontains=q) | Q(email__icontains=q))[:5]:
            resultats.append({'type': 'locataire', 'id': loc.pk, 'titre': str(loc),
                              'detail': loc.telephone, 'url': f'/locataires/{loc.pk}'})
        for r in Reservation.objects.filter(bien__proprietaire__in=prop).filter(
                Q(nom__icontains=q) | Q(telephone__icontains=q))[:3]:
            resultats.append({'type': 'reservation', 'id': r.pk, 'titre': f'{r.reference} — {r.nom}',
                              'detail': r.bien.nom, 'url': '/reservations'})
        return Response({'resultats': resultats})


class RapportFinancierView(APIView):
    permission_classes = [IsGestionnaire]

    @extend_schema(responses={200: bytes})
    def get(self, request):
        qs = Paiement.objects.filter(contrat__bien__proprietaire__in=proprietaires_visibles(request.user))
        debut, fin = request.query_params.get('debut'), request.query_params.get('fin')
        if debut:
            qs = qs.filter(mois__gte=debut)
        if fin:
            qs = qs.filter(mois__lte=fin)
        label = f"Du {debut or '…'} au {fin or '…'}" if (debut or fin) else 'Toute la période'
        fmt = request.query_params.get('export', 'csv')
        qs = qs.select_related('contrat__bien', 'contrat__locataire').order_by('-mois')
        entetes = ['Mois', 'Bien', 'Locataire', 'Loyer', 'Charges', 'Montant dû', 'Montant payé', 'Statut',
                   'Mode de paiement', 'Date de paiement']

        def lignes():
            for p in qs:
                yield [p.mois.strftime('%m/%Y'), p.contrat.bien.nom, str(p.contrat.locataire),
                       p.contrat.loyer_mensuel, p.contrat.charges_mensuelles, p.montant_du, p.montant_paye,
                       p.get_statut_display(), p.get_mode_paiement_display() if p.mode_paiement else '',
                       p.date_paiement.strftime('%d/%m/%Y') if p.date_paiement else '']

        if fmt == 'pdf':
            rep = HttpResponse(generer_rapport_financier_pdf(request.user, qs, label), content_type='application/pdf')
            rep['Content-Disposition'] = 'attachment; filename="rapport_financier.pdf"'
            return rep
        if fmt == 'xlsx':
            from openpyxl import Workbook  # type: ignore
            wb = Workbook()
            ws = wb.active
            ws.title = 'Paiements'
            ws.append(entetes)
            for ligne in lignes():
                ws.append([float(v) if hasattr(v, 'quantize') else v for v in ligne])
            rep = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            rep['Content-Disposition'] = 'attachment; filename="rapport_financier.xlsx"'
            wb.save(rep)
            return rep
        rep = HttpResponse(content_type='text/csv; charset=utf-8')
        rep['Content-Disposition'] = 'attachment; filename="rapport_financier.csv"'
        rep.write('﻿')
        writer = csv.writer(rep, delimiter=';')
        writer.writerow(entetes)
        writer.writerows(lignes())
        return rep


class DepenseViewSet(ScopedViewSet):
    queryset = Depense.objects.all()
    serializer_class = sz.DepenseSerializer
    scope_path = 'bien__proprietaire'
    select = ('bien',)
    filterset_fields = ['bien', 'categorie']
    search_fields = ['libelle', 'bien__nom', 'notes']
    ordering_fields = ['date', 'montant']

    @extend_schema(responses={200: dict})
    @action(detail=False, methods=['get'])
    def resume(self, request):
        """Totaux des 12 derniers mois : revenus encaissés, dépenses par catégorie et résultat net."""
        prop = proprietaires_visibles(request.user)
        debut = services.il_y_a_12_mois()
        depenses = Depense.objects.filter(bien__proprietaire__in=prop, date__gte=debut)
        revenus = Paiement.objects.filter(contrat__bien__proprietaire__in=prop, mois__gte=debut)
        total_dep = depenses.aggregate(t=Sum('montant'))['t'] or 0
        total_rev = revenus.aggregate(t=Sum('montant_paye'))['t'] or 0
        return Response({
            'revenus_12m': total_rev, 'depenses_12m': total_dep, 'net_12m': total_rev - total_dep,
            'par_categorie': [{'categorie': c['categorie'], 'total': c['t']}
                              for c in depenses.values('categorie').annotate(t=Sum('montant')).order_by('-t')],
        })


class DocumentViewSet(ScopedViewSet):
    """Pièces jointes. Le fichier est servi par `telecharger` (authentifié), jamais par une URL publique."""
    queryset = Document.objects.all()
    serializer_class = sz.DocumentSerializer
    filterset_fields = ['locataire', 'bien', 'type_document']
    search_fields = ['titre']

    def get_queryset(self):
        prop = proprietaires_visibles(self.request.user)
        return Document.objects.filter(Q(bien__proprietaire__in=prop) | Q(locataire__proprietaire__in=prop))

    @extend_schema(responses={(200, 'application/octet-stream'): bytes})
    @action(detail=True, methods=['get'])
    def telecharger(self, request, pk=None):
        doc = self.get_object()
        return FileResponse(doc.fichier.open('rb'), as_attachment=True,
                            filename=doc.fichier.name.rsplit('/', 1)[-1])


class CalendrierView(APIView):
    permission_classes = [IsGestionnaire]

    @extend_schema(responses={200: dict})
    def get(self, request):
        try:
            debut = date.fromisoformat(request.query_params.get('debut', ''))
            fin = date.fromisoformat(request.query_params.get('fin', ''))
        except ValueError:
            raise ValidationError({'debut': 'Dates attendues au format AAAA-MM-JJ (debut et fin).'})
        if fin < debut or (fin - debut).days > 93:
            raise ValidationError({'fin': 'La période doit être positive et ne pas dépasser 3 mois.'})
        return Response({'evenements': services.evenements_calendrier(
            proprietaires_visibles(request.user), debut, fin)})
