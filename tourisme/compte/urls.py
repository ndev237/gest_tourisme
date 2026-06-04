"""
compte/urls.py
==============
Routes pour l'app compte.

INITIATIVES PÉDAGOGIQUES :
1. `app_name = 'compte'` → namespace, on appelle via {% url 'compte:connexion' %}.
   Évite les collisions si une autre app a aussi une URL nommée 'connexion'.
2. URLs en français, parlantes, alignées avec votre convention.
"""

from django.urls import path
from compte import views

app_name = 'compte'

urlpatterns = [
    # ===== AUTHENTIFICATION =====
    path('connexion/', views.connexion_view, name='connexion'),
    path('inscription/', views.inscription_view, name='inscription'),
    path('deconnexion/', views.deconnexion_view, name='deconnexion'),

    # ===== GESTION DU COMPTE =====
    path('profil/', views.profil_view, name='profil'),
    path('profil/modifier/', views.profil_update_view, name='profil_update'),
    path('changer-password/', views.changer_password_view, name='changer_password'),
    path('compte-suspendu/', views.compte_suspendu_view, name='compte_suspendu'),

    # ===== DASHBOARDS (un par type d'utilisateur) =====
    path('dashboard/touriste/', views.dashbord_touriste_view, name='dashbord_touriste'),
    path('dashboard/gestionnaire/', views.dashbord_gestionnaire_view, name='dashbord_gestionnaire_site'),
    path('dashboard/guide/', views.dashbord_guide_view, name='dashbord_guide'),
    path('dashboard/guide/planning/', views.planning_guide_view, name='planning_guide'),
    path('dashboard/admin/', views.dashbord_admin_view, name='dashbord_admin'),

    # ===== ADMIN — GESTION INTERNE DES UTILISATEURS =====
    # (remplace le backoffice Django : tout se passe sur la plateforme)
    path('admin/utilisateurs/',    views.admin_liste_utilisateurs,    name='admin_liste_utilisateurs'),
    path('admin/touristes/',       views.admin_liste_touristes,       name='admin_liste_touristes'),
    path('admin/gestionnaires/',   views.admin_liste_gestionnaires,   name='admin_liste_gestionnaires'),
    path('admin/guides/',          views.admin_liste_guides,          name='admin_liste_guides'),
    path('admin/administrateurs/', views.admin_liste_administrateurs, name='admin_liste_administrateurs'),
    path('admin/administrateur/ajouter/',                 views.admin_add_administrateur,    name='admin_add_administrateur'),
    path('admin/administrateur/<int:admin_id>/modifier/', views.admin_update_administrateur, name='admin_update_administrateur'),
    path('admin/administrateur/<int:admin_id>/supprimer/',views.admin_delete_administrateur, name='admin_delete_administrateur'),

    # Actions de validation
    path('admin/gestionnaire/<int:gestionnaire_id>/valider/', views.admin_valider_gestionnaire, name='admin_valider_gestionnaire'),
    path('admin/gestionnaire/<int:gestionnaire_id>/rejeter/', views.admin_rejeter_gestionnaire, name='admin_rejeter_gestionnaire'),
    path('admin/guide/<int:guide_id>/valider/',               views.admin_valider_guide,         name='admin_valider_guide'),
    path('admin/guide/<int:guide_id>/rejeter/',               views.admin_rejeter_guide,         name='admin_rejeter_guide'),

    # Suspendre / réactiver un user (User PK = UUID)
    path('admin/utilisateur/<uuid:user_id>/toggle/', views.admin_toggle_user_actif, name='admin_toggle_user_actif'),
]