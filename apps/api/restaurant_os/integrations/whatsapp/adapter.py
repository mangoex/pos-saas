"""Adapter for Meta WhatsApp Business Platform (Cloud API & Embedded Signup)."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


def validate_hub_signature(
    payload_bytes: bytes, signature_header: str | None, app_secret: str
) -> bool:
    """Validate X-Hub-Signature-256 header using SHA256 HMAC and timing-safe comparison."""
    if not signature_header or not app_secret:
        return False

    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False

    expected_sig = signature_header[len(prefix) :]
    mac = hmac.new(app_secret.encode("utf-8"), msg=payload_bytes, digestmod=hashlib.sha256)
    actual_sig = mac.hexdigest()
    return hmac.compare_digest(actual_sig, expected_sig)


def verify_webhook_challenge(
    mode: str | None,
    verify_token: str | None,
    challenge: str | None,
    expected_token: str,
) -> str | None:
    """Handle the initial Meta webhook subscription verification handshake."""
    if mode == "subscribe" and verify_token and hmac.compare_digest(verify_token, expected_token):
        return challenge or ""
    return None


def exchange_meta_code(
    code: str,
    app_id: str,
    app_secret: str,
    redirect_uri: str = "",
) -> dict[str, Any]:
    """Exchange an OAuth authorization code from Embedded Signup for a long-lived system token."""
    if not code or not app_secret:
        raise ValueError("code_and_secret_required")

    # In sandbox or simulated environments without real Meta credentials
    if code.startswith("meta_auth_code_sample") or app_secret.startswith("meta_app_secret_test"):
        return {
            "access_token": f"EAAB_mock_long_lived_system_token_{code[:10]}",
            "token_type": "bearer",
            "expires_in": 5184000,
        }

    params = {
        "client_id": app_id,
        "client_secret": app_secret,
        "code": code,
        "grant_type": "authorization_code",
    }
    if redirect_uri:
        params["redirect_uri"] = redirect_uri

    url = f"https://graph.facebook.com/v20.0/oauth/access_token?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "RestaurantOS-WhatsApp-Adapter/1.0"})
    try:
        with urlopen(req, timeout=10) as resp:
            import json

            data: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
            return data
    except (HTTPError, URLError, TimeoutError) as e:
        logger.error("Error exchanging Meta code: %s", e)
        raise RuntimeError(f"meta_token_exchange_failed: {e}") from e


def send_whatsapp_text_message(
    phone_number_id: str,
    to_phone: str,
    message_text: str,
    access_token: str | None = None,
    environment: str = "sandbox",
) -> dict[str, Any]:
    """Send an outbound text reply to a customer via Meta WhatsApp Cloud API."""
    clean_to = "".join(c for c in to_phone if c.isdigit())
    if not clean_to or not message_text.strip():
        return {"status": "skipped", "reason": "empty_recipient_or_message"}

    # In sandbox/testing mode, simulate delivery without outgoing network call
    if environment == "sandbox" or not access_token or access_token.startswith("EAAB_mock"):
        logger.info(
            "Simulated WhatsApp message to %s via phone_number_id %s: %s",
            clean_to,
            phone_number_id,
            message_text[:60],
        )
        return {
            "messaging_product": "whatsapp",
            "contacts": [{"input": clean_to, "wa_id": clean_to}],
            "messages": [{"id": f"wamid.simulated_{clean_to[:6]}"}],
            "simulated": True,
        }

    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": clean_to,
        "type": "text",
        "text": {"preview_url": True, "body": message_text.strip()},
    }
    import json

    body_bytes = json.dumps(payload).encode("utf-8")
    req = Request(
        url,
        data=body_bytes,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "RestaurantOS-WhatsApp-Adapter/1.0",
        },
    )
    try:
        with urlopen(req, timeout=5) as resp:
            res: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
            return res
    except (HTTPError, URLError, TimeoutError) as e:
        logger.error("Error sending WhatsApp message: %s", e)
        return {"error": str(e), "status": "failed"}
