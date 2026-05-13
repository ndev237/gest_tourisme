"""
paiements/models.py
===================
Modèles de paiement.

Contient :
- MoyenPaiement : référentiel des moyens disponibles (MoMo, Orange, carte, cash)
- Paiement : transaction effective avec callback Mobile Money

⚠️ SÉCURITÉ : aucune donnée bancaire sensible n'est stockée.
Seules les références publiques (transaction ID) sont conservées.
Conformité PCI-DSS exigée pour les paiements par carte.
"""

import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from core.models import TimestampedModel
from reservation.models import Reservation


# ============================================================
# 1. MOYEN DE PAIEMENT (référentiel)
# ============================================================
class MoyenPaiement(TimestampedModel):
    """
    Moyen de paiement disponible sur la plateforme.

    Stocké en base pour pouvoir activer/désactiver dynamiquement
    un moyen sans toucher au code (utile si une API tombe en panne).
    """

    class TypeMoyen(models.TextChoices):
        MOBILE_MONEY = 'mobile_money', 'Mobile Money'
        CARTE_BANCAIRE = 'carte_bancaire', 'Carte bancaire'
        CASH = 'cash', 'Espèces (à l\'arrivée)'
        VIREMENT = 'virement', 'Virement bancaire'

    class Provider(models.TextChoices):
        MTN_MOMO = 'mtn_momo', 'MTN Mobile Money'
        ORANGE_MONEY = 'orange_money', 'Orange Money'
        FLUTTERWAVE = 'flutterwave', 'Flutterwave'
        STRIPE = 'stripe', 'Stripe'
        MANUEL = 'manuel', 'Manuel'

    libelle = models.CharField(
        max_length=80,
        unique=True,
        verbose_name="Libellé"
    )
    code = models.CharField(
        max_length=30,
        unique=True,
        verbose_name="Code interne",
        help_text="Ex: 'mtn_momo', 'orange_money', 'visa', 'cash'"
    )
    type = models.CharField(
        max_length=20,
        choices=TypeMoyen.choices,
        verbose_name="Type"
    )
    provider = models.CharField(
        max_length=30,
        choices=Provider.choices,
        verbose_name="Fournisseur (API)"
    )
    icone = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Icône (chemin ou nom)"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Description (affichée à l'utilisateur)"
    )
    instructions = models.TextField(
        blank=True,
        verbose_name="Instructions d'utilisation"
    )
    devises_supportees = models.JSONField(
        default=list,
        verbose_name="Devises supportées",
        help_text='Format: ["XAF", "EUR", "USD"]'
    )
    montant_min = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('100.00'),
        verbose_name="Montant minimum (FCFA)"
    )
    montant_max = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('5000000.00'),
        verbose_name="Montant maximum (FCFA)"
    )
    frais_pourcentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Frais en pourcentage (%)",
        help_text="Ex: 1.5 pour 1.5% de frais"
    )
    frais_fixe = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Frais fixe (FCFA)"
    )
    est_actif = models.BooleanField(
        default=True,
        verbose_name="Actif"
    )
    ordre_affichage = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Ordre d'affichage"
    )

    class Meta:
        verbose_name = "Moyen de paiement"
        verbose_name_plural = "Moyens de paiement"
        ordering = ['ordre_affichage', 'libelle']
        indexes = [
            models.Index(fields=['est_actif', 'ordre_affichage']),
        ]

    def __str__(self):
        return self.libelle

    def calculer_frais(self, montant):
        """Calcule les frais pour un montant donné."""
        montant = Decimal(str(montant))
        frais_calcules = (montant * self.frais_pourcentage / Decimal('100')) + self.frais_fixe
        return frais_calcules.quantize(Decimal('0.01'))


# ============================================================
# 2. PAIEMENT (transaction)
# ============================================================
class Paiement(TimestampedModel):
    """
    Transaction de paiement liée à une réservation.

    Une réservation peut avoir plusieurs paiements (acompte + solde,
    ou remboursements). Chaque tentative de paiement crée un enregistrement.

    Cycle de vie :
    initie → reussi → (eventuellement) rembourse
           ↘ echoue
           ↘ annule
    """

    class Statut(models.TextChoices):
        INITIE = 'initie', 'Initié'
        EN_COURS = 'en_cours', 'En cours de traitement'
        REUSSI = 'reussi', 'Réussi'
        ECHOUE = 'echoue', 'Échoué'
        ANNULE = 'annule', 'Annulé'
        REMBOURSE = 'rembourse', 'Remboursé'

    class TypeTransaction(models.TextChoices):
        PAIEMENT = 'paiement', 'Paiement'
        REMBOURSEMENT = 'remboursement', 'Remboursement'

    # ID UUID pour la sécurité
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    # Relations
    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.PROTECT,
        related_name='paiements',
        verbose_name="Réservation"
    )
    moyen = models.ForeignKey(
        MoyenPaiement,
        on_delete=models.PROTECT,
        related_name='paiements',
        verbose_name="Moyen de paiement"
    )

    # Montant et devise
    type_transaction = models.CharField(
        max_length=20,
        choices=TypeTransaction.choices,
        default=TypeTransaction.PAIEMENT,
        verbose_name="Type"
    )
    montant = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Montant (FCFA)"
    )
    devise = models.CharField(
        max_length=5,
        default='XAF',
        verbose_name="Devise"
    )
    montant_devise_origine = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Montant en devise d'origine",
        help_text="Pour les paiements en EUR/USD (touristes étrangers)"
    )
    taux_change = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Taux de change appliqué"
    )

    # Statut et identifiants externes
    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.INITIE,
        verbose_name="Statut"
    )
    reference_externe = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        verbose_name="Référence externe",
        help_text="ID retourné par MTN MoMo / Orange Money / Stripe"
    )
    reference_interne = models.CharField(
        max_length=50,
        unique=True,
        editable=False,
        verbose_name="Référence interne"
    )

    # Données Mobile Money
    numero_telephone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="N° téléphone (Mobile Money)",
        help_text="Format: 237 6XX XX XX XX"
    )

    # Dates clés
    date_paiement = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date du paiement"
    )
    date_remboursement = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date du remboursement"
    )
    date_echec = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de l'échec"
    )

    # Détails
    motif_echec = models.TextField(
        blank=True,
        verbose_name="Motif d'échec"
    )
    callback_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Données du callback",
        help_text="Réponse brute de l'API de paiement"
    )

    # Lien vers le paiement remboursé (cas de remboursement)
    paiement_origine = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='remboursements',
        verbose_name="Paiement original (si remboursement)"
    )

    class Meta:
        verbose_name = "Paiement"
        verbose_name_plural = "Paiements"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['reservations', 'statut']),
            models.Index(fields=['statut', '-created_at']),
            models.Index(fields=['reference_externe']),
            models.Index(fields=['reference_interne']),
        ]

    def __str__(self):
        return f"{self.reference_interne} - {self.montant} {self.devise} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        """Génère automatiquement la référence interne."""
        if not self.reference_interne:
            self.reference_interne = self._generer_reference()
        super().save(*args, **kwargs)

    def _generer_reference(self):
        """Génère une référence interne unique au format PAY-YYYYMMDD-XXXXX."""
        date_str = timezone.now().strftime('%Y%m%d')
        count = Paiement.objects.filter(
            created_at__date=timezone.now().date()
        ).count() + 1
        return f"PAY-{date_str}-{count:05d}"

    @property
    def est_reussi(self):
        """Indique si le paiement a réussi."""
        return self.statut == self.Statut.REUSSI

    @property
    def peut_etre_rembourse(self):
        """
        Indique si le paiement peut faire l'objet d'un remboursement.
        Conditions : statut REUSSI et type PAIEMENT (pas déjà un remboursement).
        """
        return (
            self.statut == self.Statut.REUSSI
            and self.type_transaction == self.TypeTransaction.PAIEMENT
            and not self.remboursements.filter(statut=self.Statut.REUSSI).exists()
        )

    def marquer_reussi(self, reference_externe="", callback_data=None):
        """Marque le paiement comme réussi (callback OK reçu)."""
        self.statut = self.Statut.REUSSI
        self.date_paiement = timezone.now()
        if reference_externe:
            self.reference_externe = reference_externe
        if callback_data:
            self.callback_data = callback_data
        self.save()

        # Confirme automatiquement la réservation
        if self.type_transaction == self.TypeTransaction.PAIEMENT:
            self.reservation.confirmer()

    def marquer_echoue(self, motif="", callback_data=None):
        """Marque le paiement comme échoué."""
        self.statut = self.Statut.ECHOUE
        self.date_echec = timezone.now()
        self.motif_echec = motif
        if callback_data:
            self.callback_data = callback_data
        self.save()

    def creer_remboursement(self, montant=None, motif=""):
        """Crée une transaction de remboursement liée à ce paiement."""
        if not self.peut_etre_rembourse:
            raise ValueError("Ce paiement ne peut pas être remboursé.")

        montant_a_rembourser = montant if montant else self.montant
        if montant_a_rembourser > self.montant:
            raise ValueError("Le montant remboursé ne peut excéder le montant initial.")

        remboursement = Paiement.objects.create(
            reservation=self.reservation,
            moyen=self.moyen,
            type_transaction=self.TypeTransaction.REMBOURSEMENT,
            montant=montant_a_rembourser,
            devise=self.devise,
            statut=self.Statut.INITIE,
            paiement_origine=self,
            motif_echec=motif,  # Réutilisé pour stocker le motif
        )
        return remboursement