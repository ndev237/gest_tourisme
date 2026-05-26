"""
reviews/urls.py
===============
Routes pour avis et favoris.

ORGANISATION
A. TOURISTE : laisser/voir/modifier/supprimer un avis, voir ses favoris
B. ADMIN    : modération
C. GESTIONNAIRE : répondre à un avis
D. PUBLIC   : signaler un avis (connecté)
"""

from django.urls import path
from reviews import views

app_name = 'reviews'

urlpatterns = [
    # =========================================================
    # A. TOURISTE — Avis
    # =========================================================
    path('avis/', views.liste_avis_view, name='liste_avis'),
    path('reservation/<int:reservation_id>/avis/ajouter/',
         views.add_avis_view, name='add_avis'),
    path('avis/<int:avis_id>/modifier/', views.update_avis_view, name='update_avis'),
    path('avis/<int:avis_id>/supprimer/', views.delete_avis_view, name='delete_avis'),

    # =========================================================
    # A. TOURISTE — Favoris
    # =========================================================
    path('favoris/', views.liste_favori_view, name='liste_favori'),
    path('favoris/<int:favori_id>/supprimer/',
         views.delete_favori_view, name='delete_favori'),

    # =========================================================
    # B. ADMIN — Modération
    # =========================================================
    path('admin/moderation/', views.moderation_avis_view, name='moderation'),
    path('admin/avis/<int:avis_id>/moderer/',
         views.moderer_avis_view, name='moderer_avis'),

    # =========================================================
    # C. GESTIONNAIRE — Réponse
    # =========================================================
    path('gestionnaire/avis/<int:avis_id>/repondre/',
         views.repondre_avis_view, name='repondre_avis'),

    # =========================================================
    # D. Tous utilisateurs connectés — Signaler
    # =========================================================
    path('avis/<int:avis_id>/signaler/',
         views.signaler_avis_view, name='signaler_avis'),
]
