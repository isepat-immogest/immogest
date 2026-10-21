from django.shortcuts import render, get_object_or_404, redirect # type: ignore
from django.contrib import messages # type: ignore
from django.core.exceptions import ValidationError # type: ignore
from django.db.models import Q # type: ignore
from django.urls import reverse # type: ignore
from gestion.models import Bien, Reservation, DemandeContact
from gestion.forms import ContactPublicForm, ReservationPublicForm
from gestion.emails import envoyer_accuse_demande, envoyer_accuse_reservation
from gestion import services


def index(request):
    """Page d'accueil du site public."""
    biens_disponibles = Bien.objects.filter(statut='libre').order_by('-created_at')
    featured = biens_disponibles[:6]
    nb_biens_disponibles = biens_disponibles.count()
    villes = (Bien.objects.filter(statut='libre')
              .exclude(ville='').values_list('ville', flat=True).distinct().order_by('ville')[:12])
    return render(request, 'site_public/index.html', {
        'featured': featured,
        'nb_biens_disponibles': nb_biens_disponibles,
        'villes': villes,
    })


def biens_public_list(request):
    """Catalogue public des biens disponibles à la location."""
    qs = Bien.objects.filter(statut='libre')
    q = request.GET.get('q', '')
    ville = request.GET.get('ville', '')
    type_bien = request.GET.get('type', '')
    prix_max = request.GET.get('prix_max', '')

    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(adresse__icontains=q) | Q(ville__icontains=q))
    if ville:
        qs = qs.filter(ville__iexact=ville)
    if type_bien:
        qs = qs.filter(type_bien=type_bien)
    if prix_max:
        try:
            qs = qs.filter(loyer_charges__lte=float(prix_max))
        except ValueError:
            pass

    villes = (Bien.objects.filter(statut='libre')
              .exclude(ville='').values_list('ville', flat=True).distinct().order_by('ville'))

    return render(request, 'site_public/biens_list.html', {
        'biens': qs.order_by('-created_at'),
        'villes': villes,
        'q': q, 'ville': ville, 'type_bien': type_bien, 'prix_max': prix_max,
        'type_choices': Bien.TYPE_CHOICES,
    })


def bien_public_detail(request, pk):
    """Fiche détaillée publique d'un bien, avec formulaire de contact."""
    bien = get_object_or_404(Bien, pk=pk, statut='libre')
    autres_biens = Bien.objects.filter(statut='libre', ville=bien.ville).exclude(pk=pk)[:3]

    if request.method == 'POST':
        form = ContactPublicForm(request.POST, initial={'bien': bien.pk})
        if form.is_valid():
            demande = form.save(commit=False)
            demande.bien = bien
            demande.save()
            envoyer_accuse_demande(demande)
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
            messages.success(request, 'Votre message a bien été envoyé. Nous vous répondrons dans les meilleurs délais.')
            return redirect('contact')
    else:
        form = ContactPublicForm(initial={'bien': None})
    return render(request, 'site_public/contact.html', {'form': form})


# ── RÉSERVATION / COMMANDE DE CHAMBRE ────────────────────────────────────────

def reservation_rooms_list(request):
    """Page 'Réserver' : liste des chambres/biens disponibles à commander."""
    qs = Bien.objects.filter(statut='libre')
    q = request.GET.get('q', '')
    ville = request.GET.get('ville', '')
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(ville__icontains=q))
    if ville:
        qs = qs.filter(ville__iexact=ville)
    villes = (Bien.objects.filter(statut='libre')
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
    bien = get_object_or_404(Bien, pk=pk, statut='libre')

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
