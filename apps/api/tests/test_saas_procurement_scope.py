# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-recovery-test-saas-procurement-scope-synthetic-v1
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import (
    BusinessError,
    cancel_purchase_document,
    confirm_purchase_document,
    create_purchase_document,
    create_purchase_presentation,
    create_supplier,
    get_purchase_document,
    list_purchase_documents,
    list_purchase_presentations,
    list_suppliers,
    set_supplier_branch_terms,
    update_supplier,
)
from restaurant_os.saas_onboarding import signup_tenant
from sqlalchemy.orm import Session

API_DIR = Path(__file__).resolve().parents[1]


def _session(tmp_path: Path) -> tuple[sa.Engine, Session]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'procurement-scope.db'}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=API_DIR,
        env={**os.environ, "RESTAURANTOS_DATABASE_URL": database_url},
        check=True,
        capture_output=True,
        text=True,
    )
    engine = sa.create_engine(database_url)
    return engine, Session(engine)


def _tenant(session: Session, suffix: str) -> dict[str, object]:
    tenant = signup_tenant(
        session,
        {
            "business_name": f"Procurement {suffix}",
            "owner_name": f"Owner {suffix}",
            "email": f"procurement-{suffix}@example.test",
            "password": "synthetic-password",
            "business_type": "blank",
        },
    )
    actor_id = str(tenant["user"]["id"])
    branch_id = str(tenant["branch"]["id"])
    organization_id = str(tenant["organization"]["id"])
    now = sa.func.now()
    unit_id, item_id = str(uuid4()), str(uuid4())
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
            name="INSUMO COMPARTIDO",
            sku="SHARED-ITEM",
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
    return {
        **tenant,
        "actor_id": actor_id,
        "branch_id": branch_id,
        "item": {"id": item_id, "base_unit_id": unit_id},
    }


def _supplier_and_presentation(
    session: Session, tenant: dict[str, object]
) -> tuple[dict[str, object], dict[str, object]]:
    actor_id, branch_id = str(tenant["actor_id"]), str(tenant["branch_id"])
    supplier = create_supplier(
        session,
        {"code": "SHARED-SUP", "commercial_name": "Proveedor Comun", "branch_id": branch_id},
        actor_id,
    )
    presentation = create_purchase_presentation(
        session,
        {
            "supplier_id": supplier["id"],
            "item_id": tenant["item"]["id"],
            "code": "SHARED-PRES",
            "name": "Presentacion Comun",
            "base_unit_id": tenant["item"]["base_unit_id"],
            "commercial_unit_id": tenant["item"]["base_unit_id"],
            "usable_content": "1",
            "last_net_price": "12",
        },
        actor_id,
    )
    return supplier, presentation


def test_procurement_scope_separates_suppliers_presentations_purchases_and_reads(
    tmp_path: Path,
) -> None:
    engine, session = _session(tmp_path)
    try:
        tenant_a, tenant_b = _tenant(session, "a"), _tenant(session, "b")
        supplier_a, presentation_a = _supplier_and_presentation(session, tenant_a)
        supplier_b, presentation_b = _supplier_and_presentation(session, tenant_b)
        assert supplier_a["id"] != supplier_b["id"]
        assert [s["id"] for s in list_suppliers(session, str(tenant_a["actor_id"]))] == [
            supplier_a["id"]
        ]
        assert [
            p["id"] for p in list_purchase_presentations(session, str(tenant_b["actor_id"]))
        ] == [presentation_b["id"]]

        with pytest.raises(BusinessError, match="Supplier was not found"):
            update_supplier(
                session,
                str(supplier_a["id"]),
                {"commercial_name": "Cross"},
                str(tenant_b["actor_id"]),
            )
        with pytest.raises(BusinessError, match="Supplier and branch"):
            set_supplier_branch_terms(
                session,
                str(supplier_a["id"]),
                str(tenant_b["branch_id"]),
                {},
                str(tenant_b["actor_id"]),
            )
        with pytest.raises(BusinessError, match="Item is required"):
            create_purchase_presentation(
                session,
                {"supplier_id": supplier_b["id"], "item_id": tenant_a["item"]["id"]},
                str(tenant_b["actor_id"]),
            )

        purchase_a = create_purchase_document(
            session,
            {
                "branch_id": tenant_a["branch_id"],
                "supplier_id": supplier_a["id"],
                "folio": "SHARED-FOLIO",
                "lines": [
                    {"presentation_id": presentation_a["id"], "quantity": "2", "unit_price": "12"}
                ],
            },
            str(tenant_a["actor_id"]),
        )
        purchase_b = create_purchase_document(
            session,
            {
                "branch_id": tenant_b["branch_id"],
                "supplier_id": supplier_b["id"],
                "folio": "SHARED-FOLIO",
                "lines": [
                    {"presentation_id": presentation_b["id"], "quantity": "2", "unit_price": "12"}
                ],
            },
            str(tenant_b["actor_id"]),
        )
        assert purchase_a["organization_id"] != purchase_b["organization_id"]
        confirm_purchase_document(
            session,
            str(purchase_a["id"]),
            "shared-confirm",
            actor_user_id=str(tenant_a["actor_id"]),
        )
        confirm_purchase_document(
            session,
            str(purchase_b["id"]),
            "shared-confirm",
            actor_user_id=str(tenant_b["actor_id"]),
        )
        with pytest.raises(BusinessError, match="Purchase document was not found"):
            get_purchase_document(session, str(purchase_a["id"]), str(tenant_b["actor_id"]))
        with pytest.raises(BusinessError, match="Purchase document was not found"):
            cancel_purchase_document(
                session, str(purchase_a["id"]), "cross tenant", str(tenant_b["actor_id"])
            )
        assert (
            get_purchase_document(session, str(purchase_a["id"]), str(tenant_a["actor_id"]))[
                "status"
            ]
            == "confirmed"
        )
        assert [
            p["id"]
            for p in list_purchase_documents(
                session, str(tenant_b["branch_id"]), str(tenant_b["actor_id"])
            )
        ] == [purchase_b["id"]]
        assert (
            session.scalar(
                sa.select(sa.func.count())
                .select_from(models.inventory_movements)
                .where(
                    models.inventory_movements.c.organization_id == tenant_a["organization"]["id"],
                    models.inventory_movements.c.source_id == purchase_a["id"],
                )
            )
            == 1
        )
    finally:
        session.close()
        engine.dispose()
