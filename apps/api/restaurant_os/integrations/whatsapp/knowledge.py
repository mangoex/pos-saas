"""Knowledge Base Service that feeds menu, hours, and promotions to WhatsApp."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from restaurant_os import models
from restaurant_os.integrations.whatsapp.urls import resolve_storefront_url


class WhatsAppKnowledgeService:
    """Reads live restaurant catalog, active hours, and promotions in real-time."""

    def __init__(self, session: Session, organization_id: str, branch_id: str) -> None:
        self.session = session
        self.organization_id = organization_id
        self.branch_id = branch_id

    def get_branch_knowledge_summary(self) -> dict[str, Any]:
        """Compile complete operational knowledge of the branch."""
        storefront_url, slug = resolve_storefront_url(
            self.session, self.organization_id, self.branch_id
        )

        # 1. Branch information
        branch = self.session.execute(
            sa.select(models.branches).where(
                models.branches.c.id == self.branch_id,
                models.branches.c.organization_id == self.organization_id,
            )
        ).mappings().first()

        if not branch:
            return {
                "branch_name": "Restaurante",
                "available_products_text": "El menú no está disponible en este momento.",
                "hours_text": "Horario no configurado.",
                "promotions_text": "Sin promociones activas.",
                "storefront_url": storefront_url,
            }

        branch_name = branch["name"]

        # 2. Query all products and group available ones by category
        catalog_items = self.get_branch_catalog_items()
        categories_map: dict[str, list[dict[str, Any]]] = {}
        for item in catalog_items:
            # Strictly exclude items not available in this branch
            if not item["is_available"]:
                continue

            cat_name = item["category_name"]
            if cat_name not in categories_map:
                categories_map[cat_name] = []

            cents = item["price_cents"]
            formatted_price = f"${cents / 100:.2f}"
            categories_map[cat_name].append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "description": item["description"],
                    "price_formatted": formatted_price,
                }
            )

        # Build readable text summary
        menu_lines = []
        for cat, items in categories_map.items():
            menu_lines.append(f"\n📂 *{cat.upper()}*")
            for item in items:
                desc = f" ({item['description']})" if item["description"] else ""
                menu_lines.append(f"• {item['name']} — {item['price_formatted']} MXN{desc}")

        available_products_text = "\n".join(menu_lines).strip()
        if not available_products_text:
            available_products_text = "Por el momento no hay productos disponibles en el catálogo."

        # 3. Hours and schedule
        hours_text = "Horario habitual: Lunes a Domingo de 10:00 AM a 10:00 PM."

        # 4. Promotions and coupons
        coupons = branch.get("coupons") or []
        promo_lines = []
        if isinstance(coupons, list):
            for c in coupons:
                if isinstance(c, dict) and c.get("is_active"):
                    code = c.get("code")
                    pct = c.get("discount_percentage")
                    promo_lines.append(f"• Cupón {code}: {pct}% de descuento en tu orden web")

        promotions_text = (
            "\n".join(promo_lines) if promo_lines else "Consulta promociones vigentes al ordenar."
        )

        return {
            "branch_id": self.branch_id,
            "branch_name": branch_name,
            "phone": branch.get("phone") or "",
            "storefront_url": storefront_url,
            "available_products_text": available_products_text,
            "hours_text": hours_text,
            "promotions_text": promotions_text,
            "categories_count": len(categories_map),
        }

    def get_branch_catalog_items(self) -> list[dict[str, Any]]:
        """Query all active products in branch with availability and current price in cents."""
        active_price = (
            sa.select(
                models.price_versions.c.product_id,
                models.price_versions.c.price_cents,
                models.price_versions.c.currency,
            )
            .where(
                models.price_versions.c.organization_id == self.organization_id,
                models.price_versions.c.valid_to.is_(None),
            )
            .subquery()
        )

        query = (
            sa.select(
                models.products.c.id,
                models.products.c.name,
                models.products.c.description,
                models.products.c.sku,
                models.products.c.category_id,
                models.products.c.status,
                models.product_categories.c.name.label("category_name"),
                active_price.c.price_cents,
                active_price.c.currency,
                sa.func.coalesce(models.branch_product_availability.c.is_available, True).label(
                    "is_available"
                ),
            )
            .select_from(
                models.products.join(
                    models.product_categories,
                    models.products.c.category_id == models.product_categories.c.id,
                )
                .join(active_price, models.products.c.id == active_price.c.product_id)
                .outerjoin(
                    models.branch_product_availability,
                    sa.and_(
                        models.branch_product_availability.c.product_id == models.products.c.id,
                        models.branch_product_availability.c.branch_id == self.branch_id,
                    ),
                )
            )
            .where(
                models.products.c.organization_id == self.organization_id,
                models.products.c.status == "active",
            )
            .order_by(models.product_categories.c.name, models.products.c.name)
        )

        rows = self.session.execute(query).mappings().all()
        items: list[dict[str, Any]] = []
        for row in rows:
            items.append(
                {
                    "id": str(row["id"]),
                    "name": str(row["name"]),
                    "description": str(row["description"] or ""),
                    "sku": str(row["sku"] or ""),
                    "category_name": str(row["category_name"] or "General"),
                    "price_cents": int(row["price_cents"] or 0),
                    "currency": str(row["currency"] or "MXN"),
                    "is_available": bool(row["is_available"]),
                }
            )
        return items
