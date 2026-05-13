"""
catalogue/views.py
==================
Vues du catalogue : accueil, liste des sites, détails.

Mix de FBV (pour la logique simple) et CBV (pour les listings avec pagination).
"""

from django.shortcuts import render, get_object_or_404
from django.views.generic import ListView
from django.db.models import Count, Avg, Q
from django.core.paginator import Paginator

from .models import SiteTouristique, Categorie, Tag
from localisation.models import Region


# ============================================================
# 1. PAGE D'ACCUEIL (FBV - simple)
# ============================================================
def accueil(request):
    """
    Page d'accueil de la plateforme.

    Affiche :
    - Hero avec barre de recherche
    - Catégories en strip
    - Sites populaires (top 6 par note)
    - Sites par région (3 régions phares)
    - Statistiques globales
    """
    # Sites populaires : note moyenne >= 4 et publiés
    sites_populaires = SiteTouristique.objects.filter(
        est_publie=True,
        note_moyenne__gte=4.0
    ).select_related(
        'categorie',
        'localisation__region',
        'gestionnaire__user'
    ).prefetch_related('photos')[:6]

    # Sites récemment ajoutés
    sites_recents = SiteTouristique.objects.filter(
        est_publie=True
    ).select_related(
        'categorie',
        'localisation__region'
    ).order_by('-created_at')[:4]

    # Toutes les catégories actives avec compte de sites
    categories = Categorie.objects.annotate(
        nb_sites=Count('sites', filter=Q(sites__est_publie=True))
    ).order_by('ordre_affichage')

    # Régions phares (avec au moins 1 site)
    regions_phares = Region.objects.annotate(
        nb_sites=Count('localisations__site', filter=Q(localisations__site__est_publie=True))
    ).filter(nb_sites__gt=0).order_by('-nb_sites')[:3]

    # Statistiques pour le bandeau
    stats = {
        'nb_sites': SiteTouristique.objects.filter(est_publie=True).count(),
        'nb_regions': Region.objects.count(),
        'nb_categories': categories.count(),
    }

    context = {
        'sites_populaires': sites_populaires,
        'sites_recents': sites_recents,
        'categories': categories,
        'regions_phares': regions_phares,
        'stats': stats,
    }
    return render(request, 'catalogue/accueil.html', context)


# ============================================================
# 2. LISTE DES SITES (CBV - avec pagination automatique)
# ============================================================
class ListeSitesView(ListView):
    """
    Liste paginée de tous les sites touristiques publiés.

    Utilise une CBV pour bénéficier de la pagination automatique.
    Gère les filtres via les paramètres GET.
    """
    model = SiteTouristique
    template_name = 'catalogue/liste_sites.html'
    context_object_name = 'sites'
    paginate_by = 12

    def get_queryset(self):
        """Construit le queryset avec les filtres appliqués."""
        queryset = SiteTouristique.objects.filter(
            est_publie=True
        ).select_related(
            'categorie',
            'localisation__region',
        ).prefetch_related('photos', 'tags')

        # Filtre par catégorie
        categorie_id = self.request.GET.get('categorie')
        if categorie_id:
            queryset = queryset.filter(categorie_id=categorie_id)

        # Filtre par région
        region_id = self.request.GET.get('region')
        if region_id:
            queryset = queryset.filter(localisation__region_id=region_id)

        # Filtre par tag
        tag_id = self.request.GET.get('tag')
        if tag_id:
            queryset = queryset.filter(tags__id=tag_id)

        # Filtre par fourchette de prix
        prix_min = self.request.GET.get('prix_min')
        prix_max = self.request.GET.get('prix_max')
        if prix_min:
            queryset = queryset.filter(tarif_adulte__gte=prix_min)
        if prix_max:
            queryset = queryset.filter(tarif_adulte__lte=prix_max)

        # Filtre par recherche textuelle
        q = self.request.GET.get('q')
        if q:
            queryset = queryset.filter(
                Q(nom__icontains=q) |
                Q(description__icontains=q) |
                Q(localisation__ville__icontains=q) |
                Q(localisation__region__nom__icontains=q)
            )

        # Tri
        tri = self.request.GET.get('tri', 'recent')
        tris_valides = {
            'recent': '-created_at',
            'populaire': '-note_moyenne',
            'prix_asc': 'tarif_adulte',
            'prix_desc': '-tarif_adulte',
            'nom': 'nom',
        }
        queryset = queryset.order_by(tris_valides.get(tri, '-created_at'))

        return queryset.distinct()

    def get_context_data(self, **kwargs):
        """Ajoute au contexte les données utiles aux filtres."""
        context = super().get_context_data(**kwargs)

        # Données pour les filtres
        context['categories'] = Categorie.objects.all().order_by('ordre_affichage')
        context['regions'] = Region.objects.all().order_by('nom')
        context['tags'] = Tag.objects.all().order_by('libelle')

        # Préserver les filtres actuels pour les liens de pagination
        context['filtres_actifs'] = {
            'categorie': self.request.GET.get('categorie', ''),
            'region': self.request.GET.get('region', ''),
            'tag': self.request.GET.get('tag', ''),
            'prix_min': self.request.GET.get('prix_min', ''),
            'prix_max': self.request.GET.get('prix_max', ''),
            'q': self.request.GET.get('q', ''),
            'tri': self.request.GET.get('tri', 'recent'),
        }

        # Compter combien de filtres sont actifs (pour afficher un badge)
        context['nb_filtres_actifs'] = sum(
            1 for v in context['filtres_actifs'].values() if v and v != 'recent'
        )

        return context


# ============================================================
# 3. DÉTAIL D'UN SITE (FBV - logique riche)
# ============================================================
def detail_site(request, slug):
    """
    Page de détail d'un site touristique.

    Affiche :
    - Galerie photos
    - Description complète
    - Localisation sur carte
    - Hébergements à proximité
    - Avis publiés
    - Formulaire de réservation latéral
    - Sites similaires
    """
    site = get_object_or_404(
        SiteTouristique.objects.select_related(
            'categorie',
            'localisation__region',
            'gestionnaire__user'
        ).prefetch_related(
            'photos',
            'tags',
            'hebergements',
            'avis',
        ),
        slug=slug,
        est_publie=True
    )

    # Incrémenter le compteur de vues (sans saturer la BDD)
    SiteTouristique.objects.filter(pk=site.pk).update(
        nombre_vues=site.nombre_vues + 1
    )

    # Avis publiés (visibles publiquement) — paginer 5 par 5
    avis_publies = site.avis.filter(
        est_visible=True
    ).select_related(
        'touriste__user'
    ).order_by('-created_at')

    paginator = Paginator(avis_publies, 5)
    page_number = request.GET.get('page_avis', 1)
    page_avis = paginator.get_page(page_number)

    # Sites similaires (même catégorie, même région) - max 4
    sites_similaires = SiteTouristique.objects.filter(
        Q(categorie=site.categorie) | Q(localisation__region=site.localisation.region),
        est_publie=True,
    ).exclude(
        pk=site.pk
    ).select_related(
        'categorie',
        'localisation__region'
    ).prefetch_related('photos').distinct()[:4]

    # Hébergements à proximité
    hebergements = site.hebergements.filter(
        est_disponible=True
    ).order_by('-etoiles', 'prix_nuit')

    # Vérifier si l'utilisateur a déjà ce site en favori
    est_favori = False
    if request.user.is_authenticated and hasattr(request.user, 'profil_touriste'):
        from reviews.models import Favori
        est_favori = Favori.objects.filter(
            touriste=request.user.profil_touriste,
            site=site
        ).exists()

    context = {
        'site': site,
        'avis_publies': page_avis,
        'sites_similaires': sites_similaires,
        'hebergements': hebergements,
        'est_favori': est_favori,
        # Statistiques détaillées des avis
        'stats_avis': site.avis.filter(est_visible=True).aggregate(
            moyenne=Avg('note'),
            moyenne_accueil=Avg('note_accueil'),
            moyenne_proprete=Avg('note_proprete'),
            moyenne_qualite_prix=Avg('note_rapport_qualite_prix'),
        ),
    }
    return render(request, 'catalogue/detail_site.html', context)


# ============================================================
# 4. SITES PAR CATÉGORIE (FBV)
# ============================================================
def sites_par_categorie(request, slug):
    """Filtre les sites par catégorie via slug."""
    categorie = get_object_or_404(Categorie, libelle__iexact=slug.replace('-', ' '))
    # Redirection vers la liste filtrée
    from django.shortcuts import redirect
    from django.urls import reverse
    url = reverse('catalogue:liste_sites')
    return redirect(f"{url}?categorie={categorie.id}")


# ============================================================
# 5. SITES PAR RÉGION (FBV)
# ============================================================
def sites_par_region(request, region_id):
    """Filtre les sites par région."""
    region = get_object_or_404(Region, pk=region_id)
    from django.shortcuts import redirect
    from django.urls import reverse
    url = reverse('catalogue:liste_sites')
    return redirect(f"{url}?region={region.id}")


# ============================================================
# 6. RECHERCHE (FBV)
# ============================================================
def recherche_sites(request):
    """Recherche textuelle dans le catalogue."""
    from django.shortcuts import redirect
    from django.urls import reverse
    q = request.GET.get('q', '')
    url = reverse('catalogue:liste_sites')
    return redirect(f"{url}?q={q}")