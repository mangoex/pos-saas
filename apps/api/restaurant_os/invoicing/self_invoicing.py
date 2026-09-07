"""1-Click Public Self-Invoicing CFDI 4.0 Service for POS-SaaS."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models
from ..operations import _trial_access_expired
from .service import InvoicingService

logger = logging.getLogger(__name__)
invoicing_service = InvoicingService()


class SelfInvoiceEmitRequest(BaseModel):
    public_key: str = Field(..., min_length=1, max_length=160)
    folio: str = Field(..., min_length=1)
    rfc: str = Field(..., min_length=12, max_length=13)
    legal_name: str = Field(..., min_length=1)
    zip: str = Field(..., min_length=5, max_length=5)
    tax_system: str = Field(default="612")
    use: str = Field(default="G03")
    email: str | None = None


def _public_invoice_scope(session: Session, public_key: str) -> dict[str, str]:
    """Resolve an opaque active key before inspecting a ticket or fiscal state."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", public_key):
        raise HTTPException(status_code=404, detail={"code": "public_ticket_not_found"})
    scope = (
        session.execute(
            sa.select(
                models.public_order_keys.c.organization_id,
                models.public_order_keys.c.branch_id,
            )
            .join(models.branches, models.branches.c.id == models.public_order_keys.c.branch_id)
            .join(
                models.organizations,
                models.organizations.c.id == models.public_order_keys.c.organization_id,
            )
            .where(
                models.public_order_keys.c.public_key == public_key,
                models.public_order_keys.c.status == "active",
                models.public_order_keys.c.organization_id == models.branches.c.organization_id,
                models.branches.c.status == "active",
                models.organizations.c.status == "active",
            )
        )
        .mappings()
        .first()
    )
    if not scope:
        raise HTTPException(status_code=404, detail={"code": "public_ticket_not_found"})
    return {"organization_id": str(scope["organization_id"]), "branch_id": str(scope["branch_id"])}


def _require_self_invoice_policy(session: Session, organization_id: str, created_at: Any) -> None:
    organization = (
        session.execute(
            sa.select(models.organizations).where(models.organizations.c.id == organization_id)
        )
        .mappings()
        .one()
    )
    if organization["subscription_status"] not in {"active", "trialing"} or _trial_access_expired(
        organization["subscription_status"], organization["trial_ends_at"]
    ):
        raise HTTPException(403, detail={"code": "self_invoicing_unavailable"})
    config = (
        session.execute(
            sa.select(models.facturapi_config).where(
                models.facturapi_config.c.organization_id == organization_id
            )
        )
        .mappings()
        .first()
    )
    if not config or not config["is_enabled"] or not config["enable_self_invoicing"]:
        raise HTTPException(403, detail={"code": "self_invoicing_disabled"})
    days = config["self_invoicing_days_valid"]
    if not isinstance(created_at, datetime) or not isinstance(days, int) or days <= 0:
        raise HTTPException(403, detail={"code": "self_invoicing_window_expired"})
    created = created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None else created_at
    if datetime.now(timezone.utc) >= created + timedelta(days=days):
        raise HTTPException(403, detail={"code": "self_invoicing_window_expired"})


def lookup_ticket_for_self_invoicing(
    session: Session, folio: str, public_key: str
) -> dict[str, Any]:
    """Public lookup for ticket verification prior to self-invoicing."""
    clean_folio = folio.strip()
    scope = _public_invoice_scope(session, public_key)
    order = (
        session.execute(
            sa.select(models.orders).where(
                models.orders.c.organization_id == scope["organization_id"],
                models.orders.c.branch_id == scope["branch_id"],
                models.orders.c.folio == clean_folio,
            )
        )
        .mappings()
        .first()
    )
    if not order:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "order_not_found",
                "message": "Ticket no encontrado con el folio especificado",
            },
        )

    _require_self_invoice_policy(session, scope["organization_id"], order["created_at"])
    org_id = scope["organization_id"]

    # Check if ticket was already invoiced
    existing_inv = (
        session.execute(
            sa.select(models.cfdi_invoices).where(
                models.cfdi_invoices.c.order_id == order["id"],
                models.cfdi_invoices.c.status != "canceled",
            )
        )
        .mappings()
        .first()
    )

    # Get Organization Name & RFC
    org_cfg = invoicing_service.get_config(session, org_id) or {}
    org_name = org_cfg.get("organization_legal_name")
    if not org_name:
        org_row = session.execute(
            sa.select(models.organizations.c.name).where(models.organizations.c.id == org_id)
        ).scalar_one_or_none()
        org_name = str(org_row) if org_row else "Restaurante"

    created_dt = order.get("created_at")
    date_str = (
        created_dt.isoformat()
        if created_dt is not None and hasattr(created_dt, "isoformat")
        else str(created_dt)
    )

    return {
        "order_id": order["id"],
        "folio": order["folio"],
        "total_cents": int(order["total_cents"]),
        "currency": order.get("currency", "MXN"),
        "date": date_str,
        "business_name": org_name,
        "business_rfc": org_cfg.get("organization_rfc", ""),
        "is_invoiced": existing_inv is not None,
        "existing_invoice_uuid": existing_inv.get("uuid_sat") if existing_inv else None,
    }


def emit_self_invoice(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Process a public 1-click self-invoice request and stamp CFDI 4.0 with FacturAPI."""
    req = SelfInvoiceEmitRequest(**payload)
    scope = _public_invoice_scope(session, req.public_key)

    # 1. Lookup order
    order = (
        session.execute(
            sa.select(models.orders).where(
                models.orders.c.organization_id == scope["organization_id"],
                models.orders.c.branch_id == scope["branch_id"],
                models.orders.c.folio == req.folio.strip(),
            )
        )
        .mappings()
        .first()
    )
    if not order:
        raise HTTPException(
            status_code=404,
            detail={"code": "order_not_found", "message": "Folio de ticket no encontrado"},
        )

    order_id = str(order["id"])
    _require_self_invoice_policy(session, scope["organization_id"], order["created_at"])
    org_id = scope["organization_id"]
    branch_id = scope["branch_id"]

    # 2. Invariant: Check if already invoiced (PRD-FR-034 Inmutabilidad fiscal)
    existing_inv = (
        session.execute(
            sa.select(models.cfdi_invoices).where(
                models.cfdi_invoices.c.order_id == order_id,
                models.cfdi_invoices.c.status != "canceled",
            )
        )
        .mappings()
        .first()
    )
    if existing_inv:
        sat_uuid = existing_inv.get("uuid_sat")
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ticket_already_invoiced",
                "message": f"Este ticket ya fue facturado previamente con folio fiscal {sat_uuid}",
                "sat_uuid": sat_uuid,
            },
        )

    # 3. Issue invoice via InvoicingService
    receptor = {
        "rfc": req.rfc.upper().strip(),
        "legal_name": req.legal_name.upper().strip(),
        "zip": req.zip.strip(),
        "tax_system": req.tax_system.strip(),
        "use": req.use.upper().strip(),
        "email": req.email.strip() if req.email else None,
        "payment_form": "01",
        "payment_method": "PUE",
    }

    try:
        inv_result = invoicing_service.issue_invoice(
            session=session,
            org_id=org_id,
            branch_id=branch_id,
            order_ids=[order_id],
            receptor=receptor,
            audit_operation="self_invoice",
        )
    except Exception as exc:
        correlation_id = uuid4().hex
        logger.error(
            "self_invoice_failed correlation_id=%s error_type=%s",
            correlation_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail={"code": "self_invoice_unavailable", "correlation_id": correlation_id},
        ) from exc

    if inv_result.get("status") == "simulated":
        return {
            "status": "simulated",
            "provider_confirmed": False,
            "folio": order["folio"],
            "total_cents": int(order["total_cents"]),
        }

    return {
        "status": "valid",
        "provider_confirmed": True,
        "folio": order["folio"],
        "uuid": inv_result.get("uuid_sat"),
        "series_folio": inv_result.get("folio_number"),
        "pdf_url": inv_result.get("pdf_url"),
        "xml_url": inv_result.get("xml_url"),
        "total_cents": int(order["total_cents"]),
        "rfc_receptor": receptor["rfc"],
        "legal_name": receptor["legal_name"],
    }
