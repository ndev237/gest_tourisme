"""
compte/views.py
===============
Vues pour l'app compte.

ORGANISATION :
- AUTHENTIFICATION : connexion, inscription, déconnexion
- COMPTE : profil, changer password, compte suspendu
- DASHBOARDS : 4 dashboards spécifiques par type d'utilisateur
- DISPATCHER : vue qui redirige vers le bon dashboard selon type_user

INITIATIVES PÉDAGOGIQUES :
1. Vues MINCES : on délègue la logique aux forms.
2. Décorateurs `@login_required` et `@user_passes_test` pour la sécurité.
3. `@transaction.atomic` sur l'inscription : si la création du profil
   échoue, on rollback le User aussi.
4. Pattern PRG (Post-Redirect-Get) : après un POST réussi, on REDIRECT
   plutôt que de render. Évite la double soumission au refresh.
5. `update_session_auth_hash` après changement de mdp : maintient
   l'user connecté (sinon Django invalide la session).
"""

import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Sum, Q, Avg
from django.http import HttpResponseForbidden
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from compte.forms import (
    ConnexionForm, InscriptionForm,
    ProfilUserForm, ProfilTouristeForm,
    ProfilGestionnaireForm, ProfilGuideForm,
    ChangerPasswordForm,
)
from compte.models import User, Touriste, Gestionnaire, Guide, Administrateur

# Imports défensifs : les autres apps peuvent ne pas encore être migrées
try:
    from reservation.models import Reservation
except ImportError:  # pragma: no cover
    Reservation = None

try:
    from catalogue.models import SiteTouristique
except ImportError:  # pragma: no cover
    SiteTouristique = None

try:
    from core.models import AuditLog
except ImportError:  # pragma: no cover
    AuditLog = None

logger = logging.getLogger(__name__)


# ============================================================
# HELPERS
# ============================================================
def get_client_ip(request):
    """Récupère l'IP réelle du client (gère X-Forwarded-For)."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_action(user, action, ressource, id_ressource='', request=None, details=None):
    """Wrapper de création d'AuditLog (DRY) — défensif si l'app core n'est pas dispo."""
    if AuditLog is None:
        return
    try:
        AuditLog.objects.create(
            utilisateur=user if user and user.is_authenticated else None,
            action=action,
            ressource=ressource,
            id_ressource=str(id_ressource),
            ip_address=get_client_ip(request) if request else None,
            user_agent=request.META.get('HTTP_USER_AGENT', '') if request else '',
            details=details or {},
        )
    except Exception as e:
        logger.warning(f"Échec audit log : {e}")


def get_dashboard_url(user):
    """
    Retourne l'URL du dashboard adapté au type d'user.

    Pédago : fonction centralisée pour le routage post-connexion.
    Si on ajoute un type d'user demain, on modifie 1 seul endroit.
    """
    mapping = {
        'touriste': 'compte:dashbord_touriste',
        'gestionnaire': 'compte:dashbord_gestionnaire_site',
        'guide': 'compte:dashbord_guide',
        'admin': 'compte:dashbord_admin',
    }
    return reverse(mapping.get(user.type_user, 'catalogue:accueil'))


# ============================================================
# TESTS D'AUTORISATION (pour @user_passes_test)
# ============================================================
def est_touriste(user):
    return user.is_authenticated and user.type_user == 'touriste'


def est_gestionnaire(user):
    return user.is_authenticated and user.type_user == 'gestionnaire'


def est_guide(user):
    return user.is_authenticated and user.type_user == 'guide'


def est_admin(user):
    return user.is_authenticated and user.type_user == 'admin'


def paginer(request, queryset, par_page=6):
    """
    Pagine un queryset (6 éléments/page par défaut) en respectant ?page=N.

    Pédago : Paginator.get_page() est tolérant — une page invalide
    (non numérique ou hors borne) retombe sur une page valide plutôt
    que de lever une exception. On affiche ainsi toujours quelque chose.
    """
    paginator = Paginator(queryset, par_page)
    return paginator.get_page(request.GET.get('page'))


# ============================================================
# A. AUTHENTIFICATION
# ============================================================

def connexion_view(request):
    """
    Connexion par email + mot de passe.

    Pédago : si user déjà connecté, on redirige vers son dashboard
    (évite qu'il voie la page de connexion par erreur).
    """
    # Si déjà connecté → redirect vers dashboard
    if request.user.is_authenticated:
        return redirect(get_dashboard_url(request.user))

    if request.method == 'POST':
        form = ConnexionForm(request.POST, request=request)
        if form.is_valid():
            user = form.get_user()

            # ---- Connexion Django (crée la session) ----
            login(request, user)

            # ---- "Se souvenir de moi" : durée de session ----
            if form.cleaned_data.get('remember_me'):
                # 30 jours
                request.session.set_expiry(60 * 60 * 24 * 30)
            else:
                # Expire à la fermeture du navigateur
                request.session.set_expiry(0)

            # ---- Audit log ----
            log_action(user, 'login', 'User', user.id, request)

            # ---- Vérification statut (gestionnaire/guide rejeté) ----
            if user.type_user == 'gestionnaire':
                if hasattr(user, 'profil_gestionnaire'):
                    if user.profil_gestionnaire.statut_validation == 'rejete':
                        return redirect('compte:compte_suspendu')
            elif user.type_user == 'guide':
                if hasattr(user, 'profil_guide'):
                    if user.profil_guide.statut_validation == 'rejete':
                        return redirect('compte:compte_suspendu')

            messages.success(request, f"Bienvenue {user.first_name or user.email} ! 👋")

            # ---- Redirection : ?next= ou dashboard ----
            # Pédago : ?next=/page-protegee/ est mis automatiquement par
            # @login_required quand un user non connecté tente d'accéder à
            # une vue protégée. On le respecte pour une UX fluide.
            next_url = request.GET.get('next') or request.POST.get('next')
            if next_url and next_url.startswith('/'):  # sécurité : URL relative seulement
                return redirect(next_url)
            return redirect(get_dashboard_url(user))
    else:
        form = ConnexionForm(request=request)

    return render(request, 'controle/connexion.html', {
        'form': form,
        'page_title': 'Connexion',
    })


def inscription_view(request):
    """
    Inscription d'un nouvel utilisateur (touriste/gestionnaire/guide).

    Pédago : @transaction.atomic garantit que si la création du profil
    échoue, le User est aussi rollback. Pas d'user orphelin sans profil.
    """
    if request.user.is_authenticated:
        return redirect(get_dashboard_url(request.user))

    if request.method == 'POST':
        form = InscriptionForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save()
                log_action(user, 'create', 'User', user.id, request,
                           details={'type': user.type_user})

                # Connexion automatique après inscription
                login(request, user)

                # Message adapté selon le type
                if user.type_user == 'touriste':
                    messages.success(
                        request,
                        f"✅ Bienvenue {user.first_name} ! Votre compte est créé."
                    )
                else:
                    messages.info(
                        request,
                        f"✅ Votre compte est créé. "
                        f"Notre équipe va valider votre profil sous 48h."
                    )

                return redirect(get_dashboard_url(user))

            except Exception as e:
                logger.error(f"Erreur inscription : {e}", exc_info=True)
                messages.error(request, "Erreur lors de la création du compte. Réessayez.")
    else:
        # Préremplir le type depuis l'URL : /inscription/?type=gestionnaire
        initial = {}
        if request.GET.get('type') in ['touriste', 'gestionnaire', 'guide']:
            initial['type_user'] = request.GET.get('type')
        form = InscriptionForm(initial=initial)

    return render(request, 'controle/inscription.html', {
        'form': form,
        'page_title': 'Inscription',
    })


@login_required
def deconnexion_view(request):
    """Déconnexion (POST uniquement pour la sécurité CSRF)."""
    if request.method == 'POST':
        user_id = request.user.id
        log_action(request.user, 'logout', 'User', user_id, request)
        logout(request)
        messages.info(request, "Vous êtes déconnecté. À bientôt ! 👋")
        return redirect('catalogue:accueil')

    # GET : page de confirmation (optionnelle, on peut aussi POST direct)
    return redirect('catalogue:accueil')


# ============================================================
# B. GESTION DU COMPTE
# ============================================================

@login_required
def profil_view(request):
    """Affichage du profil (tous les onglets dans le même template)."""
    return render(request, 'controle/profil.html', {
        'page_title': 'Mon profil',
    })


@login_required
def profil_update_view(request):
    """
    Modification du profil — multi-sections selon `section` POST.

    Le template profil.html a plusieurs forms (un par onglet), chacun
    avec un champ caché <input name="section" value="infos|touriste|...">
    On dispatch ici selon la section.
    """
    if request.method != 'POST':
        return redirect('compte:profil')

    section = request.POST.get('section', '')
    user = request.user

    # ----- SECTION INFOS (commune à tous) -----
    if section == 'infos':
        form = ProfilUserForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            log_action(user, 'update', 'User', user.id, request,
                       details={'section': 'infos'})
            messages.success(request, "✅ Informations mises à jour.")
        else:
            for field, errors in form.errors.items():
                messages.error(request, f"{field} : {errors[0]}")

    # ----- SECTION TOURISTE -----
    elif section == 'touriste' and user.type_user == 'touriste':
        form = ProfilTouristeForm(request.POST, instance=user.profil_touriste)
        if form.is_valid():
            form.save()
            log_action(user, 'update', 'Touriste', user.profil_touriste.id, request)
            messages.success(request, "✅ Profil touriste mis à jour.")
        else:
            for field, errors in form.errors.items():
                messages.error(request, f"{field} : {errors[0]}")

    # ----- SECTION GESTIONNAIRE -----
    elif section == 'gestionnaire' and user.type_user == 'gestionnaire':
        form = ProfilGestionnaireForm(request.POST, instance=user.profil_gestionnaire)
        if form.is_valid():
            form.save()
            log_action(user, 'update', 'Gestionnaire', user.profil_gestionnaire.id, request)
            messages.success(request, "✅ Profil entreprise mis à jour.")
        else:
            for field, errors in form.errors.items():
                messages.error(request, f"{field} : {errors[0]}")

    # ----- SECTION GUIDE -----
    elif section == 'guide' and user.type_user == 'guide':
        form = ProfilGuideForm(request.POST, instance=user.profil_guide)
        if form.is_valid():
            form.save()
            log_action(user, 'update', 'Guide', user.profil_guide.id, request)
            messages.success(request, "✅ Profil guide mis à jour.")
        else:
            for field, errors in form.errors.items():
                messages.error(request, f"{field} : {errors[0]}")

    else:
        messages.error(request, "Section inconnue.")

    return redirect('compte:profil')


@login_required
def changer_password_view(request):
    """Changement du mot de passe."""
    if request.method == 'POST':
        form = ChangerPasswordForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            # Pédago : update_session_auth_hash MAINTIENT l'user connecté
            # après changement de mdp. Sans ça, Django invalide la session.
            update_session_auth_hash(request, request.user)
            log_action(request.user, 'update', 'User', request.user.id, request,
                       details={'action': 'change_password'})
            messages.success(request, "✅ Mot de passe mis à jour.")
            return redirect('compte:profil')
    else:
        form = ChangerPasswordForm(user=request.user)

    return render(request, 'controle/changer_password.html', {
        'form': form,
        'page_title': 'Changer mon mot de passe',
    })


@login_required
def compte_suspendu_view(request):
    """
    Page affichée quand le compte est suspendu/rejeté.

    Pédago : on affiche le motif si dispo (transparence avec l'user).
    """
    user = request.user
    motif = None
    motif_rejet = None

    if user.type_user == 'gestionnaire' and hasattr(user, 'profil_gestionnaire'):
        if user.profil_gestionnaire.statut_validation == 'rejete':
            motif = 'rejete'
            motif_rejet = user.profil_gestionnaire.motif_rejet
        elif user.profil_gestionnaire.statut_validation == 'en_attente':
            motif = 'en_attente'

    elif user.type_user == 'guide' and hasattr(user, 'profil_guide'):
        if user.profil_guide.statut_validation == 'rejete':
            motif = 'rejete'

    return render(request, 'controle/compte_suspendu.html', {
        'motif': motif,
        'motif_rejet': motif_rejet,
        'page_title': 'Compte suspendu',
    })


# ============================================================
# C. DASHBOARDS (un par type d'utilisateur)
# ============================================================

@login_required
@user_passes_test(est_touriste, login_url='compte:connexion')
def dashbord_touriste_view(request):
    """
    Dashboard touriste : prochaines visites, stats, recommandations.
    """
    user = request.user
    touriste = user.profil_touriste

    # ---- Stats personnelles ----
    stats = {
        'total': 0,
        'a_venir': 0,
        'depenses': 0,
        'points': touriste.points_fidelite,
    }

    prochaines_reservations = []
    avis_a_laisser = []

    if Reservation:
        aujourd_hui = timezone.now().date()
        toutes_resa = Reservation.objects.filter(touriste=touriste)

        stats_agg = toutes_resa.aggregate(
            total=Count('id'),
            a_venir=Count('id', filter=Q(
                date_visite__gte=aujourd_hui,
                statut__in=['en_attente', 'confirmee'],
            )),
            depenses=Sum('montant_total', filter=Q(
                statut__in=['confirmee', 'terminee'],
            )),
        )
        stats.update({
            'total': stats_agg['total'] or 0,
            'a_venir': stats_agg['a_venir'] or 0,
            'depenses': stats_agg['depenses'] or 0,
        })

        # Prochaines visites
        prochaines_reservations = (toutes_resa
            .filter(date_visite__gte=aujourd_hui,
                    statut__in=['en_attente', 'confirmee'])
            .select_related('site')
            .order_by('date_visite')[:3]
        )

        # Visites terminées sans avis (s'il existe une FK avis→reservation)
        # Pédago : on essaie .exclude(avis__isnull=False) mais on est défensif
        # car le related_name peut ne pas exister encore.
        try:
            avis_a_laisser = (toutes_resa
                .filter(statut='terminee')
                .exclude(avis__isnull=False)
                .select_related('site')[:3]
            )
        except Exception:
            avis_a_laisser = []

    # ---- Sites recommandés (basique : 4 derniers publiés) ----
    sites_recommandes = []
    if SiteTouristique:
        try:
            sites_recommandes = (SiteTouristique.objects
                .filter(est_publie=True)
                .order_by('-created_at')[:4]
            )
        except Exception:
            sites_recommandes = []

    return render(request, 'controle/dashbord_touriste.html', {
        'stats': stats,
        'prochaines_reservations': prochaines_reservations,
        'sites_recommandes': sites_recommandes,
        'avis_a_laisser': avis_a_laisser,
        'page_title': 'Mon espace',
    })


@login_required
@user_passes_test(est_gestionnaire, login_url='compte:connexion')
def dashbord_gestionnaire_view(request):
    """
    Dashboard gestionnaire (F-GES-01) : KPIs revenus + réservations récentes.
    """
    user = request.user
    gestionnaire = user.profil_gestionnaire

    stats = {
        'resa_mois': 0,
        'revenu_mois': 0,
        'taux_occupation': 0,
        'note_moyenne': 0,
        'nb_avis': 0,
    }
    dernieres_reservations = []
    mes_sites = []

    if SiteTouristique:
        # Sites du gestionnaire
        mes_sites_qs = SiteTouristique.objects.filter(gestionnaire=gestionnaire)
        mes_sites = mes_sites_qs[:5]

        if Reservation:
            # Réservations du mois en cours
            debut_mois = timezone.now().replace(day=1).date()
            resa_mois_qs = Reservation.objects.filter(
                site__gestionnaire=gestionnaire,
                created_at__date__gte=debut_mois,
            )

            stats_agg = resa_mois_qs.aggregate(
                resa_mois=Count('id'),
                revenu_mois=Sum('montant_total', filter=Q(statut__in=['confirmee', 'terminee'])),
            )
            stats['resa_mois'] = stats_agg['resa_mois'] or 0
            stats['revenu_mois'] = stats_agg['revenu_mois'] or 0

            # Dernières réservations (top 10)
            dernieres_reservations = (Reservation.objects
                .filter(site__gestionnaire=gestionnaire)
                .select_related('site', 'touriste__user')
                .order_by('-created_at')[:10]
            )

    return render(request, 'controle/dashbord_gestionnaire_site.html', {
        'stats': stats,
        'dernieres_reservations': dernieres_reservations,
        'mes_sites': mes_sites,
        'page_title': 'Dashboard gestionnaire',
    })


@login_required
@user_passes_test(est_guide, login_url='compte:connexion')
def dashbord_guide_view(request):
    """Dashboard guide : missions, demandes en attente."""
    user = request.user
    guide = user.profil_guide

    stats = {
        'missions_mois': 0,
        'revenu_mois': 0,
        'total_missions': 0,
        'nb_avis': 0,
        'demandes_attente': 0,
    }
    prochaines_missions = []
    demandes_attente = []

    # Pédago : les missions sont liées via Reservation.guide (FK).
    # On extrait les réservations où ce guide est assigné.
    if Reservation:
        try:
            aujourd_hui = timezone.now().date()
            debut_mois = timezone.now().replace(day=1).date()

            missions_qs = Reservation.objects.filter(guide=guide)
            stats['total_missions'] = missions_qs.count()
            stats['missions_mois'] = missions_qs.filter(
                created_at__date__gte=debut_mois,
            ).count()

            stats['revenu_mois'] = missions_qs.filter(
                statut__in=['confirmee', 'terminee'],
                created_at__date__gte=debut_mois,
            ).aggregate(total=Sum('montant_total'))['total'] or 0

            prochaines_missions = (missions_qs
                .filter(date_visite__gte=aujourd_hui, statut='confirmee')
                .select_related('site')
                .order_by('date_visite')[:5]
            )

            demandes_attente = (missions_qs
                .filter(statut='en_attente')
                .select_related('site', 'touriste__user')[:5]
            )
            stats['demandes_attente'] = demandes_attente.count() if hasattr(demandes_attente, 'count') else len(demandes_attente)

        except Exception as e:
            logger.warning(f"Stats guide: {e}")

    return render(request, 'controle/dashbord_guide.html', {
        'stats': stats,
        'prochaines_missions': prochaines_missions,
        'demandes_attente': demandes_attente,
        'page_title': 'Dashboard guide',
    })


@login_required
@user_passes_test(est_guide, login_url='compte:connexion')
def planning_guide_view(request):
    """
    Planning mensuel du guide : grille calendrier 7 colonnes
    montrant les jours libres et les jours réservés (avec touriste + tél).

    Pedago :
    - Param GET 'mois' au format 'YYYY-MM' (par défaut : mois courant).
    - On regroupe les réservations confirmees/en_attente du mois par
      `date_visite` dans un dict {date -> [reservations]}.
    - Le template itère sur calendar.monthcalendar() (matrice de semaines).
    """
    import calendar
    from datetime import date as _date

    guide = request.user.profil_guide

    # --- Mois affiché ---
    mois_param = (request.GET.get('mois') or '').strip()
    today = timezone.now().date()
    try:
        annee, mois = (int(x) for x in mois_param.split('-'))
        if not (1 <= mois <= 12) or not (2000 <= annee <= 2100):
            raise ValueError
    except (ValueError, AttributeError):
        annee, mois = today.year, today.month

    premier_du_mois = _date(annee, mois, 1)
    dernier_jour = calendar.monthrange(annee, mois)[1]
    dernier_du_mois = _date(annee, mois, dernier_jour)

    # --- Mois précédent / suivant ---
    if mois == 1:
        mois_prec = f"{annee-1}-12"
    else:
        mois_prec = f"{annee}-{mois-1:02d}"
    if mois == 12:
        mois_suiv = f"{annee+1}-01"
    else:
        mois_suiv = f"{annee}-{mois+1:02d}"

    # --- Réservations du mois ---
    missions_mois = []
    missions_par_jour = {}
    if Reservation:
        try:
            missions_mois = (Reservation.objects
                .filter(
                    guide=guide,
                    date_visite__gte=premier_du_mois,
                    date_visite__lte=dernier_du_mois,
                    statut__in=['confirmee', 'en_attente'],
                )
                .select_related('site', 'touriste__user')
                .order_by('date_visite', 'heure_visite'))

            for m in missions_mois:
                missions_par_jour.setdefault(m.date_visite, []).append(m)
        except Exception as e:
            logger.warning(f"Planning guide: {e}")

    # --- Grille calendrier ---
    # calendar.monthcalendar -> liste de semaines, chaque semaine = 7 entiers
    # (0 = jour appartenant au mois précédent/suivant)
    # On enrichit avec les missions pour faciliter l'affichage.
    cal = calendar.Calendar(firstweekday=0)  # 0 = lundi
    grille = []
    for semaine in cal.monthdayscalendar(annee, mois):
        ligne = []
        for jour_num in semaine:
            if jour_num == 0:
                ligne.append(None)  # hors mois
            else:
                d = _date(annee, mois, jour_num)
                ligne.append({
                    'date': d,
                    'jour': jour_num,
                    'is_today': d == today,
                    'is_past': d < today,
                    'missions': missions_par_jour.get(d, []),
                })
        grille.append(ligne)

    # --- KPIs du mois ---
    nb_jours_reserves = len(missions_par_jour)
    nb_jours_libres = dernier_jour - nb_jours_reserves

    nom_mois_fr = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                   'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']

    return render(request, 'controle/planning_guide.html', {
        'grille': grille,
        'missions_mois': missions_mois,
        'annee': annee,
        'mois': mois,
        'nom_mois': nom_mois_fr[mois - 1],
        'mois_prec': mois_prec,
        'mois_suiv': mois_suiv,
        'mois_courant': f"{today.year}-{today.month:02d}",
        'nb_jours_total': dernier_jour,
        'nb_jours_reserves': nb_jours_reserves,
        'nb_jours_libres': nb_jours_libres,
        'nb_missions': len(missions_mois),
        'page_title': f"Mon planning — {nom_mois_fr[mois-1]} {annee}",
    })


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def dashbord_admin_view(request):
    """Dashboard admin : KPIs globaux + validations + modération."""
    # ---- KPIs globaux ----
    stats = {
        'nb_users': User.objects.count(),
        'nb_touristes': Touriste.objects.count(),
        'nb_gestionnaires': Gestionnaire.objects.count(),
        'nb_guides': Guide.objects.count(),
        'nb_admins': Administrateur.objects.count(),
        'nb_sites': 0,
        'nb_sites_total': 0,
        'nb_resa': 0,
        'nb_resa_mois': 0,
        'revenu_global': 0,
        'total_en_attente': 0,
    }

    # Nouveaux users cette semaine
    debut_semaine = timezone.now() - timezone.timedelta(days=7)
    stats['nouveaux_users_semaine'] = User.objects.filter(
        date_inscription__gte=debut_semaine,
    ).count()

    if SiteTouristique:
        stats['nb_sites_total'] = SiteTouristique.objects.count()
        try:
            stats['nb_sites'] = SiteTouristique.objects.filter(est_publie=True).count()
        except Exception:
            pass

    if Reservation:
        try:
            debut_mois = timezone.now().replace(day=1).date()
            agg = Reservation.objects.aggregate(
                nb=Count('id'),
                nb_mois=Count('id', filter=Q(created_at__date__gte=debut_mois)),
                revenu=Sum('montant_total', filter=Q(statut__in=['confirmee', 'terminee'])),
            )
            stats['nb_resa'] = agg['nb'] or 0
            stats['nb_resa_mois'] = agg['nb_mois'] or 0
            stats['revenu_global'] = agg['revenu'] or 0
        except Exception:
            pass

    # ---- Validations en attente ----
    gestionnaires_attente = Gestionnaire.objects.filter(
        statut_validation='en_attente',
    ).select_related('user').order_by('-created_at')[:10]

    guides_attente = Guide.objects.filter(
        statut_validation='en_attente',
    ).select_related('user').order_by('-created_at')[:10]

    stats['total_en_attente'] = gestionnaires_attente.count() + guides_attente.count()

    # ---- Audit log (dernières actions) ----
    dernieres_actions = []
    if AuditLog:
        try:
            dernieres_actions = (AuditLog.objects
                .select_related('utilisateur')
                .order_by('-created_at')[:10]
            )
        except Exception:
            pass

    # ---- Avis signalés (placeholder : tableau vide si pas encore implémenté) ----
    avis_signales = []

    return render(request, 'controle/dashbord_admin.html', {
        'stats': stats,
        'gestionnaires_attente': gestionnaires_attente,
        'guides_attente': guides_attente,
        'avis_signales': avis_signales,
        'dernieres_actions': dernieres_actions,
        'page_title': 'Administration',
    })


# ============================================================
# D. GESTION ADMIN DES UTILISATEURS — interne (sans backoffice Django)
# ============================================================

@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def admin_liste_utilisateurs(request):
    """Liste de TOUS les utilisateurs avec filtres."""
    q = request.GET.get('q', '').strip()
    type_filter = request.GET.get('type', '').strip()

    qs = User.objects.all().order_by('-date_inscription')
    if q:
        qs = qs.filter(
            Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
        )
    if type_filter in ('touriste', 'gestionnaire', 'guide', 'admin'):
        qs = qs.filter(type_user=type_filter)

    total = qs.count()
    page_obj = paginer(request, qs)
    return render(request, 'compte/utilisateur/liste_utilisateur.html', {
        'utilisateurs': page_obj,
        'page_obj': page_obj,
        'q': q,
        'type_filter': type_filter,
        'total': total,
        'page_title': 'Utilisateurs',
    })


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def admin_liste_touristes(request):
    """Liste des touristes."""
    q = request.GET.get('q', '').strip()
    qs = Touriste.objects.select_related('user').order_by('-created_at')
    if q:
        qs = qs.filter(
            Q(user__email__icontains=q)
            | Q(user__first_name__icontains=q)
            | Q(user__last_name__icontains=q)
            | Q(nationalite__icontains=q)
        )
    total = qs.count()
    page_obj = paginer(request, qs)
    return render(request, 'compte/touriste/liste_touriste.html', {
        'touristes': page_obj, 'page_obj': page_obj, 'q': q,
        'total': total,
        'page_title': 'Touristes',
    })


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def admin_liste_gestionnaires(request):
    """Liste des gestionnaires avec filtre statut."""
    q = request.GET.get('q', '').strip()
    statut = request.GET.get('statut', '').strip()
    qs = Gestionnaire.objects.select_related('user').order_by('-created_at')
    if q:
        qs = qs.filter(
            Q(entreprise__icontains=q)
            | Q(num_registre_commerce__icontains=q)
            | Q(user__email__icontains=q)
        )
    if statut in ('en_attente', 'valide', 'rejete'):
        qs = qs.filter(statut_validation=statut)
    total = qs.count()
    page_obj = paginer(request, qs)
    return render(request, 'compte/gestionnaire/liste_gestionnaire.html', {
        'gestionnaires': page_obj, 'page_obj': page_obj, 'q': q, 'statut_filter': statut,
        'total': total,
        'page_title': 'Gestionnaires',
    })


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def admin_liste_guides(request):
    """Liste des guides avec filtre statut."""
    q = request.GET.get('q', '').strip()
    statut = request.GET.get('statut', '').strip()
    qs = Guide.objects.select_related('user').order_by('-created_at')
    if q:
        qs = qs.filter(
            Q(licence_pro__icontains=q)
            | Q(user__email__icontains=q)
            | Q(user__first_name__icontains=q)
            | Q(user__last_name__icontains=q)
        )
    if statut in ('en_attente', 'valide', 'rejete'):
        qs = qs.filter(statut_validation=statut)
    total = qs.count()
    page_obj = paginer(request, qs)
    return render(request, 'compte/guide/liste_guide.html', {
        'guides': page_obj, 'page_obj': page_obj, 'q': q, 'statut_filter': statut,
        'total': total,
        'page_title': 'Guides',
    })


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def admin_liste_administrateurs(request):
    """Liste des administrateurs."""
    qs = Administrateur.objects.select_related('user').order_by('-created_at')
    total = qs.count()
    page_obj = paginer(request, qs)
    return render(request, 'compte/admin/liste_admin.html', {
        'admins': page_obj,
        'page_obj': page_obj,
        'total': total,
        'page_title': 'Administrateurs',
    })


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
@require_POST
def admin_valider_gestionnaire(request, gestionnaire_id):
    """Approuve un gestionnaire en attente."""
    g = get_object_or_404(Gestionnaire, id=gestionnaire_id)
    if g.statut_validation == 'en_attente':
        g.statut_validation = 'valide'
        g.date_validation = timezone.now()
        try:
            g.admin_valideur = request.user.profil_admin
        except Exception:  # noqa: BLE001
            pass
        g.save()
        log_action(request.user, 'update', 'Gestionnaire', g.id, request,
                   details={'action': 'valider', 'entreprise': g.entreprise})
        messages.success(request, f"Gestionnaire « {g.entreprise} » validé.")
    return redirect('compte:admin_liste_gestionnaires')


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
@require_POST
def admin_rejeter_gestionnaire(request, gestionnaire_id):
    """Rejette un gestionnaire en attente."""
    g = get_object_or_404(Gestionnaire, id=gestionnaire_id)
    motif = request.POST.get('motif', '').strip()
    if g.statut_validation == 'en_attente':
        g.statut_validation = 'rejete'
        g.motif_rejet = motif or 'Non précisé'
        g.save()
        log_action(request.user, 'update', 'Gestionnaire', g.id, request,
                   details={'action': 'rejeter', 'motif': motif})
        messages.warning(request, f"Gestionnaire « {g.entreprise} » rejeté.")
    return redirect('compte:admin_liste_gestionnaires')


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
@require_POST
def admin_valider_guide(request, guide_id):
    """Approuve un guide en attente."""
    g = get_object_or_404(Guide, id=guide_id)
    if g.statut_validation == 'en_attente':
        g.statut_validation = 'valide'
        g.save()
        log_action(request.user, 'update', 'Guide', g.id, request,
                   details={'action': 'valider', 'nom': g.user.nom_complet})
        messages.success(request, f"Guide « {g.user.nom_complet} » validé.")
    return redirect('compte:admin_liste_guides')


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
@require_POST
def admin_rejeter_guide(request, guide_id):
    """Rejette un guide en attente."""
    g = get_object_or_404(Guide, id=guide_id)
    if g.statut_validation == 'en_attente':
        g.statut_validation = 'rejete'
        g.save()
        log_action(request.user, 'update', 'Guide', g.id, request,
                   details={'action': 'rejeter'})
        messages.warning(request, f"Guide « {g.user.nom_complet} » rejeté.")
    return redirect('compte:admin_liste_guides')


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
@require_POST
def admin_toggle_user_actif(request, user_id):
    """Active/désactive un utilisateur (suspension douce)."""
    u = get_object_or_404(User, id=user_id)
    if u == request.user:
        messages.error(request, "Vous ne pouvez pas vous désactiver vous-même.")
    else:
        u.is_active = not u.is_active
        u.save(update_fields=['is_active'])
        log_action(request.user, 'update', 'User', u.id, request,
                   details={'action': 'toggle_actif', 'now_active': u.is_active})
        if u.is_active:
            messages.success(request, f"Compte « {u.email} » réactivé.")
        else:
            messages.warning(request, f"Compte « {u.email} » suspendu.")
    return redirect('compte:admin_liste_utilisateurs')