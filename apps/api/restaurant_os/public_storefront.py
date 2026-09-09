"""Read-only public restaurant resolution; never infer a different tenant."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from html import escape
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Response
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
        branches.append(
            {
                **{key: branch[key] for key in public_fields},
                "public_key": keys[0],
                "mobile_theme": org["mobile_theme"],
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
