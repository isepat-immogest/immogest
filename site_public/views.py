from django.shortcuts import render, get_object_or_404, redirect # type: ignore
from django.contrib import messages # type: ignore
from django.core.exceptions import ValidationError # type: ignore
from decimal import Decimal, InvalidOperation
from django.db.models import Case, Count, DecimalField, F, Q, When # type: ignore
from django.urls import reverse # type: ignore
from gestion.models import Bien, Reservation, DemandeContact
from gestion.forms import ContactPublicForm, ReservationPublicForm
from gestion.emails import envoyer_accuse_demande, envoyer_accuse_reservation
from gestion import services


def index(request):
    """Page d'accueil du site public."""
    biens_disponibles = Bien.objects.filter(statut='libre', offre='location').order_by('-created_at')
    featured = biens_disponibles[:6]
    nb_biens_disponibles = biens_disponibles.count()
    villes = (Bien.objects.filter(statut='libre', offre='location')
              .exclude(ville='').values_list('ville', flat=True).distinct().order_by('ville')[:12])
    return render(request, 'site_public/index.html', {
        'featured': featured,
        'nb_biens_disponibles': nb_biens_disponibles,
        'villes': villes,
    })


TRIS_ANNONCES = {
    'recent': ('-created_at', 'Plus récentes'),
    'prix_asc': ('prix_tri', 'Prix croissant'),
    'prix_desc': ('-prix_tri', 'Prix décroissant'),
    'surface_desc': ('-surface', 'Surface décroissante'),
}


def biens_public_list(request):
    """Annonces publiques façon portail immobilier : location et vente, filtres et tris."""
    base = Bien.annonces_publiques()
    qs = base.annotate(prix_tri=_prix_expr())
    offre = request.GET.get('offre', '')
    q = request.GET.get('q', '').strip()
    ville = request.GET.get('ville', '')
    type_bien = request.GET.get('type', '')
    prix_max = request.GET.get('prix_max', '')
    tri = request.GET.get('tri', 'recent')
    if tri not in TRIS_ANNONCES:
        tri = 'recent'

    if offre in ('location', 'vente'):
        qs = qs.filter(offre=offre)
    else:
        offre = ''
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(adresse__icontains=q) | Q(ville__icontains=q)
                       | Q(description__icontains=q))
    if ville:
        qs = qs.filter(ville__iexact=ville)
    if type_bien:
        qs = qs.filter(type_bien=type_bien)
    if prix_max:
        try:
            plafond = Decimal(prix_max)
        except InvalidOperation:
            plafond = None
        if plafond is not None:
            qs = qs.filter(prix_tri__lte=plafond)

    qs = qs.order_by(TRIS_ANNONCES[tri][0], '-created_at')

    villes = (base.exclude(ville='').values('ville').annotate(n=Count('id')).order_by('ville'))
    return render(request, 'site_public/annonces_list.html', {
        'biens': qs.prefetch_related('photos'),
        'villes': villes,
        'nb_total': base.count(),
        'nb_location': base.filter(offre='location').count(),
        'nb_vente': base.filter(offre='vente').count(),
        'offre': offre, 'q': q, 'ville': ville, 'type_bien': type_bien, 'prix_max': prix_max, 'tri': tri,
        'tris': [(cle, libelle) for cle, (_, libelle) in TRIS_ANNONCES.items()],
        'type_choices': Bien.TYPE_CHOICES,
    })


def _prix_expr():
    """Prix comparable : prix de vente pour une vente, loyer pour une location."""
    return Case(When(offre='vente', then=F('prix_vente')), default=F('loyer_charges'),
                output_field=DecimalField(max_digits=14, decimal_places=2))


def bien_public_detail(request, pk):
    """Fiche détaillée publique d'un bien, avec formulaire de contact."""
    bien = get_object_or_404(Bien.annonces_publiques().prefetch_related('equipements', 'photos'), pk=pk)
    autres_biens = (Bien.annonces_publiques().filter(ville=bien.ville, offre=bien.offre)
                    .exclude(pk=pk).prefetch_related('photos')[:3])

    if request.method == 'POST':
        form = ContactPublicForm(request.POST, initial={'bien': bien.pk})
        if form.is_valid():
            demande = form.save(commit=False)
            demande.bien = bien
            demande.save()
            envoyer_accuse_demande(demande)
            services.notifier_nouvelle_demande(demande)
            messages.success(request, 'Votre demande a bien été envoyée. Nous vous recontacterons rapidement.')
            return redirect('bien_public_detail', pk=pk)
    else:
        form = ContactPublicForm(initial={'bien': bien.pk})

    return render(request, 'site_public/bien_detail.html', {
        'bien': bien, 'form': form, 'autres_biens': autres_biens,
    })


def contact(request):
    """Page de contact générale (non liée à un bien précis)."""
    if request.method == 'POST':
        form = ContactPublicForm(request.POST)
        if form.is_valid():
            demande = form.save()
            envoyer_accuse_demande(demande)
            services.notifier_nouvelle_demande(demande)
            messages.success(request, 'Votre message a bien été envoyé. Nous vous répondrons dans les meilleurs délais.')
            return redirect('contact')
    else:
        form = ContactPublicForm(initial={'bien': None})
    return render(request, 'site_public/contact.html', {'form': form})


# ── RÉSERVATION / COMMANDE DE CHAMBRE ────────────────────────────────────────

def reservation_rooms_list(request):
    """Page 'Réserver' : liste des chambres/biens disponibles à commander."""
    qs = Bien.objects.filter(statut='libre', offre='location')
    q = request.GET.get('q', '')
    ville = request.GET.get('ville', '')
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(ville__icontains=q))
    if ville:
        qs = qs.filter(ville__iexact=ville)
    villes = (Bien.objects.filter(statut='libre', offre='location')
              .exclude(ville='').values_list('ville', flat=True).distinct().order_by('ville'))
    return render(request, 'site_public/reservation_rooms.html', {
        'biens': qs.order_by('-created_at'), 'villes': villes, 'q': q, 'ville': ville,
    })


def _creer_demande_depuis_reservation(reservation):
    """Crée dans « Demandes clients » un message signalant la nouvelle réservation."""
    depart = (f", départ le {reservation.date_depart:%d/%m/%Y}"
              if reservation.date_depart else "")
    message = (
        f"Nouvelle réservation {reservation.reference} : "
        f"arrivée le {reservation.date_arrivee:%d/%m/%Y}{depart}, "
        f"{reservation.nb_personnes} personne(s), "
        f"paiement par {reservation.get_mode_paiement_display()}."
    )
    if reservation.message:
        message += f" Message du client : {reservation.message}"
    DemandeContact.objects.create(
        bien=reservation.bien, nom=reservation.nom, email=reservation.email,
        telephone=reservation.telephone, message=message)


def reservation_create(request, pk):
    """Formulaire de commande/réservation pour une chambre précise (avec contrôle de disponibilité)."""
    bien = get_object_or_404(Bien, pk=pk, statut='libre', offre='location')

    if request.method == 'POST':
        form = ReservationPublicForm(request.POST, initial={'bien': bien.pk})
        if form.is_valid():
            donnees = {k: v for k, v in form.cleaned_data.items() if k != 'bien'}
            try:
                reservation = services.creer_reservation(bien, **donnees)
            except ValidationError as exc:
                for champ, erreurs in getattr(exc, 'message_dict', {'__all__': exc.messages}).items():
                    for erreur in erreurs:
                        form.add_error(champ if champ in form.fields else None, erreur)
            else:
                _creer_demande_depuis_reservation(reservation)
                envoyer_accuse_reservation(reservation, lien=request.build_absolute_uri(
                    reverse('reservation_confirmation', args=[reservation.token])))
                return redirect('reservation_confirmation', token=reservation.token)
    else:
        form = ReservationPublicForm(initial={'bien': bien.pk})

    return render(request, 'site_public/reservation_form.html', {
        'bien': bien, 'form': form, 'dates_occupees': services.dates_occupees(bien)})


def reservation_confirmation(request, token):
    """Page de confirmation : instructions de paiement Wave / Orange Money + WhatsApp."""
    reservation = get_object_or_404(Reservation, token=token)
    return render(request, 'site_public/reservation_confirmation.html', {'reservation': reservation})
