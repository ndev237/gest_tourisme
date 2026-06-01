"""core/admin.py — AuditLog visible dans le backoffice."""
from django.contrib import admin

try:
    from core.models import AuditLog
except ImportError:
    AuditLog = None


if AuditLog is not None:
    @admin.register(AuditLog)
    class AuditLogAdmin(admin.ModelAdmin):
        list_display = ('created_at', 'utilisateur', 'action', 'ressource', 'id_ressource', 'ip_address')
        list_filter = ('action', 'ressource')
        search_fields = ('utilisateur__email', 'ressource', 'id_ressource', 'ip_address')
        date_hierarchy = 'created_at'
        readonly_fields = ('created_at', 'utilisateur', 'action', 'ressource',
                           'id_ressource', 'details', 'ip_address', 'user_agent')

        def has_add_permission(self, request):
            return False  # AuditLog est strictement en lecture seule

        def has_delete_permission(self, request, obj=None):
            return False
