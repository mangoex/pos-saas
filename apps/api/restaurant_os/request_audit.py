"""Request-local support attribution and live issuer authorization."""

from __future__ import annotations

from typing import Annotated
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from restaurant_os import models
from restaurant_os.auth import bearer_token, verify_session_token
from restaurant_os.config import get_settings
from restaurant_os.database import get_session
from restaurant_os.operations import _audit, _require_active_actor_organization
from restaurant_os.superadmin.service import require_superadmin


def bind_support_audit_context(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> None:
    token = bearer_token(request.headers.get("authorization"))
    if not token:
        return
    payload = verify_session_token(token, get_settings().secret_key)
    if not payload or not payload.get("impersonated_by"):
        return
    issuer = str(payload["impersonated_by"])
    effective = str(payload.get("sub") or "")
    require_superadmin(session, issuer)
    _require_active_actor_organization(session, effective)
    actor = (
        session.execute(sa.select(models.users).where(models.users.c.id == effective))
        .mappings()
        .one()
    )
    target = str(actor["organization_id"])
    if payload.get("target_organization_id") != target:
        raise HTTPException(403, detail={"code": "support_scope_invalid"})
    session.info["support_audit_context"] = {
        "real_actor_user_id": issuer,
        "effective_actor_user_id": effective,
        "target_organization_id": target,
        "correlation_id": str(uuid4()),
    }
    route = request.scope.get("route")
    route_path = str(getattr(route, "path", "api"))
    _audit(
        session,
        action="support.request_authorized",
        entity_type="api_route",
        entity_id=str(uuid5(NAMESPACE_URL, f"{request.method}:{route_path}")),
        payload={"method": request.method, "route": route_path, "phase": "authorized_attempt"},
        organization_id=target,
        actor_user_id=effective,
        branch_id=None,
    )
    # Persist an attempt before the endpoint; domain events record actual effects separately.
    session.commit()
