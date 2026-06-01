"""localisation/admin.py — CRUD via backoffice Django."""
from django.contrib import admin
from localisation.models import Region, Localisation


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ('nom', 'code', 'chef_lieu')
    search_fields = ('nom', 'chef_lieu', 'code')
    ordering = ('nom',)


@admin.register(Localisation)
class LocalisationAdmin(admin.ModelAdmin):
    list_display = ('ville', 'quartier', 'region', 'latitude', 'longitude')
    list_filter = ('region',)
    search_fields = ('ville', 'quartier', 'adresse', 'point_repere')
    autocomplete_fields = ('region',)
