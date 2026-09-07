# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-recovery-test-legacy-import-synthetic-v1
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.legacy_import import (
    complete_legacy_import_batch,
    create_legacy_import_batch,
    ingest_legacy_import_records,
    list_legacy_import_batches,
    list_legacy_import_records,
)
from restaurant_os.operations import (
    ADMIN_USER_ID,
    BRANCH_ID,
    BusinessError,
    add_customer_address,
    list_customers_page,
)
from restaurant_os.platform_data import (
    list_catalog_products,
    list_inventory_items,
    list_inventory_stock,
)
from restaurant_os.saas_onboarding import signup_tenant
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[3]
OTHER_BRANCH_ID = "018f6f73-2d0a-74f0-8f1c-000000009999"


def migrated_session(tmp_path: Path) -> tuple[sa.Engine, Session]:
    database_path = tmp_path / "legacy-import.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=ROOT / "apps" / "api",
        env={**os.environ, "RESTAURANTOS_DATABASE_URL": database_url},
        check=True,
        capture_output=True,
        text=True,
    )
    engine = sa.create_engine(database_url)
    session = Session(engine)
    return engine, session


def test_constitucion_import_is_idempotent_scoped_and_non_operational(tmp_path: Path) -> None:
    engine, session = migrated_session(tmp_path)
    try:
        branch = (
            session.execute(sa.select(models.branches).where(models.branches.c.id == BRANCH_ID))
            .mappings()
            .one()
        )
        session.execute(
            models.branches.insert().values(
                id=OTHER_BRANCH_ID,
                organization_id=branch["organization_id"],
                legal_entity_id=branch["legal_entity_id"],
                business_unit_id=branch["business_unit_id"],
                name="Otra sucursal",
                code="OTRA",
                timezone="America/Mazatlan",
                status="active",
                created_at=branch["created_at"],
                updated_at=branch["updated_at"],
            )
        )
        session.commit()
        # This scenario needs an active canonical item; SaaS migrations archive demo SKUs.
        # Seed a distinct synthetic item instead of depending on or reviving archived history.
        canonical_item = dict(
            session.execute(
                sa.select(models.inventory_items).where(models.inventory_items.c.sku == "1001")
            )
            .mappings()
            .one()
        )
        canonical_item.update(
            id="018f6f73-2d0a-74f0-8f1c-000000009998", sku="99001", status="active"
        )
        session.execute(models.inventory_items.insert().values(**canonical_item))
        movements_before = session.execute(
            sa.select(sa.func.count(models.inventory_movements.c.id))
        ).scalar_one()

        manifest_checksum = "a" * 64
        batch = create_legacy_import_batch(
            session,
            ADMIN_USER_ID,
            BRANCH_ID,
            "softrestaurant",
            manifest_checksum,
            {"files": [{"filename": "fixture.xlsx", "sha256": "b" * 64}]},
        )
        repeated_batch = create_legacy_import_batch(
            session,
            ADMIN_USER_ID,
            BRANCH_ID,
            "softrestaurant",
            manifest_checksum,
            {"files": []},
        )
        assert repeated_batch["id"] == batch["id"]

        records = [
            {
                "entity_type": "customer",
                "source_key": "C-1",
                "source_row": 6,
                "raw_payload": {"CLAVE": "C-1", "NOMBRE": "Cliente de prueba"},
                "normalized_payload": {
                    "name": "Cliente de prueba",
                    "legacy_address": "dato privado",
                },
            },
            {
                "entity_type": "inventory_item",
                "source_key": "I-1",
                "source_row": 6,
                "raw_payload": {"CLAVE": "I-1", "COSTOPROMEDIO": "123.45"},
                "normalized_payload": {
                    "sku": "99001",
                    "name": "INSUMO DE PRUEBA",
                    "category_name": "ABARROTE",
                    "unit_code": "KILO",
                    "legacy_average_cost": "123.45",
                },
            },
            {
                "entity_type": "product",
                "source_key": "P-1",
                "source_row": 6,
                "raw_payload": {"CLAVE": "P-1", "PRECIO": "75.00"},
                "normalized_payload": {
                    "sku": "'01001",
                    "name": "PRODUCTO DE PRUEBA",
                    "category_name": "BEBIDAS",
                    "price_cents": 7500,
                },
            },
            {
                "entity_type": "presentation",
                "source_key": "PP-1",
                "source_row": 6,
                "raw_payload": {"CLAVE": "PP-1"},
                "normalized_payload": {"sku": "99001", "supplier_code": ""},
            },
            {
                "entity_type": "recipe",
                "source_key": "R-1",
                "source_row": 6,
                "raw_payload": {"CLAVE": "R-1"},
                "normalized_payload": {"sku": "01001", "components": []},
            },
        ]
        first = ingest_legacy_import_records(session, ADMIN_USER_ID, str(batch["id"]), records)
        second = ingest_legacy_import_records(session, ADMIN_USER_ID, str(batch["id"]), records)
        assert first["counts"] == {"imported": 2, "linked": 1, "needs_review": 2}
        assert second["counts"] == {"unchanged": 5}
        completed = complete_legacy_import_batch(session, ADMIN_USER_ID, str(batch["id"]))
        assert completed["status"] == "review"
        assert completed["summary"] == {"imported": 2, "linked": 1, "needs_review": 2}

        listed_batch = list_legacy_import_batches(session, ADMIN_USER_ID, BRANCH_ID)[0]
        assert listed_batch["entity_summary"] == {
            "customer": {"imported": 1},
            "inventory_item": {"linked": 1},
            "presentation": {"needs_review": 1},
            "product": {"imported": 1},
            "recipe": {"needs_review": 1},
        }
        product_records = list_legacy_import_records(
            session,
            ADMIN_USER_ID,
            str(batch["id"]),
            status="imported",
            entity_type="product",
        )
        assert product_records["total"] == 1
        assert product_records["items"][0]["normalized_payload"]["name"] == ("PRODUCTO DE PRUEBA")
        with pytest.raises(BusinessError, match="Unsupported import entity type"):
            list_legacy_import_records(
                session,
                ADMIN_USER_ID,
                str(batch["id"]),
                entity_type="unknown",
            )

        product = (
            session.execute(sa.select(models.products).where(models.products.c.sku == "01001"))
            .mappings()
            .one()
        )
        assert product["catalog_scope"] == "organization"
        assert product["source_branch_id"] is None
        assert product["station"] == "drinks"
        assert product["status"] == "active"
        branch_products = list_catalog_products(session, BRANCH_ID)
        assert any(row["sku"] == "01001" and row["status"] == "active" for row in branch_products)
        assert any(row["sku"] == "01001" for row in list_catalog_products(session, OTHER_BRANCH_ID))

        branch_items = list_inventory_items(session, BRANCH_ID)
        other_items = list_inventory_items(session, OTHER_BRANCH_ID)
        assert any(row["sku"] == "99001" for row in branch_items)
        assert any(row["sku"] == "99001" for row in other_items)
        assert any(row["sku"] == "99001" for row in list_inventory_stock(session, BRANCH_ID))
        movements_after = session.execute(
            sa.select(sa.func.count(models.inventory_movements.c.id))
        ).scalar_one()
        assert movements_after == movements_before

        branch_customers = list_customers_page(session, BRANCH_ID, "Cliente", limit=10)
        other_customers = list_customers_page(session, OTHER_BRANCH_ID, "Cliente", limit=10)
        assert branch_customers["total"] == 1
        assert other_customers["total"] == 0
        assert branch_customers["items"][0]["addresses"] == []
        assert branch_customers["items"][0]["phones"] == []
        assert branch_customers["items"][0]["legacy_address_reference"] == "dato privado"
        assert "raw_payload" not in branch_customers["items"][0]
        with pytest.raises(BusinessError, match="Active customer was not found"):
            add_customer_address(
                session,
                branch_customers["items"][0]["id"],
                {
                    "alias": "No autorizado",
                    "street": "Calle ajena",
                    "exterior_number": "1",
                    "neighborhood": "Centro",
                    "postal_code": "82000",
                    "city": "Mazatlan",
                    "municipality": "Mazatlan",
                    "state": "Sinaloa",
                },
                OTHER_BRANCH_ID,
                ADMIN_USER_ID,
            )
    finally:
        session.close()
        engine.dispose()


def test_legacy_import_uses_actor_tenant_for_batches_and_same_catalog_codes(
    tmp_path: Path,
) -> None:
    engine, session = migrated_session(tmp_path)
    try:
        tenant_a = signup_tenant(
            session,
            {
                "business_name": "Import A",
                "owner_name": "Owner A",
                "email": "legacy-import-a@example.test",
                "password": "synthetic-password-a",
                "business_type": "blank",
            },
        )
        tenant_b = signup_tenant(
            session,
            {
                "business_name": "Import B",
                "owner_name": "Owner B",
                "email": "legacy-import-b@example.test",
                "password": "synthetic-password-b",
                "business_type": "blank",
            },
        )
        actor_a, branch_a, org_a = (
            str(tenant_a["user"]["id"]),
            str(tenant_a["branch"]["id"]),
            str(tenant_a["organization"]["id"]),
        )
        actor_b, branch_b, org_b = (
            str(tenant_b["user"]["id"]),
            str(tenant_b["branch"]["id"]),
            str(tenant_b["organization"]["id"]),
        )
        checksum = "c" * 64
        batch_a = create_legacy_import_batch(
            session, actor_a, branch_a, "legacy", checksum, {"tenant": "A"}
        )
        batch_b = create_legacy_import_batch(
            session, actor_b, branch_b, "legacy", checksum, {"tenant": "B"}
        )
        assert batch_a["id"] != batch_b["id"]
        assert batch_a["organization_id"] == org_a
        assert batch_b["organization_id"] == org_b

        records = [
            {
                "entity_type": "inventory_item",
                "source_key": "item-1",
                "normalized_payload": {
                    "sku": "1001",
                    "name": "INSUMO COMPARTIDO",
                    "category_name": "ABARROTE",
                    "unit_code": "PZA",
                },
            },
            {
                "entity_type": "product",
                "source_key": "product-1",
                "normalized_payload": {
                    "sku": "1002",
                    "name": "PRODUCTO COMPARTIDO",
                    "category_name": "BEBIDAS",
                    "price_cents": 1500,
                },
            },
        ]
        assert ingest_legacy_import_records(session, actor_a, str(batch_a["id"]), records)[
            "counts"
        ] == {"imported": 2}
        assert ingest_legacy_import_records(session, actor_b, str(batch_b["id"]), records)[
            "counts"
        ] == {"imported": 2}
        assert session.scalar(
            sa.select(sa.func.count())
            .select_from(models.inventory_items)
            .where(models.inventory_items.c.organization_id.in_((org_a, org_b)))
        ) == 2
        assert session.scalar(
            sa.select(sa.func.count())
            .select_from(models.products)
            .where(models.products.c.organization_id.in_((org_a, org_b)))
        ) == 2
        assert session.scalar(
            sa.select(sa.func.count())
            .select_from(models.inventory_units)
            .where(
                models.inventory_units.c.organization_id.in_((org_a, org_b)),
                models.inventory_units.c.code == "PIEZA",
            )
        ) == 2
        assert session.scalar(
            sa.select(sa.func.count())
            .select_from(models.product_categories)
            .where(
                models.product_categories.c.organization_id.in_((org_a, org_b)),
                models.product_categories.c.name == "BEBIDAS",
            )
        ) == 2
        assert session.scalar(
            sa.select(sa.func.count())
            .select_from(models.price_versions)
            .where(models.price_versions.c.organization_id.in_((org_a, org_b)))
        ) == 2

        records_before = session.scalar(
            sa.select(sa.func.count()).select_from(models.legacy_import_records)
        )
        with pytest.raises(BusinessError, match="Import batch was not found"):
            ingest_legacy_import_records(session, actor_b, str(batch_a["id"]), records)
        with pytest.raises(BusinessError, match="Import batch was not found"):
            list_legacy_import_records(session, actor_b, str(batch_a["id"]))
        with pytest.raises(BusinessError, match="branch"):
            list_legacy_import_batches(session, actor_b, branch_a)
        assert session.scalar(
            sa.select(sa.func.count()).select_from(models.legacy_import_records)
        ) == records_before
        assert [row["id"] for row in list_legacy_import_batches(session, actor_a, branch_a)] == [
            batch_a["id"]
        ]
        assert [row["id"] for row in list_legacy_import_batches(session, actor_b, branch_b)] == [
            batch_b["id"]
        ]
    finally:
        session.close()
        engine.dispose()


def test_legacy_import_migration_roundtrip(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy-roundtrip.db"
    env = {
        **os.environ,
        "RESTAURANTOS_DATABASE_URL": f"sqlite+pysqlite:///{database_path}",
    }

    def alembic(*arguments: str) -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "alembic.ini", *arguments],
            cwd=ROOT / "apps" / "api",
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

    alembic("upgrade", "0025_legacy_branch_catalog_import")
    connection = sa.create_engine(env["RESTAURANTOS_DATABASE_URL"]).connect()
    try:
        columns = {
            column[1] for column in connection.exec_driver_sql("PRAGMA table_info(products)")
        }
        assert {"catalog_scope", "source_branch_id"} <= columns
        tables = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {"legacy_import_batches", "legacy_import_records"} <= tables
    finally:
        connection.close()

    alembic("downgrade", "0024_branch_admin_scope")
    alembic("upgrade", "0025_legacy_branch_catalog_import")
