"""
reviews/models.py
=================
Modèles d'avis et de favoris.

Contient :
- Avis : note + commentaire d'un touriste sur un site visité
- Favori : sites mis en favori par un touriste

Règle métier critique : un touriste ne peut laisser un avis que s'il a
effectivement réservé ET visité le site (reservation.statut = terminee).
"""

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from core.models import TimestampedModel
from compte.models import Touriste
from catalogue.models import SiteTouristique
from reservation.models import Reservation


# ============================================================
# 1. AVIS (review)
# ============================================================
class Avis(TimestampedModel):
    """
    Avis laissé par un touriste sur un site visité.

    Règles métier :
    - Un avis est obligatoirement lié à une réservation TERMINEE (anti-fraude)
    - Un seul avis par réservation (UNIQUE sur id_reservation)
    - Note de 1 à 5 étoiles obligatoire
    - Modération admin avant publication
    """

    class StatutModeration(models.TextChoices):
        EN_ATTENTE = 'en_attente', 'En attente de modération'
        APPROUVE = 'approuve', 'Approuvé'
        REJETE = 'rejete', 'Rejeté'
        SIGNALE = 'signale', 'Signalé par un utilisateur'

    # Acteurs et liens
    touriste = models.ForeignKey(
        Touriste,
        on_delete=models.CASCADE,
        related_name='avis_donnes',
        verbose_name="Touriste"
    )
    site = models.ForeignKey(
        SiteTouristique,
        on_delete=models.CASCADE,
        related_name='avis',
        verbose_name="Site"
    )
    reservation = models.OneToOneField(
        Reservation,
        on_delete=models.CASCADE,
        related_name='avis',
        verbose_name="Réservation",
        help_text="Garantit qu'un avis = une visite effective (anti-faux avis)"
    )

    # Contenu de l'avis
    note = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="Note (1-5)"
    )
    titre = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Titre de l'avis"
    )
    commentaire = models.TextField(
        verbose_name="Commentaire"
    )

    # Notes détaillées (optionnelles, pour avis riches)
    note_accueil = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="Note Accueil"
    )
    note_proprete = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="Note Propreté"
    )
    note_rapport_qualite_prix = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="Note Rapport qualité/prix"
    )

    # Modération
    statut_moderation = models.CharField(
        max_length=20,
        choices=StatutModeration.choices,
        default=StatutModeration.EN_ATTENTE,
        verbose_name="Statut de modération"
    )
    motif_rejet = models.TextField(
        blank=True,
        verbose_name="Motif de rejet"
    )
    est_visible = models.BooleanField(
        default=False,
        verbose_name="Visible publiquement"
    )

    # Réponse du gestionnaire
    reponse_gestionnaire = models.TextField(
        blank=True,
        verbose_name="Réponse du gestionnaire"
    )
    date_reponse = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de la réponse"
    )

    # Métriques
    nombre_utiles = models.PositiveIntegerField(
        default=0,
        verbose_name="Nombre de \"Utile\" reçus"
    )
    nombre_signalements = models.PositiveIntegerField(
        default=0,
        verbose_name="Nombre de signalements"
    )

    class Meta:
        verbose_name = "Avis"
        verbose_name_plural = "Avis"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['site', 'est_visible', '-created_at']),
            models.Index(fields=['statut_moderation']),
            models.Index(fields=['touriste', '-created_at']),
        ]

    def __str__(self):
        return f"{self.touriste.user.nom_complet} - {self.site.nom} - {self.note}/5"

    def approuver(self):
        """Approuve l'avis (par un admin) et le rend visible."""
        self.statut_moderation = self.StatutModeration.APPROUVE
        self.est_visible = True
        self.save()
        # Recalcule la note moyenne du site
        self._mettre_a_jour_note_site()

    def rejeter(self, motif=""):
        """Rejette l'avis (par un admin)."""
        self.statut_moderation = self.StatutModeration.REJETE
        self.est_visible = False
        self.motif_rejet = motif
        self.save()

    def repondre(self, reponse):
        """Permet au gestionnaire de répondre à l'avis."""
        self.reponse_gestionnaire = reponse
        self.date_reponse = timezone.now()
        self.save()

    def signaler(self):
        """Incrémente le compteur de signalements."""
        self.nombre_signalements += 1
        # Auto-modération : si trop de signalements, on masque
        if self.nombre_signalements >= 5:
            self.statut_moderation = self.StatutModeration.SIGNALE
            self.est_visible = False
        self.save()

    def _mettre_a_jour_note_site(self):
        """
        Recalcule la note moyenne et le nombre d'avis du site.
        Méthode appelée après chaque approbation d'avis.
        """
        from django.db.models import Avg, Count

        avis_visibles = Avis.objects.filter(
            site=self.site,
            est_visible=True
        )
        stats = avis_visibles.aggregate(
            moyenne=Avg('note'),
            total=Count('id')
        )
        self.site.note_moyenne = round(stats['moyenne'] or 0, 1)
        self.site.nombre_avis = stats['total'] or 0
        self.site.save(update_fields=['note_moyenne', 'nombre_avis'])


# ============================================================
# 2. FAVORI (sites mis en favori)
# ============================================================
class Favori(TimestampedModel):
    """
    Site mis en favori par un touriste.

    Table de jonction N..M avec un attribut supplémentaire (date_ajout).
    """
    touriste = models.ForeignKey(
        Touriste,
        on_delete=models.CASCADE,
        related_name='favoris',
        verbose_name="Touriste"
    )
    site = models.ForeignKey(
        SiteTouristique,
        on_delete=models.CASCADE,
        related_name='ajoute_aux_favoris_par',
        verbose_name="Site"
    )
    note_personnelle = models.TextField(
        blank=True,
        verbose_name="Note personnelle",
        help_text="Note privée du touriste (non visible publiquement)"
    )

    class Meta:
        verbose_name = "Favori"
        verbose_name_plural = "Favoris"
        ordering = ['-created_at']
        unique_together = [('touriste', 'site')]  # PK composite
        indexes = [
            models.Index(fields=['touriste', '-created_at']),
        ]

    def __str__(self):
        return f"{self.touriste.user.nom_complet} ♥ {self.site.nom}"


# ============================================================
# 3. UTILE (a-t-on trouvé l'avis utile ?)
# ============================================================
class UtiliteAvis(TimestampedModel):
    """
    Indique qu'un utilisateur a trouvé un avis utile.

    Permet d'afficher les avis les plus pertinents en premier.
    Un utilisateur ne peut voter qu'une seule fois par avis.
    """
    avis = models.ForeignKey(
        Avis,
        on_delete=models.CASCADE,
        related_name='votes_utiles',
        verbose_name="Avis"
    )
    touriste = models.ForeignKey(
        Touriste,
        on_delete=models.CASCADE,
        related_name='avis_juges_utiles',
        verbose_name="Touriste"
    )
    est_utile = models.BooleanField(
        default=True,
        verbose_name="Considéré comme utile",
        help_text="True = utile, False = pas utile"
    )

    class Meta:
        verbose_name = "Vote d'utilité"
        verbose_name_plural = "Votes d'utilité"
        unique_together = [('avis', 'touriste')]