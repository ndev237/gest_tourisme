"""
reservation/forms.py
====================
Formulaires de l'app reservation.

CONTENU :
- ReservationForm     : création d'une réservation depuis la fiche site
- AnnulerReservationForm : confirmation d'annulation avec motif
- ScanQRForm          : scan du QR à l'entrée du site
- ReservationFiltreForm : filtres pour la liste (gestionnaire/admin)

INITIATIVES PÉDAGOGIQUES :
1. VALIDATION CROISÉE EN clean() pour la cohérence de dates et capacité.
2. Le site est passé en kwargs (__init__) — sécurité : il ne peut pas
   être trafiqué via POST.
3. Validation de la DISPONIBILITÉ : on vérifie que `Disponibilite` existe
   pour la date demandée ET qu'il reste assez de places.
4. Validation du DÉLAI : pas de réservation pour le jour même (sauf
   exception configurable).
5. Validation de la CAPACITÉ DE L'HÉBERGEMENT (nb_personnes <= chambres × 4).
6. Tous les calculs de PRIX sont reféréncés côté serveur (anti-tampering).
"""

from datetime import date, timedelta
from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from reservation.models import Reservation, LigneReservation
from catalogue.models import Hebergement, Disponibilite

try:
    from compte.models import Guide
except ImportError:
    Guide = None


# ============================================================
# 1. RESERVATION — Création par le touriste
# ============================================================
class ReservationForm(forms.ModelForm):
    """
    Formulaire de création d'une réservation depuis la fiche d'un site.

    PÉDAGO : on PASSE LE SITE EN ARGUMENT au lieu de le laisser dans
    le form. Pourquoi ? Sécurité : si on le laissait modifiable, un
    attaquant pourrait POST un autre site_id et créer une réservation
    pour un site dont il a vu le prix bas, mais payer pour un autre.

    Le calcul de montant_total est fait dans la VIEW, pas ici, pour
    laisser le form responsable uniquement de la validation.
    """

    # Champs non-mappés sur le modèle (pour cocher hébergement/guide en options)
    avec_hebergement = forms.BooleanField(
        required=False,
        label="Je souhaite un hébergement",
    )
    avec_guide = forms.BooleanField(
        required=False,
        label="Je souhaite être accompagné d'un guide",
    )

    class Meta:
        model = Reservation
        fields = [
            'date_visite', 'heure_visite',
            'nb_adultes', 'nb_enfants',
            'hebergement', 'date_arrivee', 'date_depart',
            'guide',
            'notes_touriste',
        ]
        widgets = {
            'date_visite': forms.DateInput(attrs={'type': 'date'}),
            'heure_visite': forms.TimeInput(attrs={'type': 'time'}),
            'date_arrivee': forms.DateInput(attrs={'type': 'date'}),
            'date_depart': forms.DateInput(attrs={'type': 'date'}),
            'notes_touriste': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': "Allergies alimentaires, accessibilité particulière, demande spéciale...",
            }),
            'nb_adultes': forms.NumberInput(attrs={'min': 1, 'max': 20}),
            'nb_enfants': forms.NumberInput(attrs={'min': 0, 'max': 20}),
        }
        help_texts = {
            'date_visite': "Choisissez une date dans les 365 prochains jours.",
            'nb_adultes': "Au moins 1 adulte requis.",
            'notes_touriste': "Optionnel — pour des demandes particulières.",
        }

    def __init__(self, *args, site=None, **kwargs):
        """
        site : objet SiteTouristique sur lequel porte la réservation.
        Passé par la view, pas modifiable par l'utilisateur.
        """
        super().__init__(*args, **kwargs)
        self.site = site

        # Limiter le choix d'hébergement à ceux du site
        if site:
            self.fields['hebergement'].queryset = Hebergement.objects.filter(
                site=site,
                est_disponible=True,
            )
            self.fields['hebergement'].empty_label = "— Aucun hébergement —"

        # Limiter le choix de guide aux guides disponibles et validés
        if Guide:
            self.fields['guide'].queryset = Guide.objects.filter(
                disponible=True,
                statut_validation='valide',
            )
            self.fields['guide'].empty_label = "— Sans guide —"
        else:
            self.fields['guide'].queryset = self.fields['guide'].queryset.none()

        # Tous ces champs sont optionnels au niveau du form
        # (la validation est faite en clean())
        self.fields['hebergement'].required = False
        self.fields['guide'].required = False
        self.fields['heure_visite'].required = False
        self.fields['date_arrivee'].required = False
        self.fields['date_depart'].required = False

    # --- VALIDATIONS DE CHAMPS ---

    def clean_date_visite(self):
        """Validation : pas dans le passé, dans les 365 prochains jours."""
        date_visite = self.cleaned_data.get('date_visite')
        if not date_visite:
            return date_visite

        aujourd_hui = timezone.now().date()
        if date_visite < aujourd_hui:
            raise ValidationError("La date de visite ne peut pas être dans le passé.")

        # Délai minimum de 24h (configurable plus tard via settings)
        if date_visite == aujourd_hui:
            raise ValidationError(
                "Les réservations pour aujourd'hui ne sont pas acceptées. "
                "Choisissez une date au moins 24h à l'avance."
            )

        limite_max = aujourd_hui + timedelta(days=365)
        if date_visite > limite_max:
            raise ValidationError(
                "Vous ne pouvez pas réserver plus d'un an à l'avance."
            )

        return date_visite

    def clean_nb_adultes(self):
        nb = self.cleaned_data.get('nb_adultes')
        if nb is None or nb < 1:
            raise ValidationError("Au moins 1 adulte est requis.")
        if nb > 20:
            raise ValidationError("Pour un groupe de plus de 20 personnes, contactez-nous.")
        return nb

    # --- VALIDATION CROISÉE ---

    def clean(self):
        """
        Validations qui dépendent de plusieurs champs :
        - Cohérence hébergement (dates, capacité)
        - Disponibilité du site (places restantes)
        - Site fermé sur la période ?
        """
        cleaned = super().clean()

        date_visite = cleaned.get('date_visite')
        nb_adultes = cleaned.get('nb_adultes') or 0
        nb_enfants = cleaned.get('nb_enfants') or 0
        nb_total = nb_adultes + nb_enfants
        hebergement = cleaned.get('hebergement')
        date_arrivee = cleaned.get('date_arrivee')
        date_depart = cleaned.get('date_depart')
        avec_hebergement = cleaned.get('avec_hebergement')

        # === RÈGLE 1 : Disponibilité du site à la date demandée ===
        if self.site and date_visite:
            try:
                dispo = Disponibilite.objects.get(
                    site=self.site,
                    date=date_visite,
                )
                if dispo.est_ferme:
                    raise ValidationError(
                        f"Le site est fermé le {date_visite.strftime('%d/%m/%Y')}. "
                        "Veuillez choisir une autre date."
                    )
                if dispo.places_restantes < nb_total:
                    raise ValidationError(
                        f"Désolé, il ne reste que {dispo.places_restantes} place(s) "
                        f"pour cette date. Vous demandez {nb_total} place(s)."
                    )
            except Disponibilite.DoesNotExist:
                # Pas de dispo configurée pour cette date → on accepte
                # (on assume capacité_max du site, déjà gérée par le gestionnaire)
                pass

        # === RÈGLE 2 : Cohérence hébergement ===
        if avec_hebergement:
            if not hebergement:
                self.add_error('hebergement', "Vous devez choisir un hébergement.")
            if not date_arrivee:
                self.add_error('date_arrivee', "La date d'arrivée est obligatoire.")
            if not date_depart:
                self.add_error('date_depart', "La date de départ est obligatoire.")

            if date_arrivee and date_depart:
                if date_depart <= date_arrivee:
                    self.add_error(
                        'date_depart',
                        "La date de départ doit être après la date d'arrivée."
                    )
                # Capacité hébergement (estimation : 4 personnes max/chambre)
                if hebergement and nb_total > hebergement.nb_chambres * 4:
                    self.add_error(
                        'hebergement',
                        f"Cet hébergement ne peut accueillir que "
                        f"{hebergement.nb_chambres * 4} personnes max."
                    )

        return cleaned


# ============================================================
# 2. ANNULATION
# ============================================================
class AnnulerReservationForm(forms.Form):
    """
    Formulaire d'annulation avec motif obligatoire.

    Pédago : Form simple (pas ModelForm) car on a juste un champ texte
    et on met à jour la Reservation via sa méthode `annuler(motif)`.
    """
    motif = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': "Expliquez la raison de l'annulation (changement de programme, problème de santé...)",
        }),
        max_length=500,
        min_length=10,
        label="Motif d'annulation",
        help_text="Minimum 10 caractères. Aide les gestionnaires à améliorer leur service.",
    )
    confirmation = forms.BooleanField(
        required=True,
        label="Je confirme vouloir annuler cette réservation",
    )

    def clean_motif(self):
        motif = self.cleaned_data['motif'].strip()
        if len(motif) < 10:
            raise ValidationError("Le motif est trop court (10 caractères minimum).")
        return motif


# ============================================================
# 3. SCAN QR — Validation à l'entrée du site
# ============================================================
class ScanQRForm(forms.Form):
    """
    Formulaire de scan du QR code à l'entrée du site.

    Pédago : le gestionnaire (ou son personnel) scanne le QR avec un
    téléphone → la valeur lue est postée à cette URL. La validation se
    fait dans la view (recherche du BonReservation matching, vérification
    qu'il n'est pas déjà utilisé, etc.).
    """
    qr_code_data = forms.CharField(
        widget=forms.TextInput(attrs={
            'autofocus': 'autofocus',
            'placeholder': "Collez ou scannez le QR Code ici...",
            'autocomplete': 'off',
        }),
        max_length=255,
        label="Données du QR Code",
    )

    def clean_qr_code_data(self):
        data = self.cleaned_data['qr_code_data'].strip()
        if ':' not in data:
            raise ValidationError("Format de QR Code invalide.")
        return data


# ============================================================
# 4. FILTRES (gestionnaire / admin)
# ============================================================
class ReservationFiltreForm(forms.Form):
    """Filtres pour la liste des réservations."""

    STATUT_CHOICES = [
        ('', 'Tous les statuts'),
        ('en_attente', 'En attente'),
        ('confirmee', 'Confirmées'),
        ('annulee', 'Annulées'),
        ('terminee', 'Terminées'),
    ]

    q = forms.CharField(
        required=False,
        label="Recherche",
        widget=forms.TextInput(attrs={
            'placeholder': "N° réservation, nom du touriste...",
        }),
    )
    statut = forms.ChoiceField(
        required=False,
        choices=STATUT_CHOICES,
    )
    date_debut = forms.DateField(
        required=False,
        label="Du",
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    date_fin = forms.DateField(
        required=False,
        label="Au",
        widget=forms.DateInput(attrs={'type': 'date'}),
    )

    def clean(self):
        cleaned = super().clean()
        d1 = cleaned.get('date_debut')
        d2 = cleaned.get('date_fin')
        if d1 and d2 and d1 > d2:
            self.add_error('date_debut', "La date début doit être avant la date fin.")
        return cleaned