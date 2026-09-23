"""Transactional commercial modifiers for the mobile product editor.

Never commits: product, options and audit share the caller's transaction.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from restaurant_os import models
from restaurant_os import operations as ops


def _state(
    session: Session,
    product_id: str,
    actor_id: str,
    *,
    lock: bool = False,
) -> tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, Any]], str, bool]:
    ops.require_permission(session, actor_id, "catalog.manage")
    org_id = ops._modifier_actor_organization(session, actor_id)
    query = sa.select(models.products).where(
        models.products.c.id == product_id,
        models.products.c.organization_id == org_id,
    )
    product_row = session.execute(query.with_for_update() if lock else query).mappings().first()
    if product_row is None:
        raise ops.BusinessError("product_not_found", "Product was not found")
    product = dict(product_row)
    group_query = sa.select(models.modifier_groups).where(
        models.modifier_groups.c.product_id == product_id,
        models.modifier_groups.c.organization_id == org_id,
        models.modifier_groups.c.name == "Extras",
    )
    group_row = (
        session.execute(group_query.with_for_update() if lock else group_query).mappings().first()
    )
    group = dict(group_row) if group_row else None
    options: list[dict[str, Any]] = []
    editable = True
    if group:
        option_query = (
            sa.select(models.modifier_options)
            .where(
                models.modifier_options.c.group_id == group["id"],
            )
            .order_by(models.modifier_options.c.display_order, models.modifier_options.c.id)
        )
        options = [
            dict(row)
            for row in session.execute(
                option_query.with_for_update() if lock else option_query
            ).mappings()
        ]
        active_count = sum(o["status"] == "active" for o in options)
        branch_override = session.execute(
            sa.select(models.branch_modifier_options.c.option_id)
            .join(
                models.modifier_options,
                models.modifier_options.c.id == models.branch_modifier_options.c.option_id,
            )
            .where(models.modifier_options.c.group_id == group["id"])
            .limit(1)
        ).first()
        editable = (
            not group["is_required"]
            and group["minimum_selections"] == 0
            and (not active_count or group["maximum_selections"] == active_count)
            and not ops._modifier_catalog_is_managed_elsewhere(session, group_id=group["id"])
            and branch_override is None
            and all(
                o["effect_type"] == "instruction"
                and not o["inventory_effect"]
                and not o["affected_item_id"]
                and not o["replacement_item_id"]
                and not o["remove_quantity"]
                and not o["add_quantity"]
                and o["kitchen_text"] == o["name"]
                and o["name"] == o["name"].strip()
                and not any(char in o["name"] for char in ",\r\n")
                and o["station"] == group["station"]
                and isinstance(o["price_delta_cents"], int)
                and o["price_delta_cents"] >= 0
                for o in options
            )
            and len({o["name"].casefold() for o in options}) == len(options)
        )
    prices = [
        dict(row)
        for row in session.execute(
            sa.select(models.price_versions)
            .where(
                models.price_versions.c.product_id == product_id,
                models.price_versions.c.organization_id == org_id,
                models.price_versions.c.valid_to.is_(None),
            )
            .order_by(models.price_versions.c.valid_from.desc(), models.price_versions.c.id.desc())
        ).mappings()
    ]
    product["price_cents"] = prices[0]["price_cents"] if prices else None
    product["category_name"] = (
        session.scalar(
            sa.select(models.product_categories.c.name).where(
                models.product_categories.c.id == product["category_id"],
                models.product_categories.c.organization_id == org_id,
            )
        )
        or ""
    )
    revision = hashlib.sha256(
        json.dumps(
            [product, prices, group, options],
            sort_keys=True,
            default=str,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    return product, group, options, revision, editable


def read_simple_modifiers(
    session: Session,
    product_id: str,
    actor_id: str,
) -> dict[str, Any]:
    product, group, options, revision, editable = _state(session, product_id, actor_id)
    return {
        "product": {
            key: product[key]
            for key in (
                "id",
                "name",
                "description",
                "sku",
                "category_name",
                "station",
                "price_cents",
                "image_url",
                "status",
                "is_promo",
                "promo_price_cents",
                "promo_badge_text",
            )
        },
        "revision": revision,
        "editable": editable,
        "options": [
            {"name": o["name"], "price_delta_cents": o["price_delta_cents"]}
            for o in options
            if o["status"] == "active" and group and group["status"] == "active"
        ]
        if editable
        else [],
    }


def _validate(payload: Any) -> list[dict[str, Any]]:
    invalid = ops.BusinessError(
        "invalid_simple_modifiers", "Revisa nombres únicos y precios enteros no negativos."
    )
    if not isinstance(payload, dict) or "expected_revision" not in payload:
        raise invalid
    options = payload.get("options")
    if not isinstance(options, list) or len(options) > 100:
        raise invalid
    normalized = []
    seen: set[str] = set()
    for option in options:
        if not isinstance(option, dict) or not isinstance(option.get("name"), str):
            raise invalid
        name = option["name"].strip()
        cents = option.get("price_delta_cents")
        if (
            not name
            or any(char in name for char in ",\r\n")
            or len(name) > 120
            or name.casefold() in seen
            or type(cents) is not int
            or not 0 <= cents <= 2147483647
        ):
            raise invalid
        seen.add(name.casefold())
        normalized.append({"name": name, "price_delta_cents": cents})
    return normalized


def save_simple_modifiers(
    session: Session,
    product_id: str,
    payload: Any,
    actor_id: str,
    *,
    creating: bool = False,
) -> None:
    desired = _validate(payload)
    product, group, options, revision, editable = _state(session, product_id, actor_id, lock=True)
    if not editable:
        raise ops.BusinessError(
            "simple_modifiers_managed_elsewhere",
            "Este grupo requiere el administrador avanzado de modificadores.",
        )
    if payload["expected_revision"] != (None if creating else revision):
        raise ops.BusinessError(
            "simple_modifiers_conflict",
            "El producto cambió. Vuelve a abrirlo antes de guardar.",
        )
    # SQLite ignores FOR UPDATE. Compare-and-swap also prevents two deferred
    # transactions from both committing the same revision on that dialect.
    now = ops._now()
    claimed = session.execute(
        models.products.update()
        .where(
            models.products.c.id == product_id,
            models.products.c.organization_id == product["organization_id"],
            models.products.c.updated_at == product["updated_at"],
        )
        .values(updated_at=now)
        .returning(models.products.c.id)
    )
    if claimed.scalar_one_or_none() is None:
        raise ops.BusinessError(
            "simple_modifiers_conflict", "El producto cambió. Vuelve a abrirlo antes de guardar."
        )
    current = [
        {"name": o["name"], "price_delta_cents": o["price_delta_cents"]}
        for o in options
        if o["status"] == "active" and group and group["status"] == "active"
    ]
    if current == desired:
        ops._audit(
            session,
            "product.simple_modifiers_saved",
            "product",
            product_id,
            {"group_id": group["id"] if group else None, "option_count": len(desired)},
            organization_id=product["organization_id"],
            actor_user_id=actor_id,
        )
        return
    if group is None:
        group = {
            "id": ops._id(),
            "organization_id": product["organization_id"],
            "product_id": product_id,
            "name": "Extras",
            "is_required": False,
            "minimum_selections": 0,
            "maximum_selections": max(1, len(desired)),
            "station": None,
            "display_order": 0,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        session.execute(models.modifier_groups.insert().values(**group))
    else:
        session.execute(
            models.modifier_groups.update()
            .where(
                models.modifier_groups.c.id == group["id"],
            )
            .values(
                maximum_selections=max(1, len(desired)),
                status="active" if desired else "inactive",
                updated_at=now,
            )
        )
    by_name = {o["name"].casefold(): o for o in options}
    desired_names = {o["name"].casefold() for o in desired}
    for option in options:
        if option["name"].casefold() not in desired_names and option["status"] == "active":
            session.execute(
                models.modifier_options.update()
                .where(
                    models.modifier_options.c.id == option["id"],
                )
                .values(status="inactive", updated_at=now)
            )
    for index, option in enumerate(desired):
        values = {
            **option,
            "kitchen_text": option["name"],
            "display_order": index,
            "status": "active",
            "updated_at": now,
        }
        existing = by_name.get(option["name"].casefold())
        if existing:
            session.execute(
                models.modifier_options.update()
                .where(
                    models.modifier_options.c.id == existing["id"],
                )
                .values(**values)
            )
        else:
            session.execute(
                models.modifier_options.insert().values(
                    **values,
                    id=ops._id(),
                    group_id=group["id"],
                    effect_type="instruction",
                    inventory_effect=False,
                    affected_item_id=None,
                    replacement_item_id=None,
                    remove_quantity=0,
                    add_quantity=0,
                    station=group["station"],
                    created_at=now,
                )
            )
    ops._audit(
        session,
        "product.simple_modifiers_saved",
        "product",
        product_id,
        {"group_id": group["id"], "option_count": len(desired)},
        organization_id=product["organization_id"],
        actor_user_id=actor_id,
    )
