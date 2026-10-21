# ImmoGest — Passation pour Ibrahima

Ce fichier te permet de reprendre le projet et de l'améliorer. Branche de travail : `feature/api-react-frontend` (à fusionner dans `main` par Pull Request).

## 1. Où en est le projet

| Brique | État |
|---|---|
| API REST `/api/v1` (DRF, JWT + session/CSRF, Swagger `/api/docs/`) | ✅ fait, 31 tests pytest |
| Logique métier (`gestion/services.py`) | ✅ loyers, contrats, réservations, accès locataire |
| Interface React `/app/` (Vite, TS, Tailwind, shadcn/ui, TanStack Query) | ✅ fait, 11 tests Vitest |
| Site public Django (`/`) | ✅ existant, corrigé (jeton de confirmation, disponibilité) |
| Ancienne interface `/gestion/` | ⚠️ conservée, à supprimer à terme |
| Dépenses + rentabilité, calendrier, documents, score locataire, rappels J-3/J-1 | ✅ fait (43 tests pytest) |
| Fluidité : préchargement, gzip, index SQL, anti N+1, service worker hors-ligne | ✅ fait |
| Paiement mobile money par API (Wave / Orange Money) | ❌ à faire |
| Temps réel (WebSocket) | ❌ notifications par polling 30 s |

## 2. Lancer le projet

```bash
python -m venv .venv && .venv\Scripts\activate          # Linux/Mac : source .venv/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env                                   # Linux/Mac : cp
python manage.py migrate
python manage.py seed_demo                               # compte demo / Demo-ImmoGest-2026
python manage.py runserver                               # API + site public : :8000

cd frontend && npm install && npm run dev                # React : http://localhost:5173/app/
```

Sous Windows, si une commande affiche une erreur d'encodage (emoji), lancer avec `set PYTHONUTF8=1`.
Production / test réel : `cd frontend && npm run build`, puis `http://127.0.0.1:8000/app/`.

Vérifications avant chaque commit :

```bash
pytest                                  # backend
cd frontend && npm run lint && npm test && npm run build
```

## 3. Architecture (où mettre quoi)

```
gestion/models.py        Modèles + règles simples (clean, statut calculé du Paiement, sync du statut du Bien)
gestion/services.py      TOUTE la logique métier (loyers, versements, réservations, invitations…)
api/serializers.py       Validation et format JSON
api/views.py             Vues de gestion (ViewSets scopés par propriétaire)
api/public_views.py      API publique (sans login, limitée en débit, honeypot anti-spam)
api/espace_views.py      API de l'espace locataire
api/auth_views.py        Connexion, mot de passe, CSRF
api/errors.py            Format d'erreur unique {code, message, details}
gestion/scope.py         Périmètre des données visibles (mode partagé / isolé)
frontend/src/lib/        api.ts (client HTTP), queries.ts (hooks TanStack), types.ts, labels.ts
frontend/src/components/ FormDialog (formulaires pilotés par config), ListShell, ui/ (shadcn)
frontend/src/pages/      Une page par écran (+ espace/ pour le locataire)
tests/                   pytest : services + API
```

Règles du projet :
- **Aucune logique métier dans les vues** : on l'écrit dans `services.py` et on la teste.
- **Toute requête de gestion passe par `ScopedViewSet`** (jamais de `Model.objects.all()` exposé).
- **Montants en FCFA sans décimales** à l'affichage (`formatFCFA`).
- **Ajouter une ressource** : modèle → migration → serializer → ViewSet + `router.register` → type dans `types.ts` → page React (copier `Biens.tsx`).
- Tests d'abord pour tout bug corrigé.

## 4. Travail à faire — par priorité

### P0 — à faire en premier
1. **Pousser et fusionner** la branche (voir §6), activer la CI GitHub (`.github/workflows/ci.yml`).
2. **Paiement mobile money réel** : intégrer un agrégateur (PayDunya, CinetPay ou PayTech). Créer `integrations/` avec `initier_paiement()` et un endpoint `POST /api/v1/webhooks/paiement/<fournisseur>/` qui **vérifie la signature HMAC** puis appelle `services.enregistrer_versement` / passe la réservation en « payée ». Le numéro de paiement est encore codé en dur dans `site_public/templates/site_public/reservation_confirmation.html` (+221 77 123 45 67) : à mettre dans les réglages.
3. **Supprimer `/gestion/`** une fois l'app React validée (le template legacy affiche encore le mot de passe temporaire à l'écran dans `locataire_creer_acces`) ; rediriger `/gestion/` vers `/app/`.
4. **Changer `SECRET_KEY`**, `DEBUG=False`, `ALLOWED_HOSTS` en production (le démarrage refuse sinon).

### P1 — fort impact
- **Rôles et permissions** : admin / gestionnaire / comptable / lecture seule (modèle `Agence` + `Membre(role)`), permissions DRF par rôle.
- **Bail PDF** généré automatiquement (s'inspirer de `gestion/pdf_utils.py`) ; les documents (upload) existent déjà (`DocumentsPanel`).
- **Galerie multi-photos** par bien (`PhotoBien`) au lieu d'une seule `photo`.
- **Relances de retard** (J+1, J+7) et SMS / WhatsApp (Twilio ou API WhatsApp Cloud) : les rappels J-3/J-1 par notification + email existent dans `services.envoyer_rappels_echeance`.
- **Documents en production** : le disque n'est pas persistant sur la plupart des hébergeurs, activer S3 (`USE_S3=True`) avant d'accepter des uploads réels.
- **Dépôt de garantie** : encaissement, retenues, restitution.
- **Pagination côté Kanban** et filtre par bien dans `Interventions.tsx` (charge 200 éléments).

### P2 — confort / « wow »
- Temps réel : Django Channels ou SSE à la place du polling (`NotificationsBell.tsx`).
- Propriétaires multiples et reversements ; génération d'annonce par IA.
- Mode hors-ligne des **données** (le service worker ne met en cache que la coquille) ; icônes PNG pour la PWA.
- Vue calendrier en semaine / agenda ; glisser-déposer des événements.
- Import Excel de biens/locataires (`openpyxl` est déjà installé).
- Suppression douce (`deleted_at`) à la place de `CASCADE` : supprimer un locataire efface aujourd'hui tous ses contrats et paiements.
- Journal d'audit (`django-simple-history`).
- Internationalisation (FR/EN/Wolof).

### P3 — dette technique connue
- `views.py` historique (690 lignes) à supprimer avec `/gestion/`.
- Pas de tests E2E : ajouter Playwright (connexion → créer bien → contrat → loyer → versement).
- Les formulaires React ne valident que côté serveur (ajouter Zod si besoin d'une validation immédiate).
- Le client de test Django 5.1 est incompatible avec Python 3.14 pour le rendu de gabarits (test de confirmation fait avec `RequestFactory`) : utiliser Python 3.12 pour le dev.
- `ENUM_NAME_OVERRIDES` drf-spectacular à configurer (avertissements de schéma sans gravité).
- Pas de monitoring : brancher Sentry et des sauvegardes PostgreSQL.

## 5. Pièges à connaître
- Un **contrat actif** met le bien en « loué » automatiquement ; ne modifie pas `Bien.statut` à la main pour ça (les statuts « travaux » et « vente » restent manuels).
- `Paiement.statut` est **recalculé à chaque `save()`** : modifier `montant_paye`, jamais le statut.
- Les routes React sont sous `/app/` (`basename`) ; en dev, Vite proxifie `/api` vers Django (même origine, donc cookies + CSRF fonctionnent).
- Après `login`, le jeton CSRF change : `useAuth` le recharge (ne pas appeler `queryClient.clear()` — ça détache la requête `/me`).
- `DONNEES_PARTAGEES=True` (défaut) : tous les comptes de gestion voient les mêmes données.

## 6. Récupérer le code et pousser

Le compte GitHub utilisé jusqu'ici (`TIDIALLO`) n'a **pas** les droits d'écriture sur `isepat-immogest/immogest` : le push a été refusé (403). Il faut :
1. que le propriétaire de l'organisation t'ajoute (et/ou ajoute TIDIALLO) comme collaborateur avec accès **Write** ;
2. puis : `git checkout feature/api-react-frontend && git push -u origin feature/api-react-frontend` ;
3. ouvrir une Pull Request vers `main`, attendre que la CI passe, fusionner.

Si le code t'est transmis par archive : copier le dossier **sans** `.venv/`, `frontend/node_modules/`, `frontend/dist/` et `db.sqlite3`.

## 7. Comptes et données de démonstration
- `python manage.py seed_demo` crée le compte **demo / Demo-ImmoGest-2026**, 4 biens, 2 locataires avec contrats et 6 mois de loyers. À ne jamais utiliser en production.
- `python manage.py taches_quotidiennes --dry-run` : génération des loyers, retards, expiration des réservations, alertes.

## 8. Contexte détaillé
Le fichier `ANALYSE_360_ET_FONCTIONNALITES_MANQUANTES.md` contient l'audit complet de départ (bugs, failles, ~120 fonctionnalités) avec la liste de ce qui reste à implémenter.
