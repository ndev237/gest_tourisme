"""
URL configuration for tourisme project.

Stratégie : chaque app a son propre urls.py qui est inclus ici.
Permet une organisation modulaire et facilite la maintenance.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    # Admin Django (backup en cas de problème avec nos dashboards custom)
    path('admin/', admin.site.urls),

    # Pages publiques (accueil + catalogue sites) — racine du site
    path('', include('catalogue.urls', namespace='catalogue')),

    # Authentification et profils utilisateurs
    path('compte/', include('compte.urls', namespace='compte')),

    # Réservations (formulaire, dashboard touriste/gestionnaire)
    path('reservations/', include('reservations.urls', namespace='reservations')),

    # Paiements (page paiement + callbacks Mobile Money)
    path('paiements/', include('paiements.urls', namespace='paiements')),

    # Avis et favoris
    path('avis/', include('reviews.urls', namespace='reviews')),

    # Notifications et messagerie
    path('notifications/', include('notifications.urls', namespace='notifications')),

    # Dashboard admin personnalisé (le nôtre, pas celui de Django)
    path('dashboard-admin/', include('core.urls', namespace='core')),
]


# Servir les fichiers media en développement (UNIQUEMENT en DEBUG)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)