import hashlib
import hmac
import json
import logging
import urllib.request
import urllib.error

from decouple import config

logger = logging.getLogger(__name__)

GRAPH_API_URL = "https://graph.facebook.com/v21.0"


def get_page_access_token():
    return config("FACEBOOK_PAGE_ACCESS_TOKEN", default="")


def get_app_secret():
    return config("FACEBOOK_APP_SECRET", default="")


def get_verify_token():
    return config("FACEBOOK_VERIFY_TOKEN", default="")


def send_message(recipient_id, text):
    """Send a text message to a Facebook user via the Page."""
    token = get_page_access_token()
    if not token:
        logger.error("FACEBOOK_PAGE_ACCESS_TOKEN not configured")
        return False

    url = f"{GRAPH_API_URL}/me/messages"
    payload = json.dumps({
        "recipient": {"id": recipient_id},
        "message": {"text": text},
        "messaging_type": "RESPONSE",
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError:
        logger.exception("Failed to send Facebook message to %s", recipient_id)
        return False


def get_user_profile(user_id):
    """Fetch a Facebook user's profile name."""
    token = get_page_access_token()
    if not token:
        return {}

    url = f"{GRAPH_API_URL}/{user_id}?fields=name&access_token={token}"

    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError:
        logger.exception("Failed to fetch FB user profile %s", user_id)
        return {}


def verify_signature(payload_body, signature_header):
    """Verify that the webhook payload came from Facebook."""
    app_secret = get_app_secret()
    if not app_secret or not signature_header:
        return False

    if not signature_header.startswith("sha256="):
        return False

    expected = hmac.new(
        app_secret.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature_header[7:])
