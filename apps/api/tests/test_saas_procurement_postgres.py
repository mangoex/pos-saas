# SEC001-SYNTHETIC-FIXTURE provenance=recovery-aed286ad2494
from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import (
    confirm_purchase_document,
    create_purchase_document,
    create_purchase_presentation,
    create_supplier,
)
from restaurant_os.saas_onboarding import signup_tenant
from sqlalchemy.orm import Session, sessionmaker

API_DIR = Path(__file__).resolve().parents[1]


def _migrate(schema: str) -> str:
    url = os.environ["SAAS_TEST_POSTGRES_URL"]
    scoped = (
        sa.engine.make_url(url)
        .set(query={"options": f"-csearch_path={schema}"})
        .render_as_string(hide_password=False)
    )
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


def _seed_purchase(session: Session) -> tuple[str, str]:
    tenant = signup_tenant(
        session,
        {
            "business_name": "Procurement concurrency",
            "owner_name": "Owner",
            "email": "procurement-concurrency@example.test",
            "password": "synthetic-password",
            "business_type": "blank",
        },
    )
    organization_id = str(tenant["organization"]["id"])
    actor_id = str(tenant["user"]["id"])
    branch_id = str(tenant["branch"]["id"])
    unit_id, item_id = str(uuid4()), str(uuid4())
    now = sa.func.now()
    session.execute(
        models.inventory_units.insert().values(
            id=unit_id,
            organization_id=organization_id,
            code="PZA",
            name="Pieza",
            dimension="unit",
            precision_scale=0,
            created_at=now,
        )
    )
    session.execute(
        models.inventory_items.insert().values(
            id=item_id,
            organization_id=organization_id,
            name="Insumo",
            sku="PG-RACE",
            base_unit_id=unit_id,
            item_type="ingredient",
            catalog_scope="organization",
            source_branch_id=None,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    supplier = create_supplier(
        session,
        {
            "code": "PG-RACE",
            "commercial_name": "Proveedor",
            "branch_id": branch_id,
        },
        actor_id,
    )
    presentation = create_purchase_presentation(
        session,
        {
            "supplier_id": supplier["id"],
            "item_id": item_id,
            "code": "PG-RACE",
            "name": "Presentacion",
            "base_unit_id": unit_id,
            "commercial_unit_id": unit_id,
            "usable_content": "1",
            "last_net_price": "7",
        },
        actor_id,
    )
    purchase = create_purchase_document(
        session,
        {
            "branch_id": branch_id,
            "supplier_id": supplier["id"],
            "folio": "PG-RACE",
            "lines": [{"presentation_id": presentation["id"], "quantity": "2", "unit_price": "7"}],
        },
        actor_id,
    )
    return str(purchase["id"]), actor_id


def test_postgres_purchase_confirmation_same_target_is_serialized() -> None:
    if not os.environ.get("SAAS_TEST_POSTGRES_URL"):
        return
    url = os.environ["SAAS_TEST_POSTGRES_URL"]
    schema = f"saas_procurement_{uuid4().hex}"
    admin = sa.create_engine(url)
    with admin.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    engine: sa.Engine | None = None
    try:
        engine = sa.create_engine(_migrate(schema), pool_pre_ping=True)
        factory = sessionmaker(bind=engine)
        with factory() as session:
            purchase_id, actor_id = _seed_purchase(session)
        barrier = Barrier(2)

        def confirm() -> dict[str, object]:
            with factory() as session:
                barrier.wait()
                return confirm_purchase_document(
                    session, purchase_id, "same-command", actor_user_id=actor_id
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: confirm(), range(2)))
        assert {result["status"] for result in results} == {"confirmed"}
        with factory() as session:
            assert (
                session.scalar(
                    sa.select(sa.func.count())
                    .select_from(models.inventory_movements)
                    .where(models.inventory_movements.c.source_id == purchase_id)
                )
                == 1
            )
            assert (
                session.scalar(
                    sa.select(sa.func.count())
                    .select_from(models.purchase_documents)
                    .where(
                        models.purchase_documents.c.confirmation_idempotency_key == "same-command"
                    )
                )
                == 1
            )
    finally:
        if engine is not None:
            engine.dispose()
        with admin.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()
