"""Envoi de messages WhatsApp (alertes envoyées au gestionnaire).

Fournisseur choisi par le réglage WHATSAPP_PROVIDER (fichier .env) :

- ``cloud``   : WhatsApp Business Cloud API de Meta (graph.facebook.com)
- ``twilio``  : WhatsApp via Twilio
- ``console`` : n'envoie rien, écrit le message dans les journaux (développement)
- (vide)      : WhatsApp désactivé ; les alertes partent seulement par email et dans l'application

Aucune dépendance externe : les requêtes passent par ``urllib`` avec un délai maximal court, pour qu'un
fournisseur lent ne bloque jamais la page d'un client.

Attention (règle de Meta) : un message envoyé à quelqu'un qui ne vous a pas écrit dans les dernières 24 h doit
utiliser un *modèle* (template) approuvé. Créez un modèle « utilitaire » à une seule variable {{1}} dans le
gestionnaire WhatsApp et renseignez WHATSAPP_TEMPLATE_NAME : le texte de l'alerte est alors injecté dans {{1}}.
"""
import base64
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings  # type: ignore

logger = logging.getLogger(__name__)

TIMEOUT = 8  # secondes


class WhatsAppError(Exception):
    """Échec d'envoi WhatsApp (message lisible, enregistré dans le journal des envois)."""


def numero_international(numero):
    """« +221 77 123 45 67 » → « 221771234567 » (format attendu par les API, sans « + »)."""
    from .utils import normaliser_telephone
    return re.sub(r'\D', '', normaliser_telephone(numero))


def fournisseur():
    return (getattr(settings, 'WHATSAPP_PROVIDER', '') or '').strip().lower()


def whatsapp_configure():
    return fournisseur() in ('cloud', 'twilio', 'console')


def _post(url, corps, entetes, timeout=TIMEOUT):
    """POST HTTP minimal. Isolé dans une fonction pour être simulé dans les tests."""
    req = urllib.request.Request(url, data=corps, headers=entetes, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as rep:  # noqa: S310 (URLs fixes des fournisseurs)
            return rep.status, rep.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode('utf-8', 'replace')
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise WhatsAppError(f'Fournisseur injoignable : {exc}') from exc


def _nettoyer_variable_modele(texte):
    """Meta refuse les retours à la ligne et les longues suites d'espaces dans une variable de modèle."""
    texte = re.sub(r'\s*\n\s*', ' | ', texte.strip())
    return re.sub(r' {4,}', '   ', texte)[:1000]


def _envoyer_cloud(numero, texte):
    token = getattr(settings, 'WHATSAPP_TOKEN', '')
    phone_id = getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', '')
    if not token or not phone_id:
        raise WhatsAppError('WHATSAPP_TOKEN ou WHATSAPP_PHONE_NUMBER_ID manquant.')
    version = getattr(settings, 'WHATSAPP_API_VERSION', 'v20.0')
    modele = getattr(settings, 'WHATSAPP_TEMPLATE_NAME', '')
    if modele:
        corps = {'messaging_product': 'whatsapp', 'to': numero, 'type': 'template', 'template': {
            'name': modele, 'language': {'code': getattr(settings, 'WHATSAPP_TEMPLATE_LANG', 'fr')},
            'components': [{'type': 'body', 'parameters': [
                {'type': 'text', 'text': _nettoyer_variable_modele(texte)}]}]}}
    else:
        corps = {'messaging_product': 'whatsapp', 'to': numero, 'type': 'text',
                 'text': {'body': texte, 'preview_url': False}}
    statut, reponse = _post(
        f'https://graph.facebook.com/{version}/{phone_id}/messages', json.dumps(corps).encode(),
        {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
    if statut >= 300:
        raise WhatsAppError(f'Meta a refusé le message (HTTP {statut}) : {reponse[:300]}')


def _envoyer_twilio(numero, texte):
    sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
    jeton = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
    expediteur = getattr(settings, 'TWILIO_WHATSAPP_FROM', '')
    if not (sid and jeton and expediteur):
        raise WhatsAppError('TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN ou TWILIO_WHATSAPP_FROM manquant.')
    donnees = urllib.parse.urlencode({
        'From': f'whatsapp:{expediteur if expediteur.startswith("+") else "+" + expediteur}',
        'To': f'whatsapp:+{numero}', 'Body': texte}).encode()
    auth = base64.b64encode(f'{sid}:{jeton}'.encode()).decode()
    statut, reponse = _post(
        f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json', donnees,
        {'Authorization': f'Basic {auth}', 'Content-Type': 'application/x-www-form-urlencoded'})
    if statut >= 300:
        raise WhatsAppError(f'Twilio a refusé le message (HTTP {statut}) : {reponse[:300]}')


def envoyer_whatsapp(numero, texte):
    """Envoie `texte` au `numero`. Lève WhatsAppError en cas de problème (jamais silencieux)."""
    mode = fournisseur()
    if not mode:
        raise WhatsAppError('WhatsApp non configuré (WHATSAPP_PROVIDER vide).')
    destinataire = numero_international(numero)
    if len(destinataire) < 8:
        raise WhatsAppError(f'Numéro WhatsApp invalide : « {numero} ».')
    if mode == 'console':
        logger.info('[WhatsApp console] → +%s : %s', destinataire, texte)
    elif mode == 'cloud':
        _envoyer_cloud(destinataire, texte)
    elif mode == 'twilio':
        _envoyer_twilio(destinataire, texte)
    else:
        raise WhatsAppError(f'Fournisseur WhatsApp inconnu : « {mode} » (cloud, twilio ou console).')
