"""
notifications/views.py
======================
Vues pour la cloche de notifications.

A. liste_notifications_view  : page complète "Mes notifications" avec filtres
B. marquer_lue_view          : marque UNE notification comme lue (POST)
C. marquer_toutes_lues_view  : marque toutes comme lues (POST)
D. ajax_recentes_view        : retourne en JSON les 5 dernières non lues
                                (pour rafraîchir la cloche sans reload)
"""

import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from notifications.models import Notification

logger = logging.getLogger(__name__)


@login_required
def liste_notifications_view(request):
    """Page liste complète des notifications de l'utilisateur."""
    filtre = request.GET.get('filtre', 'toutes')  # toutes / non_lues / lues
    qs = Notification.objects.filter(destinataire=request.user).select_related('reservation')

    if filtre == 'non_lues':
        qs = qs.exclude(statut=Notification.Statut.LUE)
    elif filtre == 'lues':
        qs = qs.filter(statut=Notification.Statut.LUE)

    notifications = qs.order_by('-created_at')[:100]
    nb_non_lues = Notification.objects.filter(
        destinataire=request.user,
    ).exclude(statut=Notification.Statut.LUE).count()

    return render(request, 'notifications/liste.html', {
        'notifications': notifications,
        'filtre': filtre,
        'nb_non_lues': nb_non_lues,
        'page_title': "Mes notifications",
    })


@login_required
@require_POST
def marquer_lue_view(request, notif_id):
    """Marque une notification comme lue puis redirige vers son URL d'action."""
    notif = get_object_or_404(Notification, id=notif_id, destinataire=request.user)
    notif.marquer_lue()
    return redirect(notif.url_action or 'notifications:liste')


@login_required
@require_POST
def marquer_toutes_lues_view(request):
    """Marque toutes les notifications non lues comme lues."""
    nb = (Notification.objects
        .filter(destinataire=request.user)
        .exclude(statut=Notification.Statut.LUE)
        .update(
            statut=Notification.Statut.LUE,
            date_lecture=timezone.now(),
        )
    )
    messages.success(request, f"{nb} notification{'s' if nb > 1 else ''} marquée{'s' if nb > 1 else ''} comme lue{'s' if nb > 1 else ''}.")
    return redirect('notifications:liste')


@login_required
def ajax_recentes_view(request):
    """
    Endpoint JSON pour la cloche du navbar.
    Retourne les 5 dernières notifications non lues + compteur global.
    """
    qs_non_lues = (Notification.objects
        .filter(destinataire=request.user)
        .exclude(statut=Notification.Statut.LUE)
        .order_by('-created_at')
    )

    recentes = list(qs_non_lues[:5].values(
        'id', 'type', 'sujet', 'contenu', 'url_action', 'created_at',
    ))
    for n in recentes:
        n['created_at'] = n['created_at'].isoformat()

    return JsonResponse({
        'nb_non_lues': qs_non_lues.count(),
        'recentes': recentes,
    })
