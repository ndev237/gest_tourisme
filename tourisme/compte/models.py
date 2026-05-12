"""
compte/models.py
================
Modèles d'authentification et profils utilisateurs.

Architecture : héritage Django multi-tables
- User (parent) : authentification commune (email, password)
- Touriste, Gestionnaire, Guide, Administrateur : profils spécifiques liés via OneToOne
"""

import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils.translation import gettext_lazy as _
from core.models import TimestampedModel


# ============================================================
# 1. USER MANAGER (gestionnaire personnalisé)
# ============================================================
class UserManager(BaseUserManager):
    """
    Manager personnalisé pour notre modèle User qui utilise
    l'email comme identifiant principal (pas le username).
    """

    def create_user(self, email, password=None, **extra_fields):
        """Crée un utilisateur normal."""
        if not email:
            raise ValueError(_("L'email est obligatoire"))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)  # Hash automatique du mot de passe
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Crée un super-utilisateur (admin Django)."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('type_user', User.UserType.ADMIN)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_("Le superuser doit avoir is_staff=True"))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_("Le superuser doit avoir is_superuser=True"))

        return self.create_user(email, password, **extra_fields)


# ============================================================
# 2. USER (modèle d'authentification central)
# ============================================================
class User(AbstractUser):
    """
    Modèle utilisateur personnalisé.

    Hérite de AbstractUser pour conserver toutes les fonctionnalités
    Django (permissions, groupes, etc.) mais utilise l'email
    comme identifiant principal.
    """

    class UserType(models.TextChoices):
        TOURISTE = 'touriste', 'Touriste'
        GESTIONNAIRE = 'gestionnaire', 'Gestionnaire de site'
        GUIDE = 'guide', 'Guide touristique'
        ADMIN = 'admin', 'Administrateur'

    # On remplace l'ID auto-incrément par un UUID pour la sécurité
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    # On supprime le username (l'email devient l'identifiant)
    username = None

    # Email comme identifiant unique
    email = models.EmailField(
        unique=True,
        verbose_name="Adresse email"
    )
    telephone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Téléphone",
        help_text="Format international : +237 6XX XXX XXX"
    )
    photo_profil = models.ImageField(
        upload_to='profiles/%Y/%m/',
        blank=True,
        null=True,
        verbose_name="Photo de profil"
    )
    type_user = models.CharField(
        max_length=20,
        choices=UserType.choices,
        default=UserType.TOURISTE,
        verbose_name="Type d'utilisateur"
    )
    date_inscription = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date d'inscription"
    )

    # Authentification par email (et non par username)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []  # Champs requis lors du createsuperuser, en plus de l'email

    objects = UserManager()

    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"
        ordering = ['-date_inscription']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['type_user']),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

    @property
    def nom_complet(self):
        """Retourne le nom complet."""
        return f"{self.first_name} {self.last_name}".strip()


# ============================================================
# 3. TOURISTE (profil spécifique)
# ============================================================
class Touriste(TimestampedModel):
    """
    Profil d'un touriste sur la plateforme.
    Lié à un User par une relation OneToOne (un User = un profil Touriste).
    """

    class TypeTouriste(models.TextChoices):
        LOCAL = 'local', 'Touriste local'
        ETRANGER = 'etranger', 'Touriste étranger'

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profil_touriste',
        verbose_name="Compte utilisateur"
    )
    nationalite = models.CharField(
        max_length=50,
        default='Camerounaise',
        verbose_name="Nationalité"
    )
    cni_passeport = models.CharField(
        max_length=30,
        blank=True,
        verbose_name="N° CNI ou passeport",
        help_text="Pour vérification à l'entrée des sites"
    )
    type = models.CharField(
        max_length=20,
        choices=TypeTouriste.choices,
        default=TypeTouriste.LOCAL,
        verbose_name="Type"
    )
    langue_pref = models.CharField(
        max_length=10,
        choices=[('fr', 'Français'), ('en', 'English')],
        default='fr',
        verbose_name="Langue préférée"
    )
    date_naissance = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de naissance"
    )
    points_fidelite = models.PositiveIntegerField(
        default=0,
        verbose_name="Points de fidélité"
    )

    class Meta:
        verbose_name = "Touriste"
        verbose_name_plural = "Touristes"

    def __str__(self):
        return f"Touriste : {self.user.nom_complet}"


# ============================================================
# 4. GESTIONNAIRE (propriétaire/responsable de site)
# ============================================================
class Gestionnaire(TimestampedModel):
    """
    Profil d'un gestionnaire qui propose des sites touristiques.
    Doit être validé par un admin avant de pouvoir publier ses sites.
    """

    class StatutValidation(models.TextChoices):
        EN_ATTENTE = 'en_attente', 'En attente de validation'
        VALIDE = 'valide', 'Validé'
        REJETE = 'rejete', 'Rejeté'

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profil_gestionnaire',
        verbose_name="Compte utilisateur"
    )
    entreprise = models.CharField(
        max_length=150,
        verbose_name="Nom de l'entreprise"
    )
    num_registre_commerce = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="N° registre de commerce",
        help_text="N° d'identification légal de l'entreprise"
    )
    statut_validation = models.CharField(
        max_length=20,
        choices=StatutValidation.choices,
        default=StatutValidation.EN_ATTENTE,
        verbose_name="Statut de validation"
    )
    admin_valideur = models.ForeignKey(
        'Administrateur',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gestionnaires_valides',
        verbose_name="Admin valideur"
    )
    date_validation = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de validation"
    )
    motif_rejet = models.TextField(
        blank=True,
        verbose_name="Motif du rejet (si applicable)"
    )

    class Meta:
        verbose_name = "Gestionnaire"
        verbose_name_plural = "Gestionnaires"
        indexes = [
            models.Index(fields=['statut_validation']),
        ]

    def __str__(self):
        return f"{self.entreprise} ({self.user.email})"

    @property
    def est_valide(self):
        """Indique si le gestionnaire peut publier ses sites."""
        return self.statut_validation == self.StatutValidation.VALIDE


# ============================================================
# 5. GUIDE (guide touristique)
# ============================================================
class Guide(TimestampedModel):
    """
    Profil d'un guide touristique professionnel.
    Propose ses services d'accompagnement aux touristes.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profil_guide',
        verbose_name="Compte utilisateur"
    )
    bio = models.TextField(
        blank=True,
        verbose_name="Biographie"
    )
    tarif_journalier = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Tarif journalier (FCFA)"
    )
    annees_experience = models.PositiveIntegerField(
        default=0,
        verbose_name="Années d'expérience"
    )
    licence_pro = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="N° licence professionnelle"
    )
    note_moyenne = models.FloatField(
        default=0.0,
        verbose_name="Note moyenne (sur 5)"
    )
    disponible = models.BooleanField(
        default=True,
        verbose_name="Disponible pour de nouvelles missions"
    )
    statut_validation = models.CharField(
        max_length=20,
        choices=Gestionnaire.StatutValidation.choices,
        default=Gestionnaire.StatutValidation.EN_ATTENTE,
        verbose_name="Statut de validation"
    )

    class Meta:
        verbose_name = "Guide touristique"
        verbose_name_plural = "Guides touristiques"
        indexes = [
            models.Index(fields=['disponible']),
            models.Index(fields=['-note_moyenne']),
        ]

    def __str__(self):
        return f"Guide : {self.user.nom_complet}"


# ============================================================
# 6. LANGUE GUIDE (table de jonction N..M)
# ============================================================
class LangueGuide(models.Model):
    """
    Association entre un Guide et les langues qu'il parle.
    Table de jonction N..M avec un attribut supplémentaire (niveau).
    """

    class Niveau(models.TextChoices):
        BASIQUE = 'basique', 'Basique'
        INTERMEDIAIRE = 'intermediaire', 'Intermédiaire'
        AVANCE = 'avance', 'Avancé'
        NATIF = 'natif', 'Natif'

    guide = models.ForeignKey(
        Guide,
        on_delete=models.CASCADE,
        related_name='langues',
        verbose_name="Guide"
    )
    langue = models.CharField(
        max_length=10,
        verbose_name="Code langue",
        help_text="Ex: fr, en, es, de, ar"
    )
    niveau = models.CharField(
        max_length=20,
        choices=Niveau.choices,
        default=Niveau.INTERMEDIAIRE,
        verbose_name="Niveau"
    )

    class Meta:
        verbose_name = "Langue parlée par un guide"
        verbose_name_plural = "Langues parlées par les guides"
        unique_together = [('guide', 'langue')]  # PK composite

    def __str__(self):
        return f"{self.guide.user.nom_complet} - {self.langue} ({self.get_niveau_display()})"


# ============================================================
# 7. ADMINISTRATEUR
# ============================================================
class Administrateur(TimestampedModel):
    """
    Profil d'un administrateur de la plateforme.
    """

    class Role(models.TextChoices):
        SUPER_ADMIN = 'super_admin', 'Super administrateur'
        MODERATEUR = 'moderateur', 'Modérateur'
        SUPPORT = 'support', 'Support client'

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profil_admin',
        verbose_name="Compte utilisateur"
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.MODERATEUR,
        verbose_name="Rôle"
    )
    niveau_acces = models.PositiveSmallIntegerField(
        default=1,
        verbose_name="Niveau d'accès",
        help_text="1 = basique, 5 = total"
    )

    class Meta:
        verbose_name = "Administrateur"
        verbose_name_plural = "Administrateurs"

    def __str__(self):
        return f"Admin {self.get_role_display()} : {self.user.nom_complet}"