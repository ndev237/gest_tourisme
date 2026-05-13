"""
Django settings for tourisme project.

Plateforme de gestion et de réservation des sites touristiques au Cameroun
IUEs/INSAM - Soutenance Licence Pro 2026

Configuration :
- SQLite en développement local
- PostgreSQL en production (via variables d'environnement)
"""

import os
from pathlib import Path
from decouple import config, Csv

# ============================================================
# 1. CHEMINS DE BASE
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent


# ============================================================
# 2. SÉCURITÉ
# ============================================================
# Lue depuis le fichier .env (jamais en dur dans le code en production)
SECRET_KEY = config(
    'SECRET_KEY',
    default='django-insecure-r)e6b5(k15jz7x^p03rb1rzp9tsdk&9b*u8z_)&nj2(se^e03@'
)

DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='localhost,127.0.0.1',
    cast=Csv()
)


# ============================================================
# 3. APPLICATIONS
# ============================================================
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.sitemaps',

]

THIRD_PARTY_APPS = [
    'tailwind',
    'theme',
    # Les apps tierces seront ajoutées ici au fur et à mesure
    # 'rest_framework',
    # 'corsheaders',
    # 'django_extensions',
]

LOCAL_APPS = [
    # Apps tourisme
    'compte', # Authentification + profils utilisateursUser (custom), Touriste, Gestionnaire, Guide, Admin
    'catalogue', # Sites, hébergements, catégories,Categorie, Tag, SiteTouristique, PhotoSite, Hebergement, Disponibilite, SiteTag
    'core', # Modèles transverses, mixins, utilitairesAuditLog, TimestampedModel (mixin)
    'localisations', # GéolocalisationRegion, Localisation
    'notifications', # Notifications multi-canauxNotification
    'paiements', # Paiements et moyens de paiementMoyenPaiement, Paiement
    'reservations', # Cycle de vie des réservationsReservation, LigneReservation, BonReservation
    'reviews' # Avis et favorisAvis, Favori
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


# ============================================================
# 4. MIDDLEWARE
# ============================================================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',  # Multilingue FR/EN
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


# ============================================================
# 5. URL & WSGI
# ============================================================
ROOT_URLCONF = 'tourisme.urls'
WSGI_APPLICATION = 'tourisme.wsgi.application'


# ============================================================
# 6. TEMPLATES
# ============================================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],  # Templates globaux
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n',  # Pour le multilingue
            ],
        },
    },
]


# ============================================================
# 7. BASE DE DONNÉES
# Bascule automatique SQLite (dev) / PostgreSQL (production)
# ============================================================
if config('USE_POSTGRES', default=False, cast=bool):
    # Production : PostgreSQL
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME'),
            'USER': config('DB_USER'),
            'PASSWORD': config('DB_PASSWORD'),
            'HOST': config('DB_HOST', default='localhost'),
            'PORT': config('DB_PORT', default='5432'),
            'CONN_MAX_AGE': 60,  # Réutilise les connexions pendant 60s
        }
    }
else:
    # Développement local : SQLite
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# ============================================================
# 8. UTILISATEUR PERSONNALISÉ
# IMPORTANT : à définir AVANT toute migration !
# ============================================================
AUTH_USER_MODEL = 'compte.User'  # ← CORRIGÉ : 'accounts' → 'compte' (ton app)

AUTH_PASSWORD_VALIDATORS = [  # ← CORRIGÉ : défini une seule fois
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = '/compte/connexion/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'

# ============================================================
# 9. VALIDATION DES MOTS DE PASSE
# ============================================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ============================================================
# 10. INTERNATIONALISATION
# ============================================================
LANGUAGE_CODE = 'fr'  # Français par défaut (cible Cameroun)
TIME_ZONE = 'Africa/Douala'  # Fuseau horaire du Cameroun (UTC+1)
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ('fr', 'Français'),
    ('en', 'English'),
]

LOCALE_PATHS = [BASE_DIR / 'locale']


# ============================================================
# 11. FICHIERS STATIQUES & MÉDIAS
# ============================================================
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'  # collectstatic pour la production
STATICFILES_DIRS = [BASE_DIR / 'static']  # Fichiers statiques globaux

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'


# ============================================================
# 12. CLÉ PRIMAIRE PAR DÉFAUT
# ============================================================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ============================================================
# 13. TAILWIND CSS
# ============================================================
TAILWIND_APP_NAME = "theme"
NPM_BIN_PATH = config(
    'NPM_BIN_PATH',
    default=r"C:\Program Files\nodejs\npm.cmd"
)
INTERNAL_IPS = ["127.0.0.1"]  # Pour le rechargement Tailwind en dev


# ============================================================
# 14. EMAIL
# ============================================================
if DEBUG:
    # En dev, les emails s'affichent dans la console
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    # En production : SMTP réel
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
    EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
    EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
    EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
    EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')

DEFAULT_FROM_EMAIL = config(
    'DEFAULT_FROM_EMAIL',
    default='Tourisme Cameroun <noreply@tourisme-cameroun.cm>'
)


# ============================================================
# 15. SÉCURITÉ EN PRODUCTION
# ============================================================
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = 31536000  # 1 an
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True


# ============================================================
# 16. PAIEMENTS MOBILE MONEY (à compléter avec vos clés API)
# ============================================================
MTN_MOMO_API_USER = config('MTN_MOMO_API_USER', default='')
MTN_MOMO_API_KEY = config('MTN_MOMO_API_KEY', default='')
MTN_MOMO_SUBSCRIPTION_KEY = config('MTN_MOMO_SUBSCRIPTION_KEY', default='')
MTN_MOMO_ENVIRONMENT = config('MTN_MOMO_ENVIRONMENT', default='sandbox')

ORANGE_MONEY_CLIENT_ID = config('ORANGE_MONEY_CLIENT_ID', default='')
ORANGE_MONEY_CLIENT_SECRET = config('ORANGE_MONEY_CLIENT_SECRET', default='')


# ============================================================
# 17. CONFIGURATION MÉTIER
# ============================================================
# Délai (en heures) avant la date de visite pour annulation gratuite
CANCELLATION_FREE_HOURS = 48

# Pourcentage de remboursement après le délai gratuit
LATE_CANCELLATION_REFUND_PERCENT = 50

# Devise par défaut
DEFAULT_CURRENCY = 'XAF'

# Préfixe des numéros de réservation
RESERVATION_PREFIX = 'RES'