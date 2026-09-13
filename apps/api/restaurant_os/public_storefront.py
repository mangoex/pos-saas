"""Read-only public restaurant resolution; never infer a different tenant."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from html import escape
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from restaurant_os.config import get_settings
from restaurant_os.operations import get_public_catalog
from sqlalchemy.orm import Session

from restaurant_os import models
from restaurant_os.database import get_session

router = APIRouter(prefix="/api/v1/public/storefronts", tags=["storefronts"])
host_context_router = APIRouter(prefix="/api/v1/public", tags=["storefronts"])


def resolve_storefront(session: Session, identifier: str) -> dict[str, Any]:
    identifier = identifier.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", identifier):
        raise HTTPException(404, detail={"code": "storefront_not_found"})
    orgs = (
        session.execute(
            sa.select(models.organizations).where(
                models.organizations.c.slug == identifier,
            )
        )
        .mappings()
        .all()
    )
    # Compatibility for existing printed URLs is exact and unambiguous, never first-match.
    aliases = (
        session.execute(
            sa.select(models.branches).where(
                sa.or_(
                    sa.func.lower(models.branches.c.code) == identifier,
                    models.branches.c.id == identifier,
                )
            )
        )
        .mappings()
        .all()
    )
    org_ids = {str(org["id"]) for org in orgs}
    org_ids.update(
        str(value)
        for value in session.scalars(
            sa.select(models.storefront_aliases.c.organization_id).where(
                models.storefront_aliases.c.alias == identifier
            )
        )
    )
    org_ids.update(str(branch["organization_id"]) for branch in aliases)
    if not org_ids:
        raise HTTPException(404, detail={"code": "storefront_not_found"})
    if len(org_ids) != 1 or len(aliases) > 1:
        raise HTTPException(409, detail={"code": "storefront_ambiguous"})
    host_org = session.info.get("host_organization_id")
    if host_org and host_org not in org_ids:
        raise HTTPException(404, detail={"code": "storefront_not_found"})
    org = (
        session.execute(
            sa.select(models.organizations).where(
                models.organizations.c.id == next(iter(org_ids)),
            )
        )
        .mappings()
        .one()
    )
    now = datetime.now(timezone.utc)
    trial_end = org["trial_ends_at"]
    if trial_end and trial_end.tzinfo is None:
        trial_end = trial_end.replace(tzinfo=timezone.utc)
    if (
        org["status"] != "active"
        or org["subscription_status"] not in {"active", "trialing"}
        or (org["subscription_status"] == "trialing" and (trial_end is None or trial_end <= now))
    ):
        raise HTTPException(403, detail={"code": "storefront_unavailable"})
    if not org["slug"]:
        raise HTTPException(409, detail={"code": "storefront_setup_required"})
    branch_rows = (
        session.execute(
            sa.select(models.branches)
            .where(
                models.branches.c.organization_id == org["id"],
                models.branches.c.status == "active",
            )
            .order_by(models.branches.c.code)
        )
        .mappings()
        .all()
    )
    public_fields = (
        "id",
        "name",
        "code",
        "street",
        "exterior_number",
        "interior_number",
        "neighborhood",
        "postal_code",
        "city",
        "state",
        "cross_streets",
        "latitude",
        "longitude",
        "phone",
        "status",
        "google_review_url",
        "whatsapp_ordering_enabled",
        "delivery_fee_enabled",
        "delivery_tiers",
        "free_delivery_min_cents",
        "coupons",
    )
    branches = []
    for branch in branch_rows:
        keys = (
            session.execute(
                sa.select(models.public_order_keys.c.public_key).where(
                    models.public_order_keys.c.organization_id == org["id"],
                    models.public_order_keys.c.branch_id == branch["id"],
                    models.public_order_keys.c.status == "active",
                )
            )
            .scalars()
            .all()
        )
        if len(keys) != 1:
            raise HTTPException(409, detail={"code": "storefront_setup_required"})
        has_active_shift = bool(
            session.execute(
                sa.select(models.cash_shifts.c.id).where(
                    models.cash_shifts.c.branch_id == branch["id"],
                    sa.func.upper(models.cash_shifts.c.status).in_(("OPEN", "CLOSING")),
                )
            ).first()
        )
        branches.append(
            {
                **{key: branch[key] for key in public_fields},
                "public_key": keys[0],
                "mobile_theme": org["mobile_theme"],
                "has_active_shift": has_active_shift,
            }
        )
    selected = str(aliases[0]["id"]) if aliases else None
    if not branches or (selected and selected not in {b["id"] for b in branches}):
        raise HTTPException(404, detail={"code": "storefront_not_found"})
    fields = ("id", "name", "slug", "mobile_theme")
    return {
        "organization": {**{key: org[key] for key in fields}, "public_slug": org["slug"]},
        "branches": branches,
        "selected_branch_id": selected,
    }


@router.get("/{identifier}")
def storefront(
    identifier: str, response: Response, session: Annotated[Session, Depends(get_session)]
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    return resolve_storefront(session, identifier)


@router.get("/{identifier}/manifest.webmanifest")
def manifest(
    identifier: str, response: Response, session: Annotated[Session, Depends(get_session)]
) -> dict[str, Any]:
    result = resolve_storefront(session, identifier)
    org = result["organization"]
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Type"] = "application/manifest+json"
    path = f"/menu/{org['slug']}/"
    return _manifest(org, path)


def _manifest(org: dict[str, Any], path: str) -> dict[str, Any]:
    return {
        "id": path,
        "name": org["name"],
        "short_name": org["name"][:24],
        "start_url": path,
        "scope": path,
        "display": "standalone",
        "lang": "es",
        "theme_color": "#10b981",
        "background_color": "#ffffff",
        "icons": [
            {
                "src": f"/api/v1/public/storefronts/{org['slug']}/icon.svg",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any maskable",
            }
        ],
    }


@host_context_router.get("/storefront-context")
def host_context(session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
    """Expose a wildcard tenant already bound from Host, never from browser parsing."""
    if session.info.get("host_class") != "wildcard":
        raise HTTPException(404, detail={"code": "storefront_not_found"})
    slug = session.info.get("host_restaurant_slug")
    if not isinstance(slug, str):
        raise HTTPException(404, detail={"code": "storefront_not_found"})
    return {**resolve_storefront(session, slug), "host_class": "wildcard"}


@host_context_router.get("/storefront-context/manifest.webmanifest")
def host_context_manifest(
    response: Response, session: Annotated[Session, Depends(get_session)]
) -> dict[str, Any]:
    result = host_context(session)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Type"] = "application/manifest+json"
    return _manifest(result["organization"], "/")


@router.get("/{identifier}/icon.svg")
def icon(identifier: str, session: Annotated[Session, Depends(get_session)]) -> Response:
    org = resolve_storefront(session, identifier)["organization"]
    initials = escape("".join(word[0] for word in org["name"].split()[:2]).upper())
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
        '<rect width="512" height="512" rx="96" fill="#087f5b"/>'
        '<text x="256" y="300" text-anchor="middle" font-family="sans-serif" '
        f'font-size="160" fill="white">{initials}</text></svg>'
    )
    return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


storefront_orders_router = APIRouter(
    prefix="/api/v1/storefront/orders", tags=["storefront-orders"]
)


class VoiceOrderRequest(BaseModel):
    """Public voice order request — no authentication required."""

    transcript: str
    branch_id: str


@storefront_orders_router.post("/voice")
def post_storefront_voice_order(
    request: VoiceOrderRequest,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Parse a voice transcript into structured cart items using AI."""
    import json as _json
    import logging
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    logger = logging.getLogger("restaurant_os.storefront_voice")

    # 1. Validate branch exists
    branch_exists = session.execute(
        sa.select(models.branches.c.id).where(
            models.branches.c.id == request.branch_id
        )
    ).scalar()
    if not branch_exists:
        raise HTTPException(status_code=404, detail="Branch not found")

    # 2. Load public catalog for the branch
    catalog = get_public_catalog(session, request.branch_id)
    menu: list[dict[str, Any]] = []
    for item in catalog.get("items", []):
        menu.append({"id": str(item["id"]), "name": str(item["name"])})

    if not menu:
        raise HTTPException(
            status_code=422, detail="No catalog items found for this branch."
        )

    # 3. Build AI request using configured settings
    settings = get_settings()
    api_key = settings.openrouter_api_key
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Voice ordering is not configured on this installation.",
        )

    body = {
        "model": settings.openrouter_model,
        "temperature": 0,
        "max_tokens": 700,
        "provider": {"require_parameters": True},
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Eres un capturista de pedidos de restaurante en español de México. "
                    "Usa exclusivamente los IDs del catálogo proporcionado. "
                    "No inventes productos.\n"
                    "Devuelve EXACTAMENTE un objeto JSON con este esquema:\n"
                    '{"items": [{"product_id": "string", "quantity": 1, "modifiers": ["string"]}]}'
                ),
            },
            {
                "role": "user",
                "content": _json.dumps(
                    {"request": request.transcript, "catalog": menu},
                    ensure_ascii=False,
                ),
            },
        ],
    }

    base_url = getattr(settings, "openrouter_base_url", "https://openrouter.ai/api/v1")
    timeout = getattr(settings, "openrouter_timeout_seconds", 15)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    http_referer = getattr(settings, "openrouter_http_referer", None)
    app_title = getattr(settings, "openrouter_app_title", "RestaurantOS")
    if http_referer:
        headers["HTTP-Referer"] = http_referer
    headers["X-OpenRouter-Title"] = app_title

    req = Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=_json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urlopen(req, timeout=timeout) as resp:
            envelope = _json.loads(resp.read().decode("utf-8"))
        content = envelope["choices"][0]["message"]["content"]
        if isinstance(content, str):
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            parsed = _json.loads(content.strip())
        else:
            parsed = content
    except (HTTPError, URLError, TimeoutError) as exc:
        logger.warning("storefront_voice_order provider_error: %s", exc)
        raise HTTPException(
            status_code=502, detail="Voice service unavailable. Try again."
        ) from exc
    except (KeyError, IndexError, ValueError, _json.JSONDecodeError) as exc:
        logger.warning("storefront_voice_order parse_error: %s", exc)
        raise HTTPException(
            status_code=502, detail="Could not parse AI response."
        ) from exc

    if not isinstance(parsed, dict) or not isinstance(parsed.get("items"), list):
        return {"items": []}

    logger.info(
        "storefront_voice_order success branch_id=%s items=%d",
        request.branch_id,
        len(parsed["items"]),
    )
    return parsed
