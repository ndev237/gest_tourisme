from django.conf import settings

def paiement_settings(request):
    return {
        'PAIEMENT_MODE_MOCK': getattr(settings, 'PAIEMENT_MODE_MOCK', False),
    }