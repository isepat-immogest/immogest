from datetime import date
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Contrat, Paiement
from django import forms # type: ignore
from django.shortcuts import render, get_object_or_404, redirect # type: ignore
from django.contrib.auth.decorators import login_required # type: ignore
from django.contrib.auth import login, logout # type: ignore
from django.contrib.auth.forms import AuthenticationForm # type: ignore
from django.contrib.auth.models import User # type: ignore
from django.core.mail import send_mail # type: ignore
from django.utils.crypto import get_random_string # type: ignore
from functools import wraps # type: ignore
from django.contrib import messages # type: ignore
from django.db.models import Sum, Q, Case, When, IntegerField # type: ignore
from django.http import HttpResponse # type: ignore
from django.views.decorators.http import require_POST # type: ignore
import csv
import json
from datetime import date, timedelta
from .models import Bien, BienPhoto, Locataire, Contrat, Paiement, Intervention, DemandeContact, Reservation
from .forms import (BienForm, LocataireForm, ContratForm,
                    PaiementForm, InterventionForm, ReservationForm)
from .pdf_utils import generer_quittance_pdf, generer_rapport_financier_pdf
from .utils import mois_annee_fr_abrege
from .scope import proprietaires_visibles
from .services import interventions_du_locataire


def _mois_moins(d, n):
    """Renvoie le 1er jour du mois n mois avant la date d (calcul sans dépendance externe)."""
    mois_total = (d.year * 12 + (d.month - 1)) - n
    annee, mois = divmod(mois_total, 12)
    return date(annee, mois + 1, 1)


def locataire_required(view_func):
    """Autorise uniquement les comptes liés à un profil Locataire."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not hasattr(request.user, 'locataire_profile'):
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def login_view(request):
    if request.user.is_authenticated:
        if hasattr(request.user, 'locataire_profile'):
            return redirect('espace_locataire')
        return redirect('dashboard')
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        login(request, user)
        if hasattr(user, 'locataire_profile'):
            return redirect('espace_locataire')
        return redirect('dashboard')
    return render(request, 'gestion/login.html', {'form': form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def dashboard(request):
    u = request.user
    biens = Bien.objects.filter(proprietaire__in=proprietaires_visibles(u))
    total_biens = biens.count()
    biens_loues = biens.filter(statut='loue').count()
    biens_libres = biens.filter(statut='libre').count()
    biens_travaux = biens.filter(statut='travaux').count()

    # Revenus du mois courant
    aujourd_hui = date.today()
    debut_mois = aujourd_hui.replace(day=1)
    revenus_mois = Paiement.objects.filter(
        contrat__bien__proprietaire__in=proprietaires_visibles(u),
        mois=debut_mois,
        statut='paye'
    ).aggregate(total=Sum('montant_paye'))['total'] or 0

    # Loyers en retard
    loyers_retard = Paiement.objects.filter(
        contrat__bien__proprietaire__in=proprietaires_visibles(u),
        statut__in=['retard', 'en_attente'],
        mois__lt=debut_mois
    )
    montant_retard = loyers_retard.aggregate(
        total=Sum('montant_du'))['total'] or 0
    nb_retard = loyers_retard.count()

    # Taux occupation
    taux = round((biens_loues / total_biens * 100) if total_biens else 0)

    # Derniers biens
    derniers_biens = biens.order_by('-created_at')[:6]

    # Événements à venir (contrats se terminant dans 90 jours)
    dans_90j = aujourd_hui + timedelta(days=90)
    contrats_fin = Contrat.objects.filter(
        bien__proprietaire__in=proprietaires_visibles(u),
        statut='actif',
        date_fin__gte=aujourd_hui,
        date_fin__lte=dans_90j
    ).order_by('date_fin')[:5]

    # Interventions ouvertes
    interventions = Intervention.objects.filter(
        bien__proprietaire__in=proprietaires_visibles(u),
        statut__in=['ouverte', 'en_cours']
    ).annotate(poids=Case(
        When(priorite='urgente', then=4), When(priorite='haute', then=3),
        When(priorite='normale', then=2), default=1, output_field=IntegerField(),
    )).order_by('-poids', '-date_signalement')[:5]

    # Derniers paiements
    paiements_recents = Paiement.objects.filter(
        contrat__bien__proprietaire__in=proprietaires_visibles(u)
    ).order_by('-created_at')[:6]

    # Demandes de contact reçues via le site public
    demandes = DemandeContact.objects.filter(
        Q(bien__proprietaire__in=proprietaires_visibles(u)) | Q(bien__isnull=True)
    ).order_by('-created_at')
    nb_demandes_non_traitees = demandes.filter(traite=False).count()
    demandes_recentes = demandes[:5]

    # Réservations en attente de traitement
    reservations = Reservation.objects.filter(bien__proprietaire__in=proprietaires_visibles(u)).order_by('-created_at')
    nb_reservations_en_attente = reservations.filter(statut__in=['en_attente', 'payee']).count()
    reservations_recentes = reservations[:5]

    # Évolution des revenus sur les 6 derniers mois (pour le graphique)
    mois_debut_graph = _mois_moins(debut_mois, 5)
    revenus_par_mois = Paiement.objects.filter(
        contrat__bien__proprietaire__in=proprietaires_visibles(u),
        statut='paye',
        mois__gte=mois_debut_graph,
        mois__lte=debut_mois,
    ).values('mois').annotate(total=Sum('montant_paye')).order_by('mois')
    revenus_map = {r['mois']: float(r['total']) for r in revenus_par_mois}
    graph_labels = []
    graph_data = []
    for i in range(5, -1, -1):
        m = _mois_moins(debut_mois, i)
        graph_labels.append(mois_annee_fr_abrege(m))
        graph_data.append(revenus_map.get(m, 0))

    ctx = {
        'total_biens': total_biens,
        'biens_loues': biens_loues,
        'biens_libres': biens_libres,
        'biens_travaux': biens_travaux,
        'revenus_mois': revenus_mois,
        'nb_retard': nb_retard,
        'montant_retard': montant_retard,
        'taux': taux,
        'derniers_biens': derniers_biens,
        'contrats_fin': contrats_fin,
        'interventions': interventions,
        'paiements_recents': paiements_recents,
        'nb_demandes_non_traitees': nb_demandes_non_traitees,
        'demandes_recentes': demandes_recentes,
        'nb_reservations_en_attente': nb_reservations_en_attente,
        'reservations_recentes': reservations_recentes,
        'graph_labels': json.dumps(graph_labels),
        'graph_data': json.dumps(graph_data),
    }
    return render(request, 'gestion/dashboard.html', ctx)


# ── BIENS ──────────────────────────────────────────────────────────────────

@login_required
def biens_list(request):
    qs = Bien.objects.filter(proprietaire__in=proprietaires_visibles(request.user)).prefetch_related('contrats__locataire')
    statut = request.GET.get('statut', '')
    q = request.GET.get('q', '')
    if statut:
        qs = qs.filter(statut=statut)
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(adresse__icontains=q) | Q(ville__icontains=q))
    return render(request, 'gestion/biens_list.html', {'biens': qs, 'statut': statut, 'q': q})


@login_required
def bien_detail(request, pk):
    bien = get_object_or_404(Bien, pk=pk, proprietaire__in=proprietaires_visibles(request.user))
    contrats = bien.contrats.all()
    interventions = bien.interventions.all()
    paiements = Paiement.objects.filter(contrat__bien=bien).order_by('-mois')[:12]
    return render(request, 'gestion/bien_detail.html', {
        'bien': bien, 'contrats': contrats,
        'interventions': interventions, 'paiements': paiements
    })


PHOTOS_MAX_PAR_BIEN = 30
PHOTO_TAILLE_MAX = 8 * 1024 * 1024  # 8 Mo


@login_required
@require_POST
def bien_photos_ajouter(request, pk):
    """Ajoute une ou plusieurs photos à la galerie d'un bien."""
    bien = get_object_or_404(Bien, pk=pk, proprietaire__in=proprietaires_visibles(request.user))
    fichiers = request.FILES.getlist('photos')
    if not fichiers:
        messages.error(request, 'Choisissez au moins une photo.')
        return redirect('bien_detail', pk=pk)
    place = PHOTOS_MAX_PAR_BIEN - bien.photos.count()
    if place <= 0:
        messages.error(request, f'Limite atteinte : {PHOTOS_MAX_PAR_BIEN} photos par bien.')
        return redirect('bien_detail', pk=pk)
    legende = request.POST.get('legende', '').strip()[:120]
    ordre = bien.photos.order_by('-ordre').values_list('ordre', flat=True).first() or 0
    ajoutees, refusees = 0, []
    for fichier in fichiers[:place]:
        if fichier.size > PHOTO_TAILLE_MAX:
            refusees.append(f'{fichier.name} (plus de 8 Mo)')
            continue
        try:
            forms.ImageField().clean(fichier)  # vérifie que c'est une vraie image
        except forms.ValidationError:
            refusees.append(f'{fichier.name} (image invalide)')
            continue
        ordre += 1
        BienPhoto.objects.create(bien=bien, image=fichier, ordre=ordre,
                                 legende=legende if len(fichiers) == 1 else '')
        ajoutees += 1
    if ajoutees:
        messages.success(request, f'{ajoutees} photo{"s" if ajoutees > 1 else ""} ajoutée{"s" if ajoutees > 1 else ""}.')
    if refusees:
        messages.error(request, 'Non ajoutées : ' + ', '.join(refusees) + '.')
    if len(fichiers) > place:
        messages.warning(request, f'Seules {place} photo(s) pouvaient encore être ajoutées (limite de {PHOTOS_MAX_PAR_BIEN}).')
    return redirect('bien_detail', pk=pk)


@login_required
@require_POST
def bien_photo_supprimer(request, pk, photo_pk):
    bien = get_object_or_404(Bien, pk=pk, proprietaire__in=proprietaires_visibles(request.user))
    photo = get_object_or_404(BienPhoto, pk=photo_pk, bien=bien)
    photo.image.delete(save=False)
    photo.delete()
    messages.success(request, 'Photo supprimée.')
    return redirect('bien_detail', pk=pk)


@login_required
@require_POST
def bien_photo_principale(request, pk, photo_pk):
    """Place une photo de la galerie en tête (elle devient la photo affichée dans les listes)."""
    bien = get_object_or_404(Bien, pk=pk, proprietaire__in=proprietaires_visibles(request.user))
    photo = get_object_or_404(BienPhoto, pk=photo_pk, bien=bien)
    premier = bien.photos.exclude(pk=photo.pk).order_by('ordre').values_list('ordre', flat=True).first()
    photo.ordre = (premier - 1) if premier is not None else 0
    photo.save(update_fields=['ordre'])
    messages.success(request, 'Photo placée en premier.')
    return redirect('bien_detail', pk=pk)


@login_required
def bien_create(request):
    form = BienForm(request.POST or None, request.FILES or None, user=request.user)
    if form.is_valid():
        b = form.save(commit=False)
        b.proprietaire = request.user
        b.save()
        form.save_m2m()
        form.enregistrer_proprietaires(b)
        messages.success(request, 'Bien ajouté avec succès.')
        return redirect('bien_detail', pk=b.pk)
    return render(request, 'gestion/bien_form.html', {'form': form, 'title': 'Ajouter un bien'})


@login_required
def bien_edit(request, pk):
    bien = get_object_or_404(Bien, pk=pk, proprietaire__in=proprietaires_visibles(request.user))
    form = BienForm(request.POST or None, request.FILES or None, instance=bien, user=request.user)
    if form.is_valid():
        form.save()
        form.enregistrer_proprietaires(bien)
        messages.success(request, 'Bien modifié.')
        return redirect('bien_detail', pk=pk)
    return render(request, 'gestion/bien_form.html', {'form': form, 'title': 'Modifier le bien'})


@login_required
def bien_delete(request, pk):
    bien = get_object_or_404(Bien, pk=pk, proprietaire__in=proprietaires_visibles(request.user))
    if request.method == 'POST':
        bien.delete()
        messages.success(request, 'Bien supprimé.')
        return redirect('biens_list')
    return render(request, 'gestion/confirm_delete.html', {'objet': bien, 'nom': str(bien)})


# ── LOCATAIRES ─────────────────────────────────────────────────────────────

@login_required
def locataires_list(request):
    qs = Locataire.objects.filter(proprietaire__in=proprietaires_visibles(request.user))
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(email__icontains=q))
    return render(request, 'gestion/locataires_list.html', {'locataires': qs, 'q': q})


@login_required
def locataire_detail(request, pk):
    loc = get_object_or_404(Locataire, pk=pk, proprietaire__in=proprietaires_visibles(request.user))
    return render(request, 'gestion/locataire_detail.html', {'locataire': loc})


@login_required
def locataire_create(request):
    form = LocataireForm(request.POST or None)
    if form.is_valid():
        l = form.save(commit=False)
        l.proprietaire = request.user
        l.save()
        messages.success(request, 'Locataire ajouté.')
        return redirect('locataire_detail', pk=l.pk)
    return render(request, 'gestion/locataire_form.html', {'form': form, 'title': 'Ajouter un locataire'})


@login_required
def locataire_edit(request, pk):
    loc = get_object_or_404(Locataire, pk=pk, proprietaire__in=proprietaires_visibles(request.user))
    form = LocataireForm(request.POST or None, instance=loc)
    if form.is_valid():
        form.save()
        messages.success(request, 'Locataire modifié.')
        return redirect('locataire_detail', pk=pk)
    return render(request, 'gestion/locataire_form.html', {'form': form, 'title': 'Modifier le locataire'})


@login_required
def locataire_delete(request, pk):
    loc = get_object_or_404(Locataire, pk=pk, proprietaire__in=proprietaires_visibles(request.user))
    if request.method == 'POST':
        loc.delete()
        messages.success(request, 'Locataire supprimé.')
        return redirect('locataires_list')
    return render(request, 'gestion/confirm_delete.html', {'objet': loc, 'nom': str(loc)})


# ── CONTRATS ───────────────────────────────────────────────────────────────

@login_required
def contrats_list(request):
    qs = Contrat.objects.filter(bien__proprietaire__in=proprietaires_visibles(request.user))
    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)
    return render(request, 'gestion/contrats_list.html', {'contrats': qs, 'statut': statut})


@login_required
def contrat_create(request):
    form = ContratForm(request.user, request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Contrat créé.')
        return redirect('contrats_list')
    return render(request, 'gestion/contrat_form.html', {'form': form, 'title': 'Nouveau contrat'})


@login_required
def contrat_edit(request, pk):
    contrat = get_object_or_404(Contrat, pk=pk, bien__proprietaire__in=proprietaires_visibles(request.user))
    form = ContratForm(request.user, request.POST or None, instance=contrat)
    if form.is_valid():
        form.save()
        messages.success(request, 'Contrat modifié.')
        return redirect('contrats_list')
    return render(request, 'gestion/contrat_form.html', {'form': form, 'title': 'Modifier le contrat'})


# ── PAIEMENTS ──────────────────────────────────────────────────────────────

@login_required
def paiements_list(request):
    qs = Paiement.objects.filter(contrat__bien__proprietaire__in=proprietaires_visibles(request.user))
    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)
    total_paye = qs.filter(statut='paye').aggregate(t=Sum('montant_paye'))['t'] or 0
    total_du = qs.filter(statut__in=['retard', 'en_attente']).aggregate(t=Sum('montant_du'))['t'] or 0
    return render(request, 'gestion/paiements_list.html', {
        'paiements': qs, 'statut': statut,
        'total_paye': total_paye, 'total_du': total_du
    })


@login_required
def paiement_create(request):
    form = PaiementForm(request.user, request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Paiement enregistré.')
        return redirect('paiements_list')
    return render(request, 'gestion/paiement_form.html', {'form': form, 'title': 'Enregistrer un paiement'})


@login_required
def paiement_edit(request, pk):
    p = get_object_or_404(Paiement, pk=pk, contrat__bien__proprietaire__in=proprietaires_visibles(request.user))
    form = PaiementForm(request.user, request.POST or None, instance=p)
    if form.is_valid():
        form.save()
        messages.success(request, 'Paiement modifié.')
        return redirect('paiements_list')
    return render(request, 'gestion/paiement_form.html', {'form': form, 'title': 'Modifier le paiement'})


@login_required
def paiement_quittance_pdf(request, pk):
    """Génère et télécharge la quittance PDF d'un paiement (côté propriétaire)."""
    paiement = get_object_or_404(Paiement, pk=pk, contrat__bien__proprietaire__in=proprietaires_visibles(request.user))
    pdf_bytes = generer_quittance_pdf(paiement)
    filename = f"quittance_{paiement.contrat.locataire.nom}_{paiement.mois:%Y_%m}.pdf"
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def rapport_financier(request):
    """
    Export des paiements du propriétaire, filtrable par période (?debut=YYYY-MM-DD
    &fin=YYYY-MM-DD) et par format (?format=csv ou ?format=pdf, CSV par défaut).
    """
    qs = Paiement.objects.filter(contrat__bien__proprietaire__in=proprietaires_visibles(request.user))

    debut = request.GET.get('debut')
    fin = request.GET.get('fin')
    if debut:
        qs = qs.filter(mois__gte=debut)
    if fin:
        qs = qs.filter(mois__lte=fin)

    periode_label = "Toute la période"
    if debut or fin:
        periode_label = f"Du {debut or '…'} au {fin or '…'}"

    export_format = request.GET.get('format', 'csv')

    if export_format == 'pdf':
        pdf_bytes = generer_rapport_financier_pdf(request.user, qs, periode_label)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="rapport_financier.pdf"'
        return response

    # Export CSV par défaut
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="rapport_financier.csv"'
    response.write('\ufeff')  # BOM pour un affichage correct des accents dans Excel
    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Mois', 'Bien', 'Locataire', 'Loyer', 'Charges', 'Montant dû',
                      'Montant payé', 'Statut', 'Mode de paiement', 'Date de paiement'])
    for p in qs.select_related('contrat__bien', 'contrat__locataire').order_by('-mois'):
        writer.writerow([
            p.mois.strftime('%m/%Y'),
            p.contrat.bien.nom,
            f"{p.contrat.locataire.prenom} {p.contrat.locataire.nom}",
            p.contrat.loyer_mensuel,
            p.contrat.charges_mensuelles,
            p.montant_du,
            p.montant_paye,
            p.get_statut_display(),
            p.get_mode_paiement_display() if p.mode_paiement else '',
            p.date_paiement.strftime('%d/%m/%Y') if p.date_paiement else '',
        ])
    return response


# ── INTERVENTIONS ──────────────────────────────────────────────────────────

@login_required
def interventions_list(request):
    qs = Intervention.objects.filter(bien__proprietaire__in=proprietaires_visibles(request.user))
    statut = request.GET.get('statut', '')
    priorite = request.GET.get('priorite', '')
    if statut:
        qs = qs.filter(statut=statut)
    if priorite:
        qs = qs.filter(priorite=priorite)
    return render(request, 'gestion/interventions_list.html', {
        'interventions': qs, 'statut': statut, 'priorite': priorite
    })


@login_required
def intervention_create(request):
    form = InterventionForm(request.user, request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Intervention créée.')
        return redirect('interventions_list')
    return render(request, 'gestion/intervention_form.html', {'form': form, 'title': 'Nouvelle intervention'})


@login_required
def intervention_edit(request, pk):
    inv = get_object_or_404(Intervention, pk=pk, bien__proprietaire__in=proprietaires_visibles(request.user))
    form = InterventionForm(request.user, request.POST or None, instance=inv)
    if form.is_valid():
        form.save()
        messages.success(request, 'Intervention modifiée.')
        return redirect('interventions_list')
    return render(request, 'gestion/intervention_form.html', {'form': form, 'title': 'Modifier l\'intervention'})


# ── DEMANDES DE CONTACT (site public) ───────────────────────────────────────

@login_required
def demandes_list(request):
    qs = DemandeContact.objects.filter(
        Q(bien__proprietaire__in=proprietaires_visibles(request.user)) | Q(bien__isnull=True)
    )
    statut = request.GET.get('statut', '')
    if statut == 'traite':
        qs = qs.filter(traite=True)
    elif statut == 'non_traite':
        qs = qs.filter(traite=False)
    return render(request, 'gestion/demandes_list.html', {'demandes': qs, 'statut': statut})


@login_required
def demande_toggle_traite(request, pk):
    demande = get_object_or_404(
        DemandeContact.objects.filter(Q(bien__proprietaire__in=proprietaires_visibles(request.user)) | Q(bien__isnull=True)),
        pk=pk
    )
    demande.traite = not demande.traite
    demande.save()
    return redirect('demandes_list')


# ── RÉSERVATIONS (commandes de chambres, site public) ───────────────────────

@login_required
def reservations_list(request):
    qs = Reservation.objects.filter(bien__proprietaire__in=proprietaires_visibles(request.user))
    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)
    return render(request, 'gestion/reservations_list.html', {'reservations': qs, 'statut': statut})


@login_required
def reservation_create_manual(request):
    biens_qs = Bien.objects.filter(proprietaire__in=proprietaires_visibles(request.user))
    form = ReservationForm(request.POST or None)
    form.fields['bien'].widget = forms.Select()  # rendre visible (pas caché comme sur le site public)
    form.fields['bien'].queryset = biens_qs
    form.fields['bien'].empty_label = 'Sélectionner un bien'
    if request.method == 'POST' and form.is_valid():
        reservation = form.save(commit=False)
        reservation.statut = request.POST.get('statut', 'en_attente')
        reservation.save()
        messages.success(request, 'Réservation ajoutée avec succès.')
        return redirect('reservations_list')
    return render(request, 'gestion/reservation_form.html', {'form': form, 'statut_choices': Reservation.STATUT_CHOICES})


@login_required
def reservation_update_statut(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk, bien__proprietaire__in=proprietaires_visibles(request.user))
    if request.method == 'POST':
        nouveau_statut = request.POST.get('statut')
        if nouveau_statut in dict(Reservation.STATUT_CHOICES):
            reservation.statut = nouveau_statut
            reservation.save()
            messages.success(request, 'Statut de la réservation mis à jour.')
    return redirect('reservations_list')


# ── ACCÈS LOCATAIRE (côté propriétaire) ─────────────────────────────────────

@login_required
def locataire_creer_acces(request, pk):
    """Le propriétaire génère un compte de connexion pour un locataire."""
    locataire = get_object_or_404(Locataire, pk=pk, proprietaire__in=proprietaires_visibles(request.user))
    if request.method != 'POST':
        return redirect('locataire_detail', pk=pk)

    mot_de_passe = get_random_string(10)

    if locataire.compte:
        user = locataire.compte
        user.is_active = True
        user.set_password(mot_de_passe)
        user.save()
        messages.success(
            request,
            f"Mot de passe réinitialisé pour {locataire}. "
            f"Identifiant : {user.username} — Nouveau mot de passe : {mot_de_passe} "
            f"(communiquez-le au locataire, il ne sera plus affiché)."
        )
    else:
        base_username = f"{locataire.prenom}.{locataire.nom}".lower().replace(' ', '')
        username = base_username
        i = 1
        while User.objects.filter(username=username).exists():
            i += 1
            username = f"{base_username}{i}"
        user = User.objects.create_user(
            username=username,
            email=locataire.email or '',
            password=mot_de_passe,
            first_name=locataire.prenom,
            last_name=locataire.nom,
        )
        locataire.compte = user
        locataire.save()
        messages.success(
            request,
            f"Accès créé pour {locataire}. "
            f"Identifiant : {username} — Mot de passe : {mot_de_passe} "
            f"(communiquez-le au locataire, il ne sera plus affiché)."
        )

        if locataire.email:
            try:
                send_mail(
                    subject="Votre accès à l'espace locataire ImmoGest",
                    message=(
                        f"Bonjour {locataire.prenom},\n\n"
                        f"Un espace personnel a été créé pour vous permettre de suivre "
                        f"votre contrat et vos paiements.\n\n"
                        f"Identifiant : {username}\n"
                        f"Mot de passe temporaire : {mot_de_passe}\n\n"
                        f"Connectez-vous ici : {request.scheme}://{request.get_host()}/gestion/login/\n"
                        f"Pensez à changer ce mot de passe après votre première connexion."
                    ),
                    from_email=None,
                    recipient_list=[locataire.email],
                    fail_silently=True,
                )
            except Exception:
                pass

    return redirect('locataire_detail', pk=pk)


@login_required
def locataire_revoquer_acces(request, pk):
    """Désactive le compte de connexion du locataire (l'historique est conservé)."""
    locataire = get_object_or_404(Locataire, pk=pk, proprietaire__in=proprietaires_visibles(request.user))
    if request.method == 'POST' and locataire.compte:
        locataire.compte.is_active = False
        locataire.compte.save()
        messages.success(request, f"Accès de {locataire} désactivé.")
    return redirect('locataire_detail', pk=pk)


# ── ESPACE LOCATAIRE ─────────────────────────────────────────────────────────

@locataire_required
def espace_locataire_dashboard(request):
    locataire = request.user.locataire_profile
    contrat = locataire.contrat_actif
    paiements_recents = Paiement.objects.filter(contrat__locataire=locataire).order_by('-mois')[:6] \
        if contrat else Paiement.objects.none()
    interventions = interventions_du_locataire(locataire)[:5]

    montant_du = None
    if contrat:
        dernier = Paiement.objects.filter(contrat=contrat).order_by('-mois').first()
        if dernier and dernier.statut in ('en_attente', 'retard', 'partiel'):
            montant_du = dernier.montant_du - (dernier.montant_paye or 0)

    ctx = {
        'locataire': locataire,
        'contrat': contrat,
        'paiements_recents': paiements_recents,
        'interventions': interventions,
        'montant_du': montant_du,
    }
    return render(request, 'gestion/locataire_espace/dashboard.html', ctx)


@locataire_required
def espace_locataire_paiements(request):
    locataire = request.user.locataire_profile
    paiements = Paiement.objects.filter(contrat__locataire=locataire).order_by('-mois')
    return render(request, 'gestion/locataire_espace/paiements.html', {'locataire': locataire, 'paiements': paiements})


@locataire_required
def espace_locataire_quittance_pdf(request, pk):
    """Le locataire télécharge la quittance PDF d'un de ses propres paiements."""
    locataire = request.user.locataire_profile
    paiement = get_object_or_404(Paiement, pk=pk, contrat__locataire=locataire)
    pdf_bytes = generer_quittance_pdf(paiement)
    filename = f"quittance_{paiement.mois:%Y_%m}.pdf"
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@locataire_required
def espace_locataire_interventions(request):
    locataire = request.user.locataire_profile
    interventions = interventions_du_locataire(locataire)
    return render(request, 'gestion/locataire_espace/interventions.html', {'locataire': locataire, 'interventions': interventions})


@locataire_required
def espace_locataire_intervention_create(request):
    locataire = request.user.locataire_profile
    contrat = locataire.contrat_actif
    if not contrat:
        messages.error(request, "Aucun contrat actif : impossible de signaler un problème.")
        return redirect('espace_locataire')

    if request.method == 'POST':
        titre = request.POST.get('titre', '').strip()
        description = request.POST.get('description', '').strip()
        priorite = request.POST.get('priorite', 'normale')
        if titre and description:
            Intervention.objects.create(
                bien=contrat.bien,
                titre=titre,
                description=description,
                priorite=priorite if priorite in dict(Intervention.PRIORITE_CHOICES) else 'normale',
                signale_par=request.user,
            )
            messages.success(request, "Votre signalement a bien été transmis au propriétaire.")
            return redirect('espace_locataire_interventions')
        messages.error(request, "Merci de renseigner un titre et une description.")

    return render(request, 'gestion/locataire_espace/intervention_form.html', {
        'locataire': locataire,
        'priorite_choices': Intervention.PRIORITE_CHOICES,
    })


@locataire_required
def espace_locataire_mot_de_passe(request):
    from django.contrib.auth.forms import PasswordChangeForm
    from django.contrib.auth import update_session_auth_hash

    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Mot de passe mis à jour.')
            return redirect('espace_locataire')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'gestion/locataire_espace/mot_de_passe.html', {
        'locataire': request.user.locataire_profile, 'form': form,
    })


@login_required
def etat_loyers(request):
    mois = date.today().replace(day=1)

    contrats = (Contrat.objects
                .filter(statut='actif', bien__proprietaire__in=proprietaires_visibles(request.user))
                .select_related('bien', 'locataire'))

    paiements = {
        p.contrat_id: p
        for p in Paiement.objects.filter(contrat__in=contrats, mois=mois)
    }

    en_regle, en_retard = [], []
    for c in contrats:
        p = paiements.get(c.id)
        if p and p.montant_paye >= p.montant_du:
            en_regle.append((c, p))
        else:
            en_retard.append((c, p))

    return render(request, 'gestion/etat_loyers.html', {
        'mois': mois,
        'en_regle': en_regle,
        'en_retard': en_retard,
        'groupes': [('À régulariser', en_retard), ('En règle', en_regle)],
    })