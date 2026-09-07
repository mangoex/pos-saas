"""Bind custom hosts to tenant identity without trusting forwarding headers."""

from __future__ import annotations

from typing import Annotated

import sqlalchemy as sa
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from restaurant_os import models
from restaurant_os.auth import bearer_token, verify_session_token
from restaurant_os.config import get_settings
from restaurant_os.database import get_session
from restaurant_os.public_storefront import resolve_storefront
from restaurant_os.restaurant_domains import error, platform_hosts


def assert_host_organization(session: Session, organization_id: str) -> None:
    expected = session.info.get("host_organization_id")
    if expected and expected != organization_id:
        raise error(403, "domain_tenant_mismatch")


async def bind_domain_host(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> None:
    if request.scope["path"] in {"/health/live", "/health/ready", "/health/version"}:
        return
    try:
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
    if not row:
        if host in platform_hosts():
            return
        raise error(404, "domain_unavailable")
    if row["status"] != "active" or host in platform_hosts():
        raise error(404, "domain_unavailable")
    org_id = str(row["organization_id"])
    slug = session.scalar(
        sa.select(models.organizations.c.slug).where(models.organizations.c.id == org_id)
    )
    session.info["host_organization_id"] = org_id
    # Lifecycle, public keys and canonical identity must all remain valid.
    resolve_storefront(session, str(slug))
    request.state.restaurant_slug = slug
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
                        models.branches.c.organization_id == org_id,
                        models.branches.c.status == "active",
                    )
                ),
            )
        )
        if owner != org_id:
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
            != org_id
        ):
            raise error(404, "branch_not_found")
        return
    # Customer domains expose only the canonical mobile endpoints. Registration and
    # provider webhooks stay on the platform domain, where their own guards apply.
    if path.startswith("/api/v1/public/") or not authenticated:
        raise error(403, "domain_route_unavailable")
