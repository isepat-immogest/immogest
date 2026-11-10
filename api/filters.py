import django_filters as df  # type: ignore

from gestion.models import Bien, Contrat, DemandeContact, Equipement, Intervention, Paiement, Proprietaire, Reservation


class BienFilter(df.FilterSet):
    loyer_min = df.NumberFilter(field_name='loyer_charges', lookup_expr='gte')
    loyer_max = df.NumberFilter(field_name='loyer_charges', lookup_expr='lte')
    ville = df.CharFilter(field_name='ville', lookup_expr='iexact')
    # ?equipements=3&equipements=7 : biens qui ont TOUS les équipements demandés
    equipements = df.ModelMultipleChoiceFilter(queryset=Equipement.objects.all(), conjoined=True)
    proprietaire = df.ModelChoiceFilter(field_name='proprietaires', queryset=Proprietaire.objects.all())
    chambres_min = df.NumberFilter(field_name='nb_chambres', lookup_expr='gte')

    class Meta:
        model = Bien
        fields = ['statut', 'type_bien', 'ville', 'nb_pieces', 'meuble']


class ContratFilter(df.FilterSet):
    class Meta:
        model = Contrat
        fields = ['statut', 'type_bail', 'bien', 'locataire']


class PaiementFilter(df.FilterSet):
    mois_min = df.DateFilter(field_name='mois', lookup_expr='gte')
    mois_max = df.DateFilter(field_name='mois', lookup_expr='lte')
    locataire = df.NumberFilter(field_name='contrat__locataire')
    bien = df.NumberFilter(field_name='contrat__bien')

    class Meta:
        model = Paiement
        fields = ['statut', 'contrat', 'mode_paiement']


class InterventionFilter(df.FilterSet):
    class Meta:
        model = Intervention
        fields = ['statut', 'priorite', 'bien']


class ReservationFilter(df.FilterSet):
    class Meta:
        model = Reservation
        fields = ['statut', 'bien', 'mode_paiement']


class DemandeFilter(df.FilterSet):
    class Meta:
        model = DemandeContact
        fields = ['traite', 'bien']
