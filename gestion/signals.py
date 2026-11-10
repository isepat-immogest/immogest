"""Remplacé par `gestion/notifications.py`.

L'ancien signal envoyait un email à chaque réservation créée, à l'adresse du compte SMTP. Les réservations passent
désormais par `services.creer_reservation`, qui prévient le gestionnaire (cloche + email + WhatsApp, selon ses
préférences) ; l'adresse du compte SMTP reste utilisée en secours (réglage NOTIFICATIONS_EMAIL_DEFAUT).
Garder les deux envoyait deux emails par réservation. Ce fichier peut être supprimé.
"""
