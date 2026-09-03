"""Public Mobile Web Menu & WhatsApp Ordering Service for POS-SaaS."""

from __future__ import annotations

import urllib.parse
import uuid
from datetime import datetime, timezone
from typing import Any
from fastapi import HTTPException
from pydantic import BaseModel, Field
import sqlalchemy as sa
from sqlalchemy.orm import Session

from . import models
from .operations import _now


class WhatsAppOrderItem(BaseModel):
    product_id: str = Field(..., min_length=1)
    quantity: int = Field(default=1, ge=1, le=100)
    notes: str | None = None


class WhatsAppOrderRequest(BaseModel):
    branch_id: str = Field(..., min_length=1)
    customer_name: str = Field(..., min_length=1)
    customer_phone: str = Field(..., min_length=7)
    order_type: str = Field(default="takeaway")  # takeaway, delivery, dine-in
    delivery_address: str | None = None
    items: list[WhatsAppOrderItem] = Field(..., min_length=1)
    payment_method: str = Field(default="cash")  # cash, card, transfer
    cash_amount: str | None = None
    order_notes: str | None = None


def get_public_menu_for_branch(session: Session, branch_id: str) -> dict[str, Any]:
    """Retrieves the public menu of available products and categories for a specific branch."""
    branch = (
        session.execute(sa.select(models.branches).where(models.branches.c.id == branch_id))
        .mappings()
        .first()
    )
    if not branch:
        raise HTTPException(
            status_code=404,
            detail={"code": "branch_not_found", "message": "Sucursal no encontrada"},
        )

    org_id = str(branch["organization_id"])
    org_name = (
        session.scalar(
            sa.select(models.organizations.c.name).where(models.organizations.c.id == org_id)
        )
        or branch["name"]
    )

    # Categories
    categories_rows = session.execute(
        sa.select(models.product_categories)
        .where(models.product_categories.c.organization_id == org_id)
        .order_by(models.product_categories.c.name.asc())
    ).mappings().all()

    categories = [
        {"id": str(c["id"]), "name": str(c["name"]), "description": c.get("description")}
        for c in categories_rows
    ]

    # Active prices subquery
    active_price = (
        sa.select(
            models.price_versions.c.product_id,
            models.price_versions.c.price_cents,
            models.price_versions.c.currency,
        )
        .where(models.price_versions.c.valid_to.is_(None))
        .subquery()
    )

    # Products query with availability check
    query = (
        sa.select(
            models.products.c.id,
            models.products.c.name,
            models.products.c.sku,
            models.products.c.description,
            models.products.c.category_id,
            models.products.c.image_url,
            models.products.c.delivery_price_cents,
            models.product_categories.c.name.label("category_name"),
            active_price.c.price_cents,
            active_price.c.currency,
            sa.func.coalesce(models.branch_product_availability.c.is_available, True).label("is_available"),
        )
        .select_from(
            models.products.join(
                models.product_categories,
                models.products.c.category_id == models.product_categories.c.id,
            )
            .outerjoin(active_price, models.products.c.id == active_price.c.product_id)
            .outerjoin(
                models.branch_product_availability,
                sa.and_(
                    models.products.c.id == models.branch_product_availability.c.product_id,
                    models.branch_product_availability.c.branch_id == branch_id,
                ),
            )
        )
        .where(
            models.products.c.organization_id == org_id,
            models.products.c.status != "archived",
            sa.func.coalesce(models.branch_product_availability.c.is_available, True).is_(True),
        )
        .order_by(models.product_categories.c.name.asc(), models.products.c.name.asc())
    )

    prod_rows = session.execute(query).mappings().all()
    products = [
        {
            "id": str(p["id"]),
            "name": str(p["name"]),
            "sku": str(p["sku"]),
            "description": p.get("description"),
            "category_id": str(p["category_id"]),
            "category_name": str(p["category_name"]),
            "image_url": p.get("image_url"),
            "price_cents": int(p["price_cents"] or 0),
            "delivery_price_cents": int(p["delivery_price_cents"]) if p.get("delivery_price_cents") is not None else None,
            "currency": str(p.get("currency") or "MXN"),
            "is_available": bool(p["is_available"]),
        }
        for p in prod_rows
    ]

    phone = str(branch.get("phone") or "525512345678").strip()

    return {
        "branch": {
            "id": str(branch["id"]),
            "name": str(branch["name"]),
            "code": branch.get("code"),
            "address": branch.get("address"),
            "phone": phone,
            "whatsapp_phone": phone,
            "business_name": org_name,
        },
        "categories": categories,
        "products": products,
    }


def submit_whatsapp_order(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Process a public WhatsApp order request, validate items and compute server-side totals."""
    req = WhatsAppOrderRequest(**payload)

    branch = (
        session.execute(sa.select(models.branches).where(models.branches.c.id == req.branch_id))
        .mappings()
        .first()
    )
    if not branch:
        raise HTTPException(status_code=404, detail={"code": "branch_not_found", "message": "Sucursal no encontrada"})

    org_id = str(branch["organization_id"])
    branch_name = str(branch["name"])
    phone = str(branch.get("phone") or "525512345678").strip()
    clean_phone = phone.replace("+", "").replace(" ", "").replace("-", "")

    # Retrieve all ordered products and check availability
    product_ids = [item.product_id for item in req.items]
    active_price = (
        sa.select(
            models.price_versions.c.product_id,
            models.price_versions.c.price_cents,
        )
        .where(models.price_versions.c.valid_to.is_(None))
        .subquery()
    )

    query = (
        sa.select(
            models.products.c.id,
            models.products.c.name,
            active_price.c.price_cents,
            sa.func.coalesce(models.branch_product_availability.c.is_available, True).label("is_available"),
        )
        .select_from(
            models.products.outerjoin(active_price, models.products.c.id == active_price.c.product_id)
            .outerjoin(
                models.branch_product_availability,
                sa.and_(
                    models.products.c.id == models.branch_product_availability.c.product_id,
                    models.branch_product_availability.c.branch_id == req.branch_id,
                ),
            )
        )
        .where(
            models.products.c.id.in_(product_ids),
            models.products.c.organization_id == org_id,
        )
    )

    prod_map = {str(r["id"]): r for r in session.execute(query).mappings().all()}

    total_cents = 0
    detailed_lines = []

    for item in req.items:
        p = prod_map.get(item.product_id)
        if not p:
            raise HTTPException(
                status_code=400,
                detail={"code": "product_not_found", "message": f"Producto {item.product_id} no existe"},
            )

        if not p["is_available"]:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "product_unavailable",
                    "message": f"El producto '{p['name']}' no está disponible en este momento",
                    "product_id": item.product_id,
                },
            )

        price = int(p["price_cents"] or 0)
        line_total = price * item.quantity
        total_cents += line_total
        detailed_lines.append(
            {
                "product_name": str(p["name"]),
                "quantity": item.quantity,
                "unit_price_cents": price,
                "line_total_cents": line_total,
                "notes": item.notes,
            }
        )

    # Generate Folio
    folio_rand = uuid.uuid4().hex[:4].upper()
    folio = f"W-{folio_rand}"
    now = _now()

    # Format WhatsApp text
    type_labels = {
        "takeaway": "🛍️ Para Recoger en Sucursal",
        "delivery": "🛵 Envío a Domicilio",
        "dine-in": "🍽️ Para Comer Aquí",
    }
    type_desc = type_labels.get(req.order_type, "🛍️ Para Recoger")

    payment_labels = {
        "cash": f"Efectivo {f'(Paga con: ${req.cash_amount})' if req.cash_amount else ''}",
        "card": "Tarjeta al recibir",
        "transfer": "Transferencia bancaria",
    }
    payment_desc = payment_labels.get(req.payment_method, "Efectivo")

    lines_text = []
    for d in detailed_lines:
        price_str = f"${(d['line_total_cents'] / 100):.2f}"
        line = f"• {d['quantity']}x {d['product_name']} ({price_str})"
        if d["notes"]:
            line += f"\n   ↳ _{d['notes']}_"
        lines_text.append(line)

    order_items_block = "\n".join(lines_text)

    msg = f"🌮 *NUEVO PEDIDO - {branch_name.upper()}*\n"
    msg += f"📋 *Folio:* #{folio}\n"
    msg += f"👤 *Cliente:* {req.customer_name}\n"
    msg += f"📱 *Teléfono:* {req.customer_phone}\n"
    msg += f"📦 *Modalidad:* {type_desc}\n"

    if req.order_type == "delivery" and req.delivery_address:
        msg += f"📍 *Dirección:* {req.delivery_address}\n"

    msg += f"💳 *Método de Pago:* {payment_desc}\n\n"
    msg += f"🛒 *DETALLE DEL PEDIDO:*\n{order_items_block}\n\n"
    msg += f"💰 *TOTAL A PAGAR:* *${(total_cents / 100):.2f} MXN*\n"

    if req.order_notes:
        msg += f"📝 *Notas:* {req.order_notes}\n"

    msg += "\n✨ _Pedido generado desde Menú Web POS-SaaS_"

    encoded_text = urllib.parse.quote(msg)
    wa_url = f"https://wa.me/{clean_phone}?text={encoded_text}"

    # Register order intent in DB for real-time POS visibility
    pub_key_row = session.execute(
        sa.select(models.public_order_keys.c.public_key).where(
            models.public_order_keys.c.branch_id == req.branch_id,
            models.public_order_keys.c.status == "active",
        )
    ).scalar_one_or_none()

    if not pub_key_row:
        pub_key = f"pk_live_{uuid.uuid4().hex[:16]}"
        session.execute(
            models.public_order_keys.insert().values(
                public_key=pub_key,
                organization_id=org_id,
                branch_id=req.branch_id,
                status="active",
                created_at=now,
            )
        )
    else:
        pub_key = str(pub_key_row)

    intent_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    customer_snapshot = {
        "name": req.customer_name,
        "phone": req.customer_phone,
    }
    delivery_snapshot = {"address_text": req.delivery_address} if req.delivery_address else None

    session.execute(
        models.public_order_intents.insert().values(
            id=intent_id,
            organization_id=org_id,
            branch_id=req.branch_id,
            public_key=pub_key,
            public_reference=folio,
            correlation_id=correlation_id,
            status="PENDING_REVIEW",
            customer_snapshot=customer_snapshot,
            delivery_address_snapshot=delivery_snapshot,
            order_type=req.order_type,
            order_notes=req.order_notes,
            total_cents=total_cents,
            currency="MXN",
            version=1,
            created_at=now,
        )
    )
    session.commit()

    return {
        "folio": folio,
        "total_cents": total_cents,
        "currency": "MXN",
        "whatsapp_phone": clean_phone,
        "whatsapp_url": wa_url,
        "message_text": msg,
        "items_count": len(req.items),
        "created_at": now.isoformat(),
    }
