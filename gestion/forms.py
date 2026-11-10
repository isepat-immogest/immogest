from django import forms # type: ignore
from .models import Bien, Locataire, Contrat, Paiement, Intervention, DemandeContact, Reservation
from .scope import proprietaires_visibles


class BienForm(forms.ModelForm):
    class Meta:
        model = Bien
        exclude = ['proprietaire', 'proprietaires', 'created_at']
        widgets = {
            'equipements': forms.CheckboxSelectMultiple(),
            'date_acquisition': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class LocataireForm(forms.ModelForm):
    class Meta:
        model = Locataire
        exclude = ['proprietaire', 'created_at']
        widgets = {
            'date_naissance': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }


class ContratForm(forms.ModelForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['bien'].queryset = Bien.objects.filter(proprietaire__in=proprietaires_visibles(user))
        self.fields['locataire'].queryset = Locataire.objects.filter(proprietaire__in=proprietaires_visibles(user))

    class Meta:
        model = Contrat
        exclude = ['created_at']
        widgets = {
            'date_debut': forms.DateInput(attrs={'type': 'date'}),
            'date_fin': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }


class PaiementForm(forms.ModelForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['contrat'].queryset = Contrat.objects.filter(
            bien__proprietaire__in=proprietaires_visibles(user), statut='actif')

    class Meta:
        model = Paiement
        exclude = ['created_at', 'statut']
        widgets = {
            'mois': forms.DateInput(attrs={'type': 'date'}),
            'date_paiement': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }


class InterventionForm(forms.ModelForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['bien'].queryset = Bien.objects.filter(proprietaire__in=proprietaires_visibles(user))

    class Meta:
        model = Intervention
        exclude = ['created_at']
        widgets = {
            'date_signalement': forms.DateInput(attrs={'type': 'date'}),
            'date_intervention': forms.DateInput(attrs={'type': 'date'}),
            'date_resolution': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }


class ContactPublicForm(forms.ModelForm):
    """Formulaire utilisé par les visiteurs du site public."""
    class Meta:
        model = DemandeContact
        fields = ['bien', 'nom', 'email', 'telephone', 'message']
        widgets = {
            'bien': forms.HiddenInput(),
            'nom': forms.TextInput(attrs={'placeholder': 'Votre nom'}),
            'email': forms.EmailInput(attrs={'placeholder': 'Votre email'}),
            'telephone': forms.TextInput(attrs={'placeholder': 'Votre téléphone (optionnel)'}),
            'message': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Votre message…'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Obligatoire : c'est à cette adresse que le client reçoit sa confirmation et notre réponse.
        self.fields['email'].required = True


class ReservationForm(forms.ModelForm):
    """Formulaire de commande/réservation d'une chambre, avec choix Wave / Orange Money / Free Money."""
    class Meta:
        model = Reservation
        fields = ['bien', 'nom', 'telephone', 'email', 'date_arrivee', 'date_depart',
                  'nb_personnes', 'mode_paiement', 'message']
        widgets = {
            'bien': forms.HiddenInput(),
            'nom': forms.TextInput(attrs={'placeholder': 'Votre nom complet'}),
            'telephone': forms.TextInput(attrs={'placeholder': 'Ex : 76 339 62 73'}),
            'email': forms.EmailInput(attrs={'placeholder': 'Votre email (optionnel)'}),
            'date_arrivee': forms.DateInput(attrs={'type': 'date'}),
            'date_depart': forms.DateInput(attrs={'type': 'date'}),
            'mode_paiement': forms.RadioSelect,
            'message': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Précisions sur votre séjour (optionnel)'}),
        }


class ReservationPublicForm(ReservationForm):
    """Formulaire de réservation du site public : l'email est OBLIGATOIRE, car c'est à cette
    adresse que le client reçoit sa confirmation. (ReservationForm garde l'email facultatif
    pour la saisie manuelle d'un client sans email.)"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True
        self.fields['email'].widget.attrs['placeholder'] = 'Votre email (vous y recevrez la confirmation)'
