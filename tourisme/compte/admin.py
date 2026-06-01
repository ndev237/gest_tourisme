"""
compte/admin.py — Inscription des modèles dans le backoffice Django.
Donne à l'admin un CRUD complet sur User, Touriste, Gestionnaire, Guide, Administrateur.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin

from compte.models import User, Touriste, Gestionnaire, Guide, Administrateur, LangueGuide


@admin.register(User)
class UserAdmin(DefaultUserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'type_user', 'is_active', 'date_joined')
    list_filter = ('type_user', 'is_active', 'is_staff', 'is_superuser')
    search_fields = ('email', 'first_name', 'last_name', 'telephone')
    ordering = ('-date_joined',)
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Identité', {'fields': ('first_name', 'last_name', 'telephone', 'photo_profil')}),
        ('Rôle', {'fields': ('type_user',)}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'type_user', 'password1', 'password2'),
        }),
    )


@admin.register(Touriste)
class TouristeAdmin(admin.ModelAdmin):
    list_display = ('user', 'nationalite', 'type', 'points_fidelite', 'langue_pref')
    list_filter = ('type', 'langue_pref', 'nationalite')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'cni_passeport')
    autocomplete_fields = ('user',)


@admin.register(Gestionnaire)
class GestionnaireAdmin(admin.ModelAdmin):
    list_display = ('entreprise', 'user', 'statut_validation', 'date_validation', 'admin_valideur')
    list_filter = ('statut_validation',)
    search_fields = ('entreprise', 'num_registre_commerce', 'user__email')
    autocomplete_fields = ('user', 'admin_valideur')
    actions = ('valider_selection', 'rejeter_selection')

    def valider_selection(self, request, queryset):
        from django.utils import timezone
        n = queryset.filter(statut_validation='en_attente').update(
            statut_validation='valide',
            date_validation=timezone.now(),
        )
        self.message_user(request, f"{n} gestionnaire(s) validé(s).")
    valider_selection.short_description = "✓ Valider les gestionnaires sélectionnés"

    def rejeter_selection(self, request, queryset):
        n = queryset.filter(statut_validation='en_attente').update(statut_validation='rejete')
        self.message_user(request, f"{n} gestionnaire(s) rejeté(s).")
    rejeter_selection.short_description = "✕ Rejeter les gestionnaires sélectionnés"


@admin.register(Guide)
class GuideAdmin(admin.ModelAdmin):
    list_display = ('user', 'licence_pro', 'tarif_journalier', 'annees_experience', 'note_moyenne', 'disponible', 'statut_validation')
    list_filter = ('statut_validation', 'disponible')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'licence_pro')
    autocomplete_fields = ('user',)


@admin.register(Administrateur)
class AdministrateurAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'niveau_acces')
    list_filter = ('role', 'niveau_acces')
    search_fields = ('user__email', 'user__first_name', 'user__last_name')
    autocomplete_fields = ('user',)


@admin.register(LangueGuide)
class LangueGuideAdmin(admin.ModelAdmin):
    list_display = ('guide', 'langue', 'niveau')
    list_filter = ('langue', 'niveau')
