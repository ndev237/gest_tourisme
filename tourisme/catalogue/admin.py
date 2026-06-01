"""catalogue/admin.py — CRUD complet via le backoffice Django."""
from django.contrib import admin
from catalogue.models import (
    Categorie, Tag, SiteTouristique, PhotoSite, Hebergement, Disponibilite,
)


@admin.register(Categorie)
class CategorieAdmin(admin.ModelAdmin):
    list_display = ('libelle', 'couleur', 'ordre_affichage')
    search_fields = ('libelle',)
    ordering = ('ordre_affichage', 'libelle')


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('libelle', 'categorie_tag', 'icone')
    search_fields = ('libelle',)


class PhotoSiteInline(admin.TabularInline):
    model = PhotoSite
    extra = 0
    fields = ('image', 'legende', 'est_principale', 'ordre')


class HebergementInline(admin.TabularInline):
    model = Hebergement
    extra = 0
    fields = ('nom', 'type', 'etoiles', 'prix_nuit', 'est_disponible')


@admin.register(SiteTouristique)
class SiteTouristiqueAdmin(admin.ModelAdmin):
    list_display = ('nom', 'categorie', 'gestionnaire', 'tarif_adulte', 'note_moyenne', 'nombre_avis', 'est_publie')
    list_filter = ('est_publie', 'categorie', 'type', 'accessibilite_pmr')
    search_fields = ('nom', 'description')
    prepopulated_fields = {'slug': ('nom',)}
    autocomplete_fields = ('categorie', 'localisation', 'gestionnaire')
    # Pas de filter_horizontal sur tags : il a un through model SiteTag.
    # Les tags se gèrent via le inline SiteTag ou directement via le formulaire.
    inlines = [PhotoSiteInline, HebergementInline]
    list_editable = ('est_publie',)


@admin.register(PhotoSite)
class PhotoSiteAdmin(admin.ModelAdmin):
    list_display = ('site', 'legende', 'est_principale', 'ordre')
    list_filter = ('est_principale',)
    autocomplete_fields = ('site',)


@admin.register(Hebergement)
class HebergementAdmin(admin.ModelAdmin):
    list_display = ('nom', 'site', 'type', 'etoiles', 'prix_nuit', 'est_disponible')
    list_filter = ('type', 'etoiles', 'est_disponible')
    search_fields = ('nom', 'site__nom')
    autocomplete_fields = ('site',)


@admin.register(Disponibilite)
class DisponibiliteAdmin(admin.ModelAdmin):
    list_display = ('site', 'date', 'places_restantes', 'tarif_special', 'est_ferme')
    list_filter = ('est_ferme', 'date')
    search_fields = ('site__nom',)
    autocomplete_fields = ('site',)
    date_hierarchy = 'date'
