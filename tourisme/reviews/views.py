"""
reviews/views.py
================
Vues pour les avis et favoris.

ORGANISATION
A. TOURISTE — laisser/modifier/supprimer ses avis, voir ses favoris
B. ADMIN    — modérer les avis (file en attente + signalés)
C. GESTIONNAIRE — répondre aux avis sur ses sites

RÈGLE MÉTIER CLÉ
Un touriste ne peut laisser un avis que si :
1. Il a une réservation TERMINÉE sur le site
2. Il n'a pas encore d'avis sur cette réservation (OneToOne)
"""

import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from reviews.models import Avis, Favori
from reviews.forms import (
    AvisForm,
    AvisModerationForm,
    ReponseGestionnaireForm,
)
from reservation.models import Reservation

try:
    from core.models import AuditLog
except ImportError:
    AuditLog = None

logger = logging.getLogger(__name__)


# ============================================================
# Helpers
# ============================================================
def est_admin(user):
    return user.is_authenticated and getattr(user, 'type_user', None) == 'admin'


def est_gestionnaire(user):
    return user.is_authenticated and getattr(user, 'type_user', None) == 'gestionnaire'


def est_touriste(user):
    return user.is_authenticated and getattr(user, 'type_user', None) == 'touriste'


def log_action(user, action, ressource, ressource_id, request, details=None):
    """Log défensif : ne plante pas si AuditLog absent."""
    if AuditLog is None:
        return
    try:
        AuditLog.objects.create(
            utilisateur=user if user.is_authenticated else None,
            action=action,
            ressource=ressource,
            ressource_id=str(ressource_id) if ressource_id else '',
            details=details or {},
            ip_address=request.META.get('REMOTE_ADDR', ''),
        )
    except Exception:  # noqa: BLE001
        logger.exception("AuditLog failed")


# ============================================================
# A. TOURISTE — Avis
# ============================================================

@login_required
@user_passes_test(est_touriste, login_url='compte:connexion')
def add_avis_view(request, reservation_id):
    """
    Laisser un avis sur une réservation TERMINEE.
    Garantit : 1 avis maximum par réservation (OneToOne au modèle).
    """
    reservation = get_object_or_404(
        Reservation.objects.select_related('site', 'touriste__user'),
        id=reservation_id,
        touriste=request.user.profil_touriste,
    )

    # Règle 1 : visite effective
    if reservation.statut != 'terminee':
        messages.warning(
            request,
            "Vous ne pouvez laisser un avis qu'après la fin de votre visite."
        )
        return redirect('reservation:detail_reservation', reservation_id=reservation.id)

    # Règle 2 : pas d'avis déjà existant
    if hasattr(reservation, 'avis'):
        messages.info(
            request,
            "Vous avez déjà laissé un avis pour cette réservation. Vous pouvez le modifier."
        )
        return redirect('reviews:update_avis', avis_id=reservation.avis.id)

    if request.method == 'POST':
        form = AvisForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                avis = form.save(commit=False)
                avis.touriste = request.user.profil_touriste
                avis.site = reservation.site
                avis.reservation = reservation
                avis.save()
                log_action(request.user, 'create', 'Avis', avis.id, request,
                           details={'site': reservation.site.nom, 'note': avis.note})
            messages.success(
                request,
                "Merci ! Votre avis a été envoyé en modération et sera publié sous 24h."
            )
            return redirect('reviews:liste_avis')
    else:
        form = AvisForm()

    return render(request, 'review/avis/add_avis.html', {
        'form': form,
        'reservation': reservation,
        'page_title': f"Laisser un avis — {reservation.site.nom}",
    })


@login_required
@user_passes_test(est_touriste, login_url='compte:connexion')
def liste_avis_view(request):
    """Liste des avis du touriste connecté."""
    avis_list = (Avis.objects
        .filter(touriste=request.user.profil_touriste)
        .select_related('site', 'site__localisation')
        .order_by('-created_at')
    )
    return render(request, 'review/avis/liste_avis.html', {
        'avis_list': avis_list,
        'page_title': "Mes avis",
    })


@login_required
@user_passes_test(est_touriste, login_url='compte:connexion')
def update_avis_view(request, avis_id):
    """Modifier un avis (re-passe en modération)."""
    avis = get_object_or_404(
        Avis.objects.select_related('site'),
        id=avis_id,
        touriste=request.user.profil_touriste,
    )

    if request.method == 'POST':
        form = AvisForm(request.POST, instance=avis)
        if form.is_valid():
            with transaction.atomic():
                avis = form.save(commit=False)
                # Repasse en modération à chaque modif
                avis.statut_moderation = Avis.StatutModeration.EN_ATTENTE
                avis.est_visible = False
                avis.save()
                log_action(request.user, 'update', 'Avis', avis.id, request,
                           details={'site': avis.site.nom})
            messages.success(request, "Avis mis à jour. Il sera re-modéré sous 24h.")
            return redirect('reviews:liste_avis')
    else:
        form = AvisForm(instance=avis)

    return render(request, 'review/avis/update_avis.html', {
        'form': form,
        'avis': avis,
        'page_title': "Modifier mon avis",
    })


@login_required
@user_passes_test(est_touriste, login_url='compte:connexion')
def delete_avis_view(request, avis_id):
    """Supprimer un avis."""
    avis = get_object_or_404(
        Avis.objects.select_related('site'),
        id=avis_id,
        touriste=request.user.profil_touriste,
    )

    if request.method == 'POST':
        site_nom = avis.site.nom
        site = avis.site
        with transaction.atomic():
            avis.delete()
            # Recalcule la moyenne du site après suppression
            from django.db.models import Avg, Count
            stats = Avis.objects.filter(site=site, est_visible=True).aggregate(
                moyenne=Avg('note'), total=Count('id'),
            )
            site.note_moyenne = round(stats['moyenne'] or 0, 1)
            site.nombre_avis = stats['total'] or 0
            site.save(update_fields=['note_moyenne', 'nombre_avis'])
            log_action(request.user, 'delete', 'Avis', avis_id, request,
                       details={'site': site_nom})
        messages.success(request, "Votre avis a été supprimé.")
        return redirect('reviews:liste_avis')

    return render(request, 'review/avis/delete_avis.html', {
        'avis': avis,
        'page_title': "Supprimer mon avis",
    })


# ============================================================
# A. TOURISTE — Favoris
# ============================================================

@login_required
@user_passes_test(est_touriste, login_url='compte:connexion')
def liste_favori_view(request):
    """Liste des favoris du touriste connecté."""
    favoris = (Favori.objects
        .filter(touriste=request.user.profil_touriste)
        .select_related('site', 'site__localisation', 'site__localisation__region')
        .prefetch_related('site__photos')
        .order_by('-created_at')
    )
    return render(request, 'review/favori/liste_favori.html', {
        'favoris': favoris,
        'page_title': "Mes favoris",
    })


@login_required
@user_passes_test(est_touriste, login_url='compte:connexion')
def delete_favori_view(request, favori_id):
    """Retirer un favori (POST de la liste, ou page de confirmation)."""
    favori = get_object_or_404(
        Favori.objects.select_related('site'),
        id=favori_id,
        touriste=request.user.profil_touriste,
    )

    if request.method == 'POST':
        site_nom = favori.site.nom
        favori.delete()
        log_action(request.user, 'delete', 'Favori', favori_id, request,
                   details={'site': site_nom})
        messages.info(request, f"« {site_nom} » a été retiré de vos favoris.")
        return redirect('reviews:liste_favori')

    return render(request, 'review/favori/delete_favori.html', {
        'favori': favori,
        'page_title': "Retirer ce favori",
    })


# ============================================================
# B. ADMIN — Modération des avis
# ============================================================

@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def moderation_avis_view(request):
    """File des avis à modérer (en_attente + signales)."""
    avis_a_moderer = (Avis.objects
        .filter(Q(statut_moderation=Avis.StatutModeration.EN_ATTENTE) |
                Q(statut_moderation=Avis.StatutModeration.SIGNALE))
        .select_related('touriste__user', 'site')
        .order_by('-nombre_signalements', 'created_at')
    )

    stats = {
        'en_attente': Avis.objects.filter(
            statut_moderation=Avis.StatutModeration.EN_ATTENTE).count(),
        'signales': Avis.objects.filter(
            statut_moderation=Avis.StatutModeration.SIGNALE).count(),
        'total_avis': Avis.objects.count(),
        'publies': Avis.objects.filter(est_visible=True).count(),
    }

    return render(request, 'review/avis/moderation.html', {
        'avis_a_moderer': avis_a_moderer,
        'stats': stats,
        'page_title': "Modération des avis",
    })


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
@require_POST
def moderer_avis_view(request, avis_id):
    """Approuver ou rejeter un avis (depuis la file de modération)."""
    avis = get_object_or_404(Avis, id=avis_id)
    form = AvisModerationForm(request.POST)

    if not form.is_valid():
        for err in form.non_field_errors():
            messages.error(request, err)
        for field, errs in form.errors.items():
            for err in errs:
                messages.error(request, f"{field}: {err}")
        return redirect('reviews:moderation')

    decision = form.cleaned_data['decision']
    if decision == 'approuver':
        avis.approuver()
        log_action(request.user, 'update', 'Avis', avis.id, request,
                   details={'action': 'approuver'})
        messages.success(request, f"Avis approuvé et publié sur « {avis.site.nom} ».")
    else:
        motif = form.cleaned_data['motif_rejet']
        avis.rejeter(motif=motif)
        log_action(request.user, 'update', 'Avis', avis.id, request,
                   details={'action': 'rejeter', 'motif': motif})
        messages.warning(request, "Avis rejeté.")

    return redirect('reviews:moderation')


# ============================================================
# C. GESTIONNAIRE — Répondre à un avis
# ============================================================

@login_required
@user_passes_test(est_gestionnaire, login_url='compte:connexion')
def repondre_avis_view(request, avis_id):
    """Le gestionnaire d'un site peut répondre publiquement à un avis."""
    avis = get_object_or_404(
        Avis.objects.select_related('site', 'site__gestionnaire'),
        id=avis_id,
        est_visible=True,
    )

    # Sécurité : seul le gestionnaire du site peut répondre
    if avis.site.gestionnaire != request.user.profil_gestionnaire:
        messages.error(request, "Vous ne pouvez répondre qu'aux avis sur vos propres sites.")
        return redirect('compte:dashbord_gestionnaire_site')

    if request.method == 'POST':
        form = ReponseGestionnaireForm(request.POST)
        if form.is_valid():
            avis.repondre(form.cleaned_data['reponse'])
            log_action(request.user, 'update', 'Avis', avis.id, request,
                       details={'action': 'reponse_gestionnaire'})
            messages.success(request, "Votre réponse a été publiée.")
            return redirect('catalogue:detail_site', slug=avis.site.slug)
    else:
        form = ReponseGestionnaireForm(initial={'reponse': avis.reponse_gestionnaire})

    return render(request, 'review/avis/repondre.html', {
        'form': form,
        'avis': avis,
        'page_title': "Répondre à un avis",
    })


# ============================================================
# D. SIGNALER un avis (tout utilisateur connecté)
# ============================================================

@login_required
@require_POST
def signaler_avis_view(request, avis_id):
    """
    Tout utilisateur connecté peut signaler un avis.
    Si trop de signalements (>= 5), l'avis est auto-masqué.
    """
    avis = get_object_or_404(Avis, id=avis_id, est_visible=True)
    avis.signaler()
    log_action(request.user, 'create', 'SignalementAvis', avis.id, request,
               details={'site': avis.site.nom})
    messages.info(
        request,
        "Merci pour votre signalement. Notre équipe va l'examiner."
    )
    return redirect('catalogue:detail_site', slug=avis.site.slug)
