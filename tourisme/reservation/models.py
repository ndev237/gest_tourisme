"""
reservation/models.py
======================
Modèles du cycle de vie des réservations.

Contient :
- Reservation : la réservation principale d'un touriste
- LigneReservation : détail des services réservés (pattern Order/OrderLine)
- BonReservation : ticket d'entrée avec QR Code (généré après paiement)
"""

import uuid
import secrets
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
from core.models import TimestampedModel
from compte.models import Touriste, Guide
from catalogue.models import SiteTouristique, Hebergement


# ============================================================
# 1. RESERVATION (entité centrale du métier)
# ============================================================
class Reservation(TimestampedModel):
    """
    Réservation d'un touriste pour visiter un site.

    Une réservation est l'engagement d'un touriste à visiter un site
    à une date donnée, avec ou sans hébergement, avec ou sans guide.

    Cycle de vie :
    en_attente → confirmee → terminee
                          ↘ annulee
    """

    class Statut(models.TextChoices):
        EN_ATTENTE = 'en_attente', 'En attente de paiement'
        CONFIRMEE = 'confirmee', 'Confirmée'
        ANNULEE = 'annulee', 'Annulée'
        TERMINEE = 'terminee', 'Terminée'

    # ID UUID pour la sécurité
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    # Numéro lisible pour l'utilisateur (ex: RES-2026-00123)
    numero = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        verbose_name="N° de réservation"
    )

    # Acteurs et entités liées
    touriste = models.ForeignKey(
        Touriste,
        on_delete=models.PROTECT,
        related_name='reservation',
        verbose_name="Touriste"
    )
    site = models.ForeignKey(
        SiteTouristique,
        on_delete=models.PROTECT,
        related_name='reservation',
        verbose_name="Site touristique"
    )
    hebergement = models.ForeignKey(
        Hebergement,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reservation',
        verbose_name="Hébergement (optionnel)"
    )
    guide = models.ForeignKey(
        Guide,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reservation',
        verbose_name="Guide (optionnel)"
    )

    # Détails de la visite
    date_visite = models.DateField(
        verbose_name="Date de visite"
    )
    heure_visite = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Heure de visite"
    )
    nb_adultes = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name="Nombre d'adultes"
    )
    nb_enfants = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Nombre d'enfants"
    )

    # Hébergement (si applicable)
    date_arrivee = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date d'arrivée (hébergement)"
    )
    date_depart = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de départ (hébergement)"
    )

    # Montant et statut
    montant_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Montant total (FCFA)"
    )
    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.EN_ATTENTE,
        verbose_name="Statut"
    )

    # Données contextuelles
    notes_touriste = models.TextField(
        blank=True,
        verbose_name="Notes du touriste",
        help_text="Demandes spéciales, allergies, etc."
    )
    date_confirmation = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de confirmation"
    )
    date_annulation = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date d'annulation"
    )
    motif_annulation = models.TextField(
        blank=True,
        verbose_name="Motif d'annulation"
    )

    class Meta:
        verbose_name = "Réservation"
        verbose_name_plural = "Réservations"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['touriste', '-date_visite']),
            models.Index(fields=['site', 'date_visite']),
            models.Index(fields=['statut', 'date_visite']),
            models.Index(fields=['numero']),
        ]

    def __str__(self):
        return f"{self.numero} - {self.touriste.user.nom_complet} - {self.site.nom}"

    def save(self, *args, **kwargs):
        """Génère automatiquement le numéro de réservation."""
        if not self.numero:
            self.numero = self._generer_numero()
        super().save(*args, **kwargs)

    def _generer_numero(self):
        """Génère un numéro unique au format RES-YYYY-XXXXX."""
        annee = timezone.now().year
        prefix = settings.RESERVATION_PREFIX
        # Compte les réservations de l'année pour incrémenter
        count = Reservation.objects.filter(
            created_at__year=annee
        ).count() + 1
        return f"{prefix}-{annee}-{count:05d}"

    @property
    def nb_total_personnes(self):
        """Nombre total de personnes (adultes + enfants)."""
        return self.nb_adultes + self.nb_enfants

    @property
    def peut_etre_annulee(self):
        """
        Indique si la réservation peut être annulée gratuitement.
        Annulation gratuite uniquement avant CANCELLATION_FREE_HOURS heures.
        """
        if self.statut not in [self.Statut.EN_ATTENTE, self.Statut.CONFIRMEE]:
            return False
        delai_heures = settings.CANCELLATION_FREE_HOURS
        limite = self.date_visite - timezone.timedelta(hours=delai_heures)
        return timezone.now().date() <= limite

    @property
    def montant_remboursement(self):
        """
        Calcule le montant remboursable en cas d'annulation.
        - Avant le délai : 100% remboursé
        - Après le délai : LATE_CANCELLATION_REFUND_PERCENT (50% par défaut)
        """
        if self.peut_etre_annulee:
            return self.montant_total
        pourcentage = Decimal(settings.LATE_CANCELLATION_REFUND_PERCENT) / Decimal('100')
        return self.montant_total * pourcentage

    def calculer_montant(self):
        """Recalcule le montant total à partir des lignes de réservation."""
        total = sum(
            (ligne.sous_total for ligne in self.lignes.all()),
            Decimal('0.00')
        )
        self.montant_total = total
        return total

    def confirmer(self):
        """Marque la réservation comme confirmée (après paiement réussi)."""
        self.statut = self.Statut.CONFIRMEE
        self.date_confirmation = timezone.now()
        self.save()

    def annuler(self, motif=""):
        """Annule la réservation."""
        self.statut = self.Statut.ANNULEE
        self.date_annulation = timezone.now()
        self.motif_annulation = motif
        self.save()


# ============================================================
# 2. LIGNE RESERVATION (détail des services)
# ============================================================
class LigneReservation(TimestampedModel):
    """
    Ligne de détail d'une réservation (pattern Order/OrderLine).

    Une réservation contient plusieurs lignes :
    - Ligne 1 : visite du site (2 adultes × 5000)
    - Ligne 2 : hébergement (2 nuits × 35000)
    - Ligne 3 : guide (1 jour × 25000)
    """

    class TypeService(models.TextChoices):
        VISITE = 'visite', 'Entrée au site'
        HEBERGEMENT = 'hebergement', 'Hébergement'
        GUIDE = 'guide', 'Services de guide'
        SUPPLEMENT = 'supplement', 'Supplément'

    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name='lignes',
        verbose_name="Réservation"
    )
    type_service = models.CharField(
        max_length=20,
        choices=TypeService.choices,
        verbose_name="Type de service"
    )
    designation = models.CharField(
        max_length=200,
        verbose_name="Désignation",
        help_text="Ex: 'Entrée adulte - Plages de Kribi'"
    )
    quantite = models.PositiveSmallIntegerField(
        default=1,
        verbose_name="Quantité"
    )
    prix_unitaire = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Prix unitaire (FCFA)"
    )
    sous_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Sous-total (FCFA)"
    )

    class Meta:
        verbose_name = "Ligne de réservation"
        verbose_name_plural = "Lignes de réservation"
        ordering = ['reservation', 'type_service']

    def __str__(self):
        return f"{self.designation} ({self.quantite} × {self.prix_unitaire})"

    def save(self, *args, **kwargs):
        """Calcule automatiquement le sous-total."""
        self.sous_total = Decimal(self.quantite) * self.prix_unitaire
        super().save(*args, **kwargs)


# ============================================================
# 3. BON DE RESERVATION (ticket avec QR Code)
# ============================================================
class BonReservation(TimestampedModel):
    """
    Bon de réservation généré après confirmation du paiement.

    Contient un QR Code unique scannable à l'entrée du site
    pour valider l'arrivée du touriste.
    """
    reservation = models.OneToOneField(
        Reservation,
        on_delete=models.CASCADE,
        related_name='bon',
        verbose_name="Réservation"
    )
    qr_code_data = models.CharField(
        max_length=255,
        unique=True,
        editable=False,
        verbose_name="Données du QR Code"
    )
    qr_code_image = models.ImageField(
        upload_to='qrcodes/%Y/%m/',
        blank=True,
        null=True,
        verbose_name="Image QR Code"
    )
    pdf_fichier = models.FileField(
        upload_to='bons/%Y/%m/',
        blank=True,
        null=True,
        verbose_name="Fichier PDF"
    )
    est_utilise = models.BooleanField(
        default=False,
        verbose_name="Utilisé",
        help_text="Coché quand le QR a été scanné à l'entrée"
    )
    date_utilisation = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date d'utilisation (scan)"
    )
    scanne_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bons_scannes',
        verbose_name="Scanné par"
    )

    class Meta:
        verbose_name = "Bon de réservation"
        verbose_name_plural = "Bons de réservation"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['qr_code_data']),
            models.Index(fields=['est_utilise']),
        ]

    def __str__(self):
        return f"Bon {self.reservation.numero}"

    def save(self, *args, **kwargs):
        """Génère automatiquement le contenu unique du QR Code."""
        if not self.qr_code_data:
            self.qr_code_data = self._generer_token()
        super().save(*args, **kwargs)

    def _generer_token(self):
        """Génère un token cryptographiquement sécurisé pour le QR Code."""
        # Format : ID_RESERVATION + token aléatoire 32 caractères
        token_aleatoire = secrets.token_urlsafe(24)
        return f"{self.reservation.id}:{token_aleatoire}"

    def marquer_utilise(self, scanne_par_user=None):
        """Marque le bon comme utilisé (scan à l'entrée du site)."""
        self.est_utilise = True
        self.date_utilisation = timezone.now()
        self.scanne_par = scanne_par_user
        self.save()