"""
localisation/forms.py
=====================
Formulaires pour l'app localisation.

CONTENU :
- RegionForm : CRUD admin pour les 10 régions du Cameroun

PÉRIMÈTRE :
- LocalisationForm est déjà défini dans catalogue/forms.py
  (sous-formulaire imbriqué dans la création de Site).
  Pas besoin de le redéfinir ici.

INITIATIVES PÉDAGOGIQUES :
1. Le code région est UNIQUE (10 codes ISO disponibles).
   On force la majuscule + on valide qu'il est dans la liste autorisée.
2. Le nom est UNIQUE et de longueur minimale (anti-saisie bâclée).
3. Description optionnelle mais help_text explicite l'usage SEO.
"""

from django import forms
from django.core.exceptions import ValidationError

from localisation.models import Region


# ============================================================
# 1. REGION — CRUD admin
# ============================================================
class RegionForm(forms.ModelForm):
    """
    Formulaire pour créer/modifier une région du Cameroun.

    PÉDAGO : Bien que les 10 régions soient fixes (référentiel national),
    on permet quand même un CRUD pour :
    - Mettre à jour la description touristique
    - Changer l'image représentative
    - Corriger une coquille sur le chef-lieu
    Mais en pratique, l'admin ne devrait JAMAIS supprimer une région.
    """

    class Meta:
        model = Region
        fields = ['nom', 'code', 'chef_lieu', 'description', 'image']
        widgets = {
            'description': forms.Textarea(attrs={
                'rows': 5,
                'placeholder': "Présentez les attraits touristiques de la région...",
            }),
            'code': forms.Select(),  # Le ModelForm utilisera les TextChoices auto
        }
        help_texts = {
            'description': "Sera affichée sur la page publique de la région et utilisée pour le SEO.",
            'chef_lieu': "Capitale administrative (ex: Yaoundé pour le Centre, Douala pour le Littoral).",
            'image': "Photo représentative de la région (paysage emblématique). 1200×600px recommandé.",
        }

    def clean_nom(self):
        """Validation du nom : longueur min + unicité insensible à la casse."""
        nom = self.cleaned_data['nom'].strip()
        if len(nom) < 3:
            raise ValidationError("Le nom de la région doit faire au moins 3 caractères.")

        # Unicité insensible à la casse (avec exclusion en édition)
        qs = Region.objects.filter(nom__iexact=nom)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Une région avec ce nom existe déjà.")
        return nom

    def clean_code(self):
        """Force majuscules + validation que le code est bien dans TextChoices."""
        code = self.cleaned_data['code'].strip().upper()

        # Récupère la liste des codes valides depuis le modèle
        codes_valides = [c[0] for c in Region.CodeRegion.choices]
        if code not in codes_valides:
            raise ValidationError(
                f"Code invalide. Codes autorisés : {', '.join(codes_valides)}."
            )

        # Unicité du code (avec exclusion en édition)
        qs = Region.objects.filter(code=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"Une région utilise déjà le code « {code} ».")
        return code

    def clean_chef_lieu(self):
        """Capitalise le chef-lieu (yaoundé → Yaoundé)."""
        chef = self.cleaned_data['chef_lieu'].strip().title()
        if len(chef) < 2:
            raise ValidationError("Le chef-lieu est trop court.")
        return chef


# ============================================================
# 2. LOCALISATION — Update standalone (gestionnaire édite SA loc.)
# ============================================================
# Pédago : Ce form est SÉPARÉ du LocalisationForm de catalogue/forms.py.
# Pourquoi ne pas réutiliser ?
# - catalogue/forms.py.LocalisationForm est conçu pour être imbriqué
#   dans add_site / update_site (transaction atomique).
# - Ici, on veut un form STANDALONE pour modifier UNIQUEMENT la
#   localisation d'un site déjà existant.
# - Avoir 2 forms distincts = 2 contextes d'usage clairs = moins de
#   couplage entre les apps. C'est le principe de Single Responsibility.
# - Si demain on veut ajouter une logique spéciale au update (ex:
#   notifier les touristes ayant des réservations en cours), elle
#   ira ici sans toucher au form de création.

from localisation.models import Localisation
from decimal import Decimal

# Bornes Cameroun (dupliquées ici pour ne pas dépendre de catalogue/)
CAMEROUN_LAT_MIN = Decimal('1.5')
CAMEROUN_LAT_MAX = Decimal('13.5')
CAMEROUN_LNG_MIN = Decimal('8.0')
CAMEROUN_LNG_MAX = Decimal('16.5')


class LocalisationUpdateForm(forms.ModelForm):
    """
    Formulaire d'édition standalone d'une Localisation.

    Utilisé par le gestionnaire pour corriger l'adresse ou recalibrer
    les coordonnées GPS de son site sans toucher au reste du site.

    PÉDAGO :
    - Mêmes validations que catalogue/forms.py.LocalisationForm
      (bornes GPS du Cameroun) pour cohérence.
    - Le form Leaflet du template va mettre à jour latitude/longitude
      en temps réel quand l'utilisateur déplace le marker sur la carte.
    """

    class Meta:
        model = Localisation
        fields = ['region', 'ville', 'quartier', 'adresse',
                  'latitude', 'longitude', 'point_repere']
        widgets = {
            'adresse': forms.Textarea(attrs={'rows': 2}),
            'latitude': forms.NumberInput(attrs={
                'step': '0.000001',
                'min': '1.5',
                'max': '13.5',
            }),
            'longitude': forms.NumberInput(attrs={
                'step': '0.000001',
                'min': '8.0',
                'max': '16.5',
            }),
        }
        help_texts = {
            'latitude': "Cliquez sur la carte ou déplacez le marker pour mettre à jour.",
            'longitude': "Cliquez sur la carte ou déplacez le marker pour mettre à jour.",
            'point_repere': "Aide les visiteurs à trouver le site (ex: « À 200m du marché central »).",
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