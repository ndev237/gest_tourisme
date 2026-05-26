"""
localisation/views.py
=====================
Vues pour l'app localisation.

ORGANISATION :
A. PUBLIQUES
   - carte_view              : carte Leaflet de tous les sites
B. ADMIN — REGIONS
   - liste_region_view
   - add_region_view
   - update_region_view
   - delete_region_view

INITIATIVES PÉDAGOGIQUES :
1. Pour la CARTE, on sérialise les coordonnées en JSON côté serveur
   et on les injecte dans le template via `json_script`. Évite un
   appel AJAX supplémentaire (1 page = 1 requête).
2. On utilise select_related sur localisation->region pour éviter
   N+1 sur ~50 sites.
3. Blocage admin sur delete_region si des localisations utilisent
   cette région (FK PROTECT côté DB, message clair côté UI).
4. AuditLog défensif pour traçabilité.
"""

import json
import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404

from localisation.models import Region, Localisation
from localisation.forms import RegionForm

# Imports défensifs (on ne sait pas si tout est encore présent dans le projet)
try:
    from catalogue.models import SiteTouristique, Categorie
except ImportError:
    SiteTouristique = None
    Categorie = None

try:
    from core.models import AuditLog
except ImportError:
    AuditLog = None

logger = logging.getLogger(__name__)


# ============================================================
# HELPERS
# ============================================================
def get_client_ip(request):
    """IP réelle (gère X-Forwarded-For des proxys)."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_action(user, action, ressource, id_ressource='', request=None, details=None):
    """Wrapper AuditLog défensif (ne casse jamais la requête)."""
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


def est_admin(user):
    """Test pour @user_passes_test : seul l'admin gère les régions."""
    return user.is_authenticated and user.type_user == 'admin'


# ============================================================
# A. CARTE PUBLIQUE (Leaflet)
# ============================================================
def carte_view(request):
    """
    Carte interactive Leaflet de tous les sites publiés.

    PÉDAGO :
    - On filtre côté serveur (région, catégorie) via GET params.
    - On sérialise les sites en JSON et on les injecte via json_script
      (sécurité : auto-escape contre l'XSS).
    - Le template lit ensuite `JSON.parse(document.getElementById('sites-data').textContent)`
      pour alimenter les markers Leaflet.

    Pourquoi pas un endpoint AJAX séparé ?
    - 1 seule requête HTTP (perf)
    - Pas de problème CORS, pas de gestion d'erreur AJAX
    - Code plus simple à comprendre pour la soutenance
    """
    if SiteTouristique is None:
        # Sécurité : si l'app catalogue n'est pas chargée, retour gracieux
        return render(request, 'localisations/carte.html', {
            'sites_json': '[]',
            'regions': [],
            'categories': [],
            'region_active': None,
            'categorie_active': None,
            'total_sites': 0,
            'page_title': 'Carte des sites',
        })

    # ---- 1. Queryset de base : sites publiés avec coordonnées ----
    sites = (SiteTouristique.objects
        .filter(est_publie=True,
                localisation__latitude__isnull=False,
                localisation__longitude__isnull=False)
        .select_related('categorie', 'localisation', 'localisation__region')
        .prefetch_related('photos')
    )

    # ---- 2. Filtres optionnels (sidebar) ----
    region_id = request.GET.get('region')
    categorie_id = request.GET.get('categorie')
    region_active = None
    categorie_active = None

    if region_id:
        try:
            region_active = Region.objects.get(pk=region_id)
            sites = sites.filter(localisation__region=region_active)
        except (Region.DoesNotExist, ValueError):
            pass

    if categorie_id and Categorie is not None:
        try:
            categorie_active = Categorie.objects.get(pk=categorie_id)
            sites = sites.filter(categorie=categorie_active)
        except (Categorie.DoesNotExist, ValueError):
            pass

    # ---- 3. Sérialisation JSON pour Leaflet ----
    # Pédago : on ne sérialise QUE ce dont le front a besoin (perf + sécurité).
    sites_data = []
    for site in sites:
        # Photo principale (URL ou null)
        photo_url = None
        photo_principale = site.photo_principale  # Propriété du modèle
        if photo_principale and hasattr(photo_principale, 'image'):
            try:
                photo_url = photo_principale.image.url
            except Exception:
                photo_url = None

        sites_data.append({
            'id': str(site.id),  # UUID → string
            'nom': site.nom,
            'slug': site.slug,
            'categorie': site.categorie.libelle,
            'couleur': site.categorie.couleur or '#15803D',
            'ville': site.localisation.ville,
            'region': site.localisation.region.nom,
            'lat': float(site.localisation.latitude),
            'lng': float(site.localisation.longitude),
            'tarif': float(site.tarif_adulte) if site.tarif_adulte else 0,
            'note': float(site.note_moyenne) if site.note_moyenne else 0,
            'photo': photo_url,
            'description': site.description_courte or '',
            'url': f"/site/{site.slug}/",  # URL publique du détail
        })

    # ---- 4. Listes pour les filtres ----
    regions = (Region.objects
        .annotate(nb_sites=Count(
            'Localisations__site',
            filter=Q(Localisations__site__est_publie=True),
        ))
        .order_by('nom')
    )
    categories = (Categorie.objects.all().order_by('libelle')
                  if Categorie else [])

    return render(request, 'localisations/carte.html', {
        'sites_json': json.dumps(sites_data),
        'regions': regions,
        'categories': categories,
        'region_active': region_active,
        'categorie_active': categorie_active,
        'total_sites': len(sites_data),
        'page_title': 'Carte interactive des sites touristiques',
    })


# ============================================================
# A.2 PUBLIQUE — Liste des régions
# ============================================================

def liste_regions_publique_view(request):
    """
    Liste publique des 10 régions du Cameroun avec compteur de sites.
    Sert de page d'atterrissage 'Explorer par région' depuis le navbar.
    """
    # Relation : Region -> Localisations (FK) -> site (OneToOne, related_name='site')
    regions = (Region.objects
        .annotate(
            nb_sites=Count(
                'Localisations__site',
                filter=Q(Localisations__site__est_publie=True),
                distinct=True,
            )
        )
        .order_by('nom')
    )

    return render(request, 'Localisations/region/liste_publique.html', {
        'regions': regions,
        'page_title': 'Explorer le Cameroun par région',
    })


# ============================================================
# B. ADMIN — REGIONS (CRUD)
# ============================================================

@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def liste_region_view(request):
    """Liste de toutes les régions (admin)."""
    regions = (Region.objects
        .annotate(nb_localisations=Count('Localisations'))
        .order_by('nom')
    )

    # Stats globales pour le header
    stats = {
        'total': regions.count(),
        'avec_sites': sum(1 for r in regions if r.nb_localisations > 0),
    }

    return render(request, 'localisations/region/liste_region.html', {
        'regions': regions,
        'stats': stats,
        'page_title': 'Gestion des régions',
    })


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def add_region_view(request):
    """Ajouter une région (rare : 10 régions fixes au Cameroun)."""
    if request.method == 'POST':
        form = RegionForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                region = form.save()
                log_action(request.user, 'create', 'Region', region.id, request,
                           details={'nom': region.nom, 'code': region.code})
                messages.success(
                    request,
                    f"✅ Région « {region.nom} » créée avec succès."
                )
                return redirect('localisation:liste_region')
            except Exception as e:
                logger.error(f"Erreur création région : {e}", exc_info=True)
                messages.error(request, f"Erreur : {e}")
    else:
        form = RegionForm()

    return render(request, 'localisations/region/add_region.html', {
        'form': form,
        'page_title': 'Ajouter une région',
    })


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def update_region_view(request, region_id):
    """Modifier une région."""
    region = get_object_or_404(Region, id=region_id)

    if request.method == 'POST':
        form = RegionForm(request.POST, request.FILES, instance=region)
        if form.is_valid():
            try:
                form.save()
                log_action(request.user, 'update', 'Region', region.id, request)
                messages.success(request, f"✅ Région « {region.nom} » mise à jour.")
                return redirect('localisation:liste_region')
            except Exception as e:
                logger.error(f"Erreur update région : {e}", exc_info=True)
                messages.error(request, f"Erreur : {e}")
    else:
        form = RegionForm(instance=region)

    return render(request, 'localisations/region/update_region.html', {
        'form': form,
        'region': region,
        'page_title': f"Modifier : {region.nom}",
    })


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def delete_region_view(request, region_id):
    """
    Supprimer une région.

    PÉDAGO : Région est en FK PROTECT côté Localisation. Si des
    localisations l'utilisent, la DB refuserait la suppression.
    On vérifie côté Python pour AFFICHER un message clair plutôt
    que de laisser planter avec une IntegrityError.
    """
    region = get_object_or_404(Region, id=region_id)
    nb_localisations = region.Localisations.count()  # ATTENTION : majuscule (related_name)

    if request.method == 'POST':
        if nb_localisations > 0:
            messages.error(
                request,
                f"❌ Impossible de supprimer : {nb_localisations} localisation(s) "
                f"utilisent encore cette région."
            )
            return redirect('localisation:liste_region')

        try:
            nom = region.nom
            log_action(request.user, 'delete', 'Region', region.id, request,
                       details={'nom': nom})
            region.delete()
            messages.success(request, f"✅ Région « {nom} » supprimée.")
            return redirect('localisation:liste_region')
        except Exception as e:
            logger.error(f"Erreur suppression région : {e}", exc_info=True)
            messages.error(request, f"Suppression impossible : {e}")

    return render(request, 'localisations/region/delete_region.html', {
        'region': region,
        'nb_localisations': nb_localisations,
        'page_title': f"Supprimer : {region.nom}",
    })


# ============================================================
# C. GESTIONNAIRE — LOCALISATIONS (CRUD partiel : liste/détail/update)
# ============================================================
# PÉDAGO : Pas de create_ ni delete_ ici car Site.localisation est
# un OneToOneField(PROTECT). Donc :
#   - Création localisation = via add_site (transaction atomique)
#   - Suppression localisation = via delete_site (cascade)
# On ne propose ici que ce qui a du sens en standalone : voir et éditer.

def est_gestionnaire(user):
    """Test pour @user_passes_test : seul un gestionnaire validé gère ses localisations."""
    return (user.is_authenticated
            and user.type_user == 'gestionnaire'
            and hasattr(user, 'profil_gestionnaire'))


def check_localisation_ownership(localisation, user):
    """
    Vérifie qu'un gestionnaire peut accéder à une localisation.

    Règle : la localisation doit appartenir à un site dont l'user
    est le gestionnaire. On passe par la relation OneToOne reverse
    (localisation.site).
    """
    if not hasattr(user, 'profil_gestionnaire'):
        return False
    try:
        # Pédago : grâce au OneToOne, on accède au site via la
        # relation inverse `.site` (related_name='site' dans le modèle)
        site = localisation.site
        return site.gestionnaire_id == user.profil_gestionnaire.id
    except Exception:
        # Si la localisation n'a pas de site associé (orpheline), refus
        return False


@login_required
@user_passes_test(est_gestionnaire, login_url='compte:connexion')
def liste_localisation_view(request):
    """
    Liste des localisations du gestionnaire connecté.

    Une localisation = un site (OneToOne). On affiche en pratique
    "Les adresses de mes sites" avec un lien direct vers update.
    """
    gestionnaire = request.user.profil_gestionnaire

    # On parcourt les sites du gestionnaire pour récupérer leurs localisations.
    # select_related pour éviter N+1 sur localisation et region.
    if SiteTouristique is None:
        sites = []
    else:
        sites = (SiteTouristique.objects
            .filter(gestionnaire=gestionnaire)
            .select_related('localisation', 'localisation__region', 'categorie')
            .order_by('localisation__region__nom', 'localisation__ville')
        )

    # Stats par région (pour le résumé en haut)
    regions_count = {}
    for site in sites:
        if site.localisation:
            region_nom = site.localisation.region.nom
            regions_count[region_nom] = regions_count.get(region_nom, 0) + 1

    return render(request, 'localisations/localisation/liste_localisation.html', {
        'sites': sites,
        'total': len(sites),
        'regions_count': regions_count,
        'page_title': 'Mes localisations',
    })


@login_required
@user_passes_test(est_gestionnaire, login_url='compte:connexion')
def detail_localisation_view(request, localisation_id):
    """
    Détail d'une localisation avec mini-carte Leaflet (lecture seule).

    PÉDAGO :
    - On vérifie l'ownership AVANT de servir la page.
    - On injecte les coords en JSON pour Leaflet (sécurité XSS via
      json_script).
    """
    localisation = get_object_or_404(
        Localisation.objects.select_related('region'),
        id=localisation_id,
    )

    if not check_localisation_ownership(localisation, request.user):
        return HttpResponseForbidden("Cette localisation ne vous appartient pas.")

    # Site associé (OneToOne reverse)
    site = localisation.site

    # Données pour Leaflet (injectées via json_script dans le template)
    leaflet_data = {
        'lat': float(localisation.latitude),
        'lng': float(localisation.longitude),
        'nom': site.nom,
        'ville': localisation.ville,
        'region': localisation.region.nom,
    }

    return render(request, 'localisations/localisation/detail_localisation.html', {
        'localisation': localisation,
        'site': site,
        'leaflet_json': json.dumps(leaflet_data),
        'page_title': f"Localisation : {site.nom}",
    })


@login_required
@user_passes_test(est_gestionnaire, login_url='compte:connexion')
def update_localisation_view(request, localisation_id):
    """
    Édition standalone d'une localisation.

    PÉDAGO :
    - Form classique côté serveur (validation Cameroun, etc.)
    - Mais la carte Leaflet en mode "marker draggable" met à jour
      les champs latitude/longitude en JS quand l'user déplace le
      point. Côté serveur, on reçoit juste les valeurs finales.
    - Pas besoin de logique JS complexe côté serveur : il valide
      les nouveaux lat/lng exactement comme à la création.
    """
    from localisation.forms import LocalisationUpdateForm

    localisation = get_object_or_404(
        Localisation.objects.select_related('region'),
        id=localisation_id,
    )

    if not check_localisation_ownership(localisation, request.user):
        return HttpResponseForbidden("Cette localisation ne vous appartient pas.")

    site = localisation.site

    if request.method == 'POST':
        form = LocalisationUpdateForm(request.POST, instance=localisation)
        if form.is_valid():
            try:
                form.save()
                log_action(request.user, 'update', 'Localisation',
                           localisation.id, request,
                           details={'site': site.nom})
                messages.success(
                    request,
                    f"✅ Localisation de « {site.nom} » mise à jour."
                )
                return redirect('localisation:detail_localisation',
                                localisation_id=localisation.id)
            except Exception as e:
                logger.error(f"Erreur update localisation : {e}", exc_info=True)
                messages.error(request, f"Erreur : {e}")
    else:
        form = LocalisationUpdateForm(instance=localisation)

    # Données pour Leaflet (mode édition : marker draggable)
    leaflet_data = {
        'lat': float(localisation.latitude),
        'lng': float(localisation.longitude),
        'nom': site.nom,
    }

    return render(request, 'localisations/localisation/update_localisation.html', {
        'form': form,
        'localisation': localisation,
        'site': site,
        'leaflet_json': json.dumps(leaflet_data),
        'page_title': f"Modifier la localisation : {site.nom}",
    })