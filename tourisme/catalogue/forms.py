"""
catalogue/forms.py
==================
Formulaires Django pour l'app catalogue.

ARCHITECTURE :
- CategorieForm        : CRUD catégories (admin)
- TagForm              : CRUD tags (admin)
- LocalisationForm     : sous-form pour créer une localisation
- SiteTouristiqueForm  : CRUD sites (gestionnaire)
- PhotoSiteForm + FormSet : galerie photos d'un site
- HebergementForm      : CRUD hébergements
- DisponibiliteForm    : CRUD disponibilités (CheckConstraint site OU hebergement)
- SiteFiltreForm       : filtres publics pour la recherche

INITIATIVES PÉDAGOGIQUES :
1. ModelForm = persistance directe (un modèle = un form)
   Form = juste validation (filtres publics par exemple)
2. Validation côté SERVEUR obligatoire même si HTML5 valide côté client
   (un attaquant peut contourner le HTML5 via curl/Postman)
3. Le gestionnaire NE SAISIT JAMAIS le champ gestionnaire — c'est la
   view qui force `gestionnaire = request.user.profil_gestionnaire`.
   Sinon, faille de sécurité (un gestionnaire pourrait s'attribuer
   le site d'un autre).
4. Génération automatique du slug dans save() — l'user n'a pas à
   réfléchir à des URLs SEO-friendly.
5. PROTECT sur localisation : on gère défensivement la création
   atomique site+localisation dans la view.
"""

from decimal import Decimal
from django import forms
from django.forms import inlineformset_factory
from django.utils.text import slugify
from django.core.exceptions import ValidationError

from catalogue.models import (
    Categorie, Tag, SiteTouristique, PhotoSite,
    Hebergement, Disponibilite,
)
from localisation.models import Region, Localisation


# ============================================================
# CONSTANTES (bornes géographiques du Cameroun)
# ============================================================
# Pédago : on valide que les coordonnées GPS saisies sont DANS le
# périmètre du Cameroun (1.5°N à 13.5°N, 8°E à 16.5°E). Évite
# qu'un gestionnaire distrait place son site à New York.
CAMEROUN_LAT_MIN = Decimal('1.5')
CAMEROUN_LAT_MAX = Decimal('13.5')
CAMEROUN_LNG_MIN = Decimal('8.0')
CAMEROUN_LNG_MAX = Decimal('16.5')


# ============================================================
# 1. CATEGORIE — CRUD admin
# ============================================================
class CategorieForm(forms.ModelForm):
    """
    Formulaire pour créer/modifier une catégorie.

    ATTENTION : le champ s'appelle `libelle` (pas `nom`) dans votre modèle.
    """

    class Meta:
        model = Categorie
        fields = ['libelle', 'description', 'icone', 'couleur', 'ordre_affichage']
        widgets = {
            # Pédago : pas de classes CSS ici. Le template les ajoute via
            # `class="input input-bordered w-full"` directement. Permet de
            # changer la charte sans toucher au form Python.
            'description': forms.Textarea(attrs={'rows': 3}),
            'couleur': forms.TextInput(attrs={
                'pattern': '^#[0-9A-Fa-f]{6}$',
                'placeholder': '#15803D',
            }),
        }

    def clean_libelle(self):
        """Vérifier longueur min + unicité insensible à la casse."""
        libelle = self.cleaned_data['libelle'].strip()
        if len(libelle) < 3:
            raise ValidationError("Le libellé doit faire au moins 3 caractères.")

        # Unicité insensible à la casse + exclusion de l'instance en édition
        qs = Categorie.objects.filter(libelle__iexact=libelle)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Une catégorie avec ce libellé existe déjà.")
        return libelle

    def clean_couleur(self):
        """Format hexadécimal de la couleur."""
        couleur = self.cleaned_data.get('couleur', '').strip()
        if couleur and not couleur.startswith('#'):
            couleur = f'#{couleur}'
        # Validation du format hex
        if couleur and not (len(couleur) == 7 and all(c in '0123456789ABCDEFabcdef' for c in couleur[1:])):
            raise ValidationError("Format invalide. Utilisez #RRGGBB (ex: #15803D).")
        return couleur.upper() if couleur else couleur


# ============================================================
# 2. TAG — CRUD admin
# ============================================================
class TagForm(forms.ModelForm):
    """Formulaire pour les tags (étiquettes thématiques)."""

    class Meta:
        model = Tag
        fields = ['libelle', 'categorie_tag', 'icone']

    def clean_libelle(self):
        """Force minuscule + unicité (les tags sont conventionnellement en minuscules)."""
        libelle = self.cleaned_data['libelle'].strip().lower()
        if len(libelle) < 2:
            raise ValidationError("Le tag est trop court.")

        qs = Tag.objects.filter(libelle__iexact=libelle)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Ce tag existe déjà.")
        return libelle


# ============================================================
# 3. LOCALISATION — Sous-formulaire pour création de site
# ============================================================
class LocalisationForm(forms.ModelForm):
    """
    Formulaire de création/édition d'une localisation.

    Pédago : Comme `Site.localisation` est `OneToOneField(PROTECT)`, on
    crée la localisation EN MÊME TEMPS que le site, dans une transaction
    atomique côté view. L'user ne voit qu'UN formulaire, mais deux objets
    sont créés en BDD.
    """

    class Meta:
        model = Localisation
        fields = ['region', 'ville', 'quartier', 'adresse',
                  'latitude', 'longitude', 'point_repere']
        widgets = {
            'adresse': forms.Textarea(attrs={'rows': 2}),
            'latitude': forms.NumberInput(attrs={
                'step': '0.000001',
                'min': '-90',
                'max': '90',
            }),
            'longitude': forms.NumberInput(attrs={
                'step': '0.000001',
                'min': '-180',
                'max': '180',
            }),
        }

    def clean_ville(self):
        """Capitalise la ville (douala → Douala)."""
        ville = self.cleaned_data['ville'].strip().title()
        if len(ville) < 2:
            raise ValidationError("Le nom de la ville est trop court.")
        return ville

    def clean_latitude(self):
        """Vérifier que la latitude est dans le périmètre du Cameroun."""
        lat = self.cleaned_data.get('latitude')
        if lat is None:
            return lat
        if not (CAMEROUN_LAT_MIN <= lat <= CAMEROUN_LAT_MAX):
            raise ValidationError(
                f"La latitude doit être entre {CAMEROUN_LAT_MIN}° et {CAMEROUN_LAT_MAX}° "
                f"(périmètre du Cameroun)."
            )
        return lat

    def clean_longitude(self):
        """Idem pour la longitude."""
        lng = self.cleaned_data.get('longitude')
        if lng is None:
            return lng
        if not (CAMEROUN_LNG_MIN <= lng <= CAMEROUN_LNG_MAX):
            raise ValidationError(
                f"La longitude doit être entre {CAMEROUN_LNG_MIN}° et {CAMEROUN_LNG_MAX}° "
                f"(périmètre du Cameroun)."
            )
        return lng


# ============================================================
# 4. SITE TOURISTIQUE — CRUD principal (gestionnaire)
# ============================================================
class SiteTouristiqueForm(forms.ModelForm):
    """
    Formulaire principal pour créer/modifier un site touristique.

    SÉCURITÉ : on liste EXPLICITEMENT les champs autorisés.
    Champs EXCLUS volontairement :
    - gestionnaire : forcé par la view (= request.user.profil_gestionnaire)
    - localisation : créée séparément via LocalisationForm
    - est_publie : décidé par l'admin (pas le gestionnaire)
    - note_moyenne, nombre_avis, nombre_vues : calculés automatiquement
    - slug : généré automatiquement dans save()
    """

    class Meta:
        model = SiteTouristique
        fields = [
            'nom', 'description', 'description_courte',
            'categorie', 'type',
            'tarif_adulte', 'tarif_enfant',
            'capacite_max', 'duree_visite_moyenne',
            'horaires_ouverture', 'accessibilite_pmr',
            'tags',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 6}),
            'description_courte': forms.Textarea(attrs={
                'rows': 2,
                'maxlength': 250,
            }),
            'horaires_ouverture': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': '{"lundi": "08:00-17:00", "dimanche": "ferme"}',
            }),
            # CheckboxSelectMultiple est BIEN plus UX que le select multiple natif
            'tags': forms.CheckboxSelectMultiple(),
        }
        help_texts = {
            'description_courte': "Affichée dans les listings (250 caractères max).",
            'horaires_ouverture': "Format JSON. Utilisez 'ferme' pour les jours fermés.",
            'capacite_max': "Nombre maximum de visiteurs en simultané (sécurité, conservation).",
        }

    def clean_nom(self):
        nom = self.cleaned_data['nom'].strip()
        if len(nom) < 3:
            raise ValidationError("Le nom est trop court (3 caractères minimum).")
        return nom

    def clean(self):
        """Validation croisée : tarif_enfant <= tarif_adulte."""
        cleaned = super().clean()
        tarif_adulte = cleaned.get('tarif_adulte')
        tarif_enfant = cleaned.get('tarif_enfant')

        if tarif_adulte is not None and tarif_enfant is not None:
            if tarif_enfant > tarif_adulte:
                # add_error attache l'erreur au champ précis (meilleure UX
                # qu'une erreur globale qui apparaît en haut)
                self.add_error(
                    'tarif_enfant',
                    "Le tarif enfant ne peut pas être supérieur au tarif adulte."
                )
        return cleaned


# ============================================================
# 5. PHOTO SITE + FORMSET (galerie)
# ============================================================
class PhotoSiteForm(forms.ModelForm):
    """Formulaire individuel pour une photo."""

    class Meta:
        model = PhotoSite
        fields = ['image', 'legende', 'est_principale', 'ordre']

    def clean_image(self):
        """Limite la taille à 5 Mo."""
        image = self.cleaned_data.get('image')
        if image and hasattr(image, 'size'):
            if image.size > 5 * 1024 * 1024:
                raise ValidationError("L'image ne doit pas dépasser 5 Mo.")
        return image


# Pédago : inlineformset_factory permet de gérer plusieurs photos
# rattachées à un site dans le même formulaire HTML. extra=3 →
# 3 lignes vides supplémentaires par défaut.
PhotoSiteFormSet = inlineformset_factory(
    SiteTouristique,
    PhotoSite,
    form=PhotoSiteForm,
    extra=3,
    can_delete=True,
    min_num=0,
    validate_min=False,
)


# ============================================================
# 6. HEBERGEMENT — CRUD gestionnaire
# ============================================================
class HebergementForm(forms.ModelForm):
    """
    Formulaire pour un hébergement.

    Le champ `site` est EXCLU — passé en paramètre depuis l'URL
    (sécurité : empêche de rattacher son hôtel au site d'un concurrent).
    """

    class Meta:
        model = Hebergement
        fields = [
            'nom', 'description', 'type',
            'nb_chambres', 'prix_nuit', 'etoiles',
            'services', 'photo', 'est_disponible',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'services': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': '["wifi", "piscine", "restaurant", "climatisation"]',
            }),
            'etoiles': forms.Select(choices=[
                (1, '⭐ (1 étoile)'),
                (2, '⭐⭐ (2 étoiles)'),
                (3, '⭐⭐⭐ (3 étoiles)'),
                (4, '⭐⭐⭐⭐ (4 étoiles)'),
                (5, '⭐⭐⭐⭐⭐ (5 étoiles)'),
            ]),
        }
        help_texts = {
            'services': 'Liste JSON. Ex: ["wifi", "piscine", "petit-déjeuner inclus"]',
            'prix_nuit': "Prix par chambre par nuit en FCFA.",
        }

    def clean_prix_nuit(self):
        prix = self.cleaned_data.get('prix_nuit')
        if prix is not None and prix < 0:
            raise ValidationError("Le prix ne peut pas être négatif.")
        return prix

    def clean_nb_chambres(self):
        nb = self.cleaned_data.get('nb_chambres')
        if nb is not None and nb < 1:
            raise ValidationError("Au moins 1 chambre requise.")
        return nb


# ============================================================
# 7. DISPONIBILITE — CRUD gestionnaire
# ============================================================
class DisponibiliteForm(forms.ModelForm):
    """
    Formulaire pour une disponibilité (jour J pour un site OU un hébergement).

    Pédago : votre modèle a un CheckConstraint qui impose SOIT un site,
    SOIT un hébergement (jamais les deux, jamais aucun). On valide pareil
    côté form pour avoir un message d'erreur clair.
    """

    class Meta:
        model = Disponibilite
        fields = ['site', 'hebergement', 'date',
                  'places_restantes', 'est_ferme', 'tarif_special']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        """Cohérences métier."""
        cleaned = super().clean()
        site = cleaned.get('site')
        hebergement = cleaned.get('hebergement')

        # Règle 1 : site XOR hebergement (un et un seul des deux)
        if not site and not hebergement:
            raise ValidationError(
                "Vous devez choisir soit un site, soit un hébergement."
            )
        if site and hebergement:
            raise ValidationError(
                "Choisissez UN seul des deux : site OU hébergement."
            )

        # Règle 2 : si fermé, places_restantes = 0
        if cleaned.get('est_ferme') and (cleaned.get('places_restantes') or 0) > 0:
            self.add_error(
                'places_restantes',
                "Un jour de fermeture doit avoir 0 place restante."
            )

        return cleaned


# ============================================================
# 8. FILTRE PUBLIC — Recherche/tri sur la liste des sites
# ============================================================
class SiteFiltreForm(forms.Form):
    """
    Formulaire de filtres pour la page liste publique des sites.

    Pédago : Form (pas ModelForm) car on ne persiste RIEN. C'est juste
    une validation/sérialisation des paramètres GET de l'URL.
    Tous les champs sont required=False (le filtre est OPTIONNEL).
    """

    q = forms.CharField(
        required=False,
        label="Recherche",
        max_length=100,
    )
    region = forms.ModelChoiceField(
        queryset=Region.objects.all(),
        required=False,
        empty_label="Toutes les régions",
    )
    categorie = forms.ModelChoiceField(
        queryset=Categorie.objects.all(),
        required=False,
        empty_label="Toutes les catégories",
    )
    prix_min = forms.IntegerField(
        required=False,
        min_value=0,
    )
    prix_max = forms.IntegerField(
        required=False,
        min_value=0,
    )
    accessible_pmr = forms.BooleanField(
        required=False,
        label="Accessible aux PMR",
    )
    avec_hebergement = forms.BooleanField(
        required=False,
        label="Avec hébergement",
    )
    tri = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'Plus pertinents'),
            ('popularite', 'Plus populaires'),
            ('prix_asc', 'Prix croissant'),
            ('prix_desc', 'Prix décroissant'),
            ('note', 'Mieux notés'),
            ('recent', 'Plus récents'),
        ],
    )

    def clean(self):
        """prix_min <= prix_max."""
        cleaned = super().clean()
        pmin = cleaned.get('prix_min')
        pmax = cleaned.get('prix_max')
        if pmin is not None and pmax is not None and pmin > pmax:
            self.add_error('prix_min', "Le prix min doit être inférieur au prix max.")
        return cleaned