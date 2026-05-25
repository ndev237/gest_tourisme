"""
paiements/forms.py
==================
Formulaires de l'app paiements.

CONTENU :
- ChoixMoyenForm        : sélection du moyen pour une réservation
- NumeroTelephoneForm   : saisie du numéro MoMo / Orange Money
- MoyenPaiementForm     : CRUD admin du référentiel
- PaiementFiltreForm    : filtres pour la liste admin
- RembourserForm        : initier un remboursement

INITIATIVES PÉDAGOGIQUES :
1. ChoixMoyenForm est un ModelChoiceField qui filtre dynamiquement
   selon les moyens ACTIFS et compatibles avec le montant.
2. Validation côté serveur : montant_min ≤ paiement ≤ montant_max,
   devise supportée, frais.
3. Numéro téléphone validé selon le provider (MTN ou Orange).
"""

from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError

from paiements.models import MoyenPaiement, Paiement


# ============================================================
# 1. CHOIX DU MOYEN DE PAIEMENT
# ============================================================
class ChoixMoyenForm(forms.Form):
    """
    Formulaire de sélection du moyen de paiement pour une réservation.

    PÉDAGO :
    - Form simple (pas ModelForm) : on persiste rien ici, on choisit
      juste vers quel provider router.
    - Le queryset est filtré sur les moyens actifs ET compatibles avec
      le montant (entre montant_min et montant_max).
    """
    moyen = forms.ModelChoiceField(
        queryset=MoyenPaiement.objects.none(),  # Surchargé dans __init__
        widget=forms.RadioSelect,
        empty_label=None,
        label="Comment souhaitez-vous payer ?",
    )

    def __init__(self, *args, montant=None, **kwargs):
        """
        montant : montant à payer, pour filtrer les moyens compatibles.
        """
        super().__init__(*args, **kwargs)
        self.montant = montant or Decimal('0')

        # Filtre des moyens actifs ET compatibles avec le montant
        qs = MoyenPaiement.objects.filter(est_actif=True)
        if self.montant > 0:
            qs = qs.filter(
                montant_min__lte=self.montant,
                montant_max__gte=self.montant,
            )
        self.fields['moyen'].queryset = qs.order_by('ordre_affichage', 'libelle')


# ============================================================
# 2. NUMÉRO TÉLÉPHONE (pour MoMo / Orange Money)
# ============================================================
class NumeroTelephoneForm(forms.Form):
    """
    Formulaire de saisie du numéro de téléphone pour Mobile Money.

    PÉDAGO :
    - Validation stricte au format camerounais
    - On peut accepter 6XX XX XX XX ou 237 6XX XX XX XX
    - Normalisation interne au format 2376XXXXXXXX (sans espaces)
    """
    numero_telephone = forms.CharField(
        max_length=20,
        label="Numéro de téléphone Mobile Money",
        widget=forms.TextInput(attrs={
            'placeholder': '6XX XX XX XX',
            'inputmode': 'tel',
            'autocomplete': 'tel',
        }),
        help_text="Le numéro Mobile Money associé à votre compte (ex: 678 90 12 34)",
    )

    def __init__(self, *args, provider=None, **kwargs):
        """
        provider : code du provider ('mtn_momo' ou 'orange_money').
        Permet de valider que le numéro correspond au bon opérateur.
        """
        super().__init__(*args, **kwargs)
        self.provider = provider

    def clean_numero_telephone(self):
        """
        Normalise et valide le numéro.
        Format final : '2376XXXXXXXX' (12 chiffres au total).
        """
        raw = self.cleaned_data['numero_telephone'].strip()

        # Supprime tout sauf les chiffres
        digits = ''.join(c for c in raw if c.isdigit())

        # Si commence par 237, on garde tel quel
        # Sinon on préfixe automatiquement
        if digits.startswith('237'):
            normalise = digits
        elif digits.startswith('6'):
            normalise = '237' + digits
        else:
            raise ValidationError(
                "Format invalide. Le numéro doit commencer par 6 ou 237 6."
            )

        # Doit faire 12 chiffres au total (237 + 9 chiffres)
        if len(normalise) != 12:
            raise ValidationError(
                f"Numéro invalide ({len(normalise)} chiffres). "
                f"Format attendu : 237 suivi de 9 chiffres."
            )

        # Le numéro doit commencer par 2376 (préfixe mobile camerounais)
        if not normalise.startswith('2376'):
            raise ValidationError(
                "Ce numéro ne semble pas être un numéro mobile camerounais."
            )

        # Validation du préfixe selon le provider
        prefixe = normalise[3:5]  # Les 2 chiffres après 237

        if self.provider == 'mtn_momo':
            # MTN Cameroun : 67, 68, 65, 66, 650-654
            if prefixe not in ['67', '68', '65', '66']:
                raise ValidationError(
                    f"Ce numéro ne semble pas être un numéro MTN. "
                    f"Vérifiez le préfixe (attendu : 67, 68, 65 ou 66)."
                )
        elif self.provider == 'orange_money':
            # Orange Cameroun : 69, 65, 66, 655-659
            if prefixe not in ['69', '65', '66']:
                raise ValidationError(
                    f"Ce numéro ne semble pas être un numéro Orange. "
                    f"Vérifiez le préfixe (attendu : 69, 65 ou 66)."
                )

        return normalise


# ============================================================
# 3. CRUD ADMIN — MOYEN DE PAIEMENT
# ============================================================
class MoyenPaiementForm(forms.ModelForm):
    """Formulaire admin pour créer/modifier un moyen de paiement."""

    class Meta:
        model = MoyenPaiement
        fields = [
            'libelle', 'code', 'type', 'provider',
            'icone', 'description', 'instructions',
            'devises_supportees',
            'montant_min', 'montant_max',
            'frais_pourcentage', 'frais_fixe',
            'est_actif', 'ordre_affichage',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'instructions': forms.Textarea(attrs={'rows': 3}),
            'devises_supportees': forms.Textarea(attrs={
                'rows': 1,
                'placeholder': '["XAF", "EUR", "USD"]',
            }),
        }
        help_texts = {
            'code': "Identifiant interne unique (ex: 'mtn_momo'). Ne pas modifier après création.",
            'devises_supportees': "Liste JSON de codes ISO 4217.",
            'frais_pourcentage': "Ex: 1.5 pour 1.5% (additionné aux frais fixes).",
        }

    def clean_code(self):
        """Force minuscules + underscore."""
        code = self.cleaned_data['code'].strip().lower().replace(' ', '_')
        if len(code) < 2:
            raise ValidationError("Le code est trop court.")
        return code

    def clean(self):
        cleaned = super().clean()
        montant_min = cleaned.get('montant_min')
        montant_max = cleaned.get('montant_max')
        if montant_min is not None and montant_max is not None:
            if montant_min > montant_max:
                self.add_error('montant_min', "Le min doit être inférieur au max.")
        return cleaned


# ============================================================
# 4. FILTRES (admin)
# ============================================================
class PaiementFiltreForm(forms.Form):
    """Filtres pour la liste admin des paiements."""

    STATUT_CHOICES = [
        ('', 'Tous les statuts'),
        ('initie', 'Initiés'),
        ('en_cours', 'En cours'),
        ('reussi', 'Réussis'),
        ('echoue', 'Échoués'),
        ('annule', 'Annulés'),
        ('rembourse', 'Remboursés'),
    ]

    q = forms.CharField(
        required=False,
        label="Recherche",
        widget=forms.TextInput(attrs={
            'placeholder': 'Référence, n° réservation, n° téléphone...',
        }),
    )
    statut = forms.ChoiceField(required=False, choices=STATUT_CHOICES)
    moyen = forms.ModelChoiceField(
        required=False,
        queryset=MoyenPaiement.objects.all(),
        empty_label="Tous les moyens",
    )
    date_debut = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Du",
    )
    date_fin = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Au",
    )

    def clean(self):
        cleaned = super().clean()
        d1, d2 = cleaned.get('date_debut'), cleaned.get('date_fin')
        if d1 and d2 and d1 > d2:
            self.add_error('date_debut', "La date début doit être avant la date fin.")
        return cleaned


# ============================================================
# 5. REMBOURSEMENT
# ============================================================
class RembourserForm(forms.Form):
    """Formulaire pour initier un remboursement (admin uniquement)."""
    montant = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('0.01'),
        label="Montant à rembourser (FCFA)",
        help_text="Doit être ≤ au montant initial du paiement.",
    )
    motif = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        max_length=500,
        min_length=10,
        label="Motif du remboursement",
    )
    confirmation = forms.BooleanField(
        required=True,
        label="Je confirme vouloir initier ce remboursement",
    )

    def __init__(self, *args, paiement=None, **kwargs):
        """paiement : Paiement source à rembourser."""
        super().__init__(*args, **kwargs)
        self.paiement = paiement
        if paiement:
            # Pré-rempli avec le montant total par défaut
            self.fields['montant'].initial = paiement.montant
            self.fields['montant'].help_text = (
                f"Maximum : {paiement.montant} {paiement.devise}"
            )

    def clean_montant(self):
        montant = self.cleaned_data['montant']
        if self.paiement and montant > self.paiement.montant:
            raise ValidationError(
                f"Le montant remboursé ne peut excéder "
                f"{self.paiement.montant} {self.paiement.devise}."
            )
        return montant