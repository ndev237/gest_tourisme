from django.conf import settings


def paiement_settings(request):
    return {
        'PAIEMENT_MODE_MOCK': getattr(settings, 'PAIEMENT_MODE_MOCK', False),
    }


def notifications_context(request):
    """
    Expose le compteur de notifications non lues + les 5 dernières
    pour la cloche du navbar. Disponible dans TOUS les templates
    (configuré dans settings.TEMPLATES context_processors).
    """
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {'nb_notif_non_lues': 0, 'notif_recentes': []}

    try:
        from notifications.models import Notification
        qs = (Notification.objects
            .filter(destinataire=request.user)
            .exclude(statut=Notification.Statut.LUE)
            .order_by('-created_at')
        )
        return {
            'nb_notif_non_lues': qs.count(),
            'notif_recentes': list(qs[:5]),
        }
    except Exception:  # noqa: BLE001
        # Si la table n'existe pas encore (migrations pas faites), on n'affiche rien
        return {'nb_notif_non_lues': 0, 'notif_recentes': []}