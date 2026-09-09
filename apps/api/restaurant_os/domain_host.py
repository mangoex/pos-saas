"""Bind request Host to tenant identity without trusting forwarding headers."""

from __future__ import annotations

from typing import Annotated, Literal

import sqlalchemy as sa
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from restaurant_os import models
from restaurant_os.auth import bearer_token, verify_session_token
from restaurant_os.config import get_settings
from restaurant_os.database import get_session
from restaurant_os.public_names import is_wildcard_compatible_public_name
from restaurant_os.public_storefront import resolve_storefront
from restaurant_os.restaurant_domains import error, platform_hosts, wildcard_domain

HostClass = Literal["custom", "wildcard"]
_HEALTH_PATHS = {"/health/live", "/health/ready", "/health/version"}
_HOST_CONTEXT_PATHS = {
    "/api/v1/public/storefront-context",
    "/api/v1/public/storefront-context/manifest.webmanifest",
}


def assert_host_organization(session: Session, organization_id: str) -> None:
    expected = session.info.get("host_organization_id")
    if expected and expected != organization_id:
        raise error(403, "domain_tenant_mismatch")


def _bind_tenant(
    request: Request,
    session: Session,
    organization_id: str,
    slug: str,
    host_class: HostClass,
) -> None:
    session.info["host_organization_id"] = organization_id
    session.info["host_restaurant_slug"] = slug
    session.info["host_class"] = host_class
    request.state.restaurant_slug = slug
    request.state.host_class = host_class


def _wildcard_identifier(host: str, base: str) -> str | None:
    suffix = "." + base
    if not host.endswith(suffix):
        return None
    identifier = host[: -len(suffix)]
    if "." in identifier or not is_wildcard_compatible_public_name(identifier):
        raise error(404, "domain_unavailable")
    return identifier


def _resolve_wildcard_storefront(session: Session, identifier: str) -> dict[str, object]:
    """Avoid exposing tenant lifecycle/ambiguity details through an untrusted hostname."""
    try:
        return resolve_storefront(session, identifier)
    except HTTPException as exc:
        if exc.status_code in {403, 404, 409}:
            raise error(404, "domain_unavailable") from exc
        raise


async def bind_domain_host(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> None:
    if request.scope["path"] in _HEALTH_PATHS:
        return
    try:
        # Starlette derives this from the incoming Host header. Forwarded headers are not consulted.
        host = (request.url.hostname or "").lower().rstrip(".")
    except ValueError as exc:
        raise error(404, "domain_unavailable") from exc

    row = (
        session.execute(
            sa.select(models.restaurant_domains).where(
                models.restaurant_domains.c.hostname == host,
            )
        )
        .mappings()
        .first()
    )
    platform = platform_hosts()
    if row and host in platform:
        # Configuration drift must never silently turn a tenant domain into a platform host.
        raise error(404, "domain_unavailable")
    if row:
        if row["status"] != "active":
            raise error(404, "domain_unavailable")
        org_id = str(row["organization_id"])
        slug = session.scalar(
            sa.select(models.organizations.c.slug).where(models.organizations.c.id == org_id)
        )
        if not slug:
            raise error(404, "domain_unavailable")
        resolve_storefront(session, str(slug))
        _bind_tenant(request, session, org_id, str(slug), "custom")
    elif host in platform:
        return
    else:
        base = wildcard_domain()
        identifier = _wildcard_identifier(host, base) if base else None
        if not identifier:
            raise error(404, "domain_unavailable")
        storefront = _resolve_wildcard_storefront(session, identifier)
        organization = storefront["organization"]
        if not isinstance(organization, dict):
            raise error(404, "domain_unavailable")
        org_id = str(organization["id"])
        slug = str(organization["slug"])
        _bind_tenant(request, session, org_id, slug, "wildcard")

    path = request.url.path
    token = bearer_token(request.headers.get("authorization"))
    authenticated = False
    if token:
        claims = verify_session_token(token, get_settings().secret_key)
        user = (
            session.execute(
                sa.select(models.users).where(
                    models.users.c.id == str(claims.get("sub", "")) if claims else sa.false(),
                    models.users.c.status == "active",
                )
            )
            .mappings()
            .first()
        )
        if not user:
            raise error(401, "actor_required")
        assert_host_organization(session, str(user["organization_id"]))
        authenticated = True
    if not path.startswith("/api/"):
        # HTML for an unrelated menu must not be served even before its API request.
        if path.startswith("/menu/"):
            identifier = path[len("/menu/") :].split("/")[0]
            if identifier and identifier != "assets" and "." not in identifier:
                resolve_storefront(session, identifier)
        return
    if path in _HOST_CONTEXT_PATHS:
        if session.info.get("host_class") != "wildcard":
            raise error(404, "domain_unavailable")
        return
    if path == "/api/v1/auth/login":
        return  # login checks the authenticated organization before issuing its token.
    if path.startswith("/api/v1/public/storefronts/"):
        resolve_storefront(session, path.split("/")[5])
        return
    if path.startswith("/api/v1/public/restaurants/"):
        resolve_storefront(session, path.split("/")[5])
        return
    if path.startswith("/api/v1/public/branches/"):
        key = path.split("/")[5]
        owner = session.scalar(
            sa.select(models.public_order_keys.c.organization_id).where(
                models.public_order_keys.c.public_key == key,
                models.public_order_keys.c.status == "active",
                models.public_order_keys.c.branch_id.in_(
                    sa.select(models.branches.c.id).where(
                        models.branches.c.organization_id == session.info["host_organization_id"],
                        models.branches.c.status == "active",
                    )
                ),
            )
        )
        if owner != session.info["host_organization_id"]:
            raise error(404, "public_order_unavailable")
        return
    if path in {"/api/v1/public/branches", "/api/v1/public/mobile-theme"}:
        resolve_storefront(session, request.query_params.get("identifier", ""))
        return
    if path in {"/api/v1/public/feedback", "/api/v1/public/order-upsell-recommendations"}:
        body = await request.body()
        if len(body) > 65536:
            raise error(413, "payload_too_large")
        try:
            payload = await request.json()
            branch_id = payload.get("branch_id", "")
        except (ValueError, AttributeError) as exc:
            raise error(422, "branch_context_required") from exc
        if (
            not isinstance(branch_id, str)
            or session.scalar(
                sa.select(models.branches.c.organization_id).where(
                    models.branches.c.id == branch_id
                )
            )
            != session.info["host_organization_id"]
        ):
            raise error(404, "branch_not_found")
        return
    # Customer domains expose only the canonical mobile endpoints. Registration and
    # provider webhooks stay on the platform domain, where their own guards apply.
    if path.startswith("/api/v1/public/") or not authenticated:
        raise error(403, "domain_route_unavailable")
