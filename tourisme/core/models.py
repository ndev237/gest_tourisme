"""
core/models.py
==============
Modèles transverses utilisés par toutes les autres apps.

Contient :
- TimestampedModel : mixin abstrait pour created_at / updated_at
- UUIDModel : mixin abstrait pour utiliser un UUID comme clé primaire
- AuditLog : journal des actions sensibles (sécurité et traçabilité)
"""

import uuid
from django.db import models
from django.conf import settings


# ============================================================
# 1. TIMESTAMPED MODEL (mixin abstrait)
# ============================================================
class TimestampedModel(models.Model):
    """
    Mixin abstrait qui ajoute automatiquement les champs
    created_at et updated_at à tous les modèles qui en héritent.

    Toutes les tables métier hériteront de cette classe pour
    avoir un suivi temporel automatique.
    """
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création",
        help_text="Renseigné automatiquement à la création"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification",
        help_text="Mis à jour automatiquement à chaque save()"
    )

    class Meta:
        abstract = True  # IMPORTANT : ne crée PAS de table en BDD


# ============================================================
# 2. UUID MODEL (mixin pour les ressources sensibles)
# ============================================================
class UUIDModel(models.Model):
    """
    Mixin abstrait qui remplace l'ID auto-incrément par un UUID.

    Utilisé pour les ressources sensibles (Reservation, Paiement)
    pour empêcher l'énumération via URL (ex: /reservations/123, /124...).
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name="Identifiant unique"
    )

    class Meta:
        abstract = True


# ============================================================
# 3. AUDIT LOG (journal des actions sensibles)
# ============================================================
class AuditLog(TimestampedModel):
    """
    Journal des actions sensibles effectuées sur la plateforme.

    Permet de retracer "qui a fait quoi, quand, depuis quelle IP"
    pour la sécurité, la traçabilité et la résolution de litiges.
    """

    class ActionType(models.TextChoices):
        CREATE = 'create', 'Création'
        UPDATE = 'update', 'Modification'
        DELETE = 'delete', 'Suppression'
        LOGIN = 'login', 'Connexion'
        LOGOUT = 'logout', 'Déconnexion'
        VALIDATE = 'validate', 'Validation'
        REJECT = 'reject', 'Rejet'
        PAYMENT = 'payment', 'Paiement'
        REFUND = 'refund', 'Remboursement'

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        verbose_name="Utilisateur"
    )
    action = models.CharField(
        max_length=20,
        choices=ActionType.choices,
        verbose_name="Type d'action"
    )
    ressource = models.CharField(
        max_length=100,
        verbose_name="Ressource concernée",
        help_text="Ex: SiteTouristique, Reservation, Paiement"
    )
    id_ressource = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="ID de la ressource"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="Adresse IP"
    )
    user_agent = models.TextField(
        blank=True,
        verbose_name="User-Agent du navigateur"
    )
    details = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Détails supplémentaires",
        help_text="Données contextuelles au format JSON"
    )

    class Meta:
        verbose_name = "Journal d'audit"
        verbose_name_plural = "Journaux d'audit"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['utilisateur', '-created_at']),
            models.Index(fields=['ressource', 'id_ressource']),
        ]

    def __str__(self):
        return f"{self.get_action_display()} - {self.ressource} - {self.created_at}"