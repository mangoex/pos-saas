"""Compatibility projection and WhatsApp drafts over canonical public order intents."""

from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import quote

import sqlalchemy as sa
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from restaurant_os import models
from restaurant_os.operations import get_public_catalog
from restaurant_os.public_storefront import resolve_storefront


class WhatsAppOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    public_key: str = Field(min_length=1, max_length=160)
    branch_id: str | None = Field(default=None, max_length=36)
    customer_name: str = Field(min_length=1, max_length=160)
    customer_phone: str = Field(min_length=10, max_length=32)
    order_type: Literal["takeaway", "takeout", "delivery", "dine-in"] = "takeaway"
    delivery_address: str | None = Field(default=None, max_length=500)
    items: list[dict[str, Any]] = Field(min_length=1, max_length=50)
    payment_method: Literal["cash", "card", "transfer"] = "cash"
    cash_amount: str | None = Field(default=None, max_length=32)
    order_notes: str | None = Field(default=None, max_length=400)

    def canonical_payload(self) -> dict[str, Any]:
        notes = (self.order_notes or "").strip()
        payment = f"Método solicitado: {self.payment_method} (sin pago confirmado)"
        if self.cash_amount:
            payment += f"; efectivo declarado: {self.cash_amount}"
        return {
            "customer_name": self.customer_name,
            "customer_phone": self.customer_phone,
            "order_type": "takeout" if self.order_type == "takeaway" else self.order_type,
            "lines": self.items,
            "order_notes": f"{notes}\n{payment}".strip(),
            "delivery_address": {"address_text": self.delivery_address}
            if self.delivery_address
            else None,
        }


def get_public_menu_for_branch(session: Session, branch_id: str) -> dict[str, Any]:
    """Legacy read shape, with the same exact identity and catalog as the storefront."""
    storefront = resolve_storefront(session, branch_id)
    branch = next((branch for branch in storefront["branches"] if branch["id"] == branch_id), None)
    if branch is None:
        raise HTTPException(404, detail={"code": "branch_not_found"})
    catalog = get_public_catalog(session, branch_id)
    return {
        "branch": {**branch, "business_name": storefront["organization"]["name"]},
        "categories": catalog["categories"],
        "products": catalog["items"],
    }


def whatsapp_draft_for_intent(
    session: Session, public_key: str, result: dict[str, Any]
) -> dict[str, Any]:
    """Format committed snapshots only; this function sends nothing and writes nothing."""
    intent = (
        session.execute(
            sa.select(models.public_order_intents).where(
                models.public_order_intents.c.public_key == public_key,
                models.public_order_intents.c.public_reference == result["public_reference"],
            )
        )
        .mappings()
        .one()
    )
    branch = (
        session.execute(
            sa.select(models.branches).where(
                models.branches.c.id == intent["branch_id"],
                models.branches.c.organization_id == intent["organization_id"],
            )
        )
        .mappings()
        .one()
    )
    lines = (
        session.execute(
            sa.select(models.public_order_intent_lines)
            .where(
                models.public_order_intent_lines.c.intent_id == intent["id"],
            )
            .order_by(models.public_order_intent_lines.c.id)
        )
        .mappings()
        .all()
    )
    customer = intent["customer_snapshot"]
    text = [
        f"Solicitud pendiente de aceptación — {branch['name']}",
        f"Referencia: {result['public_reference']}",
        f"Cliente: {customer.get('name', '')}",
    ]
    for line in lines:
        text.append(f"{line['quantity']} x {line['product_name']}")
        if line["line_notes"]:
            text.append(str(line["line_notes"]))
    cents = int(intent["total_cents"])
    text.append(f"Total solicitado: ${cents // 100}.{cents % 100:02d} MXN")
    if intent["order_notes"]:
        text.append(str(intent["order_notes"]))
    message = "\n".join(text)
    phone = re.sub(r"[ +()-]", "", str(branch.get("phone") or ""))
    valid_phone = bool(re.fullmatch(r"[1-9]\d{7,14}", phone))
    return {
        **result,
        "currency": "MXN",
        "whatsapp_phone": phone if valid_phone else None,
        "whatsapp_url": f"https://wa.me/{phone}?text={quote(message)}" if valid_phone else None,
        "message_text": message,
        "items_count": len(lines),
    }
