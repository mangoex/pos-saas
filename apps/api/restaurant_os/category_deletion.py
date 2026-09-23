"""Transactional catalog archival, preserving historical references."""

from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from restaurant_os import models


def lock_catalog_organization(session: Session, organization_id: str) -> None:
    """Serialize catalog membership mutations before individual row locks."""
    session.execute(
        sa.select(models.organizations.c.id)
        .where(
            models.organizations.c.id == organization_id,
        )
        .with_for_update()
    ).scalar_one()


def delete_category(
    session: Session,
    category_id: str,
    actor_user_id: str,
    delete_products: bool = False,
) -> dict[str, Any]:
    from restaurant_os.operations import (
        BusinessError,
        _audit,
        _modifier_actor_organization,
        _now,
        require_permission,
    )

    require_permission(session, actor_user_id, "catalog.manage")
    org_id = _modifier_actor_organization(session, actor_user_id)
    if not delete_products:
        raise BusinessError(
            "category_delete_confirmation_required",
            "Confirma eliminar también los productos de la categoría.",
        )
    lock_catalog_organization(session, org_id)
    category = (
        session.execute(
            sa.select(models.product_categories)
            .where(
                models.product_categories.c.id == category_id,
                models.product_categories.c.organization_id == org_id,
            )
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if not category:
        raise BusinessError("category_not_found", "Category was not found")
    if category["status"] == "archived":
        session.commit()
        return {"id": category_id, "status": "archived", "archived_products": 0}
    scope = sa.and_(
        models.products.c.category_id == category_id, models.products.c.organization_id == org_id
    )
    products = [
        dict(p)
        for p in session.execute(
            sa.select(
                models.products.c.id,
                models.products.c.status,
            )
            .where(scope)
            .order_by(models.products.c.id)
            .with_for_update()
        ).mappings()
    ]
    try:
        now = _now()
        session.execute(
            models.products.update().where(scope).values(status="archived", updated_at=now)
        )
        session.execute(
            models.product_categories.update()
            .where(
                models.product_categories.c.id == category_id,
                models.product_categories.c.organization_id == org_id,
            )
            .values(status="archived", updated_at=now)
        )
        _audit(
            session,
            action="category.deleted",
            entity_type="category",
            entity_id=category_id,
            actor_user_id=actor_user_id,
            organization_id=org_id,
            payload={
                "name": category["name"],
                "previous_status": category["status"],
                "status": "archived",
                "products": products,
            },
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {"id": category_id, "status": "archived", "archived_products": len(products)}
