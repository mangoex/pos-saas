from __future__ import annotations

from collections import Counter
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Session

from . import models
from .catalog_policy import (
    canonical_category_name,
    canonical_inventory_item_type,
    is_numeric_sku,
    is_uppercase_name,
    normalize_inventory_sku,
    normalize_product_sku,
    product_station,
)
from .operations import (
    BusinessError,
    _audit,
    _now,
    authorize_branch_scope,
    require_permission,
)

SUPPORTED_ENTITY_TYPES = {"customer", "inventory_item", "product", "presentation", "recipe"}


def _id() -> str:
    return str(uuid4())


def _corporate_import_scope(
    session: Session, actor_user_id: str, branch_id: str
) -> tuple[str, str]:
    require_permission(session, actor_user_id, "admin.manage")
    authorized = authorize_branch_scope(session, actor_user_id, "catalog.manage", branch_id)
    if authorized != branch_id:
        raise BusinessError("invalid_branch_scope", "A target branch is required")
    organization_id = session.scalar(
        sa.select(models.users.c.organization_id).where(models.users.c.id == actor_user_id)
    )
    if not organization_id or not session.scalar(
        sa.select(models.branches.c.id).where(
            models.branches.c.id == branch_id,
            models.branches.c.organization_id == organization_id,
        )
    ):
        raise BusinessError("invalid_branch_scope", "The branch is outside the actor organization")
    return str(organization_id), branch_id


def create_legacy_import_batch(
    session: Session,
    actor_user_id: str,
    branch_id: str,
    source_system: str,
    manifest_checksum: str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    organization_id, target_branch = _corporate_import_scope(session, actor_user_id, branch_id)
    normalized_source = source_system.strip().lower()
    normalized_checksum = manifest_checksum.strip().lower()
    if not normalized_source or len(normalized_checksum) != 64:
        raise BusinessError("invalid_import_manifest", "Source and SHA-256 checksum are required")

    existing = (
        session.execute(
            sa.select(models.legacy_import_batches).where(
                models.legacy_import_batches.c.organization_id == organization_id,
                models.legacy_import_batches.c.branch_id == target_branch,
                models.legacy_import_batches.c.source_system == normalized_source,
                models.legacy_import_batches.c.manifest_checksum == normalized_checksum,
            )
        )
        .mappings()
        .first()
    )
    if existing:
        return dict(existing)

    now = _now()
    batch: dict[str, Any] = {
        "id": _id(),
        "organization_id": organization_id,
        "branch_id": target_branch,
        "source_system": normalized_source,
        "manifest_checksum": normalized_checksum,
        "manifest": manifest,
        "status": "loading",
        "summary": {},
        "created_by": actor_user_id,
        "created_at": now,
        "updated_at": now,
    }
    session.execute(models.legacy_import_batches.insert().values(**batch))
    _audit(
        session,
        "legacy_import.started",
        "legacy_import_batch",
        batch["id"],
        {"source_system": normalized_source, "manifest_checksum": normalized_checksum},
        target_branch,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
    )
    session.commit()
    return batch


def _batch_for_actor(session: Session, actor_user_id: str, batch_id: str) -> dict[str, Any]:
    organization_id = session.scalar(
        sa.select(models.users.c.organization_id).where(models.users.c.id == actor_user_id)
    )
    if not organization_id:
        raise BusinessError("import_batch_not_found", "Import batch was not found")
    batch = (
        session.execute(
            sa.select(models.legacy_import_batches).where(
                models.legacy_import_batches.c.id == batch_id,
                models.legacy_import_batches.c.organization_id == organization_id,
            )
        )
        .mappings()
        .first()
    )
    if not batch:
        raise BusinessError("import_batch_not_found", "Import batch was not found")
    batch_organization_id, _ = _corporate_import_scope(
        session, actor_user_id, str(batch["branch_id"])
    )
    if batch_organization_id != str(batch["organization_id"]):
        raise BusinessError("import_batch_not_found", "Import batch was not found")
    return dict(batch)


def _ensure_unit(session: Session, organization_id: str, payload: dict[str, Any]) -> str:
    code = str(payload.get("unit_code", "")).strip().upper()
    aliases = {"LTS": "LITRO", "LT": "LITRO", "PZA": "PIEZA", "PZ": "PIEZA"}
    code = aliases.get(code, code)
    if not code:
        raise BusinessError("missing_unit", "Inventory unit is required")
    existing = session.execute(
        sa.select(models.inventory_units.c.id).where(
            models.inventory_units.c.organization_id == organization_id,
            models.inventory_units.c.code == code,
        )
    ).scalar_one_or_none()
    if existing:
        return str(existing)
    dimensions = {"KILO": ("Kilogramo", "mass", 3), "LITRO": ("Litro", "volume", 3)}
    name, dimension, precision = dimensions.get(code, (code.title(), "discrete", 0))
    unit_id = _id()
    session.execute(
        models.inventory_units.insert().values(
            id=unit_id,
            organization_id=organization_id,
            code=code,
            name=name,
            dimension=dimension,
            precision_scale=precision,
            created_at=_now(),
        )
    )
    return unit_id


def _materialize_customer(
    session: Session, batch: dict[str, Any], payload: dict[str, Any]
) -> tuple[str, str, str | None]:
    name = str(payload.get("name", "")).strip()
    if not name:
        return "rejected", "", "missing_customer_name"
    customer_id = _id()
    now = _now()
    session.execute(
        models.customers.insert().values(
            id=customer_id,
            organization_id=batch["organization_id"],
            name=name[:160],
            email=None,
            customer_type="person",
            customer_segment=None,
            notes="Importado de sistema heredado; dirección pendiente de estructurar.",
            status="active",
            origin_branch_id=batch["branch_id"],
            created_at=now,
            updated_at=now,
        )
    )
    return "imported", customer_id, None


def _materialize_inventory_item(
    session: Session, batch: dict[str, Any], payload: dict[str, Any]
) -> tuple[str, str, str | None]:
    sku = normalize_inventory_sku(payload.get("sku"))
    name = str(payload.get("name", "")).strip()
    if not name:
        return "rejected", "", "missing_item_identity"
    if not is_numeric_sku(sku):
        return "rejected", "", "legacy_item_sku"
    existing = (
        session.execute(
            sa.select(models.inventory_items).where(
                models.inventory_items.c.organization_id == batch["organization_id"],
                models.inventory_items.c.sku == sku,
            )
        )
        .mappings()
        .first()
    )
    if existing:
        if existing["status"] != "archived":
            return "linked", str(existing["id"]), None
        return "needs_review", str(existing["id"]), "sku_conflict"
    unit_id = _ensure_unit(session, str(batch["organization_id"]), payload)
    item_id = _id()
    now = _now()
    category_name = canonical_category_name(payload.get("category_name"))
    session.execute(
        models.inventory_items.insert().values(
            id=item_id,
            organization_id=batch["organization_id"],
            name=name[:160],
            sku=sku[:64],
            base_unit_id=unit_id,
            item_type=canonical_inventory_item_type(category_name, "ingredient"),
            category_name=category_name[:120] or None,
            catalog_scope="organization",
            source_branch_id=None,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    return "imported", item_id, None


def _ensure_category(session: Session, organization_id: str, name: str) -> str:
    normalized = canonical_category_name(name)
    existing = session.execute(
        sa.select(models.product_categories.c.id).where(
            models.product_categories.c.organization_id == organization_id,
            models.product_categories.c.name == normalized,
            models.product_categories.c.status != "archived",
        )
    ).scalar_one_or_none()
    if existing:
        return str(existing)
    category_id = _id()
    now = _now()
    session.execute(
        models.product_categories.insert().values(
            id=category_id,
            organization_id=organization_id,
            name=normalized[:120],
            display_order=999,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    return category_id


def _materialize_product(
    session: Session, batch: dict[str, Any], payload: dict[str, Any]
) -> tuple[str, str, str | None]:
    sku = normalize_product_sku(payload.get("sku"))
    name = str(payload.get("name", "")).strip()
    category_name = canonical_category_name(payload.get("category_name"))
    if not name or not category_name:
        return "rejected", "", "missing_product_identity"
    if not is_numeric_sku(sku) or not is_uppercase_name(name):
        return "rejected", "", "legacy_product_identity"
    existing = (
        session.execute(
            sa.select(models.products).where(
                models.products.c.organization_id == batch["organization_id"],
                models.products.c.sku == sku,
            )
        )
        .mappings()
        .first()
    )
    if existing:
        if existing["status"] != "archived":
            return "linked", str(existing["id"]), None
        return "needs_review", str(existing["id"]), "sku_conflict"

    category_id = _ensure_category(session, str(batch["organization_id"]), category_name)
    product_id = _id()
    now = _now()
    session.execute(
        models.products.insert().values(
            id=product_id,
            organization_id=batch["organization_id"],
            category_id=category_id,
            name=name[:160],
            sku=sku[:64],
            description=None,
            station=product_station(name, category_name),
            status="active",
            image_url=None,
            catalog_scope="organization",
            source_branch_id=None,
            created_at=now,
            updated_at=now,
        )
    )
    try:
        price_cents = int(payload.get("price_cents", 0))
    except (TypeError, ValueError):
        price_cents = 0
    if price_cents > 0:
        session.execute(
            models.price_versions.insert().values(
                id=_id(),
                organization_id=batch["organization_id"],
                product_id=product_id,
                price_cents=price_cents,
                currency="MXN",
                valid_from=now,
                valid_to=None,
                created_at=now,
            )
        )
    return "imported", product_id, None


def _validate_reference_payload(entity_type: str, payload: dict[str, Any]) -> str:
    if entity_type == "presentation":
        if not str(payload.get("supplier_code", "")).strip():
            return "missing_supplier"
        return "requires_presentation_promotion"
    return "missing_recipe_components"


def ingest_legacy_import_records(
    session: Session,
    actor_user_id: str,
    batch_id: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    batch = _batch_for_actor(session, actor_user_id, batch_id)
    if batch["status"] not in {"loading", "review"}:
        raise BusinessError("import_batch_closed", "Import batch no longer accepts records")
    if not records or len(records) > 500:
        raise BusinessError("invalid_import_chunk", "A chunk must contain between 1 and 500 rows")

    result: Counter[str] = Counter()
    for incoming in records:
        entity_type = str(incoming.get("entity_type", "")).strip().lower()
        source_key = str(incoming.get("source_key", "")).strip()
        if entity_type not in SUPPORTED_ENTITY_TYPES or not source_key:
            raise BusinessError("invalid_import_record", "Entity type and source key are required")
        duplicate = session.execute(
            sa.select(models.legacy_import_records.c.status).where(
                models.legacy_import_records.c.batch_id == batch_id,
                models.legacy_import_records.c.entity_type == entity_type,
                models.legacy_import_records.c.source_key == source_key,
            )
        ).scalar_one_or_none()
        if duplicate:
            result["unchanged"] += 1
            continue

        raw_payload = dict(incoming.get("raw_payload") or {})
        normalized = dict(incoming.get("normalized_payload") or {})
        target_id = ""
        reason: str | None = None
        if entity_type == "customer":
            status, target_id, reason = _materialize_customer(session, batch, normalized)
        elif entity_type == "inventory_item":
            status, target_id, reason = _materialize_inventory_item(session, batch, normalized)
        elif entity_type == "product":
            status, target_id, reason = _materialize_product(session, batch, normalized)
        else:
            status = "needs_review"
            reason = _validate_reference_payload(entity_type, normalized)

        now = _now()
        session.execute(
            models.legacy_import_records.insert().values(
                id=_id(),
                batch_id=batch_id,
                entity_type=entity_type,
                source_key=source_key[:160],
                source_row=int(incoming.get("source_row") or 0),
                raw_payload=raw_payload,
                normalized_payload=normalized,
                status=status,
                reason_code=reason,
                target_entity_type=entity_type if target_id else None,
                target_entity_id=target_id or None,
                created_at=now,
                updated_at=now,
            )
        )
        result[status] += 1

    session.execute(
        models.legacy_import_batches.update()
        .where(
            models.legacy_import_batches.c.id == batch_id,
            models.legacy_import_batches.c.organization_id == batch["organization_id"],
        )
        .values(updated_at=_now())
    )
    session.commit()
    return {"batch_id": batch_id, "counts": dict(result)}


def complete_legacy_import_batch(
    session: Session, actor_user_id: str, batch_id: str
) -> dict[str, Any]:
    batch = _batch_for_actor(session, actor_user_id, batch_id)
    rows = session.execute(
        sa.select(
            models.legacy_import_records.c.status,
            sa.func.count(models.legacy_import_records.c.id).label("count"),
        )
        .where(models.legacy_import_records.c.batch_id == batch_id)
        .group_by(models.legacy_import_records.c.status)
    ).mappings()
    summary = {row["status"]: int(row["count"]) for row in rows}
    status = (
        "review" if summary.get("needs_review", 0) or summary.get("rejected", 0) else "completed"
    )
    session.execute(
        models.legacy_import_batches.update()
        .where(
            models.legacy_import_batches.c.id == batch_id,
            models.legacy_import_batches.c.organization_id == batch["organization_id"],
        )
        .values(status=status, summary=summary, updated_at=_now())
    )
    _audit(
        session,
        "legacy_import.completed",
        "legacy_import_batch",
        batch_id,
        {"status": status, "summary": summary},
        str(batch["branch_id"]),
        organization_id=str(batch["organization_id"]),
        actor_user_id=actor_user_id,
    )
    session.commit()
    return {**batch, "status": status, "summary": summary}


def list_legacy_import_batches(
    session: Session, actor_user_id: str, branch_id: str
) -> list[dict[str, Any]]:
    organization_id, target_branch = _corporate_import_scope(session, actor_user_id, branch_id)
    rows = session.execute(
        sa.select(models.legacy_import_batches)
        .where(
            models.legacy_import_batches.c.organization_id == organization_id,
            models.legacy_import_batches.c.branch_id == target_branch,
        )
        .order_by(models.legacy_import_batches.c.created_at.desc())
    ).mappings()
    return [
        {**dict(row), "entity_summary": _legacy_import_entity_summary(session, str(row["id"]))}
        for row in rows
    ]


def _legacy_import_entity_summary(session: Session, batch_id: str) -> dict[str, dict[str, int]]:
    entity_rows = session.execute(
        sa.select(
            models.legacy_import_records.c.entity_type,
            models.legacy_import_records.c.status,
            sa.func.count(models.legacy_import_records.c.id).label("count"),
        )
        .where(models.legacy_import_records.c.batch_id == batch_id)
        .group_by(
            models.legacy_import_records.c.entity_type,
            models.legacy_import_records.c.status,
        )
    ).mappings()
    entity_summary: dict[str, dict[str, int]] = {}
    for row in entity_rows:
        entity_summary.setdefault(str(row["entity_type"]), {})[str(row["status"])] = int(
            row["count"]
        )
    return entity_summary


def list_branch_legacy_import_batches(
    session: Session, actor_user_id: str, branch_id: str | None = None
) -> list[dict[str, Any]]:
    target_branch = authorize_branch_scope(session, actor_user_id, "branch.admin.access", branch_id)
    if not target_branch:
        raise BusinessError("invalid_branch_scope", "Select a branch to view its imports")
    organization_id = session.scalar(
        sa.select(models.users.c.organization_id).where(models.users.c.id == actor_user_id)
    )
    if not organization_id or not session.scalar(
        sa.select(models.branches.c.id).where(
            models.branches.c.id == target_branch,
            models.branches.c.organization_id == organization_id,
        )
    ):
        raise BusinessError("invalid_branch_scope", "The branch is outside the actor organization")
    batches = list(
        session.execute(
            sa.select(
                models.legacy_import_batches.c.id,
                models.legacy_import_batches.c.source_system,
                models.legacy_import_batches.c.status,
                models.legacy_import_batches.c.summary,
                models.legacy_import_batches.c.created_at,
            )
            .where(
                models.legacy_import_batches.c.organization_id == organization_id,
                models.legacy_import_batches.c.branch_id == target_branch,
            )
            .order_by(models.legacy_import_batches.c.created_at.desc())
        ).mappings()
    )
    result = []
    for batch in batches:
        result.append(
            {
                **dict(batch),
                "entity_summary": _legacy_import_entity_summary(session, str(batch["id"])),
            }
        )
    return result


def list_legacy_import_records(
    session: Session,
    actor_user_id: str,
    batch_id: str,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    entity_type: str | None = None,
) -> dict[str, Any]:
    _batch_for_actor(session, actor_user_id, batch_id)
    bounded_limit = min(max(limit, 1), 500)
    bounded_offset = max(offset, 0)
    criteria = [models.legacy_import_records.c.batch_id == batch_id]
    if status:
        criteria.append(models.legacy_import_records.c.status == status)
    if entity_type:
        if entity_type not in SUPPORTED_ENTITY_TYPES:
            raise BusinessError("invalid_import_entity_type", "Unsupported import entity type")
        criteria.append(models.legacy_import_records.c.entity_type == entity_type)
    total = session.execute(
        sa.select(sa.func.count(models.legacy_import_records.c.id)).where(*criteria)
    ).scalar_one()
    rows = session.execute(
        sa.select(models.legacy_import_records)
        .where(*criteria)
        .order_by(
            models.legacy_import_records.c.entity_type, models.legacy_import_records.c.source_row
        )
        .limit(bounded_limit)
        .offset(bounded_offset)
    ).mappings()
    return {
        "items": [dict(row) for row in rows],
        "total": int(total),
        "limit": bounded_limit,
        "offset": bounded_offset,
    }
