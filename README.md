# ImmoGest — Plateforme de gestion immobilière (Django + React)

Application de gestion locative pour le Sénégal (FCFA, Wave / Orange Money / Free Money) :
**API REST Django** + **interface React** (Vite, TypeScript, Tailwind CSS, composants shadcn/ui) + site public.

| Couche | Technologies |
|---|---|
| Backend | Django 5.1, Django REST Framework, JWT (simplejwt), django-filter, drf-spectacular |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui (Radix), TanStack Query, React Hook Form, Recharts, cmdk |
| Données | PostgreSQL (prod) / SQLite (dev), PDF reportlab, export Excel openpyxl |
| Qualité | pytest (43 tests, ~8 s), Vitest (11 tests), GitHub Actions, Docker |

## Les trois surfaces

| URL | Contenu |
|---|---|
| `/` | Site public (catalogue, réservation, contact) |
| `/app/` | **Application React** : back-office gestionnaire et espace locataire |
| `/api/v1/` · `/api/docs/` | **API REST** et documentation Swagger/OpenAPI |
| `/gestion/` | Ancienne interface Django (conservée) |

## Démarrage rapide (développement)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows : .venv\Scriptsctivate
pip install -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo            # données de démonstration (compte demo / Demo-ImmoGest-2026)
python manage.py runserver            # API + site public sur :8000

# Dans un second terminal : interface React avec rechargement à chaud
cd frontend && npm install && npm run dev      # http://localhost:5173/app/
```

Port 8000 déjà pris ? Lancer Django sur un autre port et le dire à Vite :
`python manage.py runserver 8010` puis `cd frontend && DJANGO_URL=http://127.0.0.1:8010 npm run dev`
(PowerShell : `$env:DJANGO_URL="http://127.0.0.1:8010"; npm run dev`).

Pour servir l'application React directement par Django (comme en production) :
`cd frontend && npm run build`, puis ouvrir `http://127.0.0.1:8000/app/`.

## Ce que l'application fait automatiquement

- **Loyers** : génération mensuelle (`/paiements/generer-mois/` ou `python manage.py taches_quotidiennes`) ;
  le statut (payé / partiel / en retard) est **calculé** à partir des montants et de l'échéance ; versements partiels.
- **Contrats** : un seul contrat actif par bien ; le bien passe en « loué » / « libre » automatiquement ; résiliation en un clic.
- **Réservations** : contrôle de disponibilité (pas de double réservation), montant calculé, expiration des impayées (48 h),
  conversion en contrat saisonnier, page de suivi protégée par un jeton secret.
- **Notifications** : cloche dans l'application + email à chaque réservation, message ou signalement locataire.
- **Accès locataire** : lien d'activation à usage unique (plus de mot de passe envoyé en clair).
- **Dépenses et rentabilité** : charges par bien (taxes, assurance, travaux…), résultat net et rendement sur 12 mois.
- **Calendrier** : séjours, loyers à payer, fins de bail et interventions sur une seule vue mensuelle.
- **Documents** : pièces jointes par locataire ou bien (PDF/JPG/PNG, 5 Mo), téléchargement authentifié uniquement.
- **Score locataire** : fiabilité 0-100 (ponctualité des paiements + taux d'effort loyer/revenu).
- **Rappels d'échéance** : notification et email aux locataires à J-3 et J-1.

## Fluidité

- Pages chargées à la demande **et préchargées** pendant les temps morts ; données préchargées au survol du menu.
- Cache TanStack Query (affichage instantané des pages déjà vues), mises à jour optimistes (statuts, Kanban).
- API sans N+1 (requêtes pré-chargées, vérifié par test), index SQL sur les filtres fréquents, **compression gzip** (-73 % sur les scripts).
- Service worker : coquille de l'application disponible hors-ligne, scripts en cache ; les réponses de l'API ne sont jamais mises en cache.

## API

Documentation interactive : `/api/docs/` (schéma : `/api/schema/`). Authentification par session + CSRF (application React)
ou JWT (`POST /api/v1/auth/token/`) pour les clients mobiles. Pagination, recherche (`?search=`), filtres (`?statut=`),
tri (`?ordering=`), erreurs au format `{code, message, details}`, limitation de débit sur la connexion et les formulaires publics.

## Tests et qualité

```bash
pytest                                  # backend
cd frontend && npm test && npm run lint # frontend
```

## Tâches planifiées

```
0 8 * * *  cd /chemin/immogest && .venv/bin/python manage.py taches_quotidiennes
```

---

## Documentation historique (version Django classique)

## Fonctionnalités

- **Biens** : gestion complète (appartements, maisons, studios, commerces, garages)
- **Locataires** : fiche complète avec historique
- **Contrats** : bail vide, meublé, commercial, saisonnier
- **Paiements** : suivi mensuel, détection des retards, soldes
- **Interventions** : tickets de maintenance avec priorités
- **Tableau de bord** : indicateurs clés, revenus, taux d'occupation, **graphique d'évolution des revenus sur 6 mois**
- **Quittances de loyer PDF** : génération et téléchargement, côté propriétaire et côté locataire
- **Export de rapports financiers** : CSV (compatible Excel) et PDF, avec filtre par période (`/gestion/rapport-financier/?debut=...&fin=...&format=csv|pdf`)
- **Alertes et relances automatiques** : commande `python manage.py envoyer_alertes` (loyers en retard, contrats arrivant à échéance) — à planifier via cron en production
- **Administration** : interface Django Admin incluse
- **Espace locataire** : chaque locataire peut avoir son propre accès pour consulter
  son contrat, l'historique de ses paiements, et signaler un problème
- **Mot de passe oublié** : réinitialisation par email, pour les propriétaires et les locataires

## Installation rapide (développement local)

```bash
# 1. Décompresser et entrer dans le dossier
cd immogest

# 2. Créer et activer l'environnement virtuel
python3 -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Copier le fichier d'environnement et l'adapter si besoin
cp .env.example .env

# 5. Appliquer les migrations
python manage.py migrate

# 6. Créer un compte admin (= propriétaire)
python manage.py createsuperuser

# 7. Lancer le serveur
python manage.py runserver
```

Accédez à : http://127.0.0.1:8000 (site public) et http://127.0.0.1:8000/gestion/ (interface propriétaire).

## Donner un accès à un locataire

1. Connectez-vous en tant que propriétaire et ouvrez la fiche du locataire concerné.
2. Cliquez sur **« Créer un accès »** : un identifiant et un mot de passe temporaire
   sont générés (affichés une seule fois à l'écran, et envoyés par email si le
   locataire a une adresse enregistrée).
3. Le locataire se connecte sur la même page de connexion (`/gestion/login/`) et est
   automatiquement redirigé vers son espace personnel, où il voit uniquement son
   propre contrat et ses propres paiements.
4. Vous pouvez à tout moment **réinitialiser le mot de passe** ou **révoquer l'accès**
   depuis la fiche du locataire.

## Déploiement en production

Le projet est prêt pour un hébergeur type Render, Railway ou un VPS classique.

1. **Variables d'environnement** : copiez `.env.example`, renseignez une vraie
   `SECRET_KEY` (voir la commande dans le fichier), passez `DEBUG=False`, et
   indiquez vos domaines dans `ALLOWED_HOSTS`.
2. **Base de données** : en production, définissez `DATABASE_URL` (PostgreSQL
   recommandé) ; sans cette variable, l'app utilise SQLite (à éviter en prod
   avec plusieurs utilisateurs simultanés). Pour retrouver votre PostgreSQL
   local, mettez dans `.env` :
   `DATABASE_URL=postgres://postgres:VOTRE_MOT_DE_PASSE@localhost:5432/immogest_db`
   (le mot de passe n'est plus codé en dur dans `settings.py`, c'est plus sûr).
3. **Fichiers statiques** : lancez `python manage.py collectstatic --noinput`
   avant ou pendant le déploiement (déjà pris en charge par whitenoise).
4. **Serveur** : `Procfile` fourni, utilisable tel quel sur Render/Railway/Heroku
   (`gunicorn immogest.wsgi`). Sur un VPS, utilisez `gunicorn` derrière nginx.
5. **Médias (photos)** : par défaut, les fichiers uploadés sont stockés sur le
   disque local — non persistant sur la plupart des hébergeurs. Quand vous aurez
   un compte S3/Cloudinary, activez `USE_S3=True` et complétez les variables
   `AWS_*` dans `.env` (le code est déjà prêt, il ne reste qu'à installer
   `django-storages` et `boto3`, listés en commentaire dans `requirements.txt`).
6. **Emails** : mettez `EMAIL_USE_SMTP=True` et renseignez vos identifiants SMTP
   pour que les emails (accès locataire, réinitialisation de mot de passe) soient
   réellement envoyés (sinon ils s'affichent seulement dans les logs du serveur).
7. **Alertes et relances automatiques** : planifiez `python manage.py envoyer_alertes`
   pour qu'il tourne une fois par jour (loyers en retard, contrats arrivant à échéance).
   Exemple de tâche cron (Linux, à adapter à vos chemins) :
   ```
   0 8 * * * cd /chemin/vers/immogest && /chemin/vers/venv/bin/python manage.py envoyer_alertes
   ```
   Testez d'abord sans envoyer réellement d'email avec `python manage.py envoyer_alertes --dry-run`.

## Génération de PDF (quittances, rapports)

Les quittances de loyer et les rapports financiers sont générés avec `reportlab`
(bibliothèque Python pure, sans dépendance système comme Cairo/Pango). Le code
dédié se trouve dans `gestion/pdf_utils.py`.
- Quittance d'un paiement : bouton « 📄 Quittance » sur la liste des paiements
  (propriétaire) et dans l'espace locataire.
- Rapport financier : `/gestion/rapport-financier/?format=csv` ou `?format=pdf`,
  avec filtre optionnel `?debut=YYYY-MM-DD&fin=YYYY-MM-DD`.


## Données partagées entre les comptes de gestion

Par défaut (`DONNEES_PARTAGEES=True` dans `.env`), **tous les comptes de gestion voient les
mêmes données** : tableau de bord, biens, locataires, contrats, paiements, réservations et
demandes clients. Une réservation faite sur le site public apparaît donc chez tous.
Les comptes locataires ne voient jamais ces données : ils n'ont accès qu'à leur espace.

Pour revenir à l'isolation (chaque compte ne voit que ses propres biens), mettez
`DONNEES_PARTAGEES=False` dans `.env`. Le code qui décide du périmètre est dans `gestion/scope.py`.

Chaque réservation faite sur le site public crée aussi un message dans « Demandes clients »
(référence, dates, nombre de personnes, mode de paiement). Les compteurs de notification du
menu (demandes, réservations) sont affichés sur toutes les pages.

La commande `python manage.py regrouper_biens --vers COMPTE [--dry-run]` reste disponible
pour rattacher tous les biens à un compte précis (utile surtout en mode isolé).

## Structure du projet

```
immogest/
├── frontend/          # Application React (Vite + TypeScript + Tailwind + shadcn/ui)
├── api/               # API REST (serializers, viewsets, auth, public, espace locataire)
├── tests/             # Tests pytest (services + API)
├── immogest/          # Configuration Django
│   ├── settings.py
│   └── urls.py
├── gestion/           # Application principale
│   ├── models.py      # Bien, Locataire, Contrat, Paiement, Intervention, Reservation, Notification
│   ├── services.py    # Logique métier (loyers, contrats, réservations, accès locataire)
│   ├── views.py       # Toutes les vues (dont l'espace locataire)
│   ├── forms.py       # Formulaires
│   ├── urls.py        # Routes
│   ├── admin.py       # Interface admin
│   ├── middleware.py  # Redirection automatique selon le rôle (propriétaire/locataire)
│   └── templates/     # Templates HTML (dont locataire_espace/)
├── Procfile           # Déploiement (gunicorn)
├── .env.example       # Modèle de configuration
├── requirements.txt
└── manage.py
```

## Modèles de données

| Modèle | Description |
|--------|-------------|
| `Bien` | Bien immobilier avec type, statut, adresse, loyer |
| `Locataire` | Coordonnées, profession, revenus, compte de connexion optionnel |
| `Contrat` | Lien bien↔locataire, dates, loyer, type de bail |
| `Paiement` | Suivi mensuel des loyers par contrat |
| `Intervention` | Tickets maintenance avec priorité et coût |
