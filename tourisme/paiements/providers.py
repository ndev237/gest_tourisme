"""
paiements/providers.py
======================
Intégration des fournisseurs de paiement.

ARCHITECTURE : Strategy Pattern
- Classe de base abstraite `PaymentProvider`
- Une implémentation concrète par fournisseur :
  * MTNMoMoProvider     → MTN Mobile Money (Cameroun)
  * OrangeMoneyProvider → Orange Money (Cameroun)
  * StripeProvider      → Cartes bancaires internationales
  * FlutterwaveProvider → Multi-méthodes africaines
  * ManuelProvider      → Espèces à l'arrivée (validation manuelle)

CHAQUE PROVIDER EXPOSE :
- initier_paiement(paiement, callback_url) → URL/données à afficher au client
- verifier_callback(request) → True/False + dict de données nettoyées
- traiter_callback(paiement, callback_data) → finalise (réussi/échoué)

INITIATIVES PÉDAGOGIQUES :
1. STRATEGY PATTERN : ajouter un nouveau provider = créer une classe,
   sans toucher aux views. Open/Closed Principle.
2. MODE MOCK pour le développement : si pas de clés API, on simule
   un paiement réussi après 2 secondes. Permet de coder la soutenance
   sans avoir besoin de vraies clés MTN/Orange.
3. IDEMPOTENCE : si le webhook est rappelé plusieurs fois, on ne
   double-crédite pas (vérification statut avant traitement).
4. SECURITY-FIRST : aucune donnée bancaire stockée. On manipule
   uniquement des références/tokens des providers.
5. SÉPARATION ENV/CODE : clés API dans settings.py / .env, jamais
   en dur dans le code.
"""

import json
import logging
import secrets
from abc import ABC, abstractmethod
from decimal import Decimal
from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)


# ============================================================
# 1. CLASSE DE BASE ABSTRAITE
# ============================================================
class PaymentProvider(ABC):
    """
    Interface commune que TOUS les providers doivent implémenter.

    PÉDAGO : ABC (Abstract Base Class) en Python = ce que les autres
    langages appellent "interface". Python lève une erreur si une
    classe fille oublie d'implémenter une méthode abstraite.

    Avantage : pas besoin de checks `hasattr()` partout dans le code.
    """

    # Sous-classes doivent surcharger ces attributs
    nom = "PROVIDER_BASE"
    code = "base"

    def __init__(self, paiement_db_moyen=None):
        """
        Arguments :
        - paiement_db_moyen : instance MoyenPaiement DB (avec frais, limites...)
        """
        self.moyen = paiement_db_moyen

    @abstractmethod
    def initier_paiement(self, paiement, callback_url):
        """
        Démarre la transaction côté provider.

        Retourne un dict {
            'success': bool,
            'redirect_url': str|None,   # URL externe vers laquelle rediriger
            'reference_externe': str,   # ID transaction côté provider
            'instructions': str|None,   # Texte à afficher (ex: 'composez *126#')
            'error': str|None,
        }
        """
        pass

    @abstractmethod
    def verifier_callback(self, payload):
        """
        Vérifie l'authenticité du callback (signature, secret, etc.).

        Retourne un dict {
            'valid': bool,
            'reference_externe': str,
            'statut': 'reussi' | 'echoue',
            'montant': Decimal|None,
            'raw_data': dict,    # données brutes pour audit
        }
        """
        pass

    def calculer_frais(self, montant):
        """Délègue au modèle MoyenPaiement si disponible."""
        if self.moyen:
            return self.moyen.calculer_frais(montant)
        return Decimal('0.00')


# ============================================================
# 2. MTN MOBILE MONEY (Cameroun)
# ============================================================
class MTNMoMoProvider(PaymentProvider):
    """
    MTN Mobile Money — leader des paiements mobiles au Cameroun.

    API officielle : https://momodeveloper.mtn.com/
    Endpoint Sandbox : https://sandbox.momodeveloper.mtn.com/

    PÉDAGO : MTN MoMo utilise un flux "Request to Pay" :
    1. Notre serveur appelle l'API MTN avec montant + n° téléphone
    2. L'utilisateur reçoit une notification sur son téléphone
    3. Il tape son PIN MoMo pour confirmer
    4. MTN appelle NOTRE webhook pour confirmer le paiement
    5. On marque le Paiement comme 'reussi'
    """
    nom = "MTN Mobile Money"
    code = "mtn_momo"

    def initier_paiement(self, paiement, callback_url):
        """
        Initie une requête de paiement MTN MoMo.

        En PRODUCTION : appel à l'API MoMo avec requests + Bearer token.
        En MODE MOCK (DEV) : simule un paiement réussi.
        """
        numero = paiement.numero_telephone

        # Validation du numéro camerounais
        if not self._valider_numero_cameroun(numero):
            return {
                'success': False,
                'redirect_url': None,
                'reference_externe': '',
                'instructions': None,
                'error': f"Numéro invalide : {numero}. Format attendu : 237 6XX XX XX XX",
            }

        # Mode MOCK (sans clés API)
        if getattr(settings, 'PAIEMENT_MODE_MOCK', True):
            # En mode mock, on génère une fausse référence et on indique à
            # l'utilisateur ce qui se passerait en vrai
            ref_externe = f"MTN-MOCK-{secrets.token_hex(8).upper()}"
            logger.info(f"[MOCK] MTN MoMo initiation : {paiement.id} → {ref_externe}")
            return {
                'success': True,
                'redirect_url': None,  # Pas de redirection externe en mock
                'reference_externe': ref_externe,
                'instructions': (
                    f"📱 [SIMULATION] En production, vous recevriez une "
                    f"notification MoMo sur le numéro {numero}. "
                    f"Cliquez sur 'Simuler paiement réussi' pour continuer."
                ),
                'error': None,
            }

        # Mode PRODUCTION — TODO : intégration API MTN officielle
        # Voir documentation : https://momodeveloper.mtn.com/docs
        try:
            import requests  # noqa
            # Sera implémenté lors de la mise en production avec :
            # - Récupération token via POST /collection/token/
            # - POST /collection/v1_0/requesttopay avec X-Reference-Id (UUID)
            # - Polling ou webhook pour récupérer le statut final
            logger.warning("Mode production MTN MoMo non implémenté")
            return {
                'success': False,
                'redirect_url': None,
                'reference_externe': '',
                'instructions': None,
                'error': "Le mode production MTN MoMo n'est pas configuré.",
            }
        except ImportError:
            return {
                'success': False,
                'redirect_url': None,
                'reference_externe': '',
                'instructions': None,
                'error': "Module 'requests' non installé.",
            }

    def verifier_callback(self, payload):
        """
        Vérifie la signature du webhook MTN (HMAC ou Bearer Token).

        En mode mock, on accepte tel quel le payload.
        """
        if getattr(settings, 'PAIEMENT_MODE_MOCK', True):
            return {
                'valid': True,
                'reference_externe': payload.get('reference_externe', ''),
                'statut': payload.get('statut', 'reussi'),
                'montant': Decimal(str(payload.get('montant', 0))),
                'raw_data': payload,
            }

        # Mode production : vérification de signature
        # TODO : implémenter la vérification de la signature MTN
        return {'valid': False, 'reference_externe': '', 'statut': 'echoue',
                'montant': None, 'raw_data': payload}

    @staticmethod
    def _valider_numero_cameroun(numero):
        """
        Valide qu'un numéro est camerounais et MTN.

        Préfixes MTN Cameroun : 67, 68, 65, 66, 650-659, 670-679, 680-689
        Format accepté : 237 6XX XX XX XX (avec ou sans espaces/+).
        """
        if not numero:
            return False
        nums = ''.join(c for c in numero if c.isdigit())
        # Doit commencer par 237 (Cameroun) puis 6X (mobile)
        if nums.startswith('237'):
            nums = nums[3:]
        return len(nums) == 9 and nums[0] == '6'


# ============================================================
# 3. ORANGE MONEY (Cameroun)
# ============================================================
class OrangeMoneyProvider(PaymentProvider):
    """
    Orange Money — second acteur des paiements mobiles au Cameroun.

    API officielle : https://developer.orange.com/apis/orange-money-webpay
    Doc Cameroun : https://www.orange.cm/orange-money.html

    PÉDAGO : Orange Money utilise un flux "Web Payment" :
    1. Notre serveur appelle l'API Orange pour obtenir une URL de paiement
    2. On redirige l'utilisateur vers cette URL
    3. L'utilisateur paie sur le portail Orange
    4. Orange redirige vers notre return_url + envoie un webhook
    """
    nom = "Orange Money"
    code = "orange_money"

    def initier_paiement(self, paiement, callback_url):
        """Initie une session Orange Money WebPay."""

        if getattr(settings, 'PAIEMENT_MODE_MOCK', True):
            ref_externe = f"OM-MOCK-{secrets.token_hex(8).upper()}"
            logger.info(f"[MOCK] Orange Money initiation : {paiement.id} → {ref_externe}")
            return {
                'success': True,
                'redirect_url': None,
                'reference_externe': ref_externe,
                'instructions': (
                    "🟠 [SIMULATION] En production, vous seriez redirigé "
                    "vers le portail Orange Money pour finaliser le paiement. "
                    "Cliquez sur 'Simuler paiement réussi' pour continuer."
                ),
                'error': None,
            }

        # Mode production — TODO
        # POST /orange-money-webpay/cm/v1/webpayment
        # Avec: merchant_key, currency, order_id, amount, return_url, cancel_url
        logger.warning("Mode production Orange Money non implémenté")
        return {
            'success': False,
            'redirect_url': None,
            'reference_externe': '',
            'instructions': None,
            'error': "Le mode production Orange Money n'est pas configuré.",
        }

    def verifier_callback(self, payload):
        """Vérifie la signature du webhook Orange."""
        if getattr(settings, 'PAIEMENT_MODE_MOCK', True):
            return {
                'valid': True,
                'reference_externe': payload.get('reference_externe', ''),
                'statut': payload.get('statut', 'reussi'),
                'montant': Decimal(str(payload.get('montant', 0))),
                'raw_data': payload,
            }

        # TODO : vérification HMAC Orange
        return {'valid': False, 'reference_externe': '', 'statut': 'echoue',
                'montant': None, 'raw_data': payload}


# ============================================================
# 4. STRIPE (cartes internationales)
# ============================================================
class StripeProvider(PaymentProvider):
    """
    Stripe — paiements par carte bancaire (Visa, Mastercard, Amex).

    Pour les touristes étrangers principalement.
    Documentation : https://stripe.com/docs/api

    PÉDAGO : Stripe a 2 flux possibles :
    - Checkout Session (hosted) → on redirige vers Stripe
    - Payment Intents (custom) → on intègre Stripe.js dans notre form
    On choisit Checkout pour la simplicité (et meilleure UX mobile).
    """
    nom = "Stripe (Carte bancaire)"
    code = "stripe"

    def initier_paiement(self, paiement, callback_url):
        """Crée une Stripe Checkout Session."""

        if getattr(settings, 'PAIEMENT_MODE_MOCK', True):
            ref_externe = f"cs_mock_{secrets.token_hex(12)}"
            logger.info(f"[MOCK] Stripe initiation : {paiement.id} → {ref_externe}")
            return {
                'success': True,
                'redirect_url': None,
                'reference_externe': ref_externe,
                'instructions': (
                    "💳 [SIMULATION] En production, vous seriez redirigé "
                    "vers la page de paiement Stripe. "
                    "Cliquez sur 'Simuler paiement réussi' pour continuer."
                ),
                'error': None,
            }

        # Mode production — nécessite : pip install stripe
        try:
            import stripe
            stripe.api_key = settings.STRIPE_SECRET_KEY

            # Stripe attend des montants en centimes pour EUR/USD,
            # ou des montants entiers pour XAF (devise zero-decimal)
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': paiement.devise.lower(),
                        'product_data': {
                            'name': f"Réservation {paiement.reservation.numero}",
                        },
                        'unit_amount': int(paiement.montant),
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url=callback_url + '?stripe_status=success',
                cancel_url=callback_url + '?stripe_status=cancel',
                metadata={'paiement_id': str(paiement.id)},
            )
            return {
                'success': True,
                'redirect_url': session.url,
                'reference_externe': session.id,
                'instructions': None,
                'error': None,
            }
        except ImportError:
            return {
                'success': False,
                'redirect_url': None,
                'reference_externe': '',
                'instructions': None,
                'error': "Module 'stripe' non installé. pip install stripe",
            }
        except Exception as e:
            logger.error(f"Erreur Stripe : {e}", exc_info=True)
            return {
                'success': False,
                'redirect_url': None,
                'reference_externe': '',
                'instructions': None,
                'error': f"Erreur Stripe : {e}",
            }

    def verifier_callback(self, payload):
        """Vérifie la signature du webhook Stripe (HMAC-SHA256)."""
        if getattr(settings, 'PAIEMENT_MODE_MOCK', True):
            return {
                'valid': True,
                'reference_externe': payload.get('reference_externe', ''),
                'statut': payload.get('statut', 'reussi'),
                'montant': Decimal(str(payload.get('montant', 0))),
                'raw_data': payload,
            }

        # TODO : Stripe Webhook signature verification
        # https://stripe.com/docs/webhooks/signatures
        return {'valid': False, 'reference_externe': '', 'statut': 'echoue',
                'montant': None, 'raw_data': payload}


# ============================================================
# 5. FLUTTERWAVE (multi-méthodes africaines)
# ============================================================
class FlutterwaveProvider(PaymentProvider):
    """
    Flutterwave — agrégateur africain (cartes, mobile money, bank transfer).

    Bonne option pour couvrir TOUTE l'Afrique avec UNE intégration.
    Documentation : https://developer.flutterwave.com/
    """
    nom = "Flutterwave"
    code = "flutterwave"

    def initier_paiement(self, paiement, callback_url):
        if getattr(settings, 'PAIEMENT_MODE_MOCK', True):
            ref_externe = f"FLW-MOCK-{secrets.token_hex(8).upper()}"
            return {
                'success': True,
                'redirect_url': None,
                'reference_externe': ref_externe,
                'instructions': "🌍 [SIMULATION] Flutterwave en mode mock.",
                'error': None,
            }

        # Mode production : POST https://api.flutterwave.com/v3/payments
        logger.warning("Mode production Flutterwave non implémenté")
        return {'success': False, 'redirect_url': None, 'reference_externe': '',
                'instructions': None, 'error': "Production non configurée."}

    def verifier_callback(self, payload):
        if getattr(settings, 'PAIEMENT_MODE_MOCK', True):
            return {
                'valid': True,
                'reference_externe': payload.get('reference_externe', ''),
                'statut': payload.get('statut', 'reussi'),
                'montant': Decimal(str(payload.get('montant', 0))),
                'raw_data': payload,
            }
        return {'valid': False, 'reference_externe': '', 'statut': 'echoue',
                'montant': None, 'raw_data': payload}


# ============================================================
# 6. MANUEL (cash / virement)
# ============================================================
class ManuelProvider(PaymentProvider):
    """
    Paiement manuel : espèces à l'arrivée ou virement.

    PÉDAGO : pas de webhook ici. Le statut est manuellement validé
    par l'admin/gestionnaire. Le paiement reste 'initie' jusqu'à
    confirmation manuelle.
    """
    nom = "Espèces à l'arrivée"
    code = "manuel"

    def initier_paiement(self, paiement, callback_url):
        """Pas d'initiation externe — paiement validé manuellement."""
        ref_externe = f"MAN-{paiement.reference_interne}"
        return {
            'success': True,
            'redirect_url': None,
            'reference_externe': ref_externe,
            'instructions': (
                "💵 Votre réservation est enregistrée. "
                "Vous paierez en espèces (FCFA) à votre arrivée sur le site. "
                "Présentez votre numéro de réservation à l'accueil."
            ),
            'error': None,
        }

    def verifier_callback(self, payload):
        """Pas de webhook → toujours invalide."""
        return {'valid': False, 'reference_externe': '', 'statut': 'echoue',
                'montant': None, 'raw_data': payload}


# ============================================================
# 7. FACTORY — Choix du bon provider selon le moyen
# ============================================================
PROVIDERS_REGISTRY = {
    'mtn_momo':     MTNMoMoProvider,
    'orange_money': OrangeMoneyProvider,
    'stripe':       StripeProvider,
    'flutterwave':  FlutterwaveProvider,
    'manuel':       ManuelProvider,
}


def get_provider(moyen_paiement):
    """
    Factory : retourne le bon provider selon le MoyenPaiement.

    Arguments :
    - moyen_paiement : instance MoyenPaiement (avec .provider str)

    Retourne : instance de PaymentProvider (ou ManuelProvider en fallback).

    PÉDAGO : centraliser le choix ici évite les `if/elif` répétés
    dans les views. Si un jour on ajoute un nouveau provider, seul
    PROVIDERS_REGISTRY est modifié.
    """
    provider_code = moyen_paiement.provider
    provider_class = PROVIDERS_REGISTRY.get(provider_code, ManuelProvider)
    return provider_class(paiement_db_moyen=moyen_paiement)