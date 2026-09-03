"""1-Click Public Self-Invoicing CFDI 4.0 Service for POS-SaaS."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from fastapi import HTTPException
from pydantic import BaseModel, Field
import sqlalchemy as sa
from sqlalchemy.orm import Session

from .. import models
from .service import InvoicingService

invoicing_service = InvoicingService()


class SelfInvoiceEmitRequest(BaseModel):
    folio: str = Field(..., min_length=1)
    rfc: str = Field(..., min_length=12, max_length=13)
    legal_name: str = Field(..., min_length=1)
    zip: str = Field(..., min_length=5, max_length=5)
    tax_system: str = Field(default="612")
    use: str = Field(default="G03")
    email: str | None = None


def lookup_ticket_for_self_invoicing(session: Session, folio: str) -> dict[str, Any]:
    """Public lookup for ticket verification prior to self-invoicing."""
    clean_folio = folio.strip()
    order = (
        session.execute(
            sa.select(models.orders).where(models.orders.c.folio == clean_folio)
        )
        .mappings()
        .first()
    )
    if not order:
        raise HTTPException(
            status_code=404,
            detail={"code": "order_not_found", "message": "Ticket no encontrado con el folio especificado"},
        )

    org_id = str(order["organization_id"])

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
    date_str = created_dt.isoformat() if hasattr(created_dt, "isoformat") else str(created_dt)

    return {
        "order_id": order["id"],
        "folio": order["folio"],
        "total_cents": int(order["total_cents"]),
        "currency": order.get("currency", "MXN"),
        "date": date_str,
        "business_name": org_name,
        "business_rfc": org_cfg.get("organization_rfc", ""),
        "is_invoiced": existing_inv is not None,
        "existing_invoice_uuid": existing_inv.get("sat_uuid") if existing_inv else None,
    }


def emit_self_invoice(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Process a public 1-click self-invoice request and stamp CFDI 4.0 with FacturAPI."""
    req = SelfInvoiceEmitRequest(**payload)

    # 1. Lookup order
    order = (
        session.execute(
            sa.select(models.orders).where(models.orders.c.folio == req.folio.strip())
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
    org_id = str(order["organization_id"])
    branch_id = str(order["branch_id"])

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
        sat_uuid = existing_inv.get("sat_uuid") or existing_inv.get("id")
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
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "facturapi_error", "message": str(exc)},
        ) from exc

    return {
        "status": "valid",
        "folio": order["folio"],
        "uuid": inv_result.get("sat_uuid"),
        "series_folio": inv_result.get("folio_number"),
        "pdf_url": inv_result.get("pdf_url"),
        "xml_url": inv_result.get("xml_url"),
        "total_cents": int(order["total_cents"]),
        "rfc_receptor": receptor["rfc"],
        "legal_name": receptor["legal_name"],
    }
