"""
Localisations/models.py
======================
Modèles de géolocalisation pour le Cameroun.

Contient :
- Region : les 10 régions administratives du Cameroun
- Localisation : adresse précise d'un site (ville, quartier, GPS)
"""

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from core.models import TimestampedModel


# ============================================================
# 1. REGION (10 régions administratives du Cameroun)
# ============================================================
class Region(TimestampedModel):
    """
    Région administrative du Cameroun.

    Le Cameroun compte 10 régions :
    Adamaoua, Centre, Est, Extrême-Nord, Littoral,
    Nord, Nord-Ouest, Ouest, Sud, Sud-Ouest.
    """

    class CodeRegion(models.TextChoices):
        ADAMAOUA = 'AD', 'Adamaoua'
        CENTRE = 'CE', 'Centre'
        EST = 'ES', 'Est'
        EXTREME_NORD = 'EN', 'Extrême-Nord'
        LITTORAL = 'LT', 'Littoral'
        NORD = 'NO', 'Nord'
        NORD_OUEST = 'NW', 'Nord-Ouest'
        OUEST = 'OU', 'Ouest'
        SUD = 'SU', 'Sud'
        SUD_OUEST = 'SW', 'Sud-Ouest'

    nom = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Nom de la région"
    )
    code = models.CharField(
        max_length=5,
        choices=CodeRegion.choices,
        unique=True,
        verbose_name="Code région",
        help_text="Code ISO à 2 lettres"
    )
    chef_lieu = models.CharField(
        max_length=80,
        verbose_name="Chef-lieu",
        help_text="Capitale administrative de la région"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Description touristique",
        help_text="Présentation des attraits touristiques de la région"
    )
    image = models.ImageField(
        upload_to='regions/',
        blank=True,
        null=True,
        verbose_name="Image représentative"
    )

    class Meta:
        verbose_name = "Région"
        verbose_name_plural = "Régions"
        ordering = ['nom']

    def __str__(self):
        return f"{self.nom} ({self.chef_lieu})"

    @property
    def nombre_sites(self):
        """Retourne le nombre de sites touristiques de la région."""
        # On utilise une chaîne pour éviter l'import circulaire avec catalogue
        from catalogue.models import SiteTouristique
        return SiteTouristique.objects.filter(
            localisation__region=self,
            est_publie=True
        ).count()


# ============================================================
# 2. LOCALISATION (adresse précise d'un site)
# ============================================================
class Localisation(TimestampedModel):
    """
    Localisation précise d'un site touristique.

    Inclut l'adresse textuelle et les coordonnées GPS pour
    l'affichage sur carte interactive (Leaflet/OpenStreetMap).
    """
    region = models.ForeignKey(
        Region,
        on_delete=models.PROTECT,
        related_name='Localisations',
        verbose_name="Région"
    )
    ville = models.CharField(
        max_length=80,
        verbose_name="Ville",
        help_text="Ex: Kribi, Yaoundé, Douala, Limbé"
    )
    quartier = models.CharField(
        max_length=80,
        blank=True,
        verbose_name="Quartier",
        help_text="Ex: Bastos, Bonanjo, Akwa"
    )
    adresse = models.TextField(
        blank=True,
        verbose_name="Adresse détaillée"
    )
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[
            MinValueValidator(-90.0),
            MaxValueValidator(90.0)
        ],
        verbose_name="Latitude",
        help_text="Coordonnée GPS (format décimal, ex: 3.848)"
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[
            MinValueValidator(-180.0),
            MaxValueValidator(180.0)
        ],
        verbose_name="Longitude",
        help_text="Coordonnée GPS (format décimal, ex: 11.502)"
    )
    point_repere = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Point de repère",
        help_text="Ex: 'À 200m de l'hôtel Mont Fébé'"
    )

    class Meta:
        verbose_name = "Localisation"
        verbose_name_plural = "Localisations"
        ordering = ['region__nom', 'ville']
        indexes = [
            models.Index(fields=['latitude', 'longitude']),
            models.Index(fields=['region', 'ville']),
        ]

    def __str__(self):
        if self.quartier:
            return f"{self.ville}, {self.quartier} ({self.region.nom})"
        return f"{self.ville} ({self.region.nom})"

    @property
    def coordonnees(self):
        """Retourne les coordonnées sous forme de tuple (lat, lng)."""
        return (float(self.latitude), float(self.longitude))

    @property
    def google_maps_url(self):
        """URL Google Maps pour cette Localisations."""
        return f"https://www.google.com/maps/search/?api=1&query={self.latitude},{self.longitude}"