"""
reviews/forms.py
================
Formulaires pour la gestion des avis et favoris.

INITIATIVES PÉDAGOGIQUES
1. AvisForm : note 1-5 + commentaire ; les sous-notes (accueil, propreté, qualité-prix)
   sont optionnelles pour ne pas alourdir l'UX initiale.
2. AvisModerationForm : approuver/rejeter/signaler avec motif si rejet.
3. ReponseGestionnaireForm : permet au gestionnaire de répondre à un avis.
"""

from django import forms
from django.core.exceptions import ValidationError

from reviews.models import Avis


# ============================================================
# 1. FORM TOURISTE — Laisser ou modifier un avis
# ============================================================
class AvisForm(forms.ModelForm):
    """Formulaire utilisé par le touriste pour créer/modifier un avis."""

    class Meta:
        model = Avis
        fields = [
            'note',
            'titre',
            'commentaire',
            'note_accueil',
            'note_proprete',
            'note_rapport_qualite_prix',
        ]
        widgets = {
            'note': forms.NumberInput(attrs={
                'min': 1, 'max': 5, 'step': 1,
                'class': 'hidden',  # caché — géré par Alpine.js (étoiles cliquables)
            }),
            'titre': forms.TextInput(attrs={
                'maxlength': 120,
                'placeholder': "Une visite mémorable…",
            }),
            'commentaire': forms.Textarea(attrs={
                'rows': 6, 'maxlength': 1500,
                'placeholder': "Qu'avez-vous le plus aimé ? À recommander pour qui ?",
            }),
            'note_accueil': forms.NumberInput(attrs={'min': 1, 'max': 5}),
            'note_proprete': forms.NumberInput(attrs={'min': 1, 'max': 5}),
            'note_rapport_qualite_prix': forms.NumberInput(attrs={'min': 1, 'max': 5}),
        }
        labels = {
            'note': "Note globale",
            'titre': "Titre",
            'commentaire': "Votre récit",
            'note_accueil': "Note accueil",
            'note_proprete': "Note propreté",
            'note_rapport_qualite_prix': "Note rapport qualité/prix",
        }

    def clean_commentaire(self):
        """Au minimum 20 caractères pour décourager les avis vides."""
        commentaire = self.cleaned_data.get('commentaire', '').strip()
        if len(commentaire) < 20:
            raise ValidationError(
                "Votre commentaire doit faire au moins 20 caractères pour aider les autres voyageurs."
            )
        return commentaire

    def clean_note(self):
        note = self.cleaned_data.get('note')
        if note is None or not (1 <= note <= 5):
            raise ValidationError("La note doit être comprise entre 1 et 5.")
        return note


# ============================================================
# 2. FORM ADMIN — Modération
# ============================================================
class AvisModerationForm(forms.Form):
    """Approuver ou rejeter un avis (admin)."""

    DECISION_CHOICES = [
        ('approuver', 'Approuver'),
        ('rejeter', 'Rejeter'),
    ]

    decision = forms.ChoiceField(
        choices=DECISION_CHOICES,
        widget=forms.RadioSelect,
        label="Décision",
    )
    motif_rejet = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3, 'maxlength': 500}),
        required=False,
        label="Motif (obligatoire si rejet)",
        help_text="Sera visible par le touriste qui a posté l'avis.",
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('decision') == 'rejeter' and not (cleaned.get('motif_rejet') or '').strip():
            raise ValidationError({
                'motif_rejet': "Un motif est requis pour rejeter un avis."
            })
        return cleaned


# ============================================================
# 3. FORM GESTIONNAIRE — Réponse à un avis
# ============================================================
class ReponseGestionnaireForm(forms.Form):
    """Le gestionnaire d'un site peut répondre publiquement à un avis."""

    reponse = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 4, 'maxlength': 800,
            'placeholder': "Merci pour votre visite et votre retour…",
        }),
        label="Votre réponse",
        min_length=10,
        max_length=800,
    )


# ============================================================
# 4. FORM TOURISTE — Signaler un avis abusif
# ============================================================
class SignalementAvisForm(forms.Form):
    """Permet à un utilisateur de signaler un avis problématique."""

    MOTIF_CHOICES = [
        ('faux', "Avis manifestement faux"),
        ('insulte', "Contenu insultant ou diffamatoire"),
        ('hors_sujet', "Hors-sujet par rapport au site"),
        ('spam', "Spam ou publicité"),
        ('autre', "Autre raison"),
    ]

    motif = forms.ChoiceField(
        choices=MOTIF_CHOICES,
        widget=forms.RadioSelect,
        label="Pourquoi signaler cet avis ?",
    )
    commentaire = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 2, 'maxlength': 300}),
        required=False,
        label="Précisez (optionnel)",
    )
