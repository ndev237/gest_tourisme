"""
notifications/models.py
=======================
Modèles de notifications et de messagerie.

Contient :
- Notification : notifications automatiques système → utilisateur (email/SMS/push/in-app)
- Message : messagerie manuelle utilisateur ↔ utilisateur (questions, réclamations)
- PreferencesNotification : préférences de réception par utilisateur
"""

from django.db import models
from django.conf import settings
from django.utils import timezone
from core.models import TimestampedModel
from reservation.models import Reservation


# ============================================================
# 1. NOTIFICATION (système → utilisateur)
# ============================================================
class Notification(TimestampedModel):
    """
    Notification automatique envoyée à un utilisateur.

    Différence avec Message : Notification est AUTOMATIQUE
    (système → user), Message est MANUEL (user → user).

    Canaux : email, SMS, push, in-app (visible dans la cloche du dashboard).
    """

    class TypeNotif(models.TextChoices):
        # Liées aux réservations
        RESERVATION_CREEE = 'res_creee', 'Réservation créée'
        RESERVATION_CONFIRMEE = 'res_confirmee', 'Réservation confirmée'
        RESERVATION_ANNULEE = 'res_annulee', 'Réservation annulée'
        RAPPEL_VISITE = 'rappel_visite', 'Rappel de visite (24h avant)'

        # Liées aux paiements
        PAIEMENT_REUSSI = 'paiement_reussi', 'Paiement réussi'
        PAIEMENT_ECHOUE = 'paiement_echoue', 'Paiement échoué'
        REMBOURSEMENT = 'remboursement', 'Remboursement effectué'

        # Liées aux avis
        AVIS_RECU = 'avis_recu', 'Nouvel avis reçu'
        AVIS_APPROUVE = 'avis_approuve', 'Votre avis a été approuvé'
        REPONSE_GESTIONNAIRE = 'reponse_gest', 'Réponse à votre avis'

        # Liées au compte
        COMPTE_VALIDE = 'compte_valide', 'Compte gestionnaire validé'
        COMPTE_REJETE = 'compte_rejete', 'Compte gestionnaire rejeté'
        BIENVENUE = 'bienvenue', 'Message de bienvenue'

        # Autres
        PROMOTION = 'promotion', 'Promotion / Newsletter'
        INFO = 'info', 'Information générale'

    class Canal(models.TextChoices):
        EMAIL = 'email', 'Email'
        SMS = 'sms', 'SMS'
        PUSH = 'push', 'Notification push'
        IN_APP = 'in_app', 'Notification in-app (cloche)'

    class Statut(models.TextChoices):
        EN_ATTENTE = 'en_attente', 'En attente d\'envoi'
        ENVOYEE = 'envoyee', 'Envoyée'
        ECHEC = 'echec', 'Échec d\'envoi'
        LUE = 'lue', 'Lue par le destinataire'

    # Destinataire
    destinataire = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name="Destinataire"
    )

    # Type et canal
    type = models.CharField(
        max_length=30,
        choices=TypeNotif.choices,
        verbose_name="Type"
    )
    canal = models.CharField(
        max_length=10,
        choices=Canal.choices,
        verbose_name="Canal d'envoi"
    )

    # Contenu
    sujet = models.CharField(
        max_length=200,
        verbose_name="Sujet"
    )
    contenu = models.TextField(
        verbose_name="Contenu"
    )
    url_action = models.URLField(
        max_length=500,
        blank=True,
        verbose_name="URL d'action",
        help_text="Lien vers lequel rediriger lors du clic (ex: détails de la réservation)"
    )

    # Lien optionnel vers une réservation
    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
        verbose_name="Réservation liée"
    )

    # Statut
    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.EN_ATTENTE,
        verbose_name="Statut"
    )
    date_envoi = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date d'envoi"
    )
    date_lecture = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de lecture"
    )
    motif_echec = models.TextField(
        blank=True,
        verbose_name="Motif d'échec"
    )

    # Métadonnées techniques
    metadonnees = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Métadonnées",
        help_text="Données techniques (response ID du provider email/SMS, etc.)"
    )

    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['destinataire', '-created_at']),
            models.Index(fields=['destinataire', 'statut']),
            models.Index(fields=['statut', '-created_at']),
            models.Index(fields=['canal', 'statut']),
        ]

    def __str__(self):
        return f"{self.get_type_display()} → {self.destinataire.email}"

    @property
    def est_lue(self):
        """Indique si la notification a été lue."""
        return self.statut == self.Statut.LUE

    def marquer_envoyee(self, metadonnees=None):
        """Marque la notification comme envoyée."""
        self.statut = self.Statut.ENVOYEE
        self.date_envoi = timezone.now()
        if metadonnees:
            self.metadonnees = metadonnees
        self.save()

    def marquer_lue(self):
        """Marque la notification comme lue."""
        if self.statut != self.Statut.LUE:
            self.statut = self.Statut.LUE
            self.date_lecture = timezone.now()
            self.save()

    def marquer_echec(self, motif=""):
        """Marque la notification en échec d'envoi."""
        self.statut = self.Statut.ECHEC
        self.motif_echec = motif
        self.save()


# ============================================================
# 2. MESSAGE (messagerie interne user ↔ user)
# ============================================================
class Message(TimestampedModel):
    """
    Message manuel entre deux utilisateurs (touriste ↔ gestionnaire ou guide).

    Permet de poser des questions sur un site, négocier des modalités,
    ou faire une réclamation.
    """

    class StatutMessage(models.TextChoices):
        ENVOYE = 'envoye', 'Envoyé'
        LU = 'lu', 'Lu'
        REPONDU = 'repondu', 'Répondu'

    expediteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='messages_envoyes',
        verbose_name="Expéditeur"
    )
    destinataire = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='messages_recus',
        verbose_name="Destinataire"
    )
    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='messages',
        verbose_name="Réservation liée (optionnel)"
    )

    # Threading (pour les réponses)
    message_parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='reponses',
        verbose_name="Message parent (si réponse)"
    )

    # Contenu
    sujet = models.CharField(
        max_length=200,
        verbose_name="Sujet"
    )
    corps = models.TextField(
        verbose_name="Corps du message"
    )
    piece_jointe = models.FileField(
        upload_to='messages/%Y/%m/',
        blank=True,
        null=True,
        verbose_name="Pièce jointe"
    )

    # Statut
    statut = models.CharField(
        max_length=20,
        choices=StatutMessage.choices,
        default=StatutMessage.ENVOYE,
        verbose_name="Statut"
    )
    date_lecture = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de lecture"
    )

    class Meta:
        verbose_name = "Message"
        verbose_name_plural = "Messages"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['destinataire', 'statut']),
            models.Index(fields=['expediteur', '-created_at']),
            models.Index(fields=['destinataire', '-created_at']),
            models.Index(fields=['reservations', '-created_at']),
        ]

    def __str__(self):
        return f"{self.expediteur.email} → {self.destinataire.email}: {self.sujet}"

    def marquer_lu(self):
        """Marque le message comme lu."""
        if self.statut == self.StatutMessage.ENVOYE:
            self.statut = self.StatutMessage.LU
            self.date_lecture = timezone.now()
            self.save()


# ============================================================
# 3. PREFERENCES NOTIFICATION (par utilisateur)
# ============================================================
class PreferencesNotification(TimestampedModel):
    """
    Préférences de réception des notifications par utilisateur.

    Permet à chaque user de choisir quels canaux il accepte
    pour chaque type de notification.
    """
    utilisateur = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='preferences_notification',
        verbose_name="Utilisateur"
    )

    # Notifications transactionnelles (toujours envoyées par défaut)
    reservations_email = models.BooleanField(
        default=True,
        verbose_name="Recevoir par email les notifications de réservation"
    )
    reservations_sms = models.BooleanField(
        default=False,
        verbose_name="Recevoir par SMS les notifications de réservation"
    )
    paiements_email = models.BooleanField(
        default=True,
        verbose_name="Recevoir par email les notifications de paiement"
    )
    paiements_sms = models.BooleanField(
        default=True,  # Par défaut OUI pour le SMS car critique
        verbose_name="Recevoir par SMS les notifications de paiement"
    )

    # Notifications marketing (opt-in)
    newsletter = models.BooleanField(
        default=False,
        verbose_name="Recevoir la newsletter mensuelle"
    )
    promotions = models.BooleanField(
        default=False,
        verbose_name="Recevoir les promotions et offres spéciales"
    )

    # Notifications in-app
    notifications_dashboard = models.BooleanField(
        default=True,
        verbose_name="Recevoir les notifications sur le dashboard"
    )

    class Meta:
        verbose_name = "Préférences de notification"
        verbose_name_plural = "Préférences de notification"

    def __str__(self):
        return f"Préférences de {self.utilisateur.email}"