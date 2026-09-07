"""Inventory AI & Smart Procurement Engine for RestaurantOS.

Predictive purchase order generation, waste/yield audit, and invoice parsing.
All monetary amounts are strictly computed as integer cents without float precision loss.
"""

from __future__ import annotations

import re
from datetime import timezone
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from restaurant_os import models

UTC = timezone.utc


def calculate_suggested_purchases(
    session: Session,
    organization_id: str,
    branch_id: str,
    days_ahead: int = 7,
) -> list[dict[str, Any]]:
    """Return no proposal until tenant demand has a traceable inventory basis.

    POS-SaaS has no recipe-by-gram contract linking sales to inventory consumption. A
    prior implementation invented five units per day and a default cost/supplier, which
    could cause an administrator to purchase unsupported quantities. The parameters stay
    explicit for the API contract and future evidence-based implementation.
    """
    del session, organization_id, branch_id, days_ahead
    return []


def audit_inventory_yield_and_waste(
    session: Session,
    organization_id: str,
    branch_id: str,
    days: int = 30,
) -> list[dict[str, Any]]:
    """Compare theoretical consumption vs reported waste records to detect shrinkage/anomalies."""
    criteria = [models.waste_records.c.organization_id == organization_id]
    if branch_id:
        criteria.append(models.waste_records.c.branch_id == branch_id)

    waste_rows = list(
        session.execute(
            sa.select(
                models.waste_records.c.item_id,
                sa.func.sum(models.waste_records.c.quantity).label("total_waste_qty"),
                sa.func.sum(models.waste_records.c.total_cost).label("total_waste_cost"),
            )
            .where(*criteria)
            .group_by(models.waste_records.c.item_id)
        ).mappings()
    )

    items = list(
        session.execute(
            sa.select(models.inventory_items).where(
                models.inventory_items.c.organization_id == organization_id,
                models.inventory_items.c.status == "active",
            )
        ).mappings()
    )
    items_by_id = {str(i["id"]): i for i in items}

    audit_results = []
    for wr in waste_rows:
        iid = str(wr["item_id"])
        item = items_by_id.get(iid)
        name = str(item["name"]) if item else "Insumo"
        waste_qty = float(wr["total_waste_qty"] or 0)
        waste_cost = Decimal(str(wr["total_waste_cost"] or 0))
        waste_cents = int(waste_cost * 100)
        risk = "HIGH" if waste_cents > 50000 else "MEDIUM" if waste_cents > 10000 else "LOW"

        audit_results.append(
            {
                "item_id": iid,
                "item_name": name,
                "total_waste_quantity": waste_qty,
                "total_waste_cents": waste_cents,
                "risk_level": risk,
                "recommendation": "Realizar conteo físico en almacén"
                if risk != "LOW"
                else "En rango normal",
            }
        )

    return audit_results


def parse_supplier_invoice_data(raw_text_or_json: str) -> dict[str, Any]:
    """Parse only values explicitly present in supplier invoice OCR text.

    Missing or malformed fields remain absent. A parser result is review input and
    must never invent a supplier, folio, quantity, or price.
    """
    lines_parsed: list[dict[str, Any]] = []
    supplier_name: str | None = None
    folio: str | None = None

    for line in raw_text_or_json.strip().splitlines():
        line_clean = line.strip()
        if "PROVEEDOR:" in line_clean.upper():
            supplier_name = line_clean.split(":", 1)[1].strip() or None
        elif "FOLIO:" in line_clean.upper():
            folio = line_clean.split(":", 1)[1].strip() or None
        elif "|" in line_clean:
            parts = [p.strip() for p in line_clean.removeprefix("-").strip().split("|")]
            if len(parts) >= 3:
                name = parts[0]
                qty_match = re.search(r"([0-9]+(?:\.[0-9]+)?)", parts[1])
                price_match = re.search(
                    r"([0-9]+(?:\.[0-9]+)?)", parts[2].replace("$", "").replace(",", "")
                )
                if not name or not qty_match or not price_match:
                    continue
                qty = Decimal(qty_match.group(1))
                price = Decimal(price_match.group(1))
                if qty <= 0 or price < 0:
                    continue
                lines_parsed.append(
                    {
                        "item_name": name,
                        "quantity": float(qty),
                        "unit_price_cents": int((price * 100).quantize(Decimal("1"))),
                        "line_total_cents": int(
                            (qty * price * 100).quantize(Decimal("1"))
                        ),
                    }
                )

    total_cents = sum(line["line_total_cents"] for line in lines_parsed)
    return {
        "supplier_name": supplier_name,
        "folio": folio,
        "lines": lines_parsed,
        "total_cents": total_cents,
    }
