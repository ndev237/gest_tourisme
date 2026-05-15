"""
compte/views.py
===============
Vues d'authentification, profil et tableaux de bord par type d'utilisateur.

Initiatives prises :
1. On utilise les décorateurs `@login_required` et `@user_passes_test`
   pour protéger les vues sensibles. C'est plus simple et sûr que
   de vérifier manuellement `request.user.is_authenticated`.
2. Les dashboards sont SÉPARÉS par rôle (touriste/gestionnaire/guide/admin)
   car les KPIs affichés sont très différents.
3. Audit log : chaque connexion/déconnexion est tracée (cf. cahier
   des charges §9.3 — conformité loi 2010/012 sur les données personnelles).
4. Messages flash (`messages.success`, `messages.error`) pour le feedback
   utilisateur après chaque action (UX : on confirme ou on signale l'erreur).
5. Redirection intelligente après login selon le type_user (le touriste
   va sur son dashboard touriste, le gestionnaire sur le sien, etc.).
"""

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Sum, Avg, Q
from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core.models import AuditLog
from .forms import (
    ConnexionForm, InscriptionForm, InscriptionGestionnaireForm,
    ProfilForm, ProfilTouristeForm, ChangerPasswordForm,
)
from .models import Touriste, Gestionnaire, Guide


# ============================================================
# HELPERS — fonctions utilitaires réutilisées
# ============================================================
def get_client_ip(request):
    """
    Récupère l'IP réelle du visiteur (utile derrière Nginx/reverse proxy).
    X-Forwarded-For contient la chaîne d'IPs : on prend la première.
    """
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def log_action(user, action, ressource='', ressource_id='', request=None):
    """
    Wrapper pour insérer une ligne dans AuditLog.
    On l'appelle pour les actions sensibles : connexion, paiement, etc.
    """
    AuditLog.objects.create(
        utilisateur=user,
        action=action,
        ressource=ressource,
        ressource_id=str(ressource_id) if ressource_id else '',
        ip_adresse=get_client_ip(request) if request else '',
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:300] if request else '',
    )


def redirect_dashboard(user):
    """
    Redirige l'utilisateur vers SON dashboard selon son type.
    Évite de mettre du if/else dans chaque vue.
    """
    User = user.__class__
    mapping = {
        User.UserType.TOURISTE: 'compte:dashboard_touriste',
        User.UserType.GESTIONNAIRE: 'compte:dashboard_gestionnaire',
        User.UserType.GUIDE: 'compte:dashboard_guide',
        User.UserType.ADMIN: 'compte:dashboard_admin',
    }
    return redirect(mapping.get(user.type_user, 'home'))


# ============================================================
# 1. CONNEXION
# ============================================================
@require_http_methods(["GET", "POST"])
def connexion_view(request):
    """
    Vue de connexion.

    GET  → affiche le formulaire
    POST → authentifie et redirige vers le bon dashboard.

    Sécurité :
    - Verrouillage compte après 5 échecs (à implémenter avec django-axes)
    - Compte inactif → message dédié (ex: gestionnaire en attente de validation)
    """
    # Déjà connecté ? On le renvoie vers son dashboard.
    if request.user.is_authenticated:
        return redirect_dashboard(request.user)

    if request.method == 'POST':
        form = ConnexionForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()

            # Cas 1 : compte suspendu/désactivé
            if not user.is_active:
                log_action(user, AuditLog.ActionType.LOGIN,
                           ressource='auth', request=request)
                return redirect('compte:compte_suspendu')

            # Cas 2 : gestionnaire en attente de validation
            if user.type_user == user.UserType.GESTIONNAIRE:
                profil = getattr(user, 'profil_gestionnaire', None)
                if profil and not profil.est_valide:
                    messages.warning(request,
                        "Votre compte gestionnaire est en attente de validation "
                        "par un administrateur. Vous serez notifié par email."
                    )
                    return redirect('compte:connexion')

            # Cas 3 : connexion OK
            login(request, user)
            # "Se souvenir de moi" → session de 30 jours, sinon par défaut
            if not form.cleaned_data.get('remember_me'):
                request.session.set_expiry(0)  # session fermée à la fermeture du navigateur

            log_action(user, AuditLog.ActionType.LOGIN,
                       ressource='auth', request=request)
            messages.success(request, f"Bienvenue {user.first_name} !")

            # Redirection après login : on respecte le ?next= s'il existe
            next_url = request.GET.get('next') or request.POST.get('next')
            if next_url:
                return HttpResponseRedirect(next_url)
            return redirect_dashboard(user)
    else:
        form = ConnexionForm(request)

    return render(request, 'controle/connexion.html', {
        'form': form,
        'page_title': 'Connexion',
    })


# ============================================================
# 2. INSCRIPTION
# ============================================================
@require_http_methods(["GET", "POST"])
def inscription_view(request):
    """
    Inscription publique (touriste par défaut).
    Pour s'inscrire comme gestionnaire/guide, on aura des URLs dédiées.
    """
    if request.user.is_authenticated:
        return redirect_dashboard(request.user)

    type_compte = request.GET.get('type', 'touriste')

    # On choisit dynamiquement le formulaire selon le type
    if type_compte == 'gestionnaire':
        FormClass = InscriptionGestionnaireForm
    else:
        FormClass = InscriptionForm

    if request.method == 'POST':
        form = FormClass(request.POST)
        if form.is_valid():
            user = form.save()
            log_action(user, AuditLog.ActionType.CREATE,
                       ressource='User', ressource_id=user.id, request=request)

            # Message différent selon le type
            if type_compte == 'gestionnaire':
                messages.info(request,
                    "Inscription enregistrée. Votre compte sera activé "
                    "après vérification de votre registre de commerce (24-48h)."
                )
                return redirect('compte:connexion')

            # Touriste : login automatique
            login(request, user)
            messages.success(request,
                f"Bienvenue sur Tourisme Cameroun, {user.first_name} ! "
                "Découvrez dès maintenant nos plus beaux sites."
            )
            return redirect_dashboard(user)
    else:
        form = FormClass()

    return render(request, 'controle/inscription.html', {
        'form': form,
        'type_compte': type_compte,
        'page_title': 'Inscription',
    })


# ============================================================
# 3. DÉCONNEXION
# ============================================================
@login_required
def deconnexion_view(request):
    """Déconnexion + audit log + flash message."""
    log_action(request.user, AuditLog.ActionType.LOGOUT,
               ressource='auth', request=request)
    logout(request)
    messages.success(request, "Vous avez été déconnecté avec succès.")
    return redirect('home')


# ============================================================
# 4. PROFIL UTILISATEUR
# ============================================================
@login_required
def profil_view(request):
    """
    Affiche et permet de modifier le profil de l'utilisateur connecté.
    Affiche aussi les infos spécifiques au type (touriste/gestionnaire/guide).
    """
    user = request.user

    if request.method == 'POST':
        form_user = ProfilForm(request.POST, request.FILES, instance=user)
        # Sous-formulaire selon le type
        form_profil = None
        if user.type_user == user.UserType.TOURISTE:
            touriste = getattr(user, 'profil_touriste', None)
            if touriste:
                form_profil = ProfilTouristeForm(request.POST, instance=touriste)

        if form_user.is_valid() and (form_profil is None or form_profil.is_valid()):
            form_user.save()
            if form_profil:
                form_profil.save()
            log_action(user, AuditLog.ActionType.UPDATE,
                       ressource='User', ressource_id=user.id, request=request)
            messages.success(request, "Profil mis à jour avec succès.")
            return redirect('compte:profil')
    else:
        form_user = ProfilForm(instance=user)
        form_profil = None
        if user.type_user == user.UserType.TOURISTE:
            touriste = getattr(user, 'profil_touriste', None)
            if touriste:
                form_profil = ProfilTouristeForm(instance=touriste)

    return render(request, 'controle/profil.html', {
        'form_user': form_user,
        'form_profil': form_profil,
        'page_title': 'Mon profil',
    })


# ============================================================
# 5. CHANGEMENT DE MOT DE PASSE
# ============================================================
@login_required
def changer_password_view(request):
    """
    Permet à un utilisateur connecté de changer son mot de passe.
    `update_session_auth_hash` évite que la session soit invalidée
    après le changement (sinon il faudrait se reconnecter).
    """
    if request.method == 'POST':
        form = ChangerPasswordForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # garde la session active
            log_action(user, AuditLog.ActionType.UPDATE,
                       ressource='password', request=request)
            messages.success(request,
                "Votre mot de passe a été modifié avec succès."
            )
            return redirect('compte:profil')
    else:
        form = ChangerPasswordForm(request.user)

    return render(request, 'controle/changer_password.html', {
        'form': form,
        'page_title': 'Changer mon mot de passe',
    })


# ============================================================
# 6. COMPTE SUSPENDU
# ============================================================
def compte_suspendu_view(request):
    """Page affichée quand un compte désactivé tente de se connecter."""
    return render(request, 'controle/compte_suspendu.html', {
        'page_title': 'Compte suspendu',
    })


# ============================================================
# 7. DASHBOARDS — un par type d'utilisateur
# ============================================================

# --- Décorateurs de contrôle de rôle ---
def est_touriste(user):
    return user.is_authenticated and user.type_user == user.UserType.TOURISTE

def est_gestionnaire(user):
    return user.is_authenticated and user.type_user == user.UserType.GESTIONNAIRE

def est_guide(user):
    return user.is_authenticated and user.type_user == user.UserType.GUIDE

def est_admin(user):
    return user.is_authenticated and user.type_user == user.UserType.ADMIN


@login_required
@user_passes_test(est_touriste, login_url='home')
def dashboard_touriste_view(request):
    """
    Dashboard du touriste : ses réservations, ses favoris, ses points.
    """
    user = request.user
    context = {'page_title': 'Mon espace touriste'}

    try:
        from reservation.models import Reservation
        reservations = (Reservation.objects
            .filter(touriste__user=user)
            .select_related('site', 'site__localisation')
            .order_by('-created_at')[:10]
        )
        # KPIs en haut du dashboard
        context.update({
            'reservations': reservations,
            'nb_reservations': reservations.count(),
            'nb_confirmees': reservations.filter(statut='confirmee').count(),
            'nb_terminees': reservations.filter(statut='terminee').count(),
            'points_fidelite': getattr(user.profil_touriste, 'points_fidelite', 0),
        })
    except Exception:
        context.update({
            'reservations': [], 'nb_reservations': 0,
            'nb_confirmees': 0, 'nb_terminees': 0, 'points_fidelite': 0,
        })

    return render(request, 'controle/dashbord_touriste.html', context)


@login_required
@user_passes_test(est_gestionnaire, login_url='home')
def dashboard_gestionnaire_view(request):
    """
    Dashboard gestionnaire : ses sites, réservations reçues, revenus.
    """
    user = request.user
    context = {'page_title': 'Espace gestionnaire'}

    try:
        from catalogue.models import SiteTouristique
        from reservation.models import Reservation

        # Sites publiés par ce gestionnaire
        mes_sites = SiteTouristique.objects.filter(gestionnaire__user=user)

        # Réservations sur ses sites
        reservations = (Reservation.objects
            .filter(site__in=mes_sites)
            .select_related('touriste', 'touriste__user', 'site')
            .order_by('-created_at')[:10]
        )

        # KPIs financiers
        revenus_total = (Reservation.objects
            .filter(site__in=mes_sites, statut__in=['confirmee', 'terminee'])
            .aggregate(total=Sum('montant_total'))['total'] or 0
        )

        context.update({
            'mes_sites': mes_sites,
            'nb_sites': mes_sites.count(),
            'reservations': reservations,
            'nb_reservations': Reservation.objects.filter(site__in=mes_sites).count(),
            'revenus_total': revenus_total,
            'note_moyenne': mes_sites.aggregate(n=Avg('avis__note'))['n'] or 0,
        })
    except Exception:
        context.update({
            'mes_sites': [], 'nb_sites': 0, 'reservations': [],
            'nb_reservations': 0, 'revenus_total': 0, 'note_moyenne': 0,
        })

    return render(request, 'controle/dashbord_gestionnaire_site.html', context)


@login_required
@user_passes_test(est_guide, login_url='home')
def dashboard_guide_view(request):
    """Dashboard guide : ses missions, disponibilités, revenus."""
    user = request.user
    context = {'page_title': 'Espace guide'}

    try:
        from reservation.models import Reservation
        # Missions affectées au guide (champ optionnel sur Reservation)
        missions = (Reservation.objects
            .filter(guide__user=user)
            .select_related('touriste__user', 'site')
            .order_by('-date_visite')[:10]
        )
        context.update({
            'missions': missions,
            'nb_missions': missions.count(),
            'nb_a_venir': missions.filter(
                date_visite__gte=timezone.now().date(),
                statut='confirmee'
            ).count(),
        })
    except Exception:
        context.update({'missions': [], 'nb_missions': 0, 'nb_a_venir': 0})

    return render(request, 'controle/dashbord_guide.html', context)


@login_required
@user_passes_test(est_admin, login_url='home')
def dashboard_admin_view(request):
    """
    Dashboard admin : statistiques globales de la plateforme.
    KPIs : nb utilisateurs, nb sites, CA, réservations en cours,
    gestionnaires en attente de validation, etc.
    """
    context = {'page_title': 'Tableau de bord administrateur'}

    try:
        from compte.models import User
        from catalogue.models import SiteTouristique
        from reservation.models import Reservation

        # Comptes par type
        users_par_type = (User.objects
            .values('type_user')
            .annotate(nb=Count('id'))
        )

        # Gestionnaires en attente de validation (action urgente pour l'admin)
        gestionnaires_a_valider = Gestionnaire.objects.filter(
            statut_validation='en_attente'
        ).select_related('user')[:10]

        # Top 5 sites
        top_sites = (SiteTouristique.objects
            .annotate(nb_res=Count('reservations'))
            .order_by('-nb_res')[:5]
        )

        # CA total
        ca_total = (Reservation.objects
            .filter(statut__in=['confirmee', 'terminee'])
            .aggregate(total=Sum('montant_total'))['total'] or 0
        )

        context.update({
            'nb_users_total': User.objects.count(),
            'users_par_type': users_par_type,
            'gestionnaires_a_valider': gestionnaires_a_valider,
            'nb_a_valider': gestionnaires_a_valider.count(),
            'nb_sites': SiteTouristique.objects.count(),
            'nb_reservations': Reservation.objects.count(),
            'ca_total': ca_total,
            'top_sites': top_sites,
        })
    except Exception:
        context.update({
            'nb_users_total': 0, 'users_par_type': [],
            'gestionnaires_a_valider': [], 'nb_a_valider': 0,
            'nb_sites': 0, 'nb_reservations': 0,
            'ca_total': 0, 'top_sites': [],
        })

    return render(request, 'controle/dashbord_admin.html', context)