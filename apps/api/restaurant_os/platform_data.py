from __future__ import annotations

# ruff: noqa: E501, E402
import logging
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from restaurant_os import models
from restaurant_os.operations import ORGANIZATION_ID, BusinessError

logger = logging.getLogger(__name__)


def list_organizations(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(
        sa.select(
            models.organizations.c.id,
            models.organizations.c.name,
            models.organizations.c.status,
            models.organizations.c.created_at,
        ).order_by(models.organizations.c.name)
    ).mappings()

    return [dict(row) for row in rows]


def list_business_units(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(
        sa.select(
            models.business_units.c.id,
            models.business_units.c.legal_entity_id,
            models.business_units.c.name,
            models.business_units.c.code,
            models.business_units.c.unit_type,
            models.business_units.c.status,
            models.legal_entities.c.name.label("legal_entity_name"),
        )
        .select_from(
            models.business_units.join(
                models.legal_entities,
                models.business_units.c.legal_entity_id == models.legal_entities.c.id,
            )
        )
        .where(models.business_units.c.organization_id == ORGANIZATION_ID)
        .order_by(models.business_units.c.name)
    ).mappings()
    return [dict(row) for row in rows]


def list_branches(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(
        sa.select(
            models.branches.c.id,
            models.branches.c.name,
            models.branches.c.code,
            models.branches.c.timezone,
            models.branches.c.status,
            models.branches.c.business_unit_id,
            models.branches.c.street,
            models.branches.c.exterior_number,
            models.branches.c.interior_number,
            models.branches.c.neighborhood,
            models.branches.c.postal_code,
            models.branches.c.city,
            models.branches.c.state,
            models.branches.c.cross_streets,
            models.branches.c.latitude,
            models.branches.c.longitude,
            models.branches.c.phone,
            models.branches.c.google_review_url,
            models.business_units.c.name.label("business_unit_name"),
            models.business_units.c.unit_type.label("business_unit_type"),
            models.legal_entities.c.name.label("legal_entity_name"),
            models.warehouses.c.name.label("warehouse_name"),
        )
        .select_from(
            models.branches.join(
                models.legal_entities,
                models.branches.c.legal_entity_id == models.legal_entities.c.id,
            )
            .join(
                models.business_units,
                models.branches.c.business_unit_id == models.business_units.c.id,
            )
            .join(models.warehouses, models.branches.c.id == models.warehouses.c.branch_id)
        )
        .where(models.branches.c.organization_id == ORGANIZATION_ID)
        .order_by(models.branches.c.name)
    ).mappings()

    result = []
    for row in rows:
        item = dict(row)
        if item.get("latitude") is not None:
            item["latitude"] = float(item["latitude"])
        if item.get("longitude") is not None:
            item["longitude"] = float(item["longitude"])
        result.append(item)
    return result


def list_roles(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(
        sa.select(
            models.roles.c.id,
            models.roles.c.name,
            models.roles.c.scope,
            models.roles.c.created_at,
        )
        .where(models.roles.c.organization_id == ORGANIZATION_ID)
        .order_by(models.roles.c.name)
    ).mappings()

    roles_by_id = {row["id"]: {**dict(row), "permissions": []} for row in rows}
    if not roles_by_id:
        return []

    permission_rows = session.execute(
        sa.select(
            models.role_permissions.c.role_id,
            models.permissions.c.code,
        )
        .select_from(
            models.role_permissions.join(
                models.permissions,
                models.role_permissions.c.permission_id == models.permissions.c.id,
            )
        )
        .where(models.role_permissions.c.role_id.in_(roles_by_id.keys()))
        .order_by(models.permissions.c.code)
    ).mappings()
    for row in permission_rows:
        roles_by_id[row["role_id"]]["permissions"].append(row["code"])

    return list(roles_by_id.values())


def list_users(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(
        sa.select(
            models.users.c.id,
            models.users.c.email,
            models.users.c.display_name,
            models.users.c.employee_code,
            models.users.c.status,
            models.users.c.created_at,
        )
        .where(models.users.c.organization_id == ORGANIZATION_ID)
        .order_by(models.users.c.display_name)
    ).mappings()
    users_by_id = {row["id"]: {**dict(row), "roles": []} for row in rows}
    if not users_by_id:
        return []

    role_rows = session.execute(
        sa.select(
            models.user_roles.c.user_id,
            models.user_roles.c.branch_id,
            models.roles.c.id.label("role_id"),
            models.roles.c.name.label("role_name"),
            models.roles.c.scope,
            models.branches.c.name.label("branch_name"),
        )
        .select_from(
            models.user_roles.join(
                models.roles,
                models.user_roles.c.role_id == models.roles.c.id,
            ).outerjoin(models.branches, models.user_roles.c.branch_id == models.branches.c.id)
        )
        .where(models.user_roles.c.user_id.in_(users_by_id.keys()))
        .order_by(models.roles.c.name)
    ).mappings()
    for row in role_rows:
        users_by_id[row["user_id"]]["roles"].append(
            {
                "role_id": row["role_id"],
                "role_name": row["role_name"],
                "scope": row["scope"],
                "branch_id": row["branch_id"],
                "branch_name": row["branch_name"],
            }
        )

    return list(users_by_id.values())


def _list_catalog_products_base(
    session: Session,
    branch_id: str | None = None,
    organization_id: str | None = None,
) -> list[dict[str, Any]]:
    org_id = organization_id
    if branch_id and not org_id:
        branch_org = session.execute(
            sa.select(models.branches.c.organization_id).where(models.branches.c.id == branch_id)
        ).scalar()
        if branch_org:
            org_id = str(branch_org)
    if not org_id:
        org_id = ORGANIZATION_ID

    active_price = (
        sa.select(
            models.price_versions.c.product_id,
            models.price_versions.c.price_cents,
            models.price_versions.c.currency,
        )
        .where(models.price_versions.c.valid_to.is_(None))
        .subquery()
    )

    query = sa.select(
        models.products.c.id,
        models.products.c.name,
        models.products.c.sku,
        models.products.c.description,
        models.products.c.station,
        models.products.c.status,
        models.products.c.image_url,
        models.products.c.catalog_scope,
        models.products.c.source_branch_id,
        models.products.c.category_id,
        models.products.c.delivery_price_cents,
        models.product_categories.c.name.label("category_name"),
        active_price.c.price_cents,
        active_price.c.currency,
    )

    if branch_id:
        query = (
            query.add_columns(
                sa.func.coalesce(models.branch_product_availability.c.is_available, True).label(
                    "is_available"
                )
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
                sa.or_(
                    models.products.c.catalog_scope == "organization",
                    models.products.c.source_branch_id == branch_id,
                ),
                sa.func.coalesce(models.branch_product_availability.c.is_available, True).is_(True),
            )
        )
    else:
        query = (
            query.add_columns(
                sa.func.coalesce(
                    sa.select(models.branch_product_availability.c.is_available)
                    .where(models.branch_product_availability.c.product_id == models.products.c.id)
                    .limit(1)
                    .scalar_subquery(),
                    True,
                ).label("is_available")
            )
            .select_from(
                models.products.join(
                    models.product_categories,
                    models.products.c.category_id == models.product_categories.c.id,
                ).outerjoin(active_price, models.products.c.id == active_price.c.product_id)
            )
            .where(
                models.products.c.organization_id == org_id,
                models.products.c.status != "archived",
            )
        )

    rows = session.execute(
        query.order_by(models.product_categories.c.name, models.products.c.name)
    ).mappings()

    return [{**dict(row), "is_available": bool(row.get("is_available", True))} for row in rows]


def project_pos_catalog(
    session: Session, branch_id: str, organization_id: str | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        return _project_pos_catalog(session, branch_id, organization_id=organization_id)
    except Exception:
        logger.exception("category_option_projection_error", extra={"branch_id": branch_id})
        raise


def _project_pos_catalog(
    session: Session, branch_id: str, organization_id: str | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return one fail-closed source for POS categories and concrete products."""
    org_id = organization_id
    if not org_id:
        branch_org = session.execute(
            sa.select(models.branches.c.organization_id).where(models.branches.c.id == branch_id)
        ).scalar()
        if branch_org:
            org_id = str(branch_org)
    if not org_id:
        org_id = ORGANIZATION_ID

    base_products = _list_catalog_products_base(session, branch_id, organization_id=org_id)
    eligible = {
        product["id"]: product
        for product in base_products
        if product["status"] == "active"
        and product["is_available"]
        and isinstance(product.get("price_cents"), int)
        and product["price_cents"] > 0
    }
    groups = (
        session.execute(
            sa.select(models.category_option_groups).where(
                models.category_option_groups.c.organization_id == org_id,
                models.category_option_groups.c.status == "active",
            )
        )
        .mappings()
        .all()
    )
    groups_by_category = {row["category_id"]: dict(row) for row in groups}
    group_ids = [row["id"] for row in groups]
    values_by_group: dict[str, list[dict[str, Any]]] = {group_id: [] for group_id in group_ids}
    assignments: dict[tuple[str, str], str] = {}
    if group_ids:
        value_rows = (
            session.execute(
                sa.select(models.category_option_values).where(
                    models.category_option_values.c.group_id.in_(group_ids),
                    models.category_option_values.c.status == "active",
                )
            )
            .mappings()
            .all()
        )
        active_value_ids = {row["id"] for row in value_rows}
        for value in value_rows:
            values_by_group[value["group_id"]].append(dict(value))
        assignment_rows = (
            session.execute(
                sa.select(models.product_option_value_assignments).where(
                    models.product_option_value_assignments.c.group_id.in_(group_ids),
                    models.product_option_value_assignments.c.option_value_id.in_(active_value_ids),
                )
            )
            .mappings()
            .all()
        )
        assignments = {
            (row["product_id"], row["group_id"]): row["option_value_id"] for row in assignment_rows
        }

    products: list[dict[str, Any]] = []
    eligible_value_ids: dict[str, set[str]] = {group_id: set() for group_id in group_ids}
    for product in eligible.values():
        group = groups_by_category.get(product["category_id"])
        if not group:
            products.append({**product, "selection": None})
            continue
        value_id = assignments.get((product["id"], group["id"]))
        if not value_id:
            logger.warning(
                "category_option_projection_incomplete",
                extra={"category_id": group["category_id"], "group_id": group["id"]},
            )
            continue
        selected_value = next(
            (item for item in values_by_group[group["id"]] if item["id"] == value_id), None
        )
        if not selected_value:
            logger.warning(
                "category_option_projection_incomplete",
                extra={"category_id": group["category_id"], "group_id": group["id"]},
            )
            continue
        eligible_value_ids[group["id"]].add(value_id)
        products.append(
            {
                **product,
                "selection": {
                    "group_id": group["id"],
                    "group_code": group["code"],
                    "group_name": group["name"],
                    "value_id": selected_value["id"],
                    "value_code": selected_value["code"],
                    "value_name": selected_value["name"],
                    "value_display_order": selected_value["display_order"],
                },
            }
        )

    categories: list[dict[str, Any]] = []
    category_rows = (
        session.execute(
            sa.select(models.product_categories)
            .where(
                models.product_categories.c.organization_id == ORGANIZATION_ID,
                models.product_categories.c.status != "archived",
            )
            .order_by(models.product_categories.c.display_order, models.product_categories.c.name)
        )
        .mappings()
        .all()
    )
    for category in category_rows:
        group = groups_by_category.get(category["id"])
        selection_group = None
        if group:
            selection_group = {
                "id": group["id"],
                "code": group["code"],
                "name": group["name"],
                "selection_mode": "single",
                "is_required": True,
                "values": [
                    {
                        "id": value["id"],
                        "code": value["code"],
                        "name": value["name"],
                        "display_order": value["display_order"],
                    }
                    for value in sorted(
                        values_by_group[group["id"]],
                        key=lambda item: (item["display_order"], item["name"], item["id"]),
                    )
                    if value["id"] in eligible_value_ids[group["id"]]
                ],
            }
        categories.append(
            {
                "id": category["id"],
                "name": category["name"],
                "display_order": category["display_order"],
                "status": category["status"],
                "created_at": category["created_at"].isoformat()
                if category["created_at"]
                else None,
                "selection_group": selection_group,
            }
        )
    return categories, products


def list_catalog_products(
    session: Session,
    branch_id: str | None = None,
    organization_id: str | None = None,
) -> list[dict[str, Any]]:
    if branch_id:
        return project_pos_catalog(session, branch_id, organization_id=organization_id)[1]
    return [
        {**product, "selection": None}
        for product in _list_catalog_products_base(session, organization_id=organization_id)
    ]


def list_inventory_stock(
    session: Session,
    branch_id: str | None = None,
) -> list[dict[str, Any]]:
    stock_query = sa.select(
        models.inventory_movements.c.item_id,
        models.inventory_movements.c.warehouse_id,
        sa.func.sum(models.inventory_movements.c.quantity_delta).label("quantity_on_hand"),
        sa.func.max(models.inventory_movements.c.created_at).label("last_movement_at"),
    ).group_by(
        models.inventory_movements.c.item_id,
        models.inventory_movements.c.warehouse_id,
    )
    if branch_id:
        stock_query = stock_query.where(models.inventory_movements.c.branch_id == branch_id)
    stock = stock_query.subquery()

    columns = (
        models.inventory_items.c.id,
        models.inventory_items.c.name,
        models.inventory_items.c.sku,
        models.inventory_items.c.item_type,
        models.inventory_units.c.code.label("unit_code"),
        models.inventory_units.c.name.label("unit_name"),
        models.warehouses.c.id.label("warehouse_id"),
        models.warehouses.c.name.label("warehouse_name"),
        models.branches.c.id.label("branch_id"),
        models.branches.c.name.label("branch_name"),
        stock.c.quantity_on_hand,
        stock.c.last_movement_at,
        models.inventory_cost_states.c.average_unit_cost,
        models.inventory_cost_states.c.last_unit_cost,
        models.inventory_cost_states.c.last_cost_at,
    )
    item_units = models.inventory_items.join(
        models.inventory_units,
        models.inventory_items.c.base_unit_id == models.inventory_units.c.id,
    )
    if branch_id:
        source = (
            item_units.join(models.warehouses, models.warehouses.c.branch_id == branch_id)
            .join(models.branches, models.warehouses.c.branch_id == models.branches.c.id)
            .outerjoin(
                stock,
                sa.and_(
                    models.inventory_items.c.id == stock.c.item_id,
                    models.warehouses.c.id == stock.c.warehouse_id,
                ),
            )
            .outerjoin(
                models.inventory_cost_states,
                sa.and_(
                    models.inventory_cost_states.c.item_id == models.inventory_items.c.id,
                    models.inventory_cost_states.c.warehouse_id == models.warehouses.c.id,
                    models.inventory_cost_states.c.branch_id == branch_id,
                ),
            )
        )
    else:
        source = (
            item_units.outerjoin(stock, models.inventory_items.c.id == stock.c.item_id)
            .outerjoin(models.warehouses, stock.c.warehouse_id == models.warehouses.c.id)
            .outerjoin(models.branches, models.warehouses.c.branch_id == models.branches.c.id)
            .outerjoin(
                models.inventory_cost_states,
                sa.and_(
                    models.inventory_cost_states.c.item_id == models.inventory_items.c.id,
                    models.inventory_cost_states.c.warehouse_id == stock.c.warehouse_id,
                ),
            )
        )

    query = (
        sa.select(*columns)
        .select_from(source)
        .where(
            models.inventory_items.c.organization_id == ORGANIZATION_ID,
            models.inventory_items.c.status == "active",
        )
    )
    if branch_id:
        query = query.where(
            sa.or_(
                models.inventory_items.c.catalog_scope == "organization",
                models.inventory_items.c.source_branch_id == branch_id,
            )
        )
    rows = session.execute(query.order_by(models.inventory_items.c.name)).mappings()

    return [
        {
            **dict(row),
            "quantity_on_hand": _exact_quantity_json(row["quantity_on_hand"] or 0),
        }
        for row in rows
    ]


def list_inventory_kardex(
    session: Session,
    item_id: str | None = None,
    branch_id: str | None = None,
) -> list[dict[str, Any]]:
    query = (
        sa.select(
            models.inventory_movements.c.id,
            models.inventory_movements.c.branch_id,
            models.inventory_movements.c.item_id.label("item_id"),
            models.inventory_items.c.name.label("item_name"),
            models.inventory_items.c.sku,
            models.inventory_movements.c.movement_type,
            models.inventory_movements.c.quantity_delta,
            models.inventory_movements.c.unit_cost,
            models.inventory_movements.c.total_cost,
            models.inventory_movements.c.effective_at,
            models.inventory_movements.c.actor_user_id,
            models.inventory_movements.c.document_type,
            models.inventory_movements.c.document_id,
            models.inventory_movements.c.reference,
            models.inventory_units.c.code.label("unit_code"),
            models.warehouses.c.name.label("warehouse_name"),
            models.inventory_movements.c.reason,
            models.inventory_movements.c.source_type,
            models.inventory_movements.c.idempotency_key,
            models.inventory_movements.c.status,
            models.inventory_movements.c.reversal_of_id,
            models.inventory_movements.c.created_at,
        )
        .select_from(
            models.inventory_movements.join(
                models.inventory_items,
                models.inventory_movements.c.item_id == models.inventory_items.c.id,
            )
            .join(
                models.inventory_units,
                models.inventory_movements.c.unit_id == models.inventory_units.c.id,
            )
            .join(
                models.warehouses,
                models.inventory_movements.c.warehouse_id == models.warehouses.c.id,
            )
        )
        .order_by(
            models.inventory_movements.c.created_at.desc(),
            models.inventory_movements.c.id.desc(),
        )
        .limit(80)
    )
    if item_id:
        query = query.where(models.inventory_movements.c.item_id == item_id)
    if branch_id:
        query = query.where(
            models.inventory_movements.c.branch_id == branch_id,
            sa.or_(
                models.inventory_items.c.catalog_scope == "organization",
                models.inventory_items.c.source_branch_id == branch_id,
            ),
        )

    return [
        {**dict(row), "quantity_delta": _exact_quantity_json(row["quantity_delta"])}
        for row in session.execute(query).mappings()
    ]


def _exact_quantity_json(value: Any) -> int | str:
    decimal_value = Decimal(str(value))
    if decimal_value == decimal_value.to_integral_value():
        return int(decimal_value)
    return format(decimal_value, "f")


def list_active_recipes(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(
        sa.select(
            models.recipes.c.id,
            models.recipes.c.product_id,
            models.recipes.c.output_item_id,
            models.recipes.c.branch_id,
            models.recipes.c.recipe_type,
            models.products.c.name.label("product_name"),
            models.products.c.sku.label("product_sku"),
            models.inventory_items.c.name.label("output_item_name"),
            models.inventory_items.c.sku.label("output_item_sku"),
            models.recipes.c.version,
            models.recipes.c.status,
            models.recipes.c.yield_quantity,
            models.recipes.c.yield_unit_id,
            models.inventory_units.c.code.label("yield_unit_code"),
            models.recipes.c.valid_from,
            models.recipes.c.created_at,
        )
        .select_from(
            models.recipes.outerjoin(
                models.products,
                models.recipes.c.product_id == models.products.c.id,
            )
            .outerjoin(
                models.inventory_items,
                models.recipes.c.output_item_id == models.inventory_items.c.id,
            )
            .join(
                models.inventory_units,
                models.recipes.c.yield_unit_id == models.inventory_units.c.id,
            )
        )
        .where(models.recipes.c.status == "active")
        .order_by(sa.func.coalesce(models.products.c.name, models.inventory_items.c.name))
    ).mappings()
    recipes_by_id = {
        row["id"]: {
            **dict(row),
            "yield_quantity": _exact_quantity_json(row["yield_quantity"]),
            "components": [],
            "latest_cost": None,
        }
        for row in rows
    }
    if not recipes_by_id:
        return []

    component_rows = session.execute(
        sa.select(
            models.recipe_components.c.recipe_id,
            models.inventory_items.c.name.label("item_name"),
            models.inventory_items.c.sku.label("item_sku"),
            models.recipe_components.c.unit_id,
            models.recipe_components.c.net_quantity,
            models.recipe_components.c.waste_rate,
            models.recipe_components.c.gross_quantity,
            models.inventory_units.c.code.label("unit_code"),
        )
        .select_from(
            models.recipe_components.join(
                models.inventory_items,
                models.recipe_components.c.item_id == models.inventory_items.c.id,
            ).join(
                models.inventory_units,
                models.recipe_components.c.unit_id == models.inventory_units.c.id,
            )
        )
        .where(models.recipe_components.c.recipe_id.in_(recipes_by_id.keys()))
        .order_by(models.inventory_items.c.name)
    ).mappings()
    for row in component_rows:
        recipes_by_id[row["recipe_id"]]["components"].append(
            {
                "item_name": row["item_name"],
                "item_sku": row["item_sku"],
                "unit_id": row["unit_id"],
                "net_quantity": _exact_quantity_json(row["net_quantity"]),
                "waste_rate": _exact_quantity_json(row["waste_rate"]),
                "gross_quantity": _exact_quantity_json(row["gross_quantity"]),
                "unit_code": row["unit_code"],
            }
        )

    cost_rows = session.execute(
        sa.select(models.recipe_cost_calculations)
        .where(models.recipe_cost_calculations.c.recipe_id.in_(recipes_by_id.keys()))
        .order_by(
            models.recipe_cost_calculations.c.recipe_id,
            models.recipe_cost_calculations.c.calculated_at.desc(),
        )
    ).mappings()
    for row in cost_rows:
        recipe = recipes_by_id[row["recipe_id"]]
        if recipe["latest_cost"] is None:
            recipe["latest_cost"] = dict(row)

    return list(recipes_by_id.values())


def bootstrap_status(session: Session) -> dict[str, Any]:
    counts = {
        "organizations": _count(session, models.organizations),
        "legal_entities": _count(session, models.legal_entities),
        "branches": _count(session, models.branches),
        "warehouses": _count(session, models.warehouses),
        "users": _count(session, models.users),
        "roles": _count(session, models.roles),
        "audit_events": _count(session, models.audit_events),
        "product_categories": _count_if_exists(session, models.product_categories),
        "products": _count_if_exists(session, models.products),
        "price_versions": _count_if_exists(session, models.price_versions),
        "cash_shifts": _count_if_exists(session, models.cash_shifts),
        "orders": _count_if_exists(session, models.orders),
        "production_tasks": _count_if_exists(session, models.production_tasks),
        "payments": _count_if_exists(session, models.payments),
        "cash_shift_cuts": _count_if_exists(session, models.cash_shift_cuts),
        "print_jobs": _count_if_exists(session, models.print_jobs),
        "sync_commands": _count_if_exists(session, models.sync_commands),
        "sync_events": _count_if_exists(session, models.sync_events),
        "inventory_units": _count_if_exists(session, models.inventory_units),
        "inventory_items": _count_if_exists(session, models.inventory_items),
        "recipes": _count_if_exists(session, models.recipes),
        "inventory_movements": _count_if_exists(session, models.inventory_movements),
    }
    organizations = list_organizations(session)
    branches = list_branches(session)

    return {
        "status": "ok" if counts["organizations"] and counts["branches"] else "needs_seed",
        "counts": counts,
        "primary_organization": organizations[0] if organizations else None,
        "primary_branch": branches[0] if branches else None,
    }


def _count(session: Session, table: sa.Table) -> int:
    return int(session.execute(sa.select(sa.func.count()).select_from(table)).scalar_one())


def _count_if_exists(session: Session, table: sa.Table) -> int:
    try:
        return _count(session, table)
    except sa.exc.SQLAlchemyError:
        return 0


def list_permissions(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(
        sa.select(models.permissions).order_by(models.permissions.c.code)
    ).fetchall()
    return [
        {
            "id": row.id,
            "code": row.code,
            "description": row.description,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def list_role_permissions(session: Session, role_id: str) -> list[str]:
    rows = session.execute(
        sa.select(models.role_permissions.c.permission_id).where(
            models.role_permissions.c.role_id == role_id
        )
    ).fetchall()
    return [row.permission_id for row in rows]


def list_warehouses(session: Session, branch_id: str | None = None) -> list[dict[str, Any]]:
    query = sa.select(models.warehouses).where(
        models.warehouses.c.organization_id == ORGANIZATION_ID,
    )
    if branch_id is not None:
        query = query.where(models.warehouses.c.branch_id == branch_id)
    rows = session.execute(query.order_by(models.warehouses.c.name)).fetchall()
    return [
        {
            "id": row.id,
            "branch_id": row.branch_id,
            "name": row.name,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def list_inventory_units(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(
        sa.select(models.inventory_units)
        .where(models.inventory_units.c.organization_id == ORGANIZATION_ID)
        .order_by(models.inventory_units.c.name)
    ).fetchall()
    return [
        {
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "precision_scale": row.precision_scale,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def list_inventory_items(session: Session, branch_id: str | None = None) -> list[dict[str, Any]]:
    if branch_id:
        cost_subq = (
            sa.select(
                models.inventory_cost_states.c.item_id,
                models.inventory_cost_states.c.last_unit_cost,
                models.inventory_cost_states.c.average_unit_cost,
            )
            .where(models.inventory_cost_states.c.branch_id == branch_id)
            .subquery()
        )
    else:
        cost_subq = (
            sa.select(
                models.inventory_cost_states.c.item_id,
                sa.func.max(models.inventory_cost_states.c.last_unit_cost).label("last_unit_cost"),
                sa.func.avg(models.inventory_cost_states.c.average_unit_cost).label(
                    "average_unit_cost"
                ),
            )
            .group_by(models.inventory_cost_states.c.item_id)
            .subquery()
        )

    query = (
        sa.select(
            models.inventory_items,
            models.inventory_units.c.name.label("unit_name"),
            models.inventory_units.c.code.label("unit_code"),
            cost_subq.c.last_unit_cost,
            cost_subq.c.average_unit_cost,
        )
        .select_from(
            models.inventory_items.join(
                models.inventory_units,
                models.inventory_items.c.base_unit_id == models.inventory_units.c.id,
            ).outerjoin(cost_subq, models.inventory_items.c.id == cost_subq.c.item_id)
        )
        .where(
            models.inventory_items.c.organization_id == ORGANIZATION_ID,
            models.inventory_items.c.status != "archived",
        )
    )
    if branch_id:
        query = query.where(
            sa.or_(
                models.inventory_items.c.catalog_scope == "organization",
                models.inventory_items.c.source_branch_id == branch_id,
            )
        )
    rows = session.execute(query.order_by(models.inventory_items.c.name)).fetchall()
    return [
        {
            "id": row.id,
            "name": row.name,
            "sku": row.sku,
            "base_unit_id": row.base_unit_id,
            "unit_name": row.unit_name,
            "unit_code": row.unit_code,
            "item_type": row.item_type,
            "category_name": row.category_name,
            "catalog_scope": row.catalog_scope,
            "source_branch_id": row.source_branch_id,
            "status": row.status,
            "last_unit_cost": float(row.last_unit_cost or 0.0),
            "average_unit_cost": float(row.average_unit_cost or 0.0),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def list_categories(
    session: Session,
    branch_id: str | None = None,
    organization_id: str | None = None,
) -> list[dict[str, Any]]:
    org_id = organization_id
    if branch_id and not org_id:
        branch_org = session.execute(
            sa.select(models.branches.c.organization_id).where(models.branches.c.id == branch_id)
        ).scalar()
        if branch_org:
            org_id = str(branch_org)
    if not org_id:
        org_id = ORGANIZATION_ID

    if branch_id:
        return project_pos_catalog(session, branch_id, organization_id=org_id)[0]
    rows = session.execute(
        sa.select(models.product_categories)
        .where(
            models.product_categories.c.organization_id == org_id,
            models.product_categories.c.status != "archived",
        )
        .order_by(models.product_categories.c.display_order, models.product_categories.c.name)
    ).fetchall()
    return [
        {
            "id": row.id,
            "name": row.name,
            "display_order": row.display_order,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def get_catalog_cleanup_status(session: Session) -> dict[str, Any]:
    row = (
        session.execute(
            sa.select(models.catalog_cleanup_runs)
            .order_by(models.catalog_cleanup_runs.c.created_at.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if not row:
        return {"revision": "0027_catalog_cleanup", "status": "pending", "summary": {}}
    return {
        "id": row["id"],
        "revision": row["revision"],
        "status": row["status"],
        "summary": dict(row["summary"] or {}),
        "created_at": row["created_at"],
    }


def get_product_recipe(session: Session, product_id: str) -> dict[str, Any] | None:
    recipe = (
        session.execute(
            sa.select(models.recipes)
            .where(
                models.recipes.c.product_id == product_id,
                models.recipes.c.recipe_type == "sale",
                models.recipes.c.status == "active",
            )
            .order_by(
                models.recipes.c.branch_id.is_not(None).desc(),
                models.recipes.c.version.desc(),
            )
        )
        .mappings()
        .first()
    )
    if not recipe:
        return None

    components = (
        session.execute(
            sa.select(
                models.recipe_components,
                models.inventory_items.c.name.label("item_name"),
                models.inventory_items.c.sku.label("item_sku"),
                models.inventory_units.c.code.label("unit_code"),
            )
            .select_from(
                models.recipe_components.join(
                    models.inventory_items,
                    models.recipe_components.c.item_id == models.inventory_items.c.id,
                ).join(
                    models.inventory_units,
                    models.inventory_items.c.base_unit_id == models.inventory_units.c.id,
                )
            )
            .where(models.recipe_components.c.recipe_id == recipe.id)
        )
        .mappings()
        .all()
    )

    latest_cost = (
        session.execute(
            sa.select(models.recipe_cost_calculations)
            .where(models.recipe_cost_calculations.c.recipe_id == recipe["id"])
            .order_by(models.recipe_cost_calculations.c.calculated_at.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )

    return {
        "id": recipe["id"],
        "version": recipe["version"],
        "branch_id": recipe["branch_id"],
        "recipe_type": recipe["recipe_type"],
        "yield_quantity": _exact_quantity_json(recipe["yield_quantity"]),
        "yield_unit_id": recipe["yield_unit_id"],
        "latest_cost": dict(latest_cost) if latest_cost else None,
        "components": [
            {
                "item_id": component["item_id"],
                "item_name": component["item_name"],
                "item_sku": component["item_sku"],
                "unit_id": component["unit_id"],
                "unit_code": component["unit_code"],
                "quantity": _exact_quantity_json(component["gross_quantity"]),
                "net_quantity": _exact_quantity_json(component["net_quantity"]),
                "waste_rate": _exact_quantity_json(component["waste_rate"]),
                "waste_percent": _exact_quantity_json(
                    Decimal(str(component["waste_rate"])) * Decimal("100")
                ),
                "gross_quantity": _exact_quantity_json(component["gross_quantity"]),
            }
            for component in components
        ],
    }


UTC = timezone.utc


def get_dashboard_overview(
    session: Session, branch_id: str | None = None, month: str | None = None
) -> dict[str, Any]:
    now = datetime.now(UTC)

    if month:
        try:
            year, m = map(int, month.split("-"))
            start_date = datetime(year, m, 1, tzinfo=UTC)
            if m == 12:
                end_date = datetime(year + 1, 1, 1, tzinfo=UTC)
            else:
                end_date = datetime(year, m + 1, 1, tzinfo=UTC)
        except ValueError as exc:
            raise BusinessError(
                "dashboard_period_invalid", "month must use YYYY-MM with a valid calendar month"
            ) from exc
    else:
        start_date = now - timedelta(days=30)
        end_date = now

    snapshot_q = sa.select(models.sales_operation_snapshots).where(
        models.sales_operation_snapshots.c.confirmed_at >= start_date,
        models.sales_operation_snapshots.c.confirmed_at < end_date,
    )
    if branch_id:
        snapshot_q = snapshot_q.where(models.sales_operation_snapshots.c.branch_id == branch_id)
    snapshots = [dict(row) for row in session.execute(snapshot_q).mappings()]

    # A confirmed sales snapshot is the single authority for every dashboard KPI.
    total_revenue = sum(int(row["net_cents"]) for row in snapshots)
    paid_order_ids = {str(row["order_id"]) for row in snapshots}
    total_orders = len(paid_order_ids)
    average_ticket_cents = (
        int(
            (Decimal(total_revenue) / Decimal(total_orders)).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
        if total_orders
        else 0
    )
    order_types = {"mostrador": 0, "para_llevar": 0, "domicilio": 0}
    service_labels = {
        "dine-in": "mostrador",
        "takeout": "para_llevar",
        "delivery": "domicilio",
    }
    for row in snapshots:
        order_types[service_labels[str(row["service_type_snapshot"])]] += 1

    # Total Products Active
    prod_q = sa.select(sa.func.count(models.products.c.id)).where(
        models.products.c.status == "active"
    )
    total_products = int(session.execute(prod_q).scalar() or 0)

    recent_transactions = [
        {
            "id": row["payment_id"],
            "amount_cents": int(row["net_cents"]),
            "status": "CONFIRMED",
            "created_at": row["confirmed_at"].isoformat(),
            "folio": row["folio_snapshot"],
        }
        for row in sorted(snapshots, key=lambda item: item["confirmed_at"], reverse=True)[:10]
    ]

    activity_by_day: dict[str, dict[str, int]] = {}
    for row in sorted(snapshots, key=lambda item: item["confirmed_at"]):
        day_str = row["confirmed_at"].strftime("%b %d")
        activity_by_day.setdefault(day_str, {"completed": 0, "pending": 0})["completed"] += 1
    activity_chart = [
        {"day": k, "completed": v["completed"], "pending": v["pending"]}
        for k, v in activity_by_day.items()
    ]

    # 4. Notificaciones recientes (Aperturas y cierres de caja)
    # Join audit_events → cash_shifts to get register_code; join → users for display_name
    ae = models.audit_events
    cs = models.cash_shifts
    us = models.users
    notif_q = (
        sa.select(
            ae.c.id,
            ae.c.action,
            ae.c.created_at,
            ae.c.payload,
            ae.c.entity_id.label("cash_shift_id"),
            cs.c.register_code,
            us.c.display_name.label("actor_display_name"),
        )
        .select_from(
            ae.outerjoin(cs, ae.c.entity_id == cs.c.id).outerjoin(us, ae.c.actor_user_id == us.c.id)
        )
        .where(ae.c.action.in_(["cash_shift.opened", "cash_shift.closed"]))
    )
    if branch_id:
        notif_q = notif_q.where(ae.c.branch_id == branch_id)
    notif_q = notif_q.order_by(ae.c.created_at.desc()).limit(10)

    notif_rows = session.execute(notif_q).mappings()
    recent_notifications = [
        {
            "id": n["id"],
            "action": n["action"],
            "created_at": n["created_at"].isoformat(),
            "payload": n["payload"],
            # Resolved fields for the frontend – prefer join result, fall back to payload
            "register_code": n["register_code"]
            or (n["payload"] or {}).get("register_code", "Caja"),
            "actor_name": n["actor_display_name"] or "Sistema",
        }
        for n in notif_rows
    ]

    snapshot_ids = [str(row["id"]) for row in snapshots]
    category_totals: dict[tuple[str, str], dict[str, int]] = {}
    if snapshot_ids:
        category_rows = session.execute(
            sa.select(
                models.sales_operation_line_snapshots.c.family_id_snapshot,
                models.sales_operation_line_snapshots.c.family_name_snapshot,
                models.sales_operation_line_snapshots.c.quantity,
                models.sales_operation_line_snapshots.c.net_cents,
            ).where(
                models.sales_operation_line_snapshots.c.sales_operation_snapshot_id.in_(
                    snapshot_ids
                )
            )
        ).mappings()
        for category_row in category_rows:
            key = (
                str(category_row["family_id_snapshot"]),
                str(category_row["family_name_snapshot"]),
            )
            aggregate = category_totals.setdefault(key, {"quantity": 0, "known_net_cents": 0})
            aggregate["quantity"] += int(category_row["quantity"])
            if category_row["net_cents"] is not None:
                aggregate["known_net_cents"] += int(category_row["net_cents"])
    total_category_quantity = sum(item["quantity"] for item in category_totals.values())
    popular_categories = []
    for (category_id, category_name), totals in sorted(
        category_totals.items(), key=lambda item: (-item[1]["quantity"], item[0][1], item[0][0])
    )[:15]:
        share_bps = (
            int(
                (
                    Decimal(totals["quantity"]) * Decimal(10_000) / Decimal(total_category_quantity)
                ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
            if total_category_quantity
            else 0
        )
        popular_categories.append(
            {
                "id": category_id,
                "name": category_name,
                "quantity": totals["quantity"],
                "known_net_cents": totals["known_net_cents"],
                "share_bps": share_bps,
            }
        )

    return {
        "total_revenue_cents": total_revenue,
        "total_orders": total_orders,
        "average_ticket_cents": average_ticket_cents,
        "total_products": total_products,
        "order_types": order_types,
        "period_from_utc": start_date.isoformat(),
        "period_to_utc": end_date.isoformat(),
        "recent_transactions": recent_transactions,
        "activity_chart": activity_chart[-15:],
        "recent_notifications": recent_notifications,
        "popular_categories": popular_categories,
    }
