"""Customer AI, CRM Segmentation, and Upsell Recommendations for RestaurantOS.

Predictive cross-selling, customer segmentation (VIP, At-Risk/Churn, New),
and personalized WhatsApp recovery messages. All money values in exact cents.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from restaurant_os import models
from restaurant_os.operations import ORGANIZATION_ID

UTC = timezone.utc
MIN_PAIR_ORDERS = 2

BEVERAGE_STATIONS = {"bar", "barra", "beverage", "bebidas", "drink", "drinks"}
FOOD_STATIONS = {"alimentos", "cocina", "food", "kitchen"}
BEVERAGE_CATEGORIES = {"agua", "aguas", "bebida", "bebidas", "cafe", "cafes", "jugo", "jugos"}
FOOD_CATEGORIES = {
    "alimento",
    "alimentos",
    "comida",
    "comidas",
    "ensalada",
    "ensaladas",
    "sando",
    "sandos",
}


def _normalize_catalog_label(value: Any) -> str:
    return (
        str(value or "")
        .strip()
        .casefold()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ü", "u")
    )


def _catalog_product_kind(product: dict[str, Any]) -> str | None:
    """Classify from canonical catalog fields; product names never grant a category."""
    station = _normalize_catalog_label(product.get("station"))
    if station in BEVERAGE_STATIONS:
        return "beverage"
    if station in FOOD_STATIONS:
        return "food"

    category = _normalize_catalog_label(product.get("category_name"))
    if category in BEVERAGE_CATEGORIES:
        return "beverage"
    if category in FOOD_CATEGORIES:
        return "food"
    return None


def _branch_catalog_products(session: Session, branch_id: str) -> list[dict[str, Any]]:
    branch_exists = session.scalar(
        sa.select(models.branches.c.id).where(
            models.branches.c.id == branch_id,
            models.branches.c.organization_id == ORGANIZATION_ID,
            models.branches.c.status == "active",
        )
    )
    if not branch_exists:
        return []

    # Local import avoids widening the operations/platform_data import cycle.
    from restaurant_os.platform_data import project_pos_catalog

    _, products = project_pos_catalog(session, branch_id)
    return [dict(product) for product in products]


def _branch_upsell_recommendations(
    session: Session,
    branch_id: str,
    current_product_ids: list[str] | None,
) -> list[dict[str, Any]]:
    current_ids = set(current_product_ids or [])
    if not current_ids:
        return []

    catalog_products = _branch_catalog_products(session, branch_id)
    products_by_id = {str(product["id"]): product for product in catalog_products}
    if not current_ids.issubset(products_by_id):
        return []

    cart_kinds = {_catalog_product_kind(products_by_id[product_id]) for product_id in current_ids}
    if None in cart_kinds or not cart_kinds:
        return []

    mixed_cart = cart_kinds == {"beverage", "food"}
    target_kind: str | None = None
    if cart_kinds == {"food"}:
        target_kind = "beverage"
    elif cart_kinds == {"beverage"}:
        target_kind = "food"
    elif not mixed_cart:
        return []

    candidate_ids = {
        product_id
        for product_id, product in products_by_id.items()
        if product_id not in current_ids
        and _catalog_product_kind(product) in {"beverage", "food"}
        and (target_kind is None or _catalog_product_kind(product) == target_kind)
    }
    if not candidate_ids:
        return []

    recommendations: list[dict[str, Any]] = []
    seen_ids = set(current_ids)
    l1 = models.order_lines.alias("upsell_cart_line")
    l2 = models.order_lines.alias("upsell_candidate_line")
    pair_count = sa.func.count(sa.distinct(l2.c.order_id)).label("pair_count")
    paired_rows = session.execute(
        sa.select(l2.c.product_id, pair_count)
        .select_from(
            l1.join(
                l2,
                sa.and_(l1.c.order_id == l2.c.order_id, l1.c.product_id != l2.c.product_id),
            ).join(models.orders, l1.c.order_id == models.orders.c.id)
        )
        .where(
            models.orders.c.organization_id == ORGANIZATION_ID,
            models.orders.c.branch_id == branch_id,
            models.orders.c.status != "cancelled",
            l1.c.product_id.in_(sorted(current_ids)),
            l1.c.status == "active",
            l1.c.removed_at.is_(None),
            l2.c.product_id.in_(sorted(candidate_ids)),
            l2.c.status == "active",
            l2.c.removed_at.is_(None),
        )
        .group_by(l2.c.product_id)
        .having(sa.func.count(sa.distinct(l2.c.order_id)) >= MIN_PAIR_ORDERS)
        .order_by(sa.desc(pair_count), l2.c.product_id)
        .limit(20)
    ).mappings()

    for row in paired_rows:
        product_id = str(row["product_id"])
        product = products_by_id[product_id]
        recommendations.append(
            {
                "product_id": product_id,
                "product_name": str(product["name"]),
                "price_cents": int(product["price_cents"]),
                "reason": (
                    f"Frecuentemente pedido con tu selección ({int(row['pair_count'])} pedidos)"
                ),
                "confidence_score": 0.92,
                "source": "co_occurrence",
            }
        )
        seen_ids.add(product_id)
        if len(recommendations) >= 4:
            return recommendations

    # A mixed cart only accepts direct pair evidence; generic popularity is not contextual enough.
    if mixed_cart:
        return recommendations

    remaining_ids = candidate_ids - seen_ids
    if not remaining_ids:
        return recommendations

    popularity_count = sa.func.count(sa.distinct(models.order_lines.c.order_id)).label(
        "popularity_count"
    )
    popular_rows = session.execute(
        sa.select(models.order_lines.c.product_id, popularity_count)
        .select_from(
            models.order_lines.join(
                models.orders, models.order_lines.c.order_id == models.orders.c.id
            )
        )
        .where(
            models.orders.c.organization_id == ORGANIZATION_ID,
            models.orders.c.branch_id == branch_id,
            models.orders.c.status != "cancelled",
            models.order_lines.c.product_id.in_(sorted(remaining_ids)),
            models.order_lines.c.status == "active",
            models.order_lines.c.removed_at.is_(None),
        )
        .group_by(models.order_lines.c.product_id)
        .order_by(sa.desc(popularity_count), models.order_lines.c.product_id)
        .limit(4 - len(recommendations))
    ).mappings()

    for row in popular_rows:
        product_id = str(row["product_id"])
        product = products_by_id[product_id]
        recommendations.append(
            {
                "product_id": product_id,
                "product_name": str(product["name"]),
                "price_cents": int(product["price_cents"]),
                "reason": f"Popular en esta sucursal ({int(row['popularity_count'])} pedidos)",
                "confidence_score": 0.80,
                "source": "branch_popularity",
            }
        )
    return recommendations


def _is_beverage(name: str) -> bool:
    n = name.lower()
    return any(
        w in n
        for w in (
            "jugo",
            "café",
            "cafe",
            "maccha",
            "matcha",
            "smoothie",
            "agua",
            "extracto",
            "licuado",
            "bebida",
            "drink",
            "té",
            "te",
            "latte",
            "soda",
            "infusion",
            "infusión",
            "frappé",
            "frappe",
        )
    )


def get_customer_upsell_recommendations(
    session: Session,
    customer_id: str | None = None,
    current_product_ids: list[str] | None = None,
    branch_id: str | None = None,
) -> list[dict[str, Any]]:
    """Dispatch branch-scoped mobile requests without changing the legacy admin recommender."""
    if branch_id:
        return _branch_upsell_recommendations(session, branch_id, current_product_ids)
    return _get_legacy_customer_upsell_recommendations(
        session,
        customer_id=customer_id,
        current_product_ids=current_product_ids,
    )


def _get_legacy_customer_upsell_recommendations(
    session: Session,
    customer_id: str | None = None,
    current_product_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Compute legacy suggestions from cart co-occurrences and cross-category pairing."""
    current_ids = set(current_product_ids or [])
    recommendations: list[dict[str, Any]] = []
    seen_ids = set(current_ids)

    # Helper to get price for a product
    def _get_price(product_id: str) -> int:
        price_row = session.execute(
            sa.select(models.price_versions.c.price_cents)
            .where(
                models.price_versions.c.product_id == product_id,
                models.price_versions.c.valid_to.is_(None),
            )
            .order_by(models.price_versions.c.created_at.desc())
            .limit(1)
        ).scalar()
        return int(price_row or 8500)

    # Fetch all active catalog products
    all_active_products = list(
        session.execute(
            sa.select(models.products).where(
                models.products.c.organization_id == ORGANIZATION_ID,
                models.products.c.status == "active",
            )
        ).mappings()
    )

    # Detect what is currently in the cart
    cart_prods = [
        p
        for p in all_active_products
        if str(p["id"]) in current_ids or str(p.get("sku", "")) in current_ids
    ]
    has_beverage = any(_is_beverage(str(p["name"])) for p in cart_prods)
    has_food = any(not _is_beverage(str(p["name"])) for p in cart_prods)

    # 1. Historical Co-Occurrences in same orders (Products frequently bought together)
    if current_ids:
        try:
            l1 = models.order_lines.alias("l1")
            l2 = models.order_lines.alias("l2")
            o = models.orders

            co_occurrences = list(
                session.execute(
                    sa.select(
                        l2.c.product_id,
                        l2.c.product_name,
                        sa.func.count(sa.distinct(l2.c.order_id)).label("pair_count"),
                    )
                    .select_from(
                        l1.join(
                            l2,
                            sa.and_(
                                l1.c.order_id == l2.c.order_id,
                                l1.c.product_id != l2.c.product_id,
                            ),
                        ).join(o, l1.c.order_id == o.c.id)
                    )
                    .where(
                        o.c.organization_id == ORGANIZATION_ID,
                        o.c.status != "cancelled",
                        l1.c.product_id.in_(list(current_ids)),
                    )
                    .group_by(l2.c.product_id, l2.c.product_name)
                    .order_by(sa.desc("pair_count"))
                    .limit(10)
                ).mappings()
            )

            # A single-category cart prefers co-occurrences from the opposite category.
            for row in co_occurrences:
                pid = str(row["product_id"])
                pname = str(row["product_name"])
                is_bev = _is_beverage(pname)

                # Skip same-category repetition if single-category cart
                if has_beverage and not has_food and is_bev:
                    continue
                if has_food and not has_beverage and not is_bev:
                    continue

                if pid not in seen_ids:
                    prod = (
                        session.execute(
                            sa.select(models.products).where(
                                models.products.c.id == pid,
                                models.products.c.status == "active",
                            )
                        )
                        .mappings()
                        .one_or_none()
                    )
                    if prod:
                        recommendations.append(
                            {
                                "product_id": pid,
                                "product_name": str(prod["name"]),
                                "price_cents": _get_price(pid),
                                "reason": (
                                    "Frecuentemente pedido junto "
                                    f"({row['pair_count']} clientes)"
                                ),
                                "confidence_score": 0.92,
                            }
                        )
                        seen_ids.add(pid)
                        if len(recommendations) >= 2:
                            break
        except Exception:
            pass

    # 2. Customer Personal History (if customer_id provided)
    if customer_id and len(recommendations) < 4:
        past_products = list(
            session.execute(
                sa.select(
                    models.order_lines.c.product_id,
                    models.order_lines.c.product_name,
                    sa.func.count(models.order_lines.c.id).label("times_ordered"),
                )
                .select_from(
                    models.order_lines.join(
                        models.orders,
                        models.order_lines.c.order_id == models.orders.c.id,
                    )
                )
                .where(
                    models.orders.c.organization_id == ORGANIZATION_ID,
                    models.orders.c.customer_id == customer_id,
                    models.orders.c.status != "cancelled",
                )
                .group_by(models.order_lines.c.product_id, models.order_lines.c.product_name)
                .order_by(sa.desc("times_ordered"))
            ).mappings()
        )

        for pp in past_products:
            pid = str(pp["product_id"])
            if pid not in seen_ids:
                prod = (
                    session.execute(
                        sa.select(models.products).where(
                            models.products.c.id == pid,
                            models.products.c.status == "active",
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if prod:
                    recommendations.append(
                        {
                            "product_id": pid,
                            "product_name": str(prod["name"]),
                            "price_cents": _get_price(pid),
                            "reason": (
                                "Favorito habitual del cliente "
                                f"(pedido {pp['times_ordered']} veces)"
                            ),
                            "confidence_score": 0.95,
                        }
                    )
                    seen_ids.add(pid)
                    if len(recommendations) >= 4:
                        break

    # 3. Dynamic Cross-Category Pairing (Food if beverage-only; Beverage if food-only)
    if len(recommendations) < 4:
        # Case A: Cart has ONLY beverages -> Recommend FOOD / BAKERY / SANDOS
        if has_beverage and not has_food:
            food_candidates = [
                p
                for p in all_active_products
                if str(p["id"]) not in seen_ids and not _is_beverage(str(p["name"]))
            ]
            for prod in food_candidates:
                pid = str(prod["id"])
                recommendations.append(
                    {
                        "product_id": pid,
                        "product_name": str(prod["name"]),
                        "price_cents": _get_price(pid),
                        "reason": "Combina perfecto con tu bebida ⭐",
                        "confidence_score": 0.90,
                    }
                )
                seen_ids.add(pid)
                if len(recommendations) >= 4:
                    break

        # Case B: Cart has ONLY food (or no beverages) -> Recommend BEVERAGES / JUICES / SMOOTHIES
        elif not has_beverage:
            drink_candidates = [
                p
                for p in all_active_products
                if str(p["id"]) not in seen_ids and _is_beverage(str(p["name"]))
            ]
            for prod in drink_candidates:
                pid = str(prod["id"])
                recommendations.append(
                    {
                        "product_id": pid,
                        "product_name": str(prod["name"]),
                        "price_cents": _get_price(pid),
                        "reason": "¿Acompañas con una bebida fresca? 🥤",
                        "confidence_score": 0.90,
                    }
                )
                seen_ids.add(pid)
                if len(recommendations) >= 4:
                    break

        # Case C: General House Favorites for remaining slots
        for prod in all_active_products:
            pid = str(prod["id"])
            if pid not in seen_ids:
                is_bev = _is_beverage(str(prod["name"]))
                reason = "Favorito de nuestros clientes ⭐"
                if is_bev and not has_beverage:
                    reason = "¿Acompañas con una bebida fresca? 🥤"
                elif not is_bev and has_beverage:
                    reason = "Combina perfecto con tu bebida ⭐"

                recommendations.append(
                    {
                        "product_id": pid,
                        "product_name": str(prod["name"]),
                        "price_cents": _get_price(pid),
                        "reason": reason,
                        "confidence_score": 0.85,
                    }
                )
                seen_ids.add(pid)
                if len(recommendations) >= 4:
                    break

    return recommendations


def get_crm_segments_and_churn_risk(
    session: Session,
    branch_id: str | None = None,
) -> dict[str, Any]:
    """Segment customers into VIPs, churn risk, and new customers with metrics."""
    criteria = [models.customers.c.organization_id == ORGANIZATION_ID]
    if branch_id:
        criteria.append(models.customers.c.origin_branch_id == branch_id)

    customers_list = list(session.execute(sa.select(models.customers).where(*criteria)).mappings())

    now = datetime.now(UTC)
    vips: list[dict[str, Any]] = []
    churn_risk: list[dict[str, Any]] = []
    new_customers: list[dict[str, Any]] = []

    for cust in customers_list:
        cid = str(cust["id"])

        # Aggregate total orders and total spend in exact cents
        orders = list(
            session.execute(
                sa.select(
                    models.orders.c.id,
                    models.orders.c.total_cents,
                    models.orders.c.created_at,
                ).where(
                    models.orders.c.customer_id == cid,
                    models.orders.c.status != "cancelled",
                )
            ).mappings()
        )

        total_orders = len(orders)
        total_spend_cents = sum(int(o["total_cents"] or 0) for o in orders)

        last_order_dt: datetime | None = None
        if orders:
            order_dates = [o["created_at"] for o in orders if o["created_at"]]
            if order_dates:
                last_order_dt = max(order_dates)

        days_inactive = (now - last_order_dt).days if last_order_dt else 999

        customer_summary = {
            "id": cid,
            "name": f"{cust.get('first_name', '')} {cust.get('last_name', '')}".strip()
            or "Cliente Frecuente",
            "phone": cust.get("phone") or "",
            "total_orders": total_orders,
            "total_spend_cents": total_spend_cents,
            "last_order_date": last_order_dt.isoformat() if last_order_dt else None,
            "days_inactive": days_inactive,
        }

        # Segmentation Rules:
        # VIP: >= 3 orders or spend >= $500.00 MXN (50,000 cents)
        if total_orders >= 3 or total_spend_cents >= 50000:
            vips.append(customer_summary)
        # Churn Risk: > 30 days inactive with at least 1 past order
        if days_inactive >= 30 and total_orders > 0:
            churn_risk.append(customer_summary)
        # New: 1 order within last 14 days
        if total_orders <= 1 and days_inactive <= 14:
            new_customers.append(customer_summary)

    # Sort each list
    vips.sort(key=lambda x: x["total_spend_cents"], reverse=True)
    churn_risk.sort(key=lambda x: x["days_inactive"], reverse=True)
    new_customers.sort(key=lambda x: x["last_order_date"] or "", reverse=True)

    return {
        "summary": {
            "total_customers": len(customers_list),
            "vip_count": len(vips),
            "churn_risk_count": len(churn_risk),
            "new_count": len(new_customers),
        },
        "vips": vips[:15],
        "vip_customers": vips[:15],
        "churn_risk": churn_risk[:15],
        "churn_risk_customers": churn_risk[:15],
        "new_customers": new_customers[:15],
    }


def generate_churn_recovery_message(
    session: Session | None = None,
    customer_id: str | None = None,
    customer_name: str | None = None,
    favorite_product_name: str | None = None,
    discount_code: str | None = "VUELVE10",
    restaurant_name: str | None = None,
) -> str:
    """Generate a personalized WhatsApp re-engagement message highlighting customer favorites."""
    name = customer_name
    fav_product = favorite_product_name
    code = discount_code or "VUELVE10"

    if session and customer_id and not name:
        cust = (
            session.execute(sa.select(models.customers).where(models.customers.c.id == customer_id))
            .mappings()
            .one_or_none()
        )
        if cust:
            name = cust.get("first_name") or "amigo"

        fav_row = (
            session.execute(
                sa.select(
                    models.order_lines.c.product_name,
                    sa.func.count(models.order_lines.c.id).label("cnt"),
                )
                .select_from(
                    models.order_lines.join(
                        models.orders,
                        models.order_lines.c.order_id == models.orders.c.id,
                    )
                )
                .where(
                    models.orders.c.customer_id == customer_id,
                    models.orders.c.status != "cancelled",
                )
                .group_by(models.order_lines.c.product_name)
                .order_by(sa.desc("cnt"))
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        if fav_row:
            fav_product = fav_row["product_name"]

    name = name or "amigo"
    fav_product = fav_product or "tu favorito de siempre"
    brand = restaurant_name or "tu restaurante favorito"

    return (
        f"¡Hola {name}! 👋 En {brand} te extrañamos. Hace tiempo que no disfrutamos de "
        f"prepararte {fav_product}. ✨ Hoy te regalamos 10% de descuento con el código "
        f"{code} en tu próxima visita o pedido directo. ¿Te lo preparamos?"
    )
