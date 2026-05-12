"""
catalogue/models.py
===================
Modèles du catalogue touristique.

Contient :
- Categorie : type de site (plage, parc, musée, etc.)
- Tag : étiquettes thématiques (aventure, famille, romantique...)
- SiteTouristique : entité centrale du catalogue
- PhotoSite : galerie photos d'un site
- Hebergement : options de logement liées à un site
- Disponibilite : places disponibles par jour
- SiteTag : table de jonction N..M Site ↔ Tag
"""

import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from core.models import TimestampedModel
from compte.models import Gestionnaire
from localisation.models import Localisation


# ============================================================
# 1. CATEGORIE (types de sites)
# ============================================================
class Categorie(TimestampedModel):
    """
    Catégorie d'un site touristique.

    Un site appartient à UNE seule catégorie (relation 1..N).
    Exemples : naturel, culturel, historique, plage, parc national...
    """
    libelle = models.CharField(
        max_length=60,
        unique=True,
        verbose_name="Libellé"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Description"
    )
    icone = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Icône",
        help_text="Nom d'icône Tabler/FontAwesome (ex: 'mountain', 'beach')"
    )
    couleur = models.CharField(
        max_length=7,
        default='#15803D',
        verbose_name="Couleur",
        help_text="Code hexadécimal pour l'affichage (ex: '#15803D')"
    )
    ordre_affichage = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Ordre d'affichage",
        help_text="Plus le nombre est petit, plus la catégorie apparaît en premier"
    )

    class Meta:
        verbose_name = "Catégorie"
        verbose_name_plural = "Catégories"
        ordering = ['ordre_affichage', 'libelle']

    def __str__(self):
        return self.libelle


# ============================================================
# 2. TAG (étiquettes thématiques)
# ============================================================
class Tag(TimestampedModel):
    """
    Étiquette thématique applicable à un site.

    Un site peut avoir PLUSIEURS tags (relation N..M via SiteTag).
    Exemples : aventure, famille, romantique, nature, sport, culture.
    """
    libelle = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Libellé"
    )
    categorie_tag = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Catégorie du tag",
        help_text="Ex: 'ambiance', 'public-cible', 'saison'"
    )
    icone = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Icône"
    )

    class Meta:
        verbose_name = "Tag"
        verbose_name_plural = "Tags"
        ordering = ['libelle']

    def __str__(self):
        return self.libelle


# ============================================================
# 3. SITE TOURISTIQUE (entité centrale)
# ============================================================
class SiteTouristique(TimestampedModel):
    """
    Site touristique référencé sur la plateforme.

    C'est l'entité centrale du catalogue : Plages de Kribi,
    Mont Cameroun, Musée National de Yaoundé, etc.
    """

    class TypeSite(models.TextChoices):
        PUBLIC = 'public', 'Public'
        PRIVE = 'prive', 'Privé'
        MIXTE = 'mixte', 'Mixte'

    # ID UUID pour la sécurité (empêche l'énumération via URL)
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    nom = models.CharField(
        max_length=150,
        verbose_name="Nom du site"
    )
    slug = models.SlugField(
        max_length=200,
        unique=True,
        verbose_name="Slug URL",
        help_text="Ex: plages-de-kribi (généré automatiquement)"
    )
    description = models.TextField(
        verbose_name="Description complète"
    )
    description_courte = models.CharField(
        max_length=250,
        blank=True,
        verbose_name="Description courte",
        help_text="Affichée dans les listings (max 250 caractères)"
    )

    # Relations
    categorie = models.ForeignKey(
        Categorie,
        on_delete=models.PROTECT,
        related_name='sites',
        verbose_name="Catégorie"
    )
    localisation = models.OneToOneField(
        Localisation,
        on_delete=models.PROTECT,
        related_name='site',
        verbose_name="Localisation"
    )
    gestionnaire = models.ForeignKey(
        Gestionnaire,
        on_delete=models.CASCADE,
        related_name='sites',
        verbose_name="Gestionnaire"
    )
    tags = models.ManyToManyField(
        Tag,
        through='SiteTag',
        related_name='sites',
        blank=True,
        verbose_name="Tags"
    )

    # Caractéristiques
    type = models.CharField(
        max_length=20,
        choices=TypeSite.choices,
        default=TypeSite.PUBLIC,
        verbose_name="Type"
    )
    tarif_adulte = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Tarif adulte (FCFA)"
    )
    tarif_enfant = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Tarif enfant (FCFA)",
        help_text="Tarif pour les moins de 12 ans"
    )
    horaires_ouverture = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Horaires d'ouverture",
        help_text='Format: {"lundi": "08:00-17:00", "mardi": "08:00-17:00"}'
    )
    capacite_max = models.PositiveIntegerField(
        default=100,
        verbose_name="Capacité maximum",
        help_text="Nombre maximum de visiteurs par jour"
    )
    duree_visite_moyenne = models.PositiveIntegerField(
        default=120,
        verbose_name="Durée moyenne de visite (minutes)"
    )
    accessibilite_pmr = models.BooleanField(
        default=False,
        verbose_name="Accessible aux PMR"
    )

    # Statut et metrics
    est_publie = models.BooleanField(
        default=False,
        verbose_name="Publié",
        help_text="Un site doit être validé avant d'être publié"
    )
    note_moyenne = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(5.0)],
        verbose_name="Note moyenne (sur 5)"
    )
    nombre_avis = models.PositiveIntegerField(
        default=0,
        verbose_name="Nombre d'avis"
    )
    nombre_vues = models.PositiveIntegerField(
        default=0,
        verbose_name="Nombre de vues"
    )

    class Meta:
        verbose_name = "Site touristique"
        verbose_name_plural = "Sites touristiques"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['est_publie', '-note_moyenne']),
            models.Index(fields=['categorie', 'est_publie']),
            models.Index(fields=['slug']),
        ]

    def __str__(self):
        return self.nom

    def save(self, *args, **kwargs):
        """Génère automatiquement le slug à partir du nom."""
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.nom)
        super().save(*args, **kwargs)

    @property
    def photo_principale(self):
        """Retourne la photo principale du site (ou la première)."""
        photo = self.photos.filter(est_principale=True).first()
        if not photo:
            photo = self.photos.first()
        return photo

    @property
    def est_visible(self):
        """Indique si le site est visible publiquement."""
        return self.est_publie and self.gestionnaire.est_valide


# ============================================================
# 4. PHOTO SITE (galerie photos)
# ============================================================
class PhotoSite(TimestampedModel):
    """
    Photo d'un site touristique.
    Un site a plusieurs photos (relation 1..N).
    """
    site = models.ForeignKey(
        SiteTouristique,
        on_delete=models.CASCADE,
        related_name='photos',
        verbose_name="Site"
    )
    image = models.ImageField(
        upload_to='sites/%Y/%m/',
        verbose_name="Image"
    )
    legende = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Légende"
    )
    est_principale = models.BooleanField(
        default=False,
        verbose_name="Photo principale",
        help_text="Photo affichée dans les listings"
    )
    ordre = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Ordre d'affichage"
    )

    class Meta:
        verbose_name = "Photo de site"
        verbose_name_plural = "Photos de sites"
        ordering = ['site', 'ordre', 'created_at']
        indexes = [
            models.Index(fields=['site', 'est_principale']),
        ]

    def __str__(self):
        return f"Photo de {self.site.nom} - {self.legende or 'Sans légende'}"

    def save(self, *args, **kwargs):
        """Garantit qu'une seule photo est marquée comme principale par site."""
        if self.est_principale:
            PhotoSite.objects.filter(
                site=self.site,
                est_principale=True
            ).exclude(pk=self.pk).update(est_principale=False)
        super().save(*args, **kwargs)


# ============================================================
# 5. HEBERGEMENT (hôtels, lodges, etc. liés à un site)
# ============================================================
class Hebergement(TimestampedModel):
    """
    Option d'hébergement liée à un site touristique.
    Un site peut avoir 0 ou plusieurs hébergements à proximité.
    """

    class TypeHebergement(models.TextChoices):
        HOTEL = 'hotel', 'Hôtel'
        LODGE = 'lodge', 'Lodge'
        CAMPING = 'camping', 'Camping'
        GITE = 'gite', 'Gîte'
        AUBERGE = 'auberge', 'Auberge'
        APPARTEMENT = 'appartement', 'Appartement'

    site = models.ForeignKey(
        SiteTouristique,
        on_delete=models.CASCADE,
        related_name='hebergements',
        verbose_name="Site associé"
    )
    nom = models.CharField(
        max_length=150,
        verbose_name="Nom"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Description"
    )
    type = models.CharField(
        max_length=20,
        choices=TypeHebergement.choices,
        verbose_name="Type"
    )
    nb_chambres = models.PositiveSmallIntegerField(
        default=1,
        verbose_name="Nombre de chambres"
    )
    prix_nuit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Prix par nuit (FCFA)"
    )
    etoiles = models.PositiveSmallIntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="Étoiles (1-5)"
    )
    services = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Services proposés",
        help_text='Format: ["wifi", "piscine", "restaurant", "climatisation"]'
    )
    photo = models.ImageField(
        upload_to='hebergements/%Y/%m/',
        blank=True,
        null=True,
        verbose_name="Photo principale"
    )
    est_disponible = models.BooleanField(
        default=True,
        verbose_name="Disponible"
    )

    class Meta:
        verbose_name = "Hébergement"
        verbose_name_plural = "Hébergements"
        ordering = ['site', '-etoiles', 'prix_nuit']
        indexes = [
            models.Index(fields=['site', 'est_disponible']),
            models.Index(fields=['type']),
        ]

    def __str__(self):
        return f"{self.nom} ({self.get_type_display()} {self.etoiles}★)"


# ============================================================
# 6. DISPONIBILITE (places disponibles par jour)
# ============================================================
class Disponibilite(TimestampedModel):
    """
    Disponibilité d'un site OU d'un hébergement pour une date donnée.

    Permet d'éviter le sur-booking : à chaque réservation confirmée,
    on décrémente places_restantes.
    """
    site = models.ForeignKey(
        SiteTouristique,
        on_delete=models.CASCADE,
        related_name='disponibilites',
        null=True,
        blank=True,
        verbose_name="Site"
    )
    hebergement = models.ForeignKey(
        Hebergement,
        on_delete=models.CASCADE,
        related_name='disponibilites',
        null=True,
        blank=True,
        verbose_name="Hébergement"
    )
    date = models.DateField(
        verbose_name="Date"
    )
    places_restantes = models.PositiveIntegerField(
        default=0,
        verbose_name="Places restantes"
    )
    est_ferme = models.BooleanField(
        default=False,
        verbose_name="Fermé ce jour-là",
        help_text="Coché pour les jours fériés ou fermetures exceptionnelles"
    )
    tarif_special = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Tarif spécial (FCFA)",
        help_text="Tarif promotionnel ou saisonnier (sinon tarif normal du site)"
    )

    class Meta:
        verbose_name = "Disponibilité"
        verbose_name_plural = "Disponibilités"
        ordering = ['date']
        indexes = [
            models.Index(fields=['site', 'date']),
            models.Index(fields=['hebergement', 'date']),
        ]
        constraints = [
            # Soit un site, soit un hébergement (jamais les deux, jamais aucun)
            models.CheckConstraint(
                check=(
                    models.Q(site__isnull=False, hebergement__isnull=True) |
                    models.Q(site__isnull=True, hebergement__isnull=False)
                ),
                name='disponibilite_site_ou_hebergement'
            ),
            # Une seule entrée par couple (site, date)
            models.UniqueConstraint(
                fields=['site', 'date'],
                condition=models.Q(site__isnull=False),
                name='unique_disponibilite_site_date'
            ),
            # Une seule entrée par couple (hebergement, date)
            models.UniqueConstraint(
                fields=['hebergement', 'date'],
                condition=models.Q(hebergement__isnull=False),
                name='unique_disponibilite_hebergement_date'
            ),
        ]

    def __str__(self):
        ressource = self.site or self.hebergement
        return f"{ressource} - {self.date} - {self.places_restantes} places"


# ============================================================
# 7. SITE TAG (table de jonction N..M)
# ============================================================
class SiteTag(models.Model):
    """
    Association entre un site et ses tags.
    Table de jonction N..M (un site peut avoir plusieurs tags,
    un tag peut concerner plusieurs sites).
    """
    site = models.ForeignKey(
        SiteTouristique,
        on_delete=models.CASCADE,
        verbose_name="Site"
    )
    tag = models.ForeignKey(
        Tag,
        on_delete=models.CASCADE,
        verbose_name="Tag"
    )
    date_ajout = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date d'ajout"
    )

    class Meta:
        verbose_name = "Association site-tag"
        verbose_name_plural = "Associations site-tag"
        unique_together = [('site', 'tag')]

    def __str__(self):
        return f"{self.site.nom} - {self.tag.libelle}"