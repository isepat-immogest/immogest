"""Galerie photos d'un bien dans l'API (utilisée par l'application React), sur le modèle `BienPhoto` existant.

Routes (ajoutées dans api/urls.py par `appliquer_galerie.py`) :
    GET    /api/v1/biens/<id>/galerie/                    la galerie : photo principale puis photos, dans l'ordre
    POST   /api/v1/biens/<id>/galerie/                    ajoute des photos (multipart, champ `images`, plusieurs fichiers)
    PATCH  /api/v1/biens/<id>/galerie/<photo>/            modifie la légende / l'ordre d'une photo
    DELETE /api/v1/biens/<id>/galerie/<photo>/            supprime une photo (et son fichier) ; `principale` = la photo principale
    POST   /api/v1/biens/<id>/galerie/<photo>/en-tete/    place cette photo en première position de la galerie

La couverture (image des listes) est la photo principale du bien (`Bien.photo`) si elle existe, sinon la première
photo de la galerie : c'est aussi la règle de `Bien.galerie` côté Django et du site public.
"""
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema  # type: ignore
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from gestion.models import Bien, BienPhoto
from gestion.scope import proprietaires_visibles

from .permissions import IsGestionnaire

TAILLE_MAX = 8 * 1024 * 1024      # par photo
MAX_PAR_DEFAUT = 20
LEGENDE_MAX = 120                  # longueur du champ `BienPhoto.legende`


def photos_max():
    """Même plafond que l'ajout de photos de l'interface Django (PHOTOS_MAX_PAR_BIEN), sinon 20."""
    try:
        from gestion.views import PHOTOS_MAX_PAR_BIEN
        return int(PHOTOS_MAX_PAR_BIEN)
    except Exception:  # noqa: BLE001
        return MAX_PAR_DEFAUT


def est_avif(fichier):
    """Image AVIF reconnue par sa signature : lisible par les navigateurs récents, mais pas par Pillow < 11.3."""
    position = fichier.tell() if hasattr(fichier, 'tell') else 0
    debut = fichier.read(12)
    fichier.seek(position)
    return len(debut) == 12 and debut[4:8] == b'ftyp' and debut[8:12] in (b'avif', b'avis')


def _bien(request, pk):
    qs = Bien.objects.filter(proprietaire__in=proprietaires_visibles(request.user)).prefetch_related('photos')
    return get_object_or_404(qs, pk=pk)


def _galerie(request, bien):
    """Galerie ordonnée du bien, avec liens absolus."""
    def url(fichier):
        return request.build_absolute_uri(fichier.url)
    out = []
    if bien.photo:
        out.append({'id': None, 'url': url(bien.photo), 'legende': '', 'principale': True, 'couverture': True,
                    'ordre': 0})
    for i, p in enumerate(bien.photos.all()):
        out.append({'id': p.pk, 'url': url(p.image), 'legende': p.legende, 'principale': False,
                    'couverture': not bien.photo and i == 0, 'ordre': p.ordre})
    return out


def _reponse(request, pk):
    return Response(_galerie(request, _bien(request, pk)))


def _photo(bien, photo_id):
    if not str(photo_id).isdigit():
        raise NotFound()
    return get_object_or_404(bien.photos, pk=int(photo_id))


class GalerieView(APIView):
    permission_classes = [IsGestionnaire]

    @extend_schema(responses={200: list})
    def get(self, request, pk):
        return _reponse(request, pk)

    @extend_schema(request={'multipart/form-data': dict}, responses={200: list})
    def post(self, request, pk):
        bien = _bien(request, pk)
        fichiers = request.FILES.getlist('images') or request.FILES.getlist('image')
        if not fichiers:
            raise ValidationError({'images': 'Aucune image reçue.'})
        place = photos_max() - bien.photos.count()
        if len(fichiers) > place:
            raise ValidationError({'images': f'Une galerie contient {photos_max()} photos au maximum : '
                                             f'il reste {max(place, 0)} place(s).'})
        champ = serializers.ImageField()           # vérifie que ce sont de vraies images
        for f in fichiers:
            if f.size > TAILLE_MAX:
                raise ValidationError({'images': f'« {f.name} » dépasse {TAILLE_MAX // (1024 * 1024)} Mo.'})
            if est_avif(f):
                continue
            try:
                champ.run_validation(f)
            except serializers.ValidationError:
                raise ValidationError({'images': f"« {f.name} » n'est pas une image valide."})
        legende = (request.data.get('legende') or '')[:LEGENDE_MAX]
        with transaction.atomic():
            ordre = bien.photos.order_by('-ordre').values_list('ordre', flat=True).first() or 0
            for f in fichiers:
                ordre += 1
                BienPhoto.objects.create(bien=bien, image=f, legende=legende, ordre=ordre)
        return _reponse(request, pk)


class PhotoGalerieView(APIView):
    permission_classes = [IsGestionnaire]

    @extend_schema(request=dict, responses={200: list})
    def patch(self, request, pk, photo_id):
        photo = _photo(_bien(request, pk), photo_id)
        if 'legende' in request.data:
            legende = str(request.data['legende'] or '')
            if len(legende) > LEGENDE_MAX:
                raise ValidationError({'legende': f'{LEGENDE_MAX} caractères au maximum.'})
            photo.legende = legende
        if 'ordre' in request.data:
            try:
                photo.ordre = int(request.data['ordre'])
                assert photo.ordre >= 0
            except (TypeError, ValueError, AssertionError):
                raise ValidationError({'ordre': 'Entier positif attendu.'})
        photo.save()
        return _reponse(request, pk)

    @extend_schema(responses={200: list})
    def delete(self, request, pk, photo_id):
        bien = _bien(request, pk)
        if photo_id == 'principale':
            if not bien.photo:
                raise NotFound("Ce bien n'a pas de photo principale.")
            bien.photo.delete(save=False)
            bien.photo = None
            bien.save(update_fields=['photo'])
        else:
            photo = _photo(bien, photo_id)
            photo.image.delete(save=False)           # le fichier disparaît aussi du disque
            photo.delete()
        return _reponse(request, pk)


class PhotoEnTeteView(APIView):
    permission_classes = [IsGestionnaire]

    @extend_schema(request=None, responses={200: list})
    def post(self, request, pk, photo_id):
        bien = _bien(request, pk)
        photo = _photo(bien, photo_id)
        autres = [p for p in bien.photos.all() if p.pk != photo.pk]
        with transaction.atomic():
            for rang, p in enumerate([photo] + autres, start=1):
                if p.ordre != rang:
                    p.ordre = rang
                    p.save(update_fields=['ordre'])
        return _reponse(request, pk)
