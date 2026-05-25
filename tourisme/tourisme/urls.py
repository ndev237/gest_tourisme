"""
tourisme/urls.py
================
Routeur principal (URLconf racine) du projet Django.

Rôle : c'est le « standard téléphonique » du site. Quand le navigateur
demande une URL (ex: /sites/kribi/), Django regarde ce fichier pour
savoir quelle vue doit répondre.

Initiatives prises :
1. On utilise `include()` pour déléguer chaque domaine fonctionnel à
   l'urls.py de son app (séparation des responsabilités, principe SoC).
2. Les routes d'authentification (connexion, inscription, dashboards)
   sont préfixées par /compte/ pour bien isoler le périmètre auth.
3. Les fichiers média (photos uploadées) sont servis par Django UNIQUEMENT
   en mode DEBUG (en production c'est Nginx qui s'en charge).
4. Les vues d'erreur 404 et 500 sont définies au niveau projet pour
   un rendu personnalisé sur toutes les apps.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

# Vues globales (page d'accueil, erreurs)
from . import views

urlpatterns = [
    # ============================================================
    # ADMIN DJANGO (backoffice technique)
    # ============================================================
    # On masque /admin/ derrière un préfixe moins prévisible
    # pour limiter les attaques par scan automatisé.
    path('backoffice/', admin.site.urls),

    # ============================================================
    # PAGES PUBLIQUES GÉNÉRALES
    # ============================================================
    path('', views.home, name='home'),
    path('a-propos/', views.a_propos, name='a_propos'),
    path('contact/', views.contact, name='contact'),
    path('mentions-legales/', views.mentions_legales, name='mentions_legales'),

    # ============================================================
    # APPS MÉTIER (chaque app a son propre urls.py)
    # ============================================================
    # Authentification, profils, dashboards
    path('compte/', include('compte.urls', namespace='compte')),

    # Catalogue : sites, catégories, hébergements, photos
    path('', include('catalogue.urls', namespace='catalogue')),

    # Localisations : régions, villes, GPS
    path('', include('localisation.urls', namespace='localisation')),

    # Réservations + paiements
    path('reservation/', include('reservation.urls', namespace='reservation')),
    path('paiements/', include('paiements.urls', namespace='paiements')),

    # Avis et favoris
    path('avis/', include('reviews.urls', namespace='reviews')),

    # Notifications
    path('notifications/', include('notifications.urls', namespace='notifications')),
]

# ============================================================
# FICHIERS MÉDIA (uploads des utilisateurs) — uniquement en DEV
# ============================================================
# En production, c'est Nginx qui sert /media/ (bien plus rapide
# que Django et conforme aux bonnes pratiques de déploiement).
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# ============================================================
# HANDLERS D'ERREURS PERSONNALISÉS
# ============================================================
# Quand Django rencontre une 404 ou 500, il appelle ces vues
# au lieu d'afficher la page jaune par défaut.
handler404 = 'tourisme.views.page_404'
handler500 = 'tourisme.views.page_500'