"""
notifications/signals.py
========================
Signaux Django qui créent automatiquement des notifications lors
d'événements métier (réservation confirmée, paiement réussi, avis approuvé…).

PRINCIPE
- post_save sur le modèle source (Reservation, Paiement, Avis)
- created=True OR changement de statut → on crée une Notification in-app
- L'envoi email/SMS effectif est laissé à un worker (placeholder ici)

POURQUOI les signaux et pas un appel direct dans la view ?
- Découplage : la view ne sait pas qu'une notification existe
- Évite d'oublier la notif dans 2 endroits différents
- Si on change le canal d'envoi, on touche un seul fichier
"""

import logging
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse

logger = logging.getLogger(__name__)


def _get_models():
    """Imports lazy pour éviter les imports circulaires au démarrage."""
    from notifications.models import Notification
    from reservation.models import Reservation
    try:
        from paiements.models import Paiement
    except ImportError:
        Paiement = None
    try:
        from reviews.models import Avis
    except ImportError:
        Avis = None
    return Notification, Reservation, Paiement, Avis


def _safe_url(name, **kwargs):
    """Retourne l'URL si elle existe, sinon une chaîne vide."""
    try:
        return reverse(name, kwargs=kwargs)
    except Exception:  # noqa: BLE001
        return ''


def _creer_notification(destinataire, type_notif, sujet, contenu, url=None, reservation=None):
    """Helper : crée une notification in-app + tente l'envoi email/SMS (placeholder)."""
    Notification, *_ = _get_models()
    try:
        notif = Notification.objects.create(
            destinataire=destinataire,
            type=type_notif,
            canal=Notification.Canal.IN_APP,
            sujet=sujet,
            contenu=contenu,
            url_action=url or '',
            reservation=reservation,
            statut=Notification.Statut.ENVOYEE,  # in-app : immédiate
            date_envoi=__import__('django.utils.timezone', fromlist=['timezone']).timezone.now(),
        )
        # TODO : brancher un vrai worker email/SMS ici (Celery + Mailgun/Twilio)
        # Pour l'instant : on log juste
        logger.info(
            "[notification] %s → %s : %s",
            type_notif, destinataire.email, sujet,
        )
        return notif
    except Exception:  # noqa: BLE001
        logger.exception("Échec création notification")
        return None


# ============================================================
# 1. RÉSERVATION : créée / confirmée / annulée
# ============================================================
def reservation_post_save(sender, instance, created, **kwargs):
    Notification, Reservation, *_ = _get_models()
    touriste_user = instance.touriste.user

    if created:
        # Nouvelle réservation
        _creer_notification(
            destinataire=touriste_user,
            type_notif=Notification.TypeNotif.RESERVATION_CREEE,
            sujet=f"Réservation {instance.numero} créée",
            contenu=(
                f"Votre réservation pour {instance.site.nom} le "
                f"{instance.date_visite:%d/%m/%Y} a bien été enregistrée. "
                "Procédez au paiement pour la confirmer."
            ),
            url=_safe_url('reservation:detail_reservation', reservation_id=instance.id),
            reservation=instance,
        )
        return

    # Mise à jour : on regarde le statut
    if instance.statut == 'confirmee':
        _creer_notification(
            destinataire=touriste_user,
            type_notif=Notification.TypeNotif.RESERVATION_CONFIRMEE,
            sujet=f"Réservation {instance.numero} confirmée",
            contenu=(
                f"Votre paiement a été reçu. Présentez le QR Code à l'entrée de "
                f"{instance.site.nom} le {instance.date_visite:%d/%m/%Y}."
            ),
            url=_safe_url('reservation:detail_reservation', reservation_id=instance.id),
            reservation=instance,
        )
        # Notifier le gestionnaire du site
        if hasattr(instance.site, 'gestionnaire'):
            _creer_notification(
                destinataire=instance.site.gestionnaire.user,
                type_notif=Notification.TypeNotif.RESERVATION_CONFIRMEE,
                sujet=f"Nouvelle réservation confirmée pour {instance.site.nom}",
                contenu=(
                    f"{touriste_user.nom_complet} a confirmé sa visite du "
                    f"{instance.date_visite:%d/%m/%Y} ({instance.nb_total_personnes} pers.)."
                ),
                url=_safe_url('reservation:reservations_gestionnaire'),
                reservation=instance,
            )
    elif instance.statut == 'annulee':
        _creer_notification(
            destinataire=touriste_user,
            type_notif=Notification.TypeNotif.RESERVATION_ANNULEE,
            sujet=f"Réservation {instance.numero} annulée",
            contenu=(
                f"Votre réservation pour {instance.site.nom} a été annulée. "
                "Le remboursement éventuel sera traité sous 5 jours ouvrés."
            ),
            url=_safe_url('reservation:detail_reservation', reservation_id=instance.id),
            reservation=instance,
        )


# ============================================================
# 2. PAIEMENT : réussi / échoué
# ============================================================
def paiement_post_save(sender, instance, created, **kwargs):
    Notification, Reservation, Paiement, *_ = _get_models()
    if Paiement is None:
        return

    touriste_user = instance.reservation.touriste.user

    if instance.statut == 'reussi' and instance.type_transaction == 'paiement':
        _creer_notification(
            destinataire=touriste_user,
            type_notif=Notification.TypeNotif.PAIEMENT_REUSSI,
            sujet=f"Paiement de {instance.montant:.0f} FCFA confirmé",
            contenu=(
                f"Votre paiement via {instance.moyen.libelle} a bien été reçu. "
                "Vous pouvez télécharger votre bon de réservation depuis votre espace."
            ),
            url=_safe_url('reservation:detail_reservation',
                          reservation_id=instance.reservation.id),
            reservation=instance.reservation,
        )
    elif instance.statut == 'echoue':
        _creer_notification(
            destinataire=touriste_user,
            type_notif=Notification.TypeNotif.PAIEMENT_ECHOUE,
            sujet="Paiement échoué",
            contenu=(
                f"Le paiement de {instance.montant:.0f} FCFA via "
                f"{instance.moyen.libelle} n'a pas pu être confirmé. "
                "Vous pouvez réessayer ou choisir un autre moyen."
            ),
            url=_safe_url('paiement:choix_moyen', reservation_id=instance.reservation.id),
            reservation=instance.reservation,
        )
    elif instance.type_transaction == 'remboursement' and instance.statut == 'reussi':
        _creer_notification(
            destinataire=touriste_user,
            type_notif=Notification.TypeNotif.REMBOURSEMENT,
            sujet=f"Remboursement de {instance.montant:.0f} FCFA initié",
            contenu=(
                "Un remboursement a été initié sur votre compte. "
                "Le délai d'apparition dépend de votre opérateur (jusqu'à 5 jours)."
            ),
            reservation=instance.reservation,
        )


# ============================================================
# 3. AVIS : approuvé / réponse gestionnaire
# ============================================================
def avis_post_save(sender, instance, created, **kwargs):
    Notification, _Reservation, _Paiement, Avis = _get_models()
    if Avis is None:
        return

    touriste_user = instance.touriste.user

    # Avis approuvé : notifier le touriste
    if instance.est_visible and instance.statut_moderation == 'approuve':
        # On évite les doublons : check si déjà notifié
        if not Notification.objects.filter(
            destinataire=touriste_user,
            type=Notification.TypeNotif.AVIS_APPROUVE,
            reservation=instance.reservation,
        ).exists():
            _creer_notification(
                destinataire=touriste_user,
                type_notif=Notification.TypeNotif.AVIS_APPROUVE,
                sujet="Votre avis a été publié",
                contenu=(
                    f"Merci ! Votre avis sur {instance.site.nom} est désormais "
                    "visible publiquement."
                ),
                url=_safe_url('catalogue:detail_site', slug=instance.site.slug),
            )

    # Nouvel avis pour le gestionnaire
    if created and hasattr(instance.site, 'gestionnaire'):
        _creer_notification(
            destinataire=instance.site.gestionnaire.user,
            type_notif=Notification.TypeNotif.AVIS_RECU,
            sujet=f"Nouvel avis ({instance.note}/5) sur {instance.site.nom}",
            contenu=(
                f"{touriste_user.nom_complet} a laissé un avis pour {instance.site.nom}. "
                "Vous pouvez y répondre depuis la fiche du site."
            ),
            url=_safe_url('catalogue:detail_site', slug=instance.site.slug),
        )

    # Réponse du gestionnaire : notifier le touriste
    if instance.reponse_gestionnaire and instance.date_reponse:
        if not Notification.objects.filter(
            destinataire=touriste_user,
            type=Notification.TypeNotif.REPONSE_GESTIONNAIRE,
            reservation=instance.reservation,
        ).exists():
            _creer_notification(
                destinataire=touriste_user,
                type_notif=Notification.TypeNotif.REPONSE_GESTIONNAIRE,
                sujet=f"Le gestionnaire de {instance.site.nom} a répondu",
                contenu=(
                    f"Une réponse a été apportée à votre avis sur "
                    f"{instance.site.nom}. Consultez-la sur la fiche du site."
                ),
                url=_safe_url('catalogue:detail_site', slug=instance.site.slug),
            )


# ============================================================
# Connexion des signaux
# ============================================================
def connect_signals():
    """Appelé depuis NotificationsConfig.ready()."""
    _Notification, Reservation, Paiement, Avis = _get_models()

    post_save.connect(reservation_post_save, sender=Reservation,
                      dispatch_uid='notif_reservation_post_save')

    if Paiement is not None:
        post_save.connect(paiement_post_save, sender=Paiement,
                          dispatch_uid='notif_paiement_post_save')

    if Avis is not None:
        post_save.connect(avis_post_save, sender=Avis,
                          dispatch_uid='notif_avis_post_save')

    logger.info("notifications.signals : signaux connectés.")
