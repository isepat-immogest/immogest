from django import forms # type: ignore
from decimal import Decimal

from .models import Bien, Locataire, Contrat, Paiement, Intervention, DemandeContact, Reservation, Proprietaire
from .scope import proprietaires_visibles


class BienForm(forms.ModelForm):
    """Formulaire d'un bien, avec jusqu'à deux propriétaires (et leurs parts) choisis directement ici.

    Pour plus de deux propriétaires : fiche du bien dans l'application React, ou commande assigner_proprietaire.
    Si aucun propriétaire n'est choisi, la liste actuelle du bien n'est pas modifiée.
    """
    proprietaire_1 = forms.ModelChoiceField(
        queryset=Proprietaire.objects.none(), required=False, empty_label='— Aucun —', label='Propriétaire')
    quote_1 = forms.DecimalField(
        required=False, min_value=Decimal('0.01'), max_value=100, decimal_places=2, initial=100,
        label='Part du propriétaire (%)', help_text='100 si le bien n\'a qu\'un propriétaire.')
    proprietaire_2 = forms.ModelChoiceField(
        queryset=Proprietaire.objects.none(), required=False, empty_label='— Aucun —',
        label='Second propriétaire (copropriété)')
    quote_2 = forms.DecimalField(
        required=False, min_value=Decimal('0.01'), max_value=100, decimal_places=2,
        label='Part du second propriétaire (%)', help_text='La somme des deux parts doit faire 100 %.')

    field_order = ['nom', 'proprietaire_1', 'quote_1', 'proprietaire_2', 'quote_2']

    class Meta:
        model = Bien
        exclude = ['proprietaire', 'proprietaires', 'created_at']
        widgets = {
            'equipements': forms.CheckboxSelectMultiple(),
            'date_acquisition': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            visibles = Proprietaire.objects.filter(gestionnaire__in=proprietaires_visibles(user), actif=True)
            self.fields['proprietaire_1'].queryset = visibles
            self.fields['proprietaire_2'].queryset = visibles
        parts = list(self.instance.parts.select_related('proprietaire')[:2]) if self.instance.pk else []
        if parts:
            self.fields['proprietaire_1'].initial = parts[0].proprietaire_id
            self.fields['quote_1'].initial = parts[0].quote_part
        if len(parts) > 1:
            self.fields['proprietaire_2'].initial = parts[1].proprietaire_id
            self.fields['quote_2'].initial = parts[1].quote_part
        self.nb_parts_existantes = self.instance.parts.count() if self.instance.pk else 0

    def clean(self):
        data = super().clean()
        p1, p2 = data.get('proprietaire_1'), data.get('proprietaire_2')
        q1, q2 = data.get('quote_1'), data.get('quote_2')
        self.parts_proprietaires = None
        if p2 and not p1:
            self.add_error('proprietaire_1', 'Choisissez d\'abord le propriétaire principal.')
        elif p1 and p2:
            if p1 == p2:
                self.add_error('proprietaire_2', 'Choisissez deux propriétaires différents.')
            elif q1 is None or q2 is None:
                self.add_error('quote_2', 'Indiquez la part de chacun (la somme doit faire 100 %).')
            elif abs(q1 + q2 - 100) > Decimal('0.01'):
                self.add_error('quote_2', f'Les parts totalisent {q1 + q2} % : elles doivent faire 100 %.')
            else:
                self.parts_proprietaires = [(p1, q1), (p2, q2)]
        elif p1:
            if q1 not in (None, 100) and abs(q1 - 100) > Decimal('0.01'):
                self.add_error('quote_1', 'Avec un seul propriétaire, la part doit être de 100 %.')
            else:
                self.parts_proprietaires = [(p1, Decimal(100))]
        return data

    def enregistrer_proprietaires(self, bien):
        """À appeler après save() : remplace les propriétaires du bien si l'utilisateur en a choisi."""
        if self.parts_proprietaires:
            from . import services
            services.definir_proprietaires_bien(bien, self.parts_proprietaires)


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
