"""
compte/forms.py
===============
Formulaires d'authentification et de gestion de profil.

Initiatives prises :
1. Utilisation des `ModelForm` quand le formulaire correspond à un modèle
   (DRY : on évite de redéclarer chaque champ).
2. `clean_<champ>()` pour les validations métier (ex: téléphone Cameroun).
3. Classes Tailwind directement dans les widgets pour un rendu cohérent
   sans avoir à styliser chaque champ dans le template.
4. Politique de mot de passe stricte (8+ caractères, 1 chiffre, 1 spécial)
   alignée avec le cahier des charges.
5. Confirmation du mot de passe (champ password2) + validation croisée.
"""

import re
from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.utils.translation import gettext_lazy as _

from .models import Touriste, Gestionnaire, Guide

User = get_user_model()


# ============================================================
# CLASSES CSS RÉUTILISABLES (Tailwind)
# ============================================================
# On centralise les classes pour pouvoir les modifier en un seul
# endroit. Plus maintenable que de répéter les classes dans chaque widget.
INPUT_CLASS = (
    "w-full px-4 py-2.5 border border-gray-300 rounded-lg "
    "focus:ring-2 focus:ring-green-600 focus:border-green-600 "
    "outline-none transition placeholder-gray-400 text-gray-900"
)
SELECT_CLASS = INPUT_CLASS + " bg-white"
CHECKBOX_CLASS = "w-4 h-4 text-green-600 border-gray-300 rounded focus:ring-green-500"


# ============================================================
# 1. FORMULAIRE DE CONNEXION
# ============================================================
class ConnexionForm(AuthenticationForm):
    """
    Formulaire de connexion par email + mot de passe.

    Hérite de `AuthenticationForm` de Django qui gère déjà :
    - La vérification des identifiants
    - Le verrouillage des comptes inactifs
    - Le message d'erreur générique (sécurité : on ne dit pas
      si c'est l'email ou le mot de passe qui est faux).
    """
    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': 'votre.email@exemple.com',
            'autocomplete': 'email',
            'autofocus': True,
        })
    )
    password = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': '••••••••',
            'autocomplete': 'current-password',
        })
    )
    remember_me = forms.BooleanField(
        required=False,
        label="Se souvenir de moi",
        widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS})
    )


# ============================================================
# 2. FORMULAIRE D'INSCRIPTION (Touriste par défaut)
# ============================================================
class InscriptionForm(forms.ModelForm):
    """
    Formulaire d'inscription touriste.

    Crée d'un coup :
    - Un User (table compte_user)
    - Un Touriste lié au User (table compte_touriste)

    Pour gestionnaire/guide, on a des formulaires dédiés en bas.
    """

    password = forms.CharField(
        label="Mot de passe",
        min_length=8,
        widget=forms.PasswordInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': 'Minimum 8 caractères',
            'autocomplete': 'new-password',
        }),
        help_text="Min. 8 caractères, avec 1 chiffre et 1 caractère spécial."
    )
    password_confirm = forms.CharField(
        label="Confirmer le mot de passe",
        widget=forms.PasswordInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': 'Retapez votre mot de passe',
            'autocomplete': 'new-password',
        })
    )
    nationalite = forms.CharField(
        label="Nationalité",
        initial='Camerounaise',
        widget=forms.TextInput(attrs={'class': INPUT_CLASS})
    )
    accepte_cgu = forms.BooleanField(
        label="J'accepte les conditions générales d'utilisation",
        required=True,
        widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS})
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'telephone']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': INPUT_CLASS, 'placeholder': 'Prénom'
            }),
            'last_name': forms.TextInput(attrs={
                'class': INPUT_CLASS, 'placeholder': 'Nom'
            }),
            'email': forms.EmailInput(attrs={
                'class': INPUT_CLASS, 'placeholder': 'votre.email@exemple.com'
            }),
            'telephone': forms.TextInput(attrs={
                'class': INPUT_CLASS, 'placeholder': '+237 6XX XXX XXX'
            }),
        }
        labels = {
            'first_name': 'Prénom',
            'last_name': 'Nom',
            'email': 'Adresse email',
            'telephone': 'Téléphone',
        }

    # --- Validations personnalisées ---

    def clean_email(self):
        """Vérifie l'unicité de l'email (insensible à la casse)."""
        email = self.cleaned_data['email'].lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "Un compte existe déjà avec cet email."
            )
        return email

    def clean_telephone(self):
        """
        Valide le format du numéro camerounais.
        Format attendu : +237 6XX XXX XXX ou 6XX XXX XXX
        """
        tel = self.cleaned_data.get('telephone', '').replace(' ', '')
        if tel and not re.match(r'^(\+237)?6[5-9]\d{7}$', tel):
            raise forms.ValidationError(
                "Numéro invalide. Format attendu : +237 6XX XXX XXX"
            )
        return tel

    def clean_password(self):
        """
        Politique de mot de passe stricte (cf. cahier des charges §9.1) :
        - 8 caractères minimum
        - Au moins 1 chiffre
        - Au moins 1 caractère spécial
        """
        pwd = self.cleaned_data['password']
        if not re.search(r'\d', pwd):
            raise forms.ValidationError(
                "Le mot de passe doit contenir au moins un chiffre."
            )
        if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=]', pwd):
            raise forms.ValidationError(
                "Le mot de passe doit contenir au moins un caractère spécial."
            )
        return pwd

    def clean(self):
        """Vérifie que les deux mots de passe correspondent."""
        cleaned = super().clean()
        pwd = cleaned.get('password')
        pwd2 = cleaned.get('password_confirm')
        if pwd and pwd2 and pwd != pwd2:
            self.add_error('password_confirm',
                "Les deux mots de passe ne correspondent pas."
            )
        return cleaned

    def save(self, commit=True):
        """
        Crée le User + le profil Touriste dans une transaction.
        Pourquoi ne pas appeler super().save() directement ?
        Parce que ModelForm sauve sans hasher le mot de passe.
        Il FAUT utiliser set_password() pour le hash Argon2/PBKDF2.
        """
        user = super().save(commit=False)
        user.email = user.email.lower()
        user.set_password(self.cleaned_data['password'])  # hash sécurisé
        user.type_user = User.UserType.TOURISTE

        if commit:
            user.save()
            # Création du profil touriste lié
            Touriste.objects.create(
                user=user,
                nationalite=self.cleaned_data['nationalite']
            )
        return user


# ============================================================
# 3. INSCRIPTION GESTIONNAIRE (avec validation admin)
# ============================================================
class InscriptionGestionnaireForm(InscriptionForm):
    """
    Inscription d'un gestionnaire de site.
    Champs supplémentaires : entreprise + N° registre commerce.
    Le compte reste en statut 'en_attente' jusqu'à validation admin.
    """
    entreprise = forms.CharField(
        label="Nom de l'entreprise",
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': 'Ex: Hôtel Atlantique SARL'
        })
    )
    num_registre_commerce = forms.CharField(
        label="N° de registre de commerce",
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': 'Ex: RC/YAO/2024/A/1234'
        })
    )

    # On retire le champ "nationalite" hérité du formulaire touriste
    nationalite = None

    def clean_num_registre_commerce(self):
        """Vérifie l'unicité du numéro de registre."""
        num = self.cleaned_data['num_registre_commerce'].upper().strip()
        if Gestionnaire.objects.filter(num_registre_commerce=num).exists():
            raise forms.ValidationError(
                "Ce numéro de registre est déjà utilisé."
            )
        return num

    def save(self, commit=True):
        """Crée User + profil Gestionnaire (en attente de validation)."""
        user = forms.ModelForm.save(self, commit=False)
        user.email = user.email.lower()
        user.set_password(self.cleaned_data['password'])
        user.type_user = User.UserType.GESTIONNAIRE
        user.is_active = False  # désactivé tant que pas validé

        if commit:
            user.save()
            Gestionnaire.objects.create(
                user=user,
                entreprise=self.cleaned_data['entreprise'],
                num_registre_commerce=self.cleaned_data['num_registre_commerce'],
            )
        return user


# ============================================================
# 4. MISE À JOUR DU PROFIL UTILISATEUR
# ============================================================
class ProfilForm(forms.ModelForm):
    """
    Formulaire de mise à jour du profil de base (commun à tous les types).
    Le mot de passe n'est PAS modifiable ici (formulaire dédié).
    """
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'telephone', 'photo_profil']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'last_name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'email': forms.EmailInput(attrs={'class': INPUT_CLASS}),
            'telephone': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'photo_profil': forms.ClearableFileInput(attrs={
                'class': 'block w-full text-sm text-gray-600 '
                         'file:mr-4 file:py-2 file:px-4 file:rounded-lg '
                         'file:border-0 file:bg-green-50 file:text-green-700 '
                         'hover:file:bg-green-100'
            }),
        }


class ProfilTouristeForm(forms.ModelForm):
    """Champs spécifiques au profil touriste."""
    class Meta:
        model = Touriste
        fields = ['nationalite', 'cni_passeport', 'type',
                  'langue_pref', 'date_naissance']
        widgets = {
            'nationalite': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'cni_passeport': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'type': forms.Select(attrs={'class': SELECT_CLASS}),
            'langue_pref': forms.Select(attrs={'class': SELECT_CLASS}),
            'date_naissance': forms.DateInput(attrs={
                'class': INPUT_CLASS, 'type': 'date'
            }),
        }


# ============================================================
# 5. CHANGEMENT DE MOT DE PASSE
# ============================================================
class ChangerPasswordForm(PasswordChangeForm):
    """
    Hérite du PasswordChangeForm de Django (gère déjà la vérification
    de l'ancien mot de passe + la mise à jour de la session).
    """
    old_password = forms.CharField(
        label="Mot de passe actuel",
        widget=forms.PasswordInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': 'Votre mot de passe actuel',
            'autocomplete': 'current-password',
        })
    )
    new_password1 = forms.CharField(
        label="Nouveau mot de passe",
        widget=forms.PasswordInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': 'Au moins 8 caractères',
            'autocomplete': 'new-password',
        }),
        help_text="Min. 8 caractères, avec 1 chiffre et 1 caractère spécial."
    )
    new_password2 = forms.CharField(
        label="Confirmer le nouveau mot de passe",
        widget=forms.PasswordInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': 'Retapez le nouveau mot de passe',
            'autocomplete': 'new-password',
        })
    )

    def clean_new_password1(self):
        """Politique de mot de passe identique à l'inscription."""
        pwd = self.cleaned_data['new_password1']
        if len(pwd) < 8:
            raise forms.ValidationError("8 caractères minimum.")
        if not re.search(r'\d', pwd):
            raise forms.ValidationError("Au moins un chiffre requis.")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=]', pwd):
            raise forms.ValidationError("Au moins un caractère spécial requis.")
        return pwd