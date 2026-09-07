"""TDD test suite for extended supplier fields (phone, supplier_type, address, postal_code, email, status, accounting_reference)."""

# ruff: noqa: E501

from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.database import get_session
from restaurant_os.main import create_app
from restaurant_os.operations import (
    ORGANIZATION_ID,
    create_supplier,
    delete_supplier,
    list_suppliers,
    update_supplier,
)
from sqlalchemy.orm import Session

SUPERADMIN_ID = "018f6f73-2d0a-74f0-8f1c-000000000002"


@pytest.fixture
def setup_db(tmp_path: Path):
    db_path = tmp_path / "test_suppliers.db"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    models.metadata.create_all(engine)
    now = sa.func.now()
    with Session(engine) as session:
        session.execute(models.organizations.insert().values(
            id=ORGANIZATION_ID,
            name="Kiwi Natural Org",
            status="active",
            created_at=now,
            updated_at=now,
        ))
        session.execute(models.users.insert().values(
            id=SUPERADMIN_ID,
            organization_id=ORGANIZATION_ID,
            email="superadmin@kiwi.local",
            display_name="Super Admin",
            status="active",
            created_at=now,
            updated_at=now,
        ))
        session.execute(models.permissions.insert().values([
            {"id": "p1", "code": "catalog.manage", "description": "Manage catalog", "created_at": now},
            {"id": "p2", "code": "purchases.read", "description": "Read purchases", "created_at": now},
            {"id": "p3", "code": "admin.manage", "description": "Manage admin", "created_at": now},
        ]))
        session.execute(models.roles.insert().values(
            id="r-admin",
            organization_id=ORGANIZATION_ID,
            name="Dueño",
            scope="organization",
            created_at=now,
        ))
        session.execute(models.role_permissions.insert().values([
            {"role_id": "r-admin", "permission_id": "p1"},
            {"role_id": "r-admin", "permission_id": "p2"},
            {"role_id": "r-admin", "permission_id": "p3"},
        ]))
        session.execute(models.user_roles.insert().values(
            user_id=SUPERADMIN_ID,
            role_id="r-admin",
            branch_id=None,
        ))
        session.commit()
    return engine


def test_create_supplier_with_all_extended_fields(setup_db: sa.Engine):
    with Session(setup_db) as session:
        supplier = create_supplier(
            session,
            payload={
                "code": "PROV-001",
                "commercial_name": "Carnes Selectas de Culiacan",
                "legal_name": "Carnes del Noroeste SA de CV",
                "tax_id": "CNO900101XYZ",
                "address": "Av. Alvaro Obregon 1234, Col. Centro",
                "postal_code": "80000",
                "municipality": "Culiacan",
                "state": "Sinaloa",
                "phone": "6671234567",
                "email": "ventas@carnesnoroeste.com",
                "supplier_type": "insumos",
                "status": "active",
                "accounting_reference": "201-01-001",
                "credit_days": 15,
            },
            actor_user_id=SUPERADMIN_ID,
        )

        assert supplier["code"] == "PROV-001"
        assert supplier["commercial_name"] == "Carnes Selectas de Culiacan"
        assert supplier["fiscal_address"] == "Av. Alvaro Obregon 1234, Col. Centro"
        assert supplier["fiscal_postal_code"] == "80000"
        assert supplier["phone"] == "6671234567"
        assert supplier["billing_email"] == "ventas@carnesnoroeste.com"
        assert supplier["supplier_type"] == "insumos"
        assert supplier["status"] == "active"
        assert supplier["accounting_reference"] == "201-01-001"
        assert supplier["credit_days"] == 15


def test_update_supplier_extended_fields(setup_db: sa.Engine):
    with Session(setup_db) as session:
        supplier = create_supplier(
            session,
            payload={
                "code": "PROV-002",
                "commercial_name": "Empaques Sinaloa",
                "phone": "6677000000",
                "supplier_type": "empaque",
            },
            actor_user_id=SUPERADMIN_ID,
        )

        updated = update_supplier(
            session,
            supplier_id=supplier["id"],
            payload={
                "phone": "6679998877",
                "address": "Blvd. Zapata 555, Col. El Palmito",
                "postal_code": "80160",
                "email": "contacto@empaquessinaloa.com",
                "accounting_reference": "201-02-005",
                "status": "active",
            },
            actor_user_id=SUPERADMIN_ID,
        )

        assert updated["phone"] == "6679998877"
        assert updated["fiscal_address"] == "Blvd. Zapata 555, Col. El Palmito"
        assert updated["fiscal_postal_code"] == "80160"
        assert updated["billing_email"] == "contacto@empaquessinaloa.com"
        assert updated["accounting_reference"] == "201-02-005"


def test_delete_supplier_deactivates(setup_db: sa.Engine):
    with Session(setup_db) as session:
        # 1. Unreferenced supplier gets deleted
        supplier = create_supplier(
            session,
            payload={
                "code": "PROV-003",
                "commercial_name": "Servicios de Limpieza",
                "supplier_type": "servicios",
            },
            actor_user_id=SUPERADMIN_ID,
        )

        res = delete_supplier(session, supplier["id"], actor_user_id=SUPERADMIN_ID)
        assert res["status"] == "deleted"
        assert res["deleted"] is True

        all_suppliers = list_suppliers(session, SUPERADMIN_ID)
        assert not any(s["id"] == supplier["id"] for s in all_suppliers)

        # 2. Referenced supplier gets deactivated (marked inactive)
        supplier2 = create_supplier(
            session,
            payload={
                "code": "PROV-REF",
                "commercial_name": "Carnes del Norte",
                "supplier_type": "insumos",
            },
            actor_user_id=SUPERADMIN_ID,
        )
        now = sa.func.now()
        # insert presentation referencing supplier2
        session.execute(models.purchase_presentations.insert().values(
            id="018f6f73-2d0a-74f0-8f1c-pres00000001",
            organization_id=ORGANIZATION_ID,
            supplier_id=supplier2["id"],
            item_id="018f6f73-2d0a-74f0-8f1c-000000000020",
            base_unit_id="018f6f73-2d0a-74f0-8f1c-000000000030",
            commercial_unit_id="018f6f73-2d0a-74f0-8f1c-000000000030",
            code="PRES-CARNE-01",
            name="Caja Carne 10kg",
            package_type="box",
            commercial_quantity=1,
            usable_content=10.0,
            base_unit_yield=10,
            yield_percent=1,
            last_net_price=1500,
            cost_per_base_unit=150.0,
            tax_rate=0,
            status="active",
            created_at=now,
            updated_at=now,
        ))
        session.commit()

        res2 = delete_supplier(session, supplier2["id"], actor_user_id=SUPERADMIN_ID)
        assert res2["status"] == "inactive"
        assert res2["deleted"] is False

        all_suppliers2 = list_suppliers(session, SUPERADMIN_ID)
        matching2 = next(s for s in all_suppliers2 if s["id"] == supplier2["id"])
        assert matching2["status"] == "inactive"


def test_supplier_api_endpoints(setup_db: sa.Engine):
    app = create_app()

    def override_session():
        with Session(setup_db) as s:
            yield s

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)
    headers = {"X-Actor-User-Id": SUPERADMIN_ID}

    # POST create
    post_res = client.post(
        "/api/v1/suppliers",
        json={
            "code": "PROV-API-01",
            "commercial_name": "Frutería La Palma",
            "tax_id": "FLP880101ABC",
            "address": "Mercado de Abastos Nave 3 Loc 12",
            "postal_code": "80290",
            "phone": "6673334455",
            "email": "abastos@fruterialapalma.com",
            "supplier_type": "insumos",
            "status": "active",
            "accounting_reference": "201-01-045",
        },
        headers=headers,
    )
    assert post_res.status_code == 200, post_res.text
    supplier_id = post_res.json()["id"]

    # PUT update
    put_res = client.put(
        f"/api/v1/suppliers/{supplier_id}",
        json={
            "phone": "6679991122",
            "notes": "Entrega de 6 a 9 am",
        },
        headers=headers,
    )
    assert put_res.status_code == 200, put_res.text
    assert put_res.json()["phone"] == "6679991122"

    # GET list
    get_res = client.get("/api/v1/suppliers", headers=headers)
    assert get_res.status_code == 200
    items = get_res.json()
    item = next(s for s in items if s["id"] == supplier_id)
    assert item["phone"] == "6679991122"
    assert item["fiscal_address"] == "Mercado de Abastos Nave 3 Loc 12"
    assert item["accounting_reference"] == "201-01-045"
    assert item["supplier_type"] == "insumos"

    # DELETE (unreferenced supplier gets deleted)
    del_res = client.delete(f"/api/v1/suppliers/{supplier_id}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["status"] in {"inactive", "deleted"}

    # Verify supplier is no longer in active list
    get_res2 = client.get("/api/v1/suppliers", headers=headers)
    assert get_res2.status_code == 200
    assert not any(s["id"] == supplier_id for s in get_res2.json())

    app.dependency_overrides.clear()


def test_create_supplier_with_mandatory_fields_only(setup_db: sa.Engine):
    """Verifies that creating a supplier with only code and commercial_name succeeds with valid defaults."""
    with Session(setup_db) as session:
        supplier = create_supplier(
            session,
            payload={
                "code": "PROV-MANDATORY",
                "commercial_name": "Coca Cola FEMSA",
            },
            actor_user_id=SUPERADMIN_ID,
        )
        assert supplier["code"] == "PROV-MANDATORY"
        assert supplier["commercial_name"] == "Coca Cola FEMSA"
        assert supplier["status"] == "active"
        assert supplier["supplier_type"] == "insumos"
        assert supplier["credit_days"] == 0
        assert supplier["fiscal_address"] is None
        assert supplier["billing_email"] is None


def test_create_supplier_by_branch_scoped_manager(setup_db: sa.Engine):
    """Verifies that a user assigned to a specific branch with catalog.manage or purchases.manage can create suppliers."""
    branch_user_id = "018f6f73-2d0a-74f0-8f1c-branch000001"
    branch_id = "018f6f73-2d0a-74f0-8f1c-branch000002"
    legal_entity_id = "018f6f73-2d0a-74f0-8f1c-legal0000001"
    business_unit_id = "018f6f73-2d0a-74f0-8f1c-bu000000001"
    now = sa.func.now()
    with Session(setup_db) as session:
        session.execute(models.legal_entities.insert().values(
            id=legal_entity_id,
            organization_id=ORGANIZATION_ID,
            name="Kiwi Natural S.A. de C.V.",
            tax_id="KNA200101XYZ",
            status="active",
            created_at=now,
            updated_at=now,
        ))
        session.execute(models.business_units.insert().values(
            id=business_unit_id,
            organization_id=ORGANIZATION_ID,
            legal_entity_id=legal_entity_id,
            name="Restaurantes Kiwi",
            code="BU-REST",
            unit_type="restaurant",
            status="active",
            created_at=now,
            updated_at=now,
        ))
        session.execute(models.branches.insert().values(
            id=branch_id,
            organization_id=ORGANIZATION_ID,
            legal_entity_id=legal_entity_id,
            business_unit_id=business_unit_id,
            name="La Primavera",
            code="PRIM",
            status="active",
            created_at=now,
            updated_at=now,
        ))
        session.execute(models.users.insert().values(
            id=branch_user_id,
            organization_id=ORGANIZATION_ID,
            email="manager.primavera@kiwi.local",
            display_name="Encargado Primavera",
            status="active",
            created_at=now,
            updated_at=now,
        ))
        session.execute(models.roles.insert().values(
            id="r-branch-mgr",
            organization_id=ORGANIZATION_ID,
            name="Encargado Sucursal",
            scope="branch",
            created_at=now,
        ))
        session.execute(models.role_permissions.insert().values([
            {"role_id": "r-branch-mgr", "permission_id": "p1"},  # catalog.manage
            {"role_id": "r-branch-mgr", "permission_id": "p2"},  # purchases.read
        ]))
        session.execute(models.user_roles.insert().values(
            user_id=branch_user_id,
            role_id="r-branch-mgr",
            branch_id=branch_id,
        ))
        session.commit()

    app = create_app()
    def override_get_session():
        with Session(setup_db) as session:
            yield session
    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)
    headers = {"x-actor-user-id": branch_user_id}

    post_res = client.post(
        "/api/v1/suppliers",
        json={
            "code": "PROV-PRIM-01",
            "commercial_name": "Panadería Local Culiacán",
            "branch_id": branch_id,
        },
        headers=headers,
    )
    assert post_res.status_code == 200, post_res.text
    assert post_res.json()["code"] == "PROV-PRIM-01"
    app.dependency_overrides.clear()

