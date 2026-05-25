"""
catalogue/views.py
==================
Vues pour l'app catalogue.

ORGANISATION (8 sections) :
A. PUBLIQUES        : accueil, liste, détail, favori AJAX
B. GESTIONNAIRE SITES : mes_sites, add, update, delete
C. GESTIONNAIRE HEBERGEMENT
D. GESTIONNAIRE PHOTO
E. GESTIONNAIRE DISPONIBILITE
F. ADMIN CATEGORIE
G. ADMIN TAG
H. HELPERS

INITIATIVES PÉDAGOGIQUES :
1. Ownership check via helper `check_site_ownership()` — DRY,
   sécurité critique : un gestionnaire ne peut modifier QUE ses sites.
2. select_related + prefetch_related — perf BDD (N+1 → 2-3 requêtes).
3. @transaction.atomic sur add_site — création atomique site+localisation
   (PROTECT sur OneToOne = on doit créer ensemble ou pas du tout).
4. Q objects + Paginator — recherche full-text + pagination préservant filtres.
5. AJAX favori (require_POST, JsonResponse) — optimistic UI côté front.
6. AuditLog systématique sur create/update/delete.
"""

import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Count, Avg, Prefetch
from django.http import JsonResponse, HttpResponseForbidden
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from catalogue.models import (
    Categorie, Tag, SiteTouristique, PhotoSite, Hebergement, Disponibilite,
)
from catalogue.forms import (
    CategorieForm, TagForm, LocalisationForm, SiteTouristiqueForm,
    PhotoSiteForm, PhotoSiteFormSet, HebergementForm, DisponibiliteForm,
    SiteFiltreForm,
)
from localisation.models import Region, Localisation

# Imports défensifs
try:
    from review.models import Favori, Avis
except ImportError:
    try:
        from reviews.models import Favori, Avis
    except ImportError:
        Favori = None
        Avis = None

try:
    from core.models import AuditLog
except ImportError:
    AuditLog = None

logger = logging.getLogger(__name__)


# ============================================================
# H. HELPERS (en haut pour visibilité)
# ============================================================
def get_client_ip(request):
    """IP réelle (gère X-Forwarded-For des proxys)."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_action(user, action, ressource, id_ressource='', request=None, details=None):
    """Wrapper AuditLog défensif."""
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
        logger.warning(f"Audit log échec : {e}")


def est_gestionnaire(user):
    """Test pour @user_passes_test."""
    return (user.is_authenticated
            and user.type_user == 'gestionnaire'
            and hasattr(user, 'profil_gestionnaire'))


def est_admin(user):
    return user.is_authenticated and user.type_user == 'admin'


def check_site_ownership(site, user):
    """
    Vérifie qu'un user est le gestionnaire propriétaire d'un site.

    Pédago : on encapsule ce check dans une fonction pour :
    1. Éviter la duplication (utilisé dans 4+ vues)
    2. Sécurité : si on oublie un check, il n'y a qu'UN endroit à corriger
    3. Tests : on peut tester la fonction en isolation
    """
    if not hasattr(user, 'profil_gestionnaire'):
        return False
    return site.gestionnaire_id == user.profil_gestionnaire.id


# ============================================================
# A. VUES PUBLIQUES
# ============================================================

def accueil_view(request):
    """
    Page d'accueil (home.html).

    Alimente le template avec :
    - 6 sites populaires (meilleure note moyenne)
    - 10 régions du Cameroun (avec compteur de sites)
    - Stats globales pour la section "stats"
    """
    # Sites populaires : publiés, avec photos, mieux notés
    sites_populaires = (SiteTouristique.objects
        .filter(est_publie=True)
        .select_related('categorie', 'localisation', 'localisation__region')
        .prefetch_related('photos')
        .order_by('-note_moyenne', '-nombre_avis')[:6]
    )

    # Régions avec nombre de sites annotés (évite la propriété qui ferait N+1)
    regions = (Region.objects
        .annotate(nb_sites=Count(
            'Localisations__site',
            filter=Q(Localisations__site__est_publie=True),
        ))
        .order_by('nom')
    )

    # Stats globales
    stats_qs = SiteTouristique.objects.filter(est_publie=True)
    stats = {
        'nb_sites': stats_qs.count(),
        'note_moyenne': stats_qs.aggregate(m=Avg('note_moyenne'))['m'] or 4.5,
        'nb_reservations': 0,  # à brancher quand reservation existera
    }

    return render(request, 'home.html', {
        'sites_populaires': sites_populaires,
        'regions': regions,
        'stats': stats,
    })


def liste_sites_view(request):
    """
    Catalogue paginé avec filtres et recherche.

    PÉDAGO :
    - On construit le queryset PROGRESSIVEMENT en empilant les filtres.
    - On utilise Q objects pour les recherches multi-champs.
    - On préserve les filtres dans les URLs de pagination (querydict).
    """
    # ---- 1. Form de filtres (lit les paramètres GET) ----
    filtre_form = SiteFiltreForm(request.GET or None)
    qs = (SiteTouristique.objects
        .filter(est_publie=True)
        .select_related('categorie', 'localisation', 'localisation__region',
                        'gestionnaire')
        .prefetch_related('photos', 'tags')
    )

    # ---- 2. Application des filtres ----
    if filtre_form.is_valid():
        data = filtre_form.cleaned_data

        # Recherche textuelle (multi-champs avec Q OR)
        if data.get('q'):
            terme = data['q']
            qs = qs.filter(
                Q(nom__icontains=terme)
                | Q(description__icontains=terme)
                | Q(description_courte__icontains=terme)
                | Q(localisation__ville__icontains=terme)
                | Q(localisation__region__nom__icontains=terme)
            )

        # Filtre par région (FK chaînée)
        if data.get('region'):
            qs = qs.filter(localisation__region=data['region'])

        # Filtre par catégorie
        if data.get('categorie'):
            qs = qs.filter(categorie=data['categorie'])

        # Plage de prix
        if data.get('prix_min'):
            qs = qs.filter(tarif_adulte__gte=data['prix_min'])
        if data.get('prix_max'):
            qs = qs.filter(tarif_adulte__lte=data['prix_max'])

        # Accessibilité PMR
        if data.get('accessible_pmr'):
            qs = qs.filter(accessibilite_pmr=True)

        # Avec hébergement (au moins 1 hébergement actif)
        if data.get('avec_hebergement'):
            qs = qs.filter(hebergements__est_disponible=True).distinct()

        # Tri
        tri = data.get('tri', '')
        if tri == 'popularite':
            qs = qs.order_by('-nombre_vues', '-nombre_avis')
        elif tri == 'prix_asc':
            qs = qs.order_by('tarif_adulte')
        elif tri == 'prix_desc':
            qs = qs.order_by('-tarif_adulte')
        elif tri == 'note':
            qs = qs.order_by('-note_moyenne')
        elif tri == 'recent':
            qs = qs.order_by('-created_at')
        else:
            qs = qs.order_by('-note_moyenne', '-nombre_avis')  # défaut

    # ---- 3. Pagination (12 sites/page) ----
    paginator = Paginator(qs, 12)
    page_num = request.GET.get('page', 1)
    sites_page = paginator.get_page(page_num)

    # ---- 4. Préserver les filtres dans les URLs de pagination ----
    # Pédago : si on ne fait pas ça, cliquer sur "Page 2" perd les filtres.
    # On retire 'page' du querystring pour pouvoir le concaténer avec la
    # nouvelle valeur dans le template : ?{{ querystring }}&page=2
    querystring = request.GET.copy()
    querystring.pop('page', None)
    querystring_str = querystring.urlencode()

    return render(request, 'catalogue/sites/liste_sites.html', {
        'sites': sites_page,
        'paginator': paginator,
        'filtre_form': filtre_form,
        'querystring': querystring_str,
        'total_resultats': paginator.count,
    })


def detail_site_view(request, slug):
    """
    Fiche détaillée d'un site (slug URL-friendly).

    Pédago : on utilise le slug (pas l'ID) car :
    1. SEO : /catalogue/site/mont-cameroun/ > /catalogue/site/abc-123-uuid/
    2. Lisible pour l'humain
    3. Pas d'énumération des IDs (sécurité légère)
    """
    site = get_object_or_404(
        SiteTouristique.objects
            .select_related('categorie', 'localisation', 'localisation__region',
                            'gestionnaire__user')
            .prefetch_related('photos', 'tags', 'hebergements'),
        slug=slug,
        est_publie=True,
    )

    # Incrémentation du compteur de vues (defer pour ne pas bloquer)
    SiteTouristique.objects.filter(pk=site.pk).update(
        nombre_vues=site.nombre_vues + 1,
    )

    # Avis visibles uniquement
    avis_list = []
    if Avis:
        try:
            avis_list = (Avis.objects
                .filter(site=site, est_visible=True)
                .select_related('touriste__user')
                .order_by('-created_at')[:10]
            )
        except Exception:
            avis_list = []

    # Vérifier si le site est en favori (pour l'utilisateur connecté)
    est_favori = False
    if request.user.is_authenticated and hasattr(request.user, 'profil_touriste') and Favori:
        try:
            est_favori = Favori.objects.filter(
                touriste=request.user.profil_touriste,
                site=site,
            ).exists()
        except Exception:
            est_favori = False

    return render(request, 'catalogue/sites/detail_site.html', {
        'site': site,
        'avis_list': avis_list,
        'est_favori': est_favori,
        'page_title': site.nom,
    })


@login_required
@require_POST
def toggle_favori_view(request, slug):
    """
    Ajoute/retire un site des favoris (AJAX).

    Pédago : POST (modifie un état) + AJAX (réponse JSON pour optimistic UI).
    """
    if not hasattr(request.user, 'profil_touriste'):
        return JsonResponse({'error': 'Seuls les touristes peuvent gérer les favoris.'},
                            status=403)
    if Favori is None:
        return JsonResponse({'error': 'Fonctionnalité indisponible'}, status=503)

    site = get_object_or_404(SiteTouristique, slug=slug, est_publie=True)
    touriste = request.user.profil_touriste

    favori, created = Favori.objects.get_or_create(
        touriste=touriste,
        site=site,
    )

    if not created:
        # Existait déjà → on retire
        favori.delete()
        action = 'retire'
        log_action(request.user, 'delete', 'Favori', site.id, request,
                   details={'site': site.nom})
    else:
        action = 'ajoute'
        log_action(request.user, 'create', 'Favori', site.id, request,
                   details={'site': site.nom})

    return JsonResponse({
        'success': True,
        'action': action,
        'est_favori': created,
    })


# ============================================================
# B. GESTIONNAIRE — SITES
# ============================================================

@login_required
@user_passes_test(est_gestionnaire, login_url='compte:connexion')
def mes_sites_view(request):
    """Liste des sites du gestionnaire connecté."""
    gestionnaire = request.user.profil_gestionnaire

    sites = (SiteTouristique.objects
        .filter(gestionnaire=gestionnaire)
        .select_related('categorie', 'localisation')
        .prefetch_related('photos')
        .order_by('-created_at')
    )

    return render(request, 'catalogue/sites/mes_sites.html', {
        'sites': sites,
        'page_title': 'Mes sites',
    })


@login_required
@user_passes_test(est_gestionnaire, login_url='compte:connexion')
def add_site_view(request):
    """
    Création d'un site : SITE + LOCALISATION dans une transaction atomique.

    PÉDAGO : votre modèle a `localisation = OneToOneField(PROTECT)`. Donc :
    - On ne peut pas créer un site SANS localisation.
    - Si la création du site échoue, on ne veut PAS de localisation orpheline.
    - Solution : @transaction.atomic → tout ou rien.
    """
    if request.user.profil_gestionnaire.statut_validation != 'valide':
        messages.warning(
            request,
            "Votre compte doit être validé avant de pouvoir créer des sites."
        )
        return redirect('compte:dashbord_gestionnaire_site')

    if request.method == 'POST':
        site_form = SiteTouristiqueForm(request.POST)
        localisation_form = LocalisationForm(request.POST)

        # Les deux forms doivent être valides (validation parallèle)
        if site_form.is_valid() and localisation_form.is_valid():
            try:
                with transaction.atomic():
                    # 1. Créer la localisation EN PREMIER (PROTECT impose
                    #    qu'elle existe avant le site)
                    localisation = localisation_form.save()

                    # 2. Créer le site en lui passant la localisation
                    site = site_form.save(commit=False)
                    site.gestionnaire = request.user.profil_gestionnaire
                    site.localisation = localisation
                    site.est_publie = False  # publication = décision admin
                    site.save()
                    # save_m2m() obligatoire après commit=False quand il y a des M2M
                    site_form.save_m2m()

                log_action(request.user, 'create', 'SiteTouristique', site.id, request,
                           details={'nom': site.nom})
                messages.success(
                    request,
                    f"✅ Site « {site.nom } » créé. Il sera visible après validation admin."
                )
                return redirect('catalogue:mes_sites')

            except Exception as e:
                logger.error(f"Erreur création site : {e}", exc_info=True)
                messages.error(request, f"Erreur lors de la création : {e}")
    else:
        site_form = SiteTouristiqueForm()
        localisation_form = LocalisationForm()

    return render(request, 'catalogue/sites/add_sites.html', {
        'site_form': site_form,
        'localisation_form': localisation_form,
        'page_title': 'Ajouter un site',
    })


@login_required
@user_passes_test(est_gestionnaire, login_url='compte:connexion')
def update_site_view(request, slug):
    """Modification d'un site (avec sa localisation)."""
    site = get_object_or_404(SiteTouristique, slug=slug)

    # SÉCURITÉ : seul le propriétaire peut modifier
    if not check_site_ownership(site, request.user):
        return HttpResponseForbidden("Ce site ne vous appartient pas.")

    if request.method == 'POST':
        site_form = SiteTouristiqueForm(request.POST, instance=site)
        localisation_form = LocalisationForm(request.POST, instance=site.localisation)

        if site_form.is_valid() and localisation_form.is_valid():
            try:
                with transaction.atomic():
                    localisation_form.save()
                    site_form.save()

                log_action(request.user, 'update', 'SiteTouristique', site.id, request)
                messages.success(request, f"✅ Site « {site.nom} » mis à jour.")
                return redirect('catalogue:mes_sites')

            except Exception as e:
                logger.error(f"Erreur update site : {e}", exc_info=True)
                messages.error(request, f"Erreur : {e}")
    else:
        site_form = SiteTouristiqueForm(instance=site)
        localisation_form = LocalisationForm(instance=site.localisation)

    return render(request, 'catalogue/sites/update_sites.html', {
        'site_form': site_form,
        'localisation_form': localisation_form,
        'site': site,
        'page_title': f"Modifier : {site.nom}",
    })


@login_required
@user_passes_test(est_gestionnaire, login_url='compte:connexion')
def delete_site_view(request, slug):
    """Suppression d'un site (avec confirmation)."""
    site = get_object_or_404(SiteTouristique, slug=slug)

    if not check_site_ownership(site, request.user):
        return HttpResponseForbidden("Ce site ne vous appartient pas.")

    if request.method == 'POST':
        nom = site.nom
        site_id = str(site.id)
        try:
            with transaction.atomic():
                # Pédago : la localisation est en PROTECT, donc on doit
                # supprimer le site d'abord, puis la localisation manuellement
                # (sinon DB error). À ce stade, plus rien ne référence la localisation.
                localisation = site.localisation
                site.delete()
                localisation.delete()

            log_action(request.user, 'delete', 'SiteTouristique', site_id, request,
                       details={'nom': nom})
            messages.success(request, f"✅ Site « {nom} » supprimé.")
            return redirect('catalogue:mes_sites')
        except Exception as e:
            logger.error(f"Erreur suppression : {e}", exc_info=True)
            messages.error(request, f"Suppression impossible : {e}")

    return render(request, 'catalogue/sites/delete_sites.html', {
        'site': site,
        'page_title': f"Supprimer : {site.nom}",
    })


# ============================================================
# C. GESTIONNAIRE — HEBERGEMENT
# ============================================================

@login_required
@user_passes_test(est_gestionnaire, login_url='compte:connexion')
def liste_hebergement_view(request, slug):
    """Liste des hébergements d'un site."""
    site = get_object_or_404(SiteTouristique, slug=slug)
    if not check_site_ownership(site, request.user):
        return HttpResponseForbidden()

    hebergements = site.hebergements.order_by('-etoiles', 'prix_nuit')

    return render(request, 'catalogue/hebergement/liste_hebergement.html', {
        'site': site,
        'hebergements': hebergements,
        'page_title': f"Hébergements de {site.nom}",
    })


@login_required
@user_passes_test(est_gestionnaire, login_url='compte:connexion')
def add_hebergement_view(request, slug):
    """Ajouter un hébergement à un site."""
    site = get_object_or_404(SiteTouristique, slug=slug)
    if not check_site_ownership(site, request.user):
        return HttpResponseForbidden()

    if request.method == 'POST':
        form = HebergementForm(request.POST, request.FILES)
        if form.is_valid():
            hebergement = form.save(commit=False)
            hebergement.site = site
            hebergement.save()
            log_action(request.user, 'create', 'Hebergement', hebergement.id, request)
            messages.success(request, f"✅ Hébergement « {hebergement.nom} » ajouté.")
            return redirect('catalogue:liste_hebergement', slug=site.slug)
    else:
        form = HebergementForm()

    return render(request, 'catalogue/hebergement/add_hebergement.html', {
        'form': form,
        'site': site,
        'page_title': f"Ajouter un hébergement à {site.nom}",
    })


@login_required
@user_passes_test(est_gestionnaire, login_url='compte:connexion')
def update_hebergement_view(request, hebergement_id):
    """Modifier un hébergement."""
    hebergement = get_object_or_404(Hebergement, id=hebergement_id)
    if not check_site_ownership(hebergement.site, request.user):
        return HttpResponseForbidden()

    if request.method == 'POST':
        form = HebergementForm(request.POST, request.FILES, instance=hebergement)
        if form.is_valid():
            form.save()
            log_action(request.user, 'update', 'Hebergement', hebergement.id, request)
            messages.success(request, "✅ Hébergement mis à jour.")
            return redirect('catalogue:liste_hebergement', slug=hebergement.site.slug)
    else:
        form = HebergementForm(instance=hebergement)

    return render(request, 'catalogue/hebergement/update_hebergement.html', {
        'form': form,
        'hebergement': hebergement,
        'site': hebergement.site,
        'page_title': f"Modifier : {hebergement.nom}",
    })


@login_required
@user_passes_test(est_gestionnaire, login_url='compte:connexion')
def delete_hebergement_view(request, hebergement_id):
    """Supprimer un hébergement."""
    hebergement = get_object_or_404(Hebergement, id=hebergement_id)
    if not check_site_ownership(hebergement.site, request.user):
        return HttpResponseForbidden()

    site_slug = hebergement.site.slug

    if request.method == 'POST':
        nom = hebergement.nom
        log_action(request.user, 'delete', 'Hebergement', hebergement.id, request,
                   details={'nom': nom})
        hebergement.delete()
        messages.success(request, f"✅ Hébergement « {nom } » supprimé.")
        return redirect('catalogue:liste_hebergement', slug=site_slug)

    return render(request, 'catalogue/hebergement/delete_hebergement.html', {
        'hebergement': hebergement,
        'page_title': f"Supprimer : {hebergement.nom}",
    })


# ============================================================
# D. GESTIONNAIRE — PHOTOS
# ============================================================

@login_required
@user_passes_test(est_gestionnaire, login_url='compte:connexion')
def liste_photosite_view(request, slug):
    """Galerie photos d'un site."""
    site = get_object_or_404(SiteTouristique, slug=slug)
    if not check_site_ownership(site, request.user):
        return HttpResponseForbidden()

    photos = site.photos.order_by('ordre', 'created_at')

    return render(request, 'catalogue/photosite/liste_photosite.html', {
        'site': site,
        'photos': photos,
        'page_title': f"Photos de {site.nom}",
    })


@login_required
@user_passes_test(est_gestionnaire, login_url='compte:connexion')
def add_photosite_view(request, slug):
    """Ajouter une photo à la galerie."""
    site = get_object_or_404(SiteTouristique, slug=slug)
    if not check_site_ownership(site, request.user):
        return HttpResponseForbidden()

    if request.method == 'POST':
        form = PhotoSiteForm(request.POST, request.FILES)
        if form.is_valid():
            photo = form.save(commit=False)
            photo.site = site
            photo.save()
            log_action(request.user, 'create', 'PhotoSite', photo.id, request)
            messages.success(request, "✅ Photo ajoutée.")
            return redirect('catalogue:liste_photosite', slug=site.slug)
    else:
        form = PhotoSiteForm()

    return render(request, 'catalogue/photosite/add_photosite.html', {
        'form': form,
        'site': site,
        'page_title': f"Ajouter une photo à {site.nom}",
    })


@login_required
@user_passes_test(est_gestionnaire, login_url='compte:connexion')
def update_photosite_view(request, photo_id):
    """Modifier une photo."""
    photo = get_object_or_404(PhotoSite, id=photo_id)
    if not check_site_ownership(photo.site, request.user):
        return HttpResponseForbidden()

    if request.method == 'POST':
        form = PhotoSiteForm(request.POST, request.FILES, instance=photo)
        if form.is_valid():
            form.save()
            messages.success(request, "✅ Photo mise à jour.")
            return redirect('catalogue:liste_photosite', slug=photo.site.slug)
    else:
        form = PhotoSiteForm(instance=photo)

    return render(request, 'catalogue/photosite/update_photosite.html', {
        'form': form,
        'photo': photo,
        'site': photo.site,
        'page_title': "Modifier la photo",
    })


@login_required
@user_passes_test(est_gestionnaire, login_url='compte:connexion')
def delete_photosite_view(request, photo_id):
    """Supprimer une photo."""
    photo = get_object_or_404(PhotoSite, id=photo_id)
    if not check_site_ownership(photo.site, request.user):
        return HttpResponseForbidden()

    site_slug = photo.site.slug

    if request.method == 'POST':
        photo.delete()
        messages.success(request, "✅ Photo supprimée.")
        return redirect('catalogue:liste_photosite', slug=site_slug)

    return render(request, 'catalogue/photosite/delete_photosite.html', {
        'photo': photo,
        'page_title': "Supprimer la photo",
    })


# ============================================================
# E. GESTIONNAIRE — DISPONIBILITES
# ============================================================

@login_required
@user_passes_test(est_gestionnaire, login_url='compte:connexion')
def liste_disponibilite_view(request, slug):
    """Calendrier des disponibilités d'un site."""
    site = get_object_or_404(SiteTouristique, slug=slug)
    if not check_site_ownership(site, request.user):
        return HttpResponseForbidden()

    disponibilites = (site.disponibilites
        .order_by('date')
        .filter(date__gte=timezone.now().date())  # Futur uniquement
    )

    return render(request, 'catalogue/disponibilite/liste_disponibilite.html', {
        'site': site,
        'disponibilites': disponibilites,
        'page_title': f"Disponibilités de {site.nom}",
    })


@login_required
@user_passes_test(est_gestionnaire, login_url='compte:connexion')
def add_disponibilite_view(request, slug):
    """Ajouter une disponibilité (jour J)."""
    site = get_object_or_404(SiteTouristique, slug=slug)
    if not check_site_ownership(site, request.user):
        return HttpResponseForbidden()

    if request.method == 'POST':
        form = DisponibiliteForm(request.POST)
        # Force le site (sécurité + UX : l'user n'a pas à choisir)
        post = request.POST.copy()
        post['site'] = site.id
        form = DisponibiliteForm(post)

        if form.is_valid():
            try:
                dispo = form.save()
                log_action(request.user, 'create', 'Disponibilite', dispo.id, request)
                messages.success(
                    request,
                    f"✅ Disponibilité créée pour le {dispo.date.strftime('%d/%m/%Y')}."
                )
                return redirect('catalogue:liste_disponibilite', slug=site.slug)
            except Exception as e:
                messages.error(request, f"Erreur : {e}")
    else:
        form = DisponibiliteForm(initial={'site': site, 'places_restantes': site.capacite_max})

    return render(request, 'catalogue/disponibilite/add_disponibilite.html', {
        'form': form,
        'site': site,
        'page_title': "Ajouter une disponibilité",
    })


@login_required
@user_passes_test(est_gestionnaire, login_url='compte:connexion')
def update_disponibilite_view(request, dispo_id):
    """Modifier une disponibilité."""
    dispo = get_object_or_404(Disponibilite, id=dispo_id)

    # Trouver le site associé (site ou hébergement.site)
    site = dispo.site or (dispo.hebergement.site if dispo.hebergement else None)
    if not site or not check_site_ownership(site, request.user):
        return HttpResponseForbidden()

    if request.method == 'POST':
        form = DisponibiliteForm(request.POST, instance=dispo)
        if form.is_valid():
            form.save()
            log_action(request.user, 'update', 'Disponibilite', dispo.id, request)
            messages.success(request, "✅ Disponibilité mise à jour.")
            return redirect('catalogue:liste_disponibilite', slug=site.slug)
    else:
        form = DisponibiliteForm(instance=dispo)

    return render(request, 'catalogue/disponibilite/update_disponibilite.html', {
        'form': form,
        'dispo': dispo,
        'site': site,
        'page_title': "Modifier la disponibilité",
    })


@login_required
@user_passes_test(est_gestionnaire, login_url='compte:connexion')
def delete_disponibilite_view(request, dispo_id):
    """Supprimer une disponibilité."""
    dispo = get_object_or_404(Disponibilite, id=dispo_id)
    site = dispo.site or (dispo.hebergement.site if dispo.hebergement else None)
    if not site or not check_site_ownership(site, request.user):
        return HttpResponseForbidden()

    site_slug = site.slug

    if request.method == 'POST':
        dispo.delete()
        messages.success(request, "✅ Disponibilité supprimée.")
        return redirect('catalogue:liste_disponibilite', slug=site_slug)

    return render(request, 'catalogue/disponibilite/delete_disponibilite.html', {
        'dispo': dispo,
        'site': site,
        'page_title': "Supprimer la disponibilité",
    })


# ============================================================
# F. ADMIN — CATEGORIES
# ============================================================

@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def liste_categorie_view(request):
    """Liste de toutes les catégories (admin)."""
    categories = (Categorie.objects
        .annotate(nb_sites=Count('sites'))
        .order_by('ordre_affichage', 'libelle')
    )
    return render(request, 'catalogue/categorie/liste_categorie.html', {
        'categories': categories,
        'page_title': 'Gestion des catégories',
    })


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def add_categorie_view(request):
    """Ajouter une catégorie."""
    if request.method == 'POST':
        form = CategorieForm(request.POST)
        if form.is_valid():
            cat = form.save()
            log_action(request.user, 'create', 'Categorie', cat.id, request)
            messages.success(request, f"✅ Catégorie « {cat.libelle} » créée.")
            return redirect('catalogue:liste_categorie')
    else:
        form = CategorieForm()

    return render(request, 'catalogue/categorie/add_categorie.html', {
        'form': form,
        'page_title': 'Ajouter une catégorie',
    })


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def update_categorie_view(request, categorie_id):
    """Modifier une catégorie."""
    categorie = get_object_or_404(Categorie, id=categorie_id)

    if request.method == 'POST':
        form = CategorieForm(request.POST, instance=categorie)
        if form.is_valid():
            form.save()
            log_action(request.user, 'update', 'Categorie', categorie.id, request)
            messages.success(request, "✅ Catégorie mise à jour.")
            return redirect('catalogue:liste_categorie')
    else:
        form = CategorieForm(instance=categorie)

    return render(request, 'catalogue/categorie/update_categorie.html', {
        'form': form,
        'categorie': categorie,
        'page_title': f"Modifier : {categorie.libelle}",
    })


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def delete_categorie_view(request, categorie_id):
    """Supprimer une catégorie (impossible si des sites l'utilisent)."""
    categorie = get_object_or_404(Categorie, id=categorie_id)

    if request.method == 'POST':
        nb_sites = categorie.sites.count()
        if nb_sites > 0:
            messages.error(
                request,
                f"❌ Impossible de supprimer : {nb_sites} site(s) utilisent cette catégorie."
            )
        else:
            libelle = categorie.libelle
            log_action(request.user, 'delete', 'Categorie', categorie.id, request)
            categorie.delete()
            messages.success(request, f"✅ Catégorie « {libelle} » supprimée.")
        return redirect('catalogue:liste_categorie')

    return render(request, 'catalogue/categorie/delete_categorie.html', {
        'categorie': categorie,
        'nb_sites': categorie.sites.count(),
        'page_title': f"Supprimer : {categorie.libelle}",
    })


# ============================================================
# G. ADMIN — TAGS
# ============================================================

@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def liste_tag_view(request):
    """Liste de tous les tags (admin)."""
    tags = (Tag.objects
        .annotate(nb_sites=Count('sites'))
        .order_by('libelle')
    )
    return render(request, 'catalogue/tag/liste_tag.html', {
        'tags': tags,
        'page_title': 'Gestion des tags',
    })


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def add_tag_view(request):
    """Ajouter un tag."""
    if request.method == 'POST':
        form = TagForm(request.POST)
        if form.is_valid():
            tag = form.save()
            log_action(request.user, 'create', 'Tag', tag.id, request)
            messages.success(request, f"✅ Tag « {tag.libelle} » créé.")
            return redirect('catalogue:liste_tag')
    else:
        form = TagForm()

    return render(request, 'catalogue/tag/add_tag.html', {
        'form': form,
        'page_title': 'Ajouter un tag',
    })


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def update_tag_view(request, tag_id):
    """Modifier un tag."""
    tag = get_object_or_404(Tag, id=tag_id)

    if request.method == 'POST':
        form = TagForm(request.POST, instance=tag)
        if form.is_valid():
            form.save()
            log_action(request.user, 'update', 'Tag', tag.id, request)
            messages.success(request, "✅ Tag mis à jour.")
            return redirect('catalogue:liste_tag')
    else:
        form = TagForm(instance=tag)

    return render(request, 'catalogue/tag/update_tag.html', {
        'form': form,
        'tag': tag,
        'page_title': f"Modifier : {tag.libelle}",
    })


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def delete_tag_view(request, tag_id):
    """Supprimer un tag."""
    tag = get_object_or_404(Tag, id=tag_id)

    if request.method == 'POST':
        libelle = tag.libelle
        log_action(request.user, 'delete', 'Tag', tag.id, request)
        tag.delete()
        messages.success(request, f"✅ Tag « {libelle} » supprimé.")
        return redirect('catalogue:liste_tag')

    return render(request, 'catalogue/tag/delete_tag.html', {
        'tag': tag,
        'page_title': f"Supprimer : {tag.libelle}",
    })