# Ajouts : équipements, propriétaires multiples, cohérence, notifications WhatsApp / email

Ce document décrit ce qui a été ajouté **sur votre version** du projet (celle qui avait déjà un modèle `Equipement`,
`signals.py`, la preuve de paiement et les types « chambre / piscine / Hotel »). Rien de votre travail n'a été retiré :
tout a été fusionné.

## 1. Mise en route
```bash
pip install -r requirements-dev.txt
python manage.py migrate        # 0012 (modèles) et 0013 (catalogue de 36 équipements), après vos 0008 à 0011
python -m pytest                # 105 tests
cd frontend && npm install && npm run build
```
Ensuite, dans l'application : menu **Notifications** → email + numéro WhatsApp → « Envoyer un message de test ».

## 2. Ce qui a été fait avec votre travail existant
- **`Equipement`** : votre modèle (`nom`, `icone`) est conservé ; ajout d'une `categorie`, d'un nom **unique** (les doublons éventuels sont fusionnés par la migration 0012) et d'un catalogue de départ. Votre champ `Bien.equipements` est gardé tel quel.
- **`signals.py`** : le signal qui envoyait un email à chaque réservation est **remplacé** par le circuit de notification (sinon le gestionnaire recevait deux emails). L'adresse du compte SMTP reste utilisée **en secours** si le compte du gestionnaire n'a pas d'email (réglage `NOTIFICATIONS_EMAIL_DEFAUT`). Le fichier `signals.py` n'est plus qu'une note : vous pouvez le supprimer.
- **Preuve de paiement** : conservée. Elle n'est plus modifiable par l'API (aucun écran ne permet de l'envoyer) ; la colonne « Voir la preuve » de l'admin, qui ne s'affichait jamais (liste écrasée par la suivante), fonctionne.
- **Types de bien** `chambre`, `piscine`, `Hotel` : ajoutés aussi dans l'application React.
- **`/gestion/loyers/`** : le gabarit `etat_loyers.html` manquait (erreur 500) ; il est créé, et la vue respecte maintenant le périmètre de données.
- **`biens_list.html`** : l'image de fond pointait vers un fichier inexistant ; corrigé.
- Deux méthodes `_str_` (un seul tiret bas) jamais appelées, dont une qui référençait un attribut inexistant, ont été retirées de `models.py`. La faute `defaul_app_config` de `immogest/__init__.py` aussi.
- Deux tests échouaient déjà avant les ajouts (email en double ; liste des biens passée de 5 à 13 requêtes à cause des équipements non préchargés). Ils passent.

## 3. Équipements
Catalogue par catégorie (confort, eau et énergie, cuisine, connectivité, sécurité, extérieur), extensible. Cases à cocher sur chaque bien (loué ou libre), fiche du bien, liste, ancienne interface Django, site public, API publique et filtre `?equipements=3&equipements=7`. Nouveaux champs du bien : chambres, salles de bain, meublé, capacité.

## 4. Propriétaires multiples
Modèle `Proprietaire` (distinct du compte de connexion) et quotes-parts `BienProprietaire` : **la somme doit valoir 100 %**. Page **Propriétaires**, panneau sur la fiche du bien, relevé de reversement mensuel (loyers − commission − dépenses). Chaque propriétaire choisit s'il reçoit ses relevés par email et/ou WhatsApp.

## 5. Notifications
**Au gestionnaire** (cloche + email + WhatsApp, selon ses préférences par événement) : nouvelle réservation, message d'un visiteur (site Django **et** API), signalement locataire, paiement reçu, contrat résilié, réservation expirée, récapitulatif quotidien (retards, échéances, documents, anomalies).

**Aux locataires** (WhatsApp **uniquement avec leur accord**, case « WhatsApp » sur leur fiche ; email via leur compte) : reçu de paiement, rappels J-3 / J-1, relances J+1, J+7 puis chaque semaine.

**Aux propriétaires** (selon leurs cases email / WhatsApp) : leur part de chaque loyer encaissé, relevé mensuel (le 1er du mois, ou `python manage.py envoyer_releves`, ou bouton « Envoyer au propriétaire »).

Tout envoi est tracé (page Notifications), les échecs sont rejoués 3 fois, les messages partent après validation de la transaction.

### Brancher WhatsApp (fichier `.env`)
```
SITE_URL=https://votre-domaine.com
WHATSAPP_PROVIDER=cloud            # cloud | twilio | console (journal seulement) | vide = désactivé
WHATSAPP_TOKEN=...   WHATSAPP_PHONE_NUMBER_ID=...   WHATSAPP_TEMPLATE_NAME=...
# ou Twilio : TWILIO_ACCOUNT_SID=...  TWILIO_AUTH_TOKEN=...  TWILIO_WHATSAPP_FROM=+14155238886
```
**Règle de Meta** : pour écrire à quelqu'un qui ne vous a pas écrit depuis 24 h, WhatsApp impose un *modèle* approuvé : créez un modèle « Utilitaire » dont le corps est `{{1}}`, attendez son approbation, puis mettez son nom dans `WHATSAPP_TEMPLATE_NAME`. Avec Twilio en bac à sable, chaque destinataire doit d'abord envoyer le code d'activation.

**Planification** (une fois par jour, 8 h) : `python manage.py taches_quotidiennes`

## 6. Cohérence
Un bien ne peut plus être « loué » sans contrat actif (ni changer de statut sous un contrat actif) ; suppression refusée avec message d'un bien / locataire sous contrat actif ou d'un propriétaire qui possède des biens ; contrat refusé sur un bien en travaux ; paiement ≤ dû et dans la durée du contrat ; dates d'intervention cohérentes ; réservation saisie par le gestionnaire soumise aux mêmes règles que le site public (disponibilité, capacité) ; téléphones normalisés en `+221…` ; lien des notifications corrigé (menait à une page 404). Carte **Cohérence** sur le tableau de bord (`GET /api/v1/coherence/`).

## 7. Points d'attention
- **Fichiers `media/`** : servis publiquement par défaut (`SERVE_MEDIA`). Les preuves de paiement y sont accessibles à qui connaît l'URL ; à protéger (stockage privé ou S3) avant d'en collecter via l'application.
- Le type de bien `Hotel` garde sa majuscule (valeur déjà en base chez vous) alors que les autres sont en minuscules.
- WhatsApp Business impose le consentement : c'est pourquoi les cases sont décochées par défaut pour les locataires et, pour WhatsApp, les propriétaires.
