"""
core/management/commands/seed_demo.py
====================================
Commande Django pour peupler la base avec des données de démonstration
prêtes pour soutenance.

USAGE
    python manage.py seed_demo            # ajoute (idempotent)
    python manage.py seed_demo --reset    # vide d'abord la BDD
    python manage.py seed_demo --light    # version réduite (5 sites au lieu de 30)

CONTENU
- 10 régions du Cameroun (référentiel officiel)
- 8 catégories (Plage, Parc, Musée, Montagne, Chefferie, Cascade, Forêt, Lac)
- 12 tags (aventure, famille, romantique, gastronomie, photo…)
- 3 admins
- 5 gestionnaires validés
- 4 guides validés
- 8 touristes
- 30 sites touristiques publiés (vrais lieux du Cameroun avec GPS réels)
- Disponibilités sur 60 jours
- 15 hébergements
- 20 réservations à différents statuts
- 20 paiements (réussis/échoués/remboursés)
- 12 avis approuvés
- 8 favoris
"""

import random
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

User = get_user_model()


# ============================================================
# Référentiel : vrais sites du Cameroun avec coordonnées GPS
# ============================================================
SITES_REELS = [
    # (nom, ville, region_code, lat, lng, categorie_libelle, tarif, description)
    ("Mont Cameroun", "Buea", "SW", 4.2030, 9.1700, "Montagne", 25000,
     "Plus haut sommet d'Afrique de l'Ouest (4095 m). Ascension en 2 à 4 jours selon votre niveau."),
    ("Plages de Kribi", "Kribi", "SU", 2.9405, 9.9100, "Plage", 5000,
     "Plages de sable fin bordées de cocotiers, à 200 km au sud de Yaoundé."),
    ("Chutes de la Lobé", "Kribi", "SU", 2.8556, 9.9100, "Cascade", 3000,
     "Les seules chutes au monde qui se jettent directement dans l'océan."),
    ("Parc National de Waza", "Waza", "EN", 11.3833, 14.5667, "Parc", 15000,
     "Parc emblématique du Nord avec girafes, éléphants, lions et antilopes."),
    ("Lac Nyos", "Wum", "NW", 6.4382, 10.2982, "Lac", 8000,
     "Lac de cratère mystérieux, théâtre de la catastrophe gazeuse de 1986."),
    ("Chefferie de Bandjoun", "Bandjoun", "OU", 5.3833, 10.4167, "Chefferie", 4000,
     "Chefferie traditionnelle Bamiléké avec architecture en bois sculpté."),
    ("Musée National de Yaoundé", "Yaoundé", "CE", 3.8480, 11.5021, "Musée", 2500,
     "Histoire et culture du Cameroun, art africain et artefacts précoloniaux."),
    ("Réserve du Dja", "Somalomo", "ES", 3.2500, 13.0000, "Forêt", 12000,
     "Réserve UNESCO de forêt équatoriale primaire — gorilles, chimpanzés, éléphants."),
    ("Mont Manengouba", "Bangem", "LT", 5.0167, 9.8333, "Montagne", 10000,
     "Volcan éteint avec deux lacs jumeaux dans le cratère (Mâle et Femelle)."),
    ("Limbe Wildlife Centre", "Limbé", "SW", 4.0233, 9.2150, "Parc", 5000,
     "Centre de réhabilitation des primates orphelins, en bord de mer."),
    ("Palais des Sultans de Foumban", "Foumban", "OU", 5.7250, 10.9000, "Chefferie", 5500,
     "Palais royal Bamoun, art traditionnel et histoire du sultanat."),
    ("Cascades d'Ekom-Nkam", "Nkongsamba", "LT", 4.9667, 9.9333, "Cascade", 4000,
     "Chutes spectaculaires en pleine forêt tropicale, hauteur 80 m."),
    ("Parc National du Mbam et Djerem", "Tibati", "AD", 6.4667, 12.6333, "Parc", 13000,
     "Plus grand parc national du Cameroun (savane + forêt + cours d'eau)."),
    ("Île de Manoka", "Douala", "LT", 3.9667, 9.5500, "Plage", 3500,
     "Île au large de Douala, plages préservées et villages de pêcheurs."),
    ("Mont Kupe", "Bangem", "SW", 4.8000, 9.7167, "Montagne", 9000,
     "Forêt-nuage et mont sacré, biodiversité endémique exceptionnelle."),
    ("Chefferie de Bafut", "Bafut", "NW", 6.0967, 10.1033, "Chefferie", 4500,
     "Chefferie historique des Tikars, palais du roi Achirimbi II."),
    ("Plage de Londji", "Londji", "SU", 2.8333, 9.9000, "Plage", 4000,
     "Plage tranquille au sud de Kribi, idéale pour les couchers de soleil."),
    ("Parc National de Bénoué", "Tcholliré", "NO", 8.5000, 13.7833, "Parc", 14000,
     "Savane et galeries forestières, refuge des grands mammifères."),
    ("Lac Awing", "Awing", "NW", 5.9000, 10.1500, "Lac", 4500,
     "Lac de cratère paisible, vues panoramiques sur les hautes terres de l'Ouest."),
    ("Plage de Down Beach", "Limbé", "SW", 4.0167, 9.2167, "Plage", 3000,
     "Sable volcanique noir au pied du Mont Cameroun, restaurants de poisson grillé."),
    ("Musée Maritime de Douala", "Douala", "LT", 4.0500, 9.6967, "Musée", 3000,
     "Histoire de la navigation et du port de Douala, premier port d'Afrique centrale."),
    ("Grottes de Pinyin", "Pinyin", "NW", 5.9333, 10.1833, "Forêt", 5500,
     "Réseau de grottes calcaires, refuge ancestral des Pinyin."),
    ("Parc National de Korup", "Mundemba", "SW", 5.0500, 8.8500, "Forêt", 11000,
     "Une des plus anciennes forêts tropicales d'Afrique (60 millions d'années)."),
    ("Île aux Cocotiers", "Kribi", "SU", 2.9000, 9.9000, "Plage", 6000,
     "Petite île paradisiaque accessible en barque depuis Kribi."),
    ("Chefferie de Bangoua", "Bangoua", "OU", 5.4333, 10.4500, "Chefferie", 4000,
     "Architecture traditionnelle bamiléké et masques rituels."),
    ("Réserve de Faune de Lobéké", "Yokadouma", "ES", 2.2333, 15.7500, "Forêt", 16000,
     "Réserve forestière du Sud-Est, gorilles des plaines de l'Ouest."),
    ("Mont Oku", "Oku", "NW", 6.2500, 10.4500, "Montagne", 8500,
     "Deuxième sommet du Cameroun, lac sacré et oiseaux endémiques."),
    ("Chutes de la Mefou", "Mfou", "CE", 3.6800, 11.6300, "Cascade", 3500,
     "Cascades en cascade dans la forêt à 30 km de Yaoundé."),
    ("Musée Afhémi", "Douala", "LT", 4.0400, 9.7000, "Musée", 2500,
     "Collection d'art moderne et traditionnel camerounais et africain."),
    ("Réserve du Mbi Crater", "Belo", "NW", 6.1500, 10.2167, "Lac",  6000,
     "Cratère volcanique et lac alcalin, oiseaux migrateurs."),
]


REGIONS_DATA = [
    ('Adamaoua', 'AD', 'Ngaoundéré',
     "Plateau volcanique élevé entre savane et forêt. Grands parcs nationaux et élevage transhumant."),
    ('Centre', 'CE', 'Yaoundé',
     "Capitale politique, sept collines et nombreux musées. Cœur administratif du pays."),
    ('Est', 'ES', 'Bertoua',
     "Forêt équatoriale dense, réserves UNESCO et peuples Baka."),
    ('Extrême-Nord', 'EN', 'Maroua',
     "Mosaïque culturelle Sahel, marchés colorés et parcs animaliers (Waza, Mozogo)."),
    ('Littoral', 'LT', 'Douala',
     "Capitale économique, port maritime, plages et forêts atlantiques."),
    ('Nord', 'NO', 'Garoua',
     "Vallée de la Bénoué, parcs nationaux et architecture peuhle."),
    ('Nord-Ouest', 'NW', 'Bamenda',
     "Hauts plateaux, lacs de cratère, chefferies anglophones (Bafut, Mankon)."),
    ('Ouest', 'OU', 'Bafoussam',
     "Montagnes Bamilékés, chefferies traditionnelles, artisanat et cafés."),
    ('Sud', 'SU', 'Ebolowa',
     "Plages atlantiques (Kribi, Campo), forêt équatoriale et chutes de la Lobé."),
    ('Sud-Ouest', 'SW', 'Buea',
     "Mont Cameroun, plages de sable volcanique noir, ancien Cameroun britannique."),
]

CATEGORIES_DATA = [
    ('Plage',     '#F59E0B', 'Plages dorées et noires, sable, océan et palmiers.'),
    ('Parc',      '#15803D', 'Parcs nationaux et réserves animalières.'),
    ('Musée',     '#7C3AED', 'Musées et institutions culturelles.'),
    ('Montagne',  '#92400E', 'Sommets et volcans, du Mont Cameroun au Mont Oku.'),
    ('Chefferie', '#DC2626', 'Chefferies traditionnelles et palais royaux.'),
    ('Cascade',   '#0891B2', 'Chutes d\'eau et cascades.'),
    ('Forêt',     '#166534', 'Forêts équatoriales et réserves naturelles.'),
    ('Lac',       '#1E40AF', 'Lacs de cratère et lagunes côtières.'),
]

TAGS_DATA = [
    'aventure', 'famille', 'romantique', 'gastronomie', 'photo',
    'nature', 'culture', 'sport', 'détente', 'patrimoine',
    'enfants', 'éco-tourisme',
]


class Command(BaseCommand):
    help = "Peuple la base avec des données de démonstration prêtes pour soutenance."

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true',
                            help='Vide d\'abord les tables avant de remplir.')
        parser.add_argument('--light', action='store_true',
                            help='Version réduite (10 sites au lieu de 30).')

    def handle(self, *args, **opts):
        from localisation.models import Region, Localisation
        from catalogue.models import Categorie, Tag, SiteTouristique, Hebergement, Disponibilite
        from compte.models import Touriste, Gestionnaire, Guide, Administrateur
        from reservation.models import Reservation
        try:
            from paiements.models import Paiement, MoyenPaiement
        except ImportError:
            Paiement = None
            MoyenPaiement = None
        try:
            from reviews.models import Avis, Favori
        except ImportError:
            Avis = None
            Favori = None

        self.stdout.write(self.style.NOTICE('=' * 60))
        self.stdout.write(self.style.NOTICE('  SEED_DEMO — Tourisme Cameroun'))
        self.stdout.write(self.style.NOTICE('=' * 60))

        light = opts['light']
        if light:
            self.stdout.write(self.style.WARNING('Mode léger : 10 sites max.'))

        if opts['reset']:
            self.stdout.write(self.style.WARNING('[RESET] : suppression des données existantes…'))
            if Favori: Favori.objects.all().delete()
            if Avis: Avis.objects.all().delete()
            if Paiement: Paiement.objects.all().delete()
            Reservation.objects.all().delete()
            Disponibilite.objects.all().delete()
            Hebergement.objects.all().delete()
            SiteTouristique.objects.all().delete()
            Localisation.objects.all().delete()
            Touriste.objects.all().delete()
            Guide.objects.all().delete()
            Gestionnaire.objects.all().delete()
            Administrateur.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()

        with transaction.atomic():
            regions = self._seed_regions(Region)
            categories = self._seed_categories(Categorie)
            tags = self._seed_tags(Tag)

            admins = self._seed_admins(Administrateur)
            gestionnaires = self._seed_gestionnaires(Gestionnaire, admins)
            guides = self._seed_guides(Guide)
            touristes = self._seed_touristes(Touriste)

            sites = self._seed_sites(
                SiteTouristique, Localisation, regions, categories, tags,
                gestionnaires, max_sites=10 if light else 30,
            )

            self._seed_hebergements(Hebergement, sites)
            self._seed_disponibilites(Disponibilite, sites)

            if MoyenPaiement:
                moyens = self._seed_moyens_paiement(MoyenPaiement)
            else:
                moyens = []

            reservations = self._seed_reservations(
                Reservation, touristes, sites, light=light,
            )

            if Paiement and moyens:
                self._seed_paiements(Paiement, reservations, moyens)

            if Avis:
                self._seed_avis(Avis, reservations)

            if Favori:
                self._seed_favoris(Favori, touristes, sites)

        self.stdout.write(self.style.SUCCESS('\nBase de demo prete !'))
        self.stdout.write(self.style.SUCCESS('\nComptes de démonstration :'))
        self.stdout.write('  Admin       : admin@demo.cm        / Demo1234!')
        self.stdout.write('  Gestionnaire: gestionnaire@demo.cm / Demo1234!')
        self.stdout.write('  Guide       : guide@demo.cm        / Demo1234!')
        self.stdout.write('  Touriste    : touriste@demo.cm     / Demo1234!')
        self.stdout.write(self.style.NOTICE('=' * 60))

    # ---------- Helpers de création ----------

    def _seed_regions(self, Region):
        self.stdout.write('-Régions…', ending=' ')
        regions = {}
        for nom, code, chef_lieu, desc in REGIONS_DATA:
            r, _ = Region.objects.get_or_create(
                code=code,
                defaults={'nom': nom, 'chef_lieu': chef_lieu, 'description': desc},
            )
            regions[code] = r
        self.stdout.write(self.style.SUCCESS(f'{len(regions)} OK'))
        return regions

    def _seed_categories(self, Categorie):
        self.stdout.write('-Catégories…', ending=' ')
        categories = {}
        for i, (libelle, couleur, desc) in enumerate(CATEGORIES_DATA):
            c, _ = Categorie.objects.get_or_create(
                libelle=libelle,
                defaults={
                    'description': desc,
                    'couleur': couleur,
                    'ordre_affichage': i,
                },
            )
            categories[libelle] = c
        self.stdout.write(self.style.SUCCESS(f'{len(categories)} OK'))
        return categories

    def _seed_tags(self, Tag):
        self.stdout.write('-Tags…', ending=' ')
        tags = []
        for libelle in TAGS_DATA:
            t, _ = Tag.objects.get_or_create(libelle=libelle.lower())
            tags.append(t)
        self.stdout.write(self.style.SUCCESS(f'{len(tags)} OK'))
        return tags

    def _seed_admins(self, Administrateur):
        self.stdout.write('-Admins…', ending=' ')
        admins = []
        data = [
            ('admin@demo.cm',          'Marie',   'Ngono'),
            ('admin2@demo.cm',         'Jean',    'Mballa'),
            ('superadmin@demo.cm',     'Aïssa',   'Bello'),
        ]
        for email, prenom, nom in data:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': prenom, 'last_name': nom,
                    'type_user': 'admin', 'is_staff': True,
                    'is_active': True,
                },
            )
            if created:
                user.set_password('Demo1234!')
                user.save()
            admin, _ = Administrateur.objects.get_or_create(
                user=user,
                defaults={'role': 'super_admin', 'niveau_acces': 5},
            )
            admins.append(admin)
        self.stdout.write(self.style.SUCCESS(f'{len(admins)} OK'))
        return admins

    def _seed_gestionnaires(self, Gestionnaire, admins):
        self.stdout.write('-Gestionnaires…', ending=' ')
        gestionnaires = []
        data = [
            ('gestionnaire@demo.cm', 'Paul',     'Eteki',    'Eteki Tours SARL',       'RC/YA/2023/B/1234'),
            ('ges2@demo.cm',         'Sandra',   'Mbida',    'Mbida Travel & Events',  'RC/DLA/2023/B/5678'),
            ('ges3@demo.cm',         'Bertrand', 'Nguemo',   'Nguemo Expéditions',     'RC/YA/2024/B/0042'),
            ('ges4@demo.cm',         'Estelle',  'Tchoumi',  'Tchoumi Holidays',       'RC/BAF/2024/B/1111'),
            ('ges5@demo.cm',         'Hervé',    'Onana',    'Cameroon Wonders',       'RC/KRI/2024/B/2025'),
        ]
        for email, prenom, nom, entreprise, rc in data:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': prenom, 'last_name': nom,
                    'type_user': 'gestionnaire', 'is_active': True,
                },
            )
            if created:
                user.set_password('Demo1234!')
                user.save()
            g, _ = Gestionnaire.objects.get_or_create(
                user=user,
                defaults={
                    'entreprise': entreprise,
                    'num_registre_commerce': rc,
                    'statut_validation': 'valide',
                    'admin_valideur': admins[0],
                    'date_validation': timezone.now(),
                },
            )
            gestionnaires.append(g)
        self.stdout.write(self.style.SUCCESS(f'{len(gestionnaires)} OK'))
        return gestionnaires

    def _seed_guides(self, Guide):
        self.stdout.write('-Guides…', ending=' ')
        guides = []
        data = [
            ('guide@demo.cm',  'Yannick',  'Etoundi',  'GUI-001', 8,  35000),
            ('guide2@demo.cm', 'Aurélie',  'Manga',    'GUI-002', 12, 50000),
            ('guide3@demo.cm', 'Idriss',   'Sani',     'GUI-003', 5,  25000),
            ('guide4@demo.cm', 'Cécile',   'Voundi',   'GUI-004', 15, 65000),
        ]
        for email, prenom, nom, licence, exp, tarif in data:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': prenom, 'last_name': nom,
                    'type_user': 'guide', 'is_active': True,
                },
            )
            if created:
                user.set_password('Demo1234!')
                user.save()
            g, _ = Guide.objects.get_or_create(
                user=user,
                defaults={
                    'licence_pro': licence,
                    'tarif_journalier': Decimal(tarif),
                    'annees_experience': exp,
                    'bio': f"{prenom} {nom}, guide professionnel certifié depuis {exp} ans. "
                           "Spécialisé dans les visites culturelles et naturelles du Cameroun.",
                    'statut_validation': 'valide',
                    'disponible': True,
                    'note_moyenne': round(random.uniform(4.2, 4.9), 1),
                },
            )
            guides.append(g)
        self.stdout.write(self.style.SUCCESS(f'{len(guides)} OK'))
        return guides

    def _seed_touristes(self, Touriste):
        self.stdout.write('-Touristes…', ending=' ')
        touristes = []
        data = [
            ('touriste@demo.cm', 'Alice',    'Dupont',  'Française',    'etranger'),
            ('tou2@demo.cm',     'Marc',     'Tabi',    'Camerounaise', 'local'),
            ('tou3@demo.cm',     'Sophie',   'Owona',   'Camerounaise', 'local'),
            ('tou4@demo.cm',     'James',    'Brown',   'Américaine',   'etranger'),
            ('tou5@demo.cm',     'Linda',    'Nkam',    'Camerounaise', 'local'),
            ('tou6@demo.cm',     'Olivier',  'Bayemi',  'Camerounaise', 'local'),
            ('tou7@demo.cm',     'Karine',   'Eyenga',  'Camerounaise', 'local'),
            ('tou8@demo.cm',     'Yuki',     'Tanaka',  'Japonaise',    'etranger'),
        ]
        for email, prenom, nom, nat, typ in data:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': prenom, 'last_name': nom,
                    'type_user': 'touriste', 'is_active': True,
                },
            )
            if created:
                user.set_password('Demo1234!')
                user.save()
            t, _ = Touriste.objects.get_or_create(
                user=user,
                defaults={
                    'nationalite': nat, 'type': typ,
                    'langue_pref': 'fr' if typ == 'local' else random.choice(['fr', 'en']),
                    'points_fidelite': random.randint(0, 250),
                },
            )
            touristes.append(t)
        self.stdout.write(self.style.SUCCESS(f'{len(touristes)} OK'))
        return touristes

    def _seed_sites(self, Site, Localisation, regions, categories, tags, gestionnaires, max_sites=30):
        self.stdout.write(f'-Sites touristiques (jusqu\'à {max_sites})…', ending=' ')
        sites = []
        for i, (nom, ville, region_code, lat, lng, cat_lib, tarif, desc) in enumerate(SITES_REELS[:max_sites]):
            slug = slugify(nom)
            if Site.objects.filter(slug=slug).exists():
                sites.append(Site.objects.get(slug=slug))
                continue

            loc = Localisation.objects.create(
                region=regions[region_code],
                ville=ville,
                quartier='',
                adresse=f"{ville}, {regions[region_code].nom}, Cameroun",
                latitude=Decimal(str(lat)),
                longitude=Decimal(str(lng)),
                point_repere=f"Accès depuis {regions[region_code].chef_lieu}",
            )

            site = Site.objects.create(
                nom=nom,
                slug=slug,
                description=desc + " " * 3 + ("Conditions de visite normales en saison sèche. "
                                              "Prévoir bonnes chaussures, chapeau et eau. "
                                              "Hébergement et restauration disponibles à proximité.") * 2,
                description_courte=desc[:240],
                categorie=categories[cat_lib],
                localisation=loc,
                gestionnaire=random.choice(gestionnaires),
                type=random.choice(['public', 'prive', 'mixte']),
                tarif_adulte=Decimal(tarif),
                tarif_enfant=Decimal(int(tarif * 0.5)),
                capacite_max=random.choice([50, 100, 200, 500]),
                duree_visite_moyenne=random.choice([60, 90, 120, 180, 240]),
                accessibilite_pmr=random.random() > 0.4,
                est_publie=True,
                note_moyenne=round(random.uniform(3.8, 4.9), 1),
                nombre_avis=random.randint(5, 80),
                nombre_vues=random.randint(50, 2000),
                horaires_ouverture={
                    'lundi':    '08:00-17:00',
                    'mardi':    '08:00-17:00',
                    'mercredi': '08:00-17:00',
                    'jeudi':    '08:00-17:00',
                    'vendredi': '08:00-17:00',
                    'samedi':   '09:00-18:00',
                    'dimanche': '10:00-16:00' if random.random() > 0.3 else 'ferme',
                },
            )

            # Ajouter 2-4 tags aléatoires
            site.tags.set(random.sample(tags, k=random.randint(2, 4)))

            sites.append(site)

        self.stdout.write(self.style.SUCCESS(f'{len(sites)} OK'))
        return sites

    def _seed_hebergements(self, Hebergement, sites):
        self.stdout.write('-Hébergements…', ending=' ')
        types = ['hotel', 'lodge', 'gite', 'auberge', 'camping']
        services_pool = ['wifi', 'piscine', 'restaurant', 'climatisation', 'parking',
                         'petit-dejeuner', 'spa', 'salle de sport', 'navette aeroport']
        nb = 0
        # Hébergements pour 1/3 des sites
        for site in random.sample(sites, k=len(sites) // 2):
            for j in range(random.randint(1, 2)):
                Hebergement.objects.create(
                    site=site,
                    nom=f"{random.choice(['Hôtel', 'Lodge', 'Auberge', 'Résidence'])} {random.choice(['Le Palmier', 'La Lagune', 'Mont Cameroun', 'Sawa', 'Bamenda', 'Faro', 'du Lac'])}",
                    description="Hébergement confortable à proximité du site, idéal pour prolonger votre visite.",
                    type=random.choice(types),
                    nb_chambres=random.randint(5, 50),
                    prix_nuit=Decimal(random.choice([15000, 25000, 35000, 50000, 75000, 100000])),
                    etoiles=random.randint(2, 5),
                    services=random.sample(services_pool, k=random.randint(3, 6)),
                    est_disponible=True,
                )
                nb += 1
        self.stdout.write(self.style.SUCCESS(f'{nb} OK'))

    def _seed_disponibilites(self, Disponibilite, sites):
        self.stdout.write('-Disponibilités (60 jours sur chaque site)…', ending=' ')
        nb = 0
        today = date.today()
        for site in sites:
            for delta in range(60):
                d = today + timedelta(days=delta)
                est_ferme = (
                    site.horaires_ouverture.get(
                        ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche'][d.weekday()]
                    ) == 'ferme'
                )
                Disponibilite.objects.get_or_create(
                    site=site, date=d,
                    defaults={
                        'est_ferme': est_ferme,
                        'places_restantes': 0 if est_ferme else random.randint(20, site.capacite_max),
                        'tarif_special': None if random.random() > 0.15
                                         else Decimal(int(float(site.tarif_adulte) * random.choice([0.8, 1.2]))),
                    },
                )
                nb += 1
        self.stdout.write(self.style.SUCCESS(f'{nb} dispos'))

    def _seed_moyens_paiement(self, MoyenPaiement):
        self.stdout.write('-Moyens de paiement…', ending=' ')
        data = [
            ('MTN Mobile Money',  'mtn_momo',      'mobile_money', 'mtn_momo',      0, 0,    True),
            ('Orange Money',      'orange_money',  'mobile_money', 'orange_money',  0, 0,    True),
            ('Carte bancaire',    'carte_stripe',  'carte',        'stripe',        2.9, 100, True),
            ('Espèces (sur place)','cash',         'cash',         'manuel',        0, 0,    True),
        ]
        moyens = []
        for libelle, code, type_m, provider, frais_pct, frais_fixe, actif in data:
            m, _ = MoyenPaiement.objects.get_or_create(
                code=code,
                defaults={
                    'libelle': libelle,
                    'type': type_m,
                    'provider': provider,
                    'frais_pourcentage': Decimal(frais_pct),
                    'frais_fixe': Decimal(frais_fixe),
                    'est_actif': actif,
                    'montant_min': Decimal(500),
                    'montant_max': Decimal(5000000),
                    'devises_supportees': ['XAF'],
                },
            )
            moyens.append(m)
        self.stdout.write(self.style.SUCCESS(f'{len(moyens)} OK'))
        return moyens

    def _seed_reservations(self, Reservation, touristes, sites, light=False):
        self.stdout.write('-Réservations (échantillon)…', ending=' ')
        reservations = []
        nb_total = 6 if light else 20
        today = date.today()
        statuts = ['en_attente', 'confirmee', 'confirmee', 'confirmee', 'terminee', 'terminee', 'annulee']

        for i in range(nb_total):
            touriste = random.choice(touristes)
            site = random.choice(sites)
            statut = random.choice(statuts)
            # Date passée pour terminee, future pour confirmee/en_attente
            if statut == 'terminee':
                d = today - timedelta(days=random.randint(5, 90))
            elif statut == 'annulee':
                d = today + timedelta(days=random.randint(-10, 30))
            else:
                d = today + timedelta(days=random.randint(1, 45))

            nb_adultes = random.randint(1, 4)
            nb_enfants = random.randint(0, 3)
            montant = (float(site.tarif_adulte) * nb_adultes +
                       float(site.tarif_enfant) * nb_enfants)

            numero = f"RES-{today.year}-{(i + 1):05d}"
            r = Reservation.objects.create(
                numero=numero,
                touriste=touriste, site=site,
                date_visite=d,
                heure_visite=time(10, 0),
                nb_adultes=nb_adultes,
                nb_enfants=nb_enfants,
                montant_total=Decimal(int(montant)),
                statut=statut,
                date_confirmation=timezone.now() if statut in ('confirmee', 'terminee') else None,
                date_annulation=timezone.now() if statut == 'annulee' else None,
                motif_annulation="Changement de programme" if statut == 'annulee' else '',
                notes_touriste='' if random.random() > 0.4 else "Pas d'allergies particulières.",
            )
            reservations.append(r)
        self.stdout.write(self.style.SUCCESS(f'{len(reservations)} OK'))
        return reservations

    def _seed_paiements(self, Paiement, reservations, moyens):
        self.stdout.write('-Paiements…', ending=' ')
        nb = 0
        for r in reservations:
            if r.statut == 'en_attente':
                continue  # pas encore payé
            moyen = random.choice(moyens)
            statut = 'reussi' if r.statut in ('confirmee', 'terminee') else 'echoue'
            Paiement.objects.create(
                reservation=r,
                moyen=moyen,
                montant=r.montant_total,
                devise='XAF',
                type_transaction='paiement',
                statut=statut,
                reference_interne=f"PAY-{uuid.uuid4().hex[:10].upper()}",
                reference_externe=f"EXT-{uuid.uuid4().hex[:14].upper()}" if statut == 'reussi' else '',
                date_paiement=timezone.now() if statut == 'reussi' else None,
                numero_telephone=f"237{random.choice(['67','68','69'])}{random.randint(1000000,9999999)}" if moyen.type == 'mobile_money' else '',
            )
            nb += 1
        self.stdout.write(self.style.SUCCESS(f'{nb} OK'))

    def _seed_avis(self, Avis, reservations):
        self.stdout.write('-Avis (sur réservations terminées)…', ending=' ')
        nb = 0
        titres_pool = [
            "Une expérience inoubliable",
            "À refaire absolument",
            "Très bon accueil",
            "Site magnifique mais peu d'infos",
            "Bon rapport qualité/prix",
            "Bel endroit, bien organisé",
            "Visite agréable en famille",
        ]
        commentaires_pool = [
            "Le site est vraiment magnifique, nous avons passé une journée mémorable. "
            "L'accueil était chaleureux et les explications très instructives. À recommander !",
            "Visite très enrichissante, parfait pour découvrir la culture locale. "
            "Quelques améliorations possibles sur la signalétique mais l'ensemble est très bien.",
            "Cadre exceptionnel, paysages à couper le souffle. "
            "Bien préparer la journée (eau, casquette, bonnes chaussures).",
            "Site bien entretenu, équipe accueillante. Les enfants ont adoré. "
            "On reviendra avec plaisir lors de notre prochain séjour.",
            "Très belle découverte. Le rapport qualité-prix est excellent. "
            "On se sent dépaysé en quelques heures seulement.",
        ]
        for r in reservations:
            if r.statut != 'terminee':
                continue
            if random.random() > 0.7:  # 70% des resa terminées ont un avis
                continue
            if hasattr(r, 'avis'):
                continue
            note = random.randint(3, 5)
            avis = Avis.objects.create(
                touriste=r.touriste,
                site=r.site,
                reservation=r,
                note=note,
                titre=random.choice(titres_pool),
                commentaire=random.choice(commentaires_pool),
                statut_moderation='approuve',
                est_visible=True,
            )
            nb += 1
        self.stdout.write(self.style.SUCCESS(f'{nb} avis approuvés'))

    def _seed_favoris(self, Favori, touristes, sites):
        self.stdout.write('-Favoris…', ending=' ')
        nb = 0
        for t in touristes:
            for site in random.sample(sites, k=random.randint(1, min(5, len(sites)))):
                _, created = Favori.objects.get_or_create(touriste=t, site=site)
                if created:
                    nb += 1
        self.stdout.write(self.style.SUCCESS(f'{nb} OK'))
