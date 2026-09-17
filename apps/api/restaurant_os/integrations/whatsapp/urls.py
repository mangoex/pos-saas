"""URL formatting and canonical storefront resolution for WhatsApp integrations."""

from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from restaurant_os import models
from restaurant_os.config import get_settings
from restaurant_os.public_names import is_wildcard_compatible_public_name

GENERIC_BRANCH_SLUGS = frozenset({"matriz", "default", "main", "sucursal", "branch"})


def is_uuid_string(val: Any) -> bool:
    """Check if a value is a UUID string."""
    if not val or not isinstance(val, (str, uuid.UUID)):
        return False
    val_str = str(val).strip()
    try:
        parsed = uuid.UUID(val_str)
        return str(parsed).lower() == val_str.lower()
    except (ValueError, AttributeError, TypeError):
        return False


def slugify(text: str) -> str:
    """Normalize and convert text into a safe DNS wildcard label."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return slug[:63].rstrip("-")


def get_wildcard_domain() -> str:
    """Return the configured platform storefront wildcard domain, defaulting to 'mimenu.onl'."""
    configured = get_settings().storefront_wildcard_domain
    if configured and configured.strip():
        return configured.strip().lower()
    return "mimenu.onl"


def resolve_storefront_slug(
    session: Session,
    organization_id: str,
    branch_id: str | None = None,
) -> str:
    """Resolve a clean, human-readable storefront slug.

    Never returns a raw UUID. Hierarchy:
    1. Organization preferred_public_slug (if valid and not UUID)
    2. Branch slug (if valid, not UUID, and not a generic placeholder like 'matriz')
    3. Organization canonical slug (if valid and not UUID)
    4. Branch slug (even if 'matriz', as long as not UUID)
    5. Slugified Organization name
    6. Slugified Branch name
    7. Fallback to 'menu'
    """
    org = None
    if organization_id:
        org = (
            session.execute(
                sa.select(models.organizations).where(models.organizations.c.id == organization_id)
            )
            .mappings()
            .first()
        )

    branch = None
    if branch_id:
        branch = (
            session.execute(
                sa.select(models.branches).where(models.branches.c.id == branch_id)
            )
            .mappings()
            .first()
        )

    # 1. Organization preferred_public_slug
    if org:
        pref = org.get("preferred_public_slug")
        if pref and not is_uuid_string(pref) and is_wildcard_compatible_public_name(str(pref)):
            return str(pref).lower()

    # 2. Specific branch slug (non-generic)
    if branch:
        b_slug = branch.get("slug")
        if (
            b_slug
            and not is_uuid_string(b_slug)
            and str(b_slug).lower() not in GENERIC_BRANCH_SLUGS
            and is_wildcard_compatible_public_name(str(b_slug))
        ):
            return str(b_slug).lower()

    # 3. Organization canonical slug
    if org:
        org_slug = org.get("slug")
        if (
            org_slug
            and not is_uuid_string(org_slug)
            and is_wildcard_compatible_public_name(str(org_slug))
        ):
            return str(org_slug).lower()

    # 4. Branch slug (even if generic like 'matriz')
    if branch:
        b_slug = branch.get("slug")
        if (
            b_slug
            and not is_uuid_string(b_slug)
            and is_wildcard_compatible_public_name(str(b_slug))
        ):
            return str(b_slug).lower()

    # 5. Slugified Organization name
    if org and org.get("name"):
        candidate = slugify(str(org["name"]))
        if (
            candidate
            and not is_uuid_string(candidate)
            and is_wildcard_compatible_public_name(candidate)
        ):
            return candidate

    # 6. Slugified Branch name
    if branch and branch.get("name"):
        candidate = slugify(str(branch["name"]))
        if (
            candidate
            and not is_uuid_string(candidate)
            and is_wildcard_compatible_public_name(candidate)
        ):
            return candidate

    return "menu"


def resolve_storefront_url(
    session: Session,
    organization_id: str,
    branch_id: str | None = None,
) -> tuple[str, str]:
    """Resolve (storefront_url, slug) for a tenant/branch.

    Format: https://{slug}.mimenu.onl
    """
    domain = get_wildcard_domain()
    slug = resolve_storefront_slug(session, organization_id, branch_id)
    url = f"https://{slug}.{domain}"
    return url, slug


def build_cart_url(storefront_url: str, items: list[dict[str, Any]]) -> str:
    """Build pre-filled cart URL: https://{slug}.mimenu.onl/cart?items=...&from=wa"""
    base = storefront_url.rstrip("/")
    if not items:
        return f"{base}/cart"
    encoded_payload = urllib.parse.quote(json.dumps(items))
    return f"{base}/cart?items={encoded_payload}&from=wa"


def build_tracking_url(storefront_url: str, order_id_or_folio: str) -> str:
    """Build live order tracking URL: https://{slug}.mimenu.onl/orders/{order_id}"""
    base = storefront_url.rstrip("/")
    clean_id = str(order_id_or_folio).strip()
    return f"{base}/orders/{clean_id}"


def build_rating_url(storefront_url: str, order_id_or_folio: str) -> str:
    """Build order review/rating URL: https://{slug}.mimenu.onl/orders/{order_id}/review"""
    base = storefront_url.rstrip("/")
    clean_id = str(order_id_or_folio).strip()
    return f"{base}/orders/{clean_id}/review"
