"""Outgoing alert channels. Each one does nothing until its settings are filled in (see .env.example)."""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail import send_mail

log = logging.getLogger(__name__)
TIMEOUT = 15


def _post_json(url, payload, headers):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:   # noqa: S310 (fixed https URLs below)
        return resp.status


def whatsapp_enabled():
    return bool(settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_ID)


def send_whatsapp(mobile: str, text: str) -> str:
    """Meta WhatsApp Cloud API, using an approved template with one body parameter.
    Business-initiated messages must use a template; free text only works inside a 24-hour customer window."""
    if not whatsapp_enabled():
        return "off"
    url = f"https://graph.facebook.com/v21.0/{settings.WHATSAPP_PHONE_ID}/messages"
    payload = {
        "messaging_product": "whatsapp", "to": f"91{mobile}", "type": "template",
        "template": {"name": settings.WHATSAPP_TEMPLATE, "language": {"code": "en"},
                     "components": [{"type": "body", "parameters": [{"type": "text", "text": text[:1000]}]}]},
    }
    try:
        _post_json(url, payload, {"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"})
        return "ok"
    except urllib.error.HTTPError as e:
        log.warning("WhatsApp send failed: %s %s", e.code, e.read()[:300])
        return f"error: {e.code}"
    except Exception as e:  # network etc.
        log.warning("WhatsApp send failed: %s", e)
        return "error"


def sms_enabled():
    return settings.SMS_PROVIDER == "msg91" and bool(settings.MSG91_AUTH_KEY and settings.MSG91_FLOW_ID)


def send_sms(mobile: str, text: str) -> str:
    """MSG91 Flow API (DLT-registered template with a ##message## variable)."""
    if not sms_enabled():
        return "off"
    payload = {"template_id": settings.MSG91_FLOW_ID, "short_url": "0",
               "recipients": [{"mobiles": f"91{mobile}", "message": text[:300]}]}
    try:
        _post_json("https://control.msg91.com/api/v5/flow/", payload, {"authkey": settings.MSG91_AUTH_KEY})
        return "ok"
    except Exception as e:
        log.warning("SMS send failed: %s", e)
        return "error"


def send_email(address: str, subject: str, text: str) -> str:
    if not address:
        return "off"
    try:
        send_mail(subject, text, settings.DEFAULT_FROM_EMAIL, [address], fail_silently=False)
        return "ok"
    except Exception as e:
        log.warning("Email send failed: %s", e)
        return "error"
