"""
compte/forms.py
===============
Formulaires Django pour l'app compte.

ARCHITECTURE :
- ConnexionForm        : email + password (authentification)
- InscriptionForm      : crée User + profil selon type_user
- ProfilUserForm       : modification infos User (nom, téléphone, photo)
- ProfilTouristeForm   : champs spécifiques touriste
- ProfilGestionnaireForm : champs spécifiques gestionnaire
- ProfilGuideForm      : champs spécifiques guide
- ChangerPasswordForm  : changement de mot de passe

INITIATIVES PÉDAGOGIQUES :
1. Forms Django (pas ModelForms) pour ConnexionForm car pas de
   persistance directe — c'est juste de la validation d'inputs.
2. ModelForms pour les profils (1 form = 1 modèle = persistance).
3. Validation côté serveur OBLIGATOIRE même si l'HTML5 valide côté
   client. Un attaquant peut contourner le HTML5 (curl, Postman).
4. Hash automatique du mot de passe via UserManager.create_user().
"""

from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

from compte.models import User, Touriste, Gestionnaire, Guide


# ============================================================
# CONSTANTES (Tailwind/DaisyUI classes)
# ============================================================
# Pédago : on utilise les classes DaisyUI directement dans les templates
# pour les widgets standards. Ici on s'occupe juste de la VALIDATION,
# pas du rendu visuel (le template fait le HTML, le form fait la logique).


# ============================================================
# 1. CONNEXION
# ============================================================
class ConnexionForm(forms.Form):
    """
    Formulaire de connexion par email + mot de passe.

    Pédago : Form (pas ModelForm) car on n'écrit RIEN en BDD ici.
    On valide juste les credentials puis on passe la main à
    authenticate() qui vérifie le hash du mdp.
    """
    email = forms.EmailField(
        label="Adresse email",
        widget=forms.EmailInput(),
        error_messages={
            'required': "L'email est obligatoire",
            'invalid': "Format d'email invalide",
        },
    )
    password = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(),
        min_length=1,
        error_messages={
            'required': "Le mot de passe est obligatoire",
        },
    )
    remember_me = forms.BooleanField(
        required=False,
        label="Se souvenir de moi",
    )

    def __init__(self, *args, **kwargs):
        # Pédago : on récupère le request pour pouvoir appeler authenticate()
        # avec le bon backend (utile si on a plusieurs backends d'authentification).
        self.request = kwargs.pop('request', None)
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        """
        Validation globale du form : on tente d'authentifier l'user.
        Si échec, on met une erreur globale (pas par champ pour ne
        pas donner d'indice à un attaquant — "email existe mais mdp
        faux" est une fuite d'info).
        """
        cleaned = super().clean()
        email = cleaned.get('email')
        password = cleaned.get('password')

        if email and password:
            # authenticate() retourne le user si OK, None sinon.
            # Comme on a configuré USERNAME_FIELD='email', on passe
            # `username=email` (sémantique Django).
            self.user_cache = authenticate(
                request=self.request,
                username=email,
                password=password,
            )
            if self.user_cache is None:
                # Pédago : message volontairement vague ("ou" entre les deux)
                # pour ne pas révéler quel champ est faux.
                raise ValidationError(
                    "Email ou mot de passe incorrect.",
                    code='invalid_login',
                )
            # Vérifier que l'user est actif (pas suspendu)
            if not self.user_cache.is_active:
                raise ValidationError(
                    "Ce compte a été désactivé. Contactez le support.",
                    code='inactive',
                )

        return cleaned

    def get_user(self):
        """Renvoie l'instance User authentifiée (à appeler après is_valid)."""
        return self.user_cache


# ============================================================
# 2. INSCRIPTION (création User + profil selon type)
# ============================================================
class InscriptionForm(forms.Form):
    """
    Formulaire d'inscription avec choix du type d'utilisateur.

    Pédago : Form (pas ModelForm) car on crée 2 objets : un User
    et un profil spécifique (Touriste/Gestionnaire/Guide).
    Plus simple à gérer en Form avec une méthode save() custom.
    """

    # ---- Champs COMMUNS ----
    type_user = forms.ChoiceField(
        choices=[
            ('touriste', 'Touriste'),
            ('gestionnaire', 'Gestionnaire'),
            ('guide', 'Guide'),
            # Pédago : 'admin' INTERDIT publiquement.
            # Les admins sont créés via createsuperuser.
        ],
        widget=forms.RadioSelect(),
    )
    first_name = forms.CharField(
        label="Prénom",
        max_length=50,
        min_length=2,
    )
    last_name = forms.CharField(
        label="Nom",
        max_length=50,
        min_length=2,
    )
    email = forms.EmailField(
        label="Email",
    )
    telephone = forms.CharField(
        label="Téléphone",
        max_length=20,
        required=False,
        # Pédago : RegexValidator valide le format avec une expression régulière.
        # Format international : + suivi de 8 à 15 chiffres (espaces tolérés).
        validators=[RegexValidator(
            regex=r'^\+?[\d\s]{8,20}$',
            message="Format de téléphone invalide. Exemple : +237 6XX XXX XXX",
        )],
    )
    password1 = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(),
        min_length=8,
    )
    password2 = forms.CharField(
        label="Confirmation du mot de passe",
        widget=forms.PasswordInput(),
    )
    accept_cgu = forms.BooleanField(
        label="J'accepte les CGU",
        required=True,
        error_messages={
            'required': "Vous devez accepter les CGU pour continuer.",
        },
    )

    # ---- Champs SPÉCIFIQUES TOURISTE ----
    nationalite = forms.CharField(max_length=50, required=False, initial='Camerounaise')
    type_touriste = forms.ChoiceField(
        choices=Touriste.TypeTouriste.choices,
        required=False,
        initial='local',
    )
    date_naissance = forms.DateField(required=False)

    # ---- Champs SPÉCIFIQUES GESTIONNAIRE ----
    entreprise = forms.CharField(max_length=150, required=False)
    num_registre_commerce = forms.CharField(max_length=50, required=False)

    # ---- Champs SPÉCIFIQUES GUIDE ----
    licence_pro = forms.CharField(max_length=50, required=False)
    tarif_journalier = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=0,
    )
    annees_experience = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=70,
        initial=0,
    )
    bio = forms.CharField(
        widget=forms.Textarea(),
        required=False,
        max_length=1000,
    )

    # ============================================================
    # VALIDATIONS
    # ============================================================
    def clean_email(self):
        """Vérifier que l'email n'est pas déjà utilisé."""
        email = self.cleaned_data['email'].lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(
                "Un compte existe déjà avec cet email. "
                "Connectez-vous ou utilisez un autre email."
            )
        return email

    def clean_password1(self):
        """
        Valider le mot de passe avec les validators Django configurés
        dans settings.AUTH_PASSWORD_VALIDATORS.
        """
        password = self.cleaned_data['password1']
        try:
            validate_password(password)
        except ValidationError as e:
            raise ValidationError(e.messages)
        return password

    def clean_password2(self):
        """Vérifier que les 2 mots de passe correspondent."""
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise ValidationError("Les deux mots de passe ne correspondent pas.")
        return password2

    def clean(self):
        """
        Validation croisée selon le type_user choisi.
        On valide les champs spécifiques OBLIGATOIRES selon le type.
        """
        cleaned = super().clean()
        type_user = cleaned.get('type_user')

        # GESTIONNAIRE : entreprise + n° registre obligatoires
        if type_user == 'gestionnaire':
            if not cleaned.get('entreprise'):
                self.add_error('entreprise', "Le nom de l'entreprise est obligatoire.")
            if not cleaned.get('num_registre_commerce'):
                self.add_error('num_registre_commerce', "Le n° de registre est obligatoire.")
            else:
                # Vérifier l'unicité du n° de registre
                num = cleaned['num_registre_commerce']
                if Gestionnaire.objects.filter(num_registre_commerce=num).exists():
                    self.add_error('num_registre_commerce',
                                   "Ce n° de registre est déjà enregistré.")

        # GUIDE : licence + tarif obligatoires
        elif type_user == 'guide':
            if not cleaned.get('licence_pro'):
                self.add_error('licence_pro', "Le n° de licence est obligatoire.")
            else:
                licence = cleaned['licence_pro']
                if Guide.objects.filter(licence_pro=licence).exists():
                    self.add_error('licence_pro', "Cette licence est déjà enregistrée.")
            if not cleaned.get('tarif_journalier'):
                self.add_error('tarif_journalier', "Le tarif journalier est obligatoire.")

        return cleaned

    # ============================================================
    # SAVE — Crée le User + profil spécifique
    # ============================================================
    def save(self):
        """
        Crée le User et le profil spécifique selon type_user.

        Pédago : on encapsule la création dans une transaction atomique
        (à faire dans la view). Si la création du profil échoue, on rollback
        le User.

        Returns:
            User: l'instance créée
        """
        data = self.cleaned_data
        type_user = data['type_user']

        # ---- ÉTAPE 1 : Création du User ----
        # Pédago : UserManager.create_user() hash automatiquement le mdp
        # via set_password(). NE JAMAIS faire User(password=mdp) → mdp en clair !
        user = User.objects.create_user(
            email=data['email'],
            password=data['password1'],
            first_name=data['first_name'],
            last_name=data['last_name'],
            telephone=data.get('telephone', ''),
            type_user=type_user,
        )

        # ---- ÉTAPE 2 : Création du profil spécifique ----
        if type_user == 'touriste':
            Touriste.objects.create(
                user=user,
                nationalite=data.get('nationalite', 'Camerounaise'),
                type=data.get('type_touriste', 'local'),
                date_naissance=data.get('date_naissance'),
            )

        elif type_user == 'gestionnaire':
            Gestionnaire.objects.create(
                user=user,
                entreprise=data['entreprise'],
                num_registre_commerce=data['num_registre_commerce'],
                # statut_validation = 'en_attente' par défaut (cf. modèle)
            )

        elif type_user == 'guide':
            Guide.objects.create(
                user=user,
                licence_pro=data['licence_pro'],
                tarif_journalier=data['tarif_journalier'],
                annees_experience=data.get('annees_experience', 0),
                bio=data.get('bio', ''),
                # statut_validation = 'en_attente' par défaut
            )

        return user


# ============================================================
# 3. PROFIL USER (infos communes)
# ============================================================
class ProfilUserForm(forms.ModelForm):
    """
    Modification des infos communes du User (nom, prénom, téléphone, photo).
    L'email n'est PAS modifiable ici (sécurité).
    """
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'telephone', 'photo_profil']

    def clean_telephone(self):
        telephone = self.cleaned_data.get('telephone', '').strip()
        if telephone and not telephone.replace(' ', '').replace('+', '').isdigit():
            raise ValidationError("Le téléphone doit contenir uniquement des chiffres.")
        return telephone


# ============================================================
# 4. PROFIL TOURISTE
# ============================================================
class ProfilTouristeForm(forms.ModelForm):
    """Champs spécifiques au profil touriste."""
    class Meta:
        model = Touriste
        fields = ['nationalite', 'cni_passeport', 'type', 'langue_pref', 'date_naissance']


# ============================================================
# 5. PROFIL GESTIONNAIRE
# ============================================================
class ProfilGestionnaireForm(forms.ModelForm):
    """
    Champs spécifiques au profil gestionnaire.

    Le n° de registre de commerce est en lecture seule
    (sécurité : on ne change pas son identité légale après inscription).
    """
    class Meta:
        model = Gestionnaire
        fields = ['entreprise']  # SEUL le nom est modifiable
        # num_registre_commerce : volontairement EXCLU
        # statut_validation : géré par l'admin uniquement


# ============================================================
# 6. PROFIL GUIDE
# ============================================================
class ProfilGuideForm(forms.ModelForm):
    """Champs spécifiques au profil guide."""
    class Meta:
        model = Guide
        fields = ['bio', 'tarif_journalier', 'annees_experience', 'disponible']
        # licence_pro : en lecture seule (identité pro)
        # note_moyenne : calculée automatiquement
        # statut_validation : géré par l'admin


# ============================================================
# 7. CHANGEMENT DE MOT DE PASSE
# ============================================================
class ChangerPasswordForm(forms.Form):
    """
    Form de changement de mot de passe.

    Pédago : 3 champs (ancien, nouveau, confirmation) — l'ancien est
    obligatoire pour la sécurité (si quelqu'un vole votre session sur
    un poste public, il ne peut pas changer votre mdp sans le connaître).
    """
    old_password = forms.CharField(
        label="Mot de passe actuel",
        widget=forms.PasswordInput(),
    )
    new_password1 = forms.CharField(
        label="Nouveau mot de passe",
        widget=forms.PasswordInput(),
        min_length=8,
    )
    new_password2 = forms.CharField(
        label="Confirmation",
        widget=forms.PasswordInput(),
    )

    def __init__(self, user, *args, **kwargs):
        # Pédago : on injecte le user via __init__ pour pouvoir
        # vérifier l'ancien mdp dans clean_old_password().
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_old_password(self):
        """Vérifier que l'ancien mdp est correct."""
        old = self.cleaned_data['old_password']
        # check_password() compare le mdp en clair avec le hash en BDD
        if not self.user.check_password(old):
            raise ValidationError("Mot de passe actuel incorrect.")
        return old

    def clean_new_password1(self):
        new = self.cleaned_data['new_password1']
        try:
            validate_password(new, self.user)
        except ValidationError as e:
            raise ValidationError(e.messages)
        return new

    def clean_new_password2(self):
        new1 = self.cleaned_data.get('new_password1')
        new2 = self.cleaned_data.get('new_password2')
        if new1 and new2 and new1 != new2:
            raise ValidationError("Les deux nouveaux mots de passe ne correspondent pas.")
        return new2

    def save(self):
        """Applique le nouveau mot de passe (hash automatique)."""
        # Pédago : set_password() hash automatiquement avec PBKDF2 + salt.
        # NE JAMAIS assigner self.user.password = new (laisse en clair !).
        self.user.set_password(self.cleaned_data['new_password1'])
        self.user.save(update_fields=['password'])
        return self.user