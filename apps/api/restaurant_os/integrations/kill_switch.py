"""Unified Delivery Hub & Global Kill-Switch Domain Service for POS-SaaS."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field
import sqlalchemy as sa
from sqlalchemy.orm import Session

from .. import models
from ..operations import AuthorizationError, BusinessError, NotFoundError, _audit, _now

UTC = timezone.utc


class KillSwitchRequest(BaseModel):
    product_id: str = Field(..., min_length=1)
    is_available: bool = Field(default=False)
    branch_id: str | None = None
    reason: str | None = Field(default="sold_out")


def toggle_kill_switch(
    session: Session,
    actor_user_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Atomically toggle a product's availability across POS, Web Menu, and Delivery Apps."""
    req = KillSwitchRequest(**payload)

    actor = (
        session.execute(sa.select(models.users).where(models.users.c.id == actor_user_id))
        .mappings()
        .first()
    )
    if not actor:
        raise AuthorizationError("actor_required", "Actor is not valid")

    org_id = str(actor["organization_id"])

    # Verify product exists in tenant
    product = (
        session.execute(
            sa.select(models.products).where(
                models.products.c.id == req.product_id,
                models.products.c.organization_id == org_id,
            )
        )
        .mappings()
        .first()
    )
    if not product:
        raise NotFoundError("product_not_found", "Product does not exist in this organization")

    now = _now()

    # 1. Update local branch availability for all branches in organization (or specific branch)
    if req.branch_id:
        target_branches = [req.branch_id]
    else:
        target_branches = list(
            session.execute(
                sa.select(models.branches.c.id).where(
                    models.branches.c.organization_id == org_id,
                    models.branches.c.status == "active",
                )
            ).scalars()
        )

    for b_id in target_branches:
        existing_avail = session.execute(
            sa.select(models.branch_product_availability.c.product_id).where(
                models.branch_product_availability.c.branch_id == b_id,
                models.branch_product_availability.c.product_id == req.product_id,
            )
        ).first()

        if existing_avail:
            session.execute(
                sa.update(models.branch_product_availability)
                .where(
                    models.branch_product_availability.c.branch_id == b_id,
                    models.branch_product_availability.c.product_id == req.product_id,
                )
                .values(is_available=req.is_available, updated_at=now)
            )
        else:
            session.execute(
                models.branch_product_availability.insert().values(
                    branch_id=b_id,
                    product_id=req.product_id,
                    is_available=req.is_available,
                    updated_at=now,
                )
            )

    # 2. Update channel_product_mappings across external providers
    session.execute(
        sa.update(models.channel_product_mappings)
        .where(
            models.channel_product_mappings.c.organization_id == org_id,
            models.channel_product_mappings.c.product_id == req.product_id,
        )
        .values(is_active=req.is_available)
    )

    # 3. Retrieve configured integrations
    active_integrations = set(
        session.execute(
            sa.select(models.channel_integrations.c.provider).where(
                models.channel_integrations.c.organization_id == org_id,
                models.channel_integrations.c.is_enabled.is_(True),
            )
        ).scalars()
    )

    channel_statuses: dict[str, Any] = {
        "pos": {
            "status": "synced",
            "is_available": req.is_available,
            "message": "Disponibilidad en terminal local actualizada",
        },
        "web_menu": {
            "status": "synced",
            "is_available": req.is_available,
            "message": "Menú web propio sincronizado",
        },
    }

    providers_catalog = [
        ("uber_eats", "UBER_EATS", "Uber Eats"),
        ("didi_food", "DIDI_FOOD", "DiDi Food"),
        ("rappi", "RAPPI", "Rappi"),
    ]

    for key, prov_code, prov_name in providers_catalog:
        if prov_code in active_integrations:
            action_desc = "reactivado" if req.is_available else "pausado"
            channel_statuses[key] = {
                "status": "synced",
                "is_available": req.is_available,
                "message": f"Producto {action_desc} en {prov_name}",
            }
        else:
            channel_statuses[key] = {
                "status": "not_configured",
                "is_available": req.is_available,
                "message": f"{prov_name} no está conectado",
            }

    # 4. Audit Log
    _audit(
        session,
        action="kill_switch.toggled",
        entity_type="product",
        entity_id=req.product_id,
        payload={
            "product_name": product["name"],
            "sku": product["sku"],
            "is_available": req.is_available,
            "reason": req.reason,
            "channels": list(channel_statuses.keys()),
        },
        branch_id=target_branches[0] if target_branches else None,
        organization_id=org_id,
        actor_user_id=actor_user_id,
    )

    session.commit()

    return {
        "product_id": req.product_id,
        "is_available": req.is_available,
        "reason": req.reason,
        "channel_statuses": channel_statuses,
        "updated_at": now.isoformat(),
    }


def get_channels_status(session: Session, actor_user_id: str) -> list[dict[str, Any]]:
    """Get the connection status, mapped store counts, and today's order metrics per delivery channel."""
    actor = (
        session.execute(sa.select(models.users).where(models.users.c.id == actor_user_id))
        .mappings()
        .first()
    )
    if not actor:
        raise AuthorizationError("actor_required", "Actor is not valid")

    org_id = str(actor["organization_id"])

    channels_def = [
        {"provider": "UBER_EATS", "key": "uber_eats", "name": "Uber Eats"},
        {"provider": "DIDI_FOOD", "key": "didi_food", "name": "DiDi Food"},
        {"provider": "RAPPI", "key": "rappi", "name": "Rappi"},
    ]

    results = []
    for c in channels_def:
        prov = c["provider"]
        cfg = (
            session.execute(
                sa.select(models.channel_integrations).where(
                    models.channel_integrations.c.organization_id == org_id,
                    models.channel_integrations.c.provider == prov,
                )
            )
            .mappings()
            .first()
        )

        stores_count = session.execute(
            sa.select(sa.func.count(models.channel_store_mappings.c.id)).where(
                models.channel_store_mappings.c.organization_id == org_id,
                models.channel_store_mappings.c.provider == prov,
                models.channel_store_mappings.c.is_active.is_(True),
            )
        ).scalar() or 0

        is_enabled = bool(cfg["is_enabled"]) if cfg else False
        environment = str(cfg["environment"]) if cfg else "sandbox"

        results.append(
            {
                "provider": prov,
                "channel_key": c["key"],
                "name": c["name"],
                "is_enabled": is_enabled,
                "environment": environment,
                "status": "connected" if is_enabled and stores_count > 0 else ("ready" if is_enabled else "disconnected"),
                "mapped_stores_count": stores_count,
                "auto_accept": bool(cfg["auto_accept"]) if cfg else True,
                "default_prep_time_minutes": int(cfg["default_prep_time_minutes"]) if cfg else 20,
            }
        )

    return results
