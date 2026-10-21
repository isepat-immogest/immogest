#!/bin/bash
# Script de démarrage ImmoGest
# Usage: bash setup.sh

echo "=== ImmoGest — Installation ==="

# Vérifier Python
python3 --version || { echo "Python 3 requis"; exit 1; }

# Créer un environnement virtuel
python3 -m venv venv
source venv/bin/activate

# Installer les dépendances
pip install -r requirements-dev.txt

# Migrations
python manage.py makemigrations gestion
python manage.py migrate

# Créer un superutilisateur
echo ""
echo "=== Créer un compte administrateur ==="
python manage.py createsuperuser

# Charger des données de démonstration (optionnel)
# python manage.py loaddata demo.json

echo ""
echo "=== Démarrage du serveur ==="
echo "Accès : http://127.0.0.1:8000"
python manage.py runserver
