"""
tourisme/views.py
=================
Vues globales du projet (pages publiques, erreurs).

Les vues métier sont dans chaque app : catalogue/views.py,
reservation/views.py, etc. Ici, on garde uniquement ce qui est
transverse : accueil, pages statiques, handlers d'erreurs.

Initiatives prises :
1. La page d'accueil charge dynamiquement les 6 sites les plus
   populaires (note moyenne + nombre d'avis) et les catégories
   avec leur compteur de sites — pour donner vie à la home.
2. On utilise `select_related` et `prefetch_related` pour éviter
   les requêtes N+1 (perf importante en production).
3. Les vues d'erreur retournent les bons codes HTTP (404, 500).
"""

from django.shortcuts import render
from django.db.models import Count, Avg


def home(request):
    """
    Page d'accueil publique du site.

    Affiche :
    - Hero avec barre de recherche
    - Strip des catégories (Plages, Montagnes, Parcs, etc.)
    - Grille des sites populaires (top 6 par note moyenne)
    - Section "Régions à découvrir"

    Pourquoi ce contexte ? La home doit donner envie au touriste
    de cliquer. On lui montre du contenu réel dès le premier
    chargement, pas des placeholders.
    """
    context = {
        'page_title': 'Accueil — Découvrez le Cameroun',
        # Les imports sont faits ici (et non en haut) pour éviter
        # un import circulaire si les apps ne sont pas encore chargées.
    }

    # ============================================================
    # Sites populaires (top 6) — chargement défensif
    # ============================================================
    # On enveloppe dans un try/except car la home doit fonctionner
    # même si une app n'est pas encore migrée (utile en début de projet).
    try:
        from catalogue.models import SiteTouristique, Categorie
        from localisation.models import Region

        # Les 6 sites les plus appréciés (note moyenne décroissante)
        # select_related → JOIN SQL pour récupérer la localisation
        #                  et la catégorie en une seule requête.
        # annotate → calcule la note_moyenne directement en SQL,
        #            beaucoup plus rapide que de boucler en Python.
        sites_populaires = (
            SiteTouristique.objects
            .filter(est_publie=True)
            .select_related('localisation', 'localisations__region', 'categorie')
            .prefetch_related('photos')
            .annotate(
                note_moyenne=Avg('avis__note'),
                nb_avis=Count('avis')
            )
            .order_by('-note_moyenne', '-nb_avis')[:6]
        )

        # Catégories avec compteur de sites
        categories = (
            Categorie.objects
            .annotate(nb_sites=Count('sites', filter=models_publie_filter()))
            .order_by('-nb_sites')[:6]
        )

        # 4 régions phares
        regions = Region.objects.annotate(
            nb_sites=Count('localisation__sites', distinct=True)
        ).order_by('-nb_sites')[:4]

        context.update({
            'sites_populaires': sites_populaires,
            'categories': categories,
            'regions': regions,
        })
    except Exception:
        # Si les modèles ne sont pas encore migrés, on affiche une
        # home « vide » plutôt que de planter le site.
        context.update({
            'sites_populaires': [],
            'categories': [],
            'regions': [],
        })

    return render(request, 'home.html', context)


def models_publie_filter():
    """
    Helper qui retourne un Q-object pour filtrer les sites publiés.
    Séparé pour pouvoir le réutiliser dans plusieurs annotations.
    """
    from django.db.models import Q
    return Q(sites__est_publie=True)


def a_propos(request):
    """Page statique 'À propos' présentant le projet."""
    return render(request, 'pages/a_propos.html', {
        'page_title': 'À propos',
    })


def contact(request):
    """Page statique 'Contact' avec formulaire (à implémenter)."""
    return render(request, 'pages/contact.html', {
        'page_title': 'Nous contacter',
    })


def mentions_legales(request):
    """Mentions légales — obligatoires pour conformité loi 2010/012."""
    return render(request, 'pages/mentions_legales.html', {
        'page_title': 'Mentions légales',
    })


# ============================================================
# HANDLERS D'ERREURS
# ============================================================
def page_404(request, exception):
    """
    Page 404 personnalisée.

    Django passe automatiquement l'exception en argument quand
    on définit `handler404` dans urls.py.
    Le status=404 est OBLIGATOIRE sinon Django renvoie un 200
    (et Google indexerait des pages d'erreur, désastreux pour le SEO).
    """
    return render(request, '404.html', status=404)


def page_500(request):
    """Page 500 personnalisée (erreur serveur)."""
    return render(request, '500.html', status=500)