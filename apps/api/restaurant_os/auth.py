from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 260_000
SESSION_TTL_SECONDS = 60 * 60 * 12


def hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        _b64decode(salt),
        PASSWORD_ITERATIONS,
    )
    return _b64encode(digest)


def generate_password_salt() -> str:
    return _b64encode(secrets.token_bytes(16))


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    actual_hash = hash_password(password, salt)
    return hmac.compare_digest(actual_hash, expected_hash)


def create_session_token(
    payload: dict[str, Any],
    secret_key: str,
    now: int | None = None,
) -> str:
    issued_at = now or int(time.time())
    body = {
        **payload,
        "iat": issued_at,
        "exp": issued_at + SESSION_TTL_SECONDS,
    }
    encoded_body = _b64encode(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    signature = _sign(encoded_body, secret_key)
    return f"{encoded_body}.{signature}"


def verify_session_token(
    token: str,
    secret_key: str,
    now: int | None = None,
) -> dict[str, Any] | None:
    if "." not in token:
        return None
    encoded_body, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(_sign(encoded_body, secret_key), signature):
        return None
    try:
        raw_payload: object = json.loads(_b64decode(encoded_body))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(raw_payload, dict):
        return None
    payload: dict[str, Any] = {str(key): value for key, value in raw_payload.items()}
    if int(payload.get("exp", 0)) < (now or int(time.time())):
        return None
    return payload


def _sign(value: str, secret_key: str) -> str:
    digest = hmac.new(secret_key.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).digest()
    return _b64encode(digest)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def bearer_token(authorization: str | None) -> str | None:
    """Parse the case-insensitive HTTP authentication scheme consistently."""
    scheme, separator, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not separator or not token.strip():
        return None
    return token.strip()
