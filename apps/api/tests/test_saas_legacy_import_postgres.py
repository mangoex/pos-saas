# SEC001-SYNTHETIC-FIXTURE provenance=recovery-c61212672d61
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.legacy_import import create_legacy_import_batch, ingest_legacy_import_records
from restaurant_os.saas_onboarding import signup_tenant
from sqlalchemy.orm import Session, sessionmaker

API_DIR = Path(__file__).resolve().parents[1]


def _migrate(schema: str) -> str:
    url = os.environ["SAAS_TEST_POSTGRES_URL"]
    scoped = str(sa.engine.make_url(url).set(query={"options": f"-csearch_path={schema}"}))
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=API_DIR,
        env={**os.environ, "RESTAURANTOS_DATABASE_URL": scoped},
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return scoped


def _tenant(session: Session, suffix: str) -> dict[str, object]:
    return signup_tenant(
        session,
        {
            "business_name": f"Legacy PG {suffix}",
            "owner_name": f"Owner {suffix}",
            "email": f"legacy-pg-{suffix}@example.test",
            "password": "synthetic-pg-password",
            "business_type": "blank",
        },
    )


def test_postgres_legacy_import_catalog_codes_stay_in_actor_organization() -> None:
    url = os.environ["SAAS_TEST_POSTGRES_URL"]
    schema = f"saas_legacy_import_{uuid4().hex}"
    admin = sa.create_engine(url)
    with admin.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    scoped = _migrate(schema)
    engine = sa.create_engine(scoped)
    factory = sessionmaker(bind=engine)
    try:
        with factory() as session:
            a, b = _tenant(session, "a"), _tenant(session, "b")
            checksum = "d" * 64
            batches = []
            for tenant in (a, b):
                batch = create_legacy_import_batch(
                    session,
                    str(tenant["user"]["id"]),
                    str(tenant["branch"]["id"]),
                    "legacy",
                    checksum,
                    {},
                )
                ingest_legacy_import_records(
                    session,
                    str(tenant["user"]["id"]),
                    str(batch["id"]),
                    [
                        {
                            "entity_type": "inventory_item",
                            "source_key": "shared-item",
                            "normalized_payload": {
                                "sku": "1001",
                                "name": "INSUMO PG",
                                "category_name": "ABARROTE",
                                "unit_code": "PZA",
                            },
                        },
                        {
                            "entity_type": "product",
                            "source_key": "shared-product",
                            "normalized_payload": {
                                "sku": "1002",
                                "name": "PRODUCTO PG",
                                "category_name": "BEBIDAS",
                                "price_cents": 1500,
                            },
                        },
                    ],
                )
                batches.append(batch)
            assert {batch["organization_id"] for batch in batches} == {
                a["organization"]["id"],
                b["organization"]["id"],
            }
            assert session.scalar(
                sa.select(sa.func.count())
                .select_from(models.products)
                .where(models.products.c.sku == "1002")
            ) == 2
            assert session.scalar(
                sa.select(sa.func.count())
                .select_from(models.inventory_units)
                .where(
                    models.inventory_units.c.code == "PIEZA",
                    models.inventory_units.c.organization_id.in_(
                        (a["organization"]["id"], b["organization"]["id"])
                    ),
                )
            ) == 2
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()
