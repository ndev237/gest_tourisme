"""paiements/admin.py — CRUD via backoffice."""
from django.contrib import admin
from paiements.models import Paiement, MoyenPaiement


@admin.register(MoyenPaiement)
class MoyenPaiementAdmin(admin.ModelAdmin):
    list_display = ('libelle', 'code', 'type', 'provider', 'est_actif', 'ordre_affichage')
    list_filter = ('type', 'provider', 'est_actif')
    search_fields = ('libelle', 'code')
    list_editable = ('est_actif', 'ordre_affichage')


@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    list_display = ('reference_interne', 'reservation', 'moyen', 'type_transaction', 'montant', 'statut', 'created_at')
    list_filter = ('statut', 'type_transaction', 'moyen', 'devise')
    search_fields = ('reference_interne', 'reference_externe', 'reservation__numero', 'numero_telephone')
    date_hierarchy = 'created_at'
    autocomplete_fields = ('reservation', 'moyen')
    readonly_fields = ('reference_interne', 'date_paiement')
