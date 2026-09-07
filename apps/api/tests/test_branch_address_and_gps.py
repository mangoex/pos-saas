# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-branch-gps-tests-v1
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.auth import create_session_token
from restaurant_os.config import get_settings
from restaurant_os.database import get_session
from restaurant_os.main import create_app
from restaurant_os.models import metadata
from restaurant_os.operations import ORGANIZATION_ID
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    # Seed base organization, legal entity, business unit, and admin user
    now = datetime.now(timezone.utc)
    session.execute(
        models.organizations.insert().values(
            id=ORGANIZATION_ID,
            slug="test-restaurant",
            name="Kiwi Restaurante",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.legal_entities.insert().values(
            id="legal-kiwi-01",
            organization_id=ORGANIZATION_ID,
            name="Kiwi S.A. de C.V.",
            tax_id=None,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.business_units.insert().values(
            id="unit-kiwi-01",
            organization_id=ORGANIZATION_ID,
            legal_entity_id="legal-kiwi-01",
            name="Operaciones Kiwi",
            code="KIWI",
            unit_type="restaurant",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    admin_user_id = "user-admin-01"
    session.execute(
        models.users.insert().values(
            id=admin_user_id,
            organization_id=ORGANIZATION_ID,
            email="admin@kiwi.test",
            display_name="Admin Test",
            employee_code="999001",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    admin_role_id = "role-admin-01"
    session.execute(
        models.roles.insert().values(
            id=admin_role_id,
            organization_id=ORGANIZATION_ID,
            name="Admin Rol",
            scope="organization",
            created_at=now,
        )
    )
    session.execute(
        models.user_roles.insert().values(
            user_id=admin_user_id,
            role_id=admin_role_id,
            branch_id=None,
        )
    )
    # Insert permissions
    for perm_id, perm_code in [
        ("p1", "admin.manage"),
        ("p2", "catalog.manage"),
        ("p3", "orders.read"),
    ]:
        session.execute(
            models.permissions.insert().values(
                id=perm_id,
                code=perm_code,
                description=perm_code,
                created_at=now,
            )
        )
        session.execute(
            models.role_permissions.insert().values(
                role_id=admin_role_id,
                permission_id=perm_id,
            )
        )
    session.commit()

    yield session
    session.close()


@pytest.fixture
def client(test_db: Session):
    app = create_app()

    def override_get_session():
        yield test_db

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_headers():
    settings = get_settings()
    token = create_session_token(
        {
            "sub": "user-admin-01",
            "user_id": "user-admin-01",
            "email": "admin@kiwi.test",
            "roles": ["Admin Rol"],
            "permissions": ["admin.manage", "catalog.manage", "orders.read"],
            "scope": "organization",
        },
        settings.secret_key,
    )
    return {"Authorization": f"Bearer {token}"}


def test_create_and_list_branch_with_address_and_gps(
    client: TestClient, admin_headers: dict[str, str]
):
    payload = {
        "name": "Constitución",
        "code": "SUC07",
        "business_unit_id": "unit-kiwi-01",
        "street": "Av. Constitución",
        "exterior_number": "450",
        "interior_number": "Local 3",
        "neighborhood": "Centro",
        "postal_code": "80000",
        "city": "Culiacán",
        "state": "Sinaloa",
        "cross_streets": "Entre Ruperto Paliza y Domingo Rubí",
        "latitude": 24.8083,
        "longitude": -107.3941,
        "phone": "6671234567",
    }
    response = client.post("/api/v1/branches", json=payload, headers=admin_headers)
    assert response.status_code == 200, response.text
    created = response.json()
    assert created["name"] == "Constitución"
    assert created["code"] == "SUC07"
    assert created["street"] == "Av. Constitución"
    assert created["cross_streets"] == "Entre Ruperto Paliza y Domingo Rubí"
    assert created["latitude"] == 24.8083
    assert created["longitude"] == -107.3941
    assert created["phone"] == "6671234567"

    # List branches
    list_res = client.get("/api/v1/branches", headers=admin_headers)
    assert list_res.status_code == 200
    branches_list = list_res.json()
    assert len(branches_list) >= 1
    branch = next(b for b in branches_list if b["code"] == "SUC07")
    assert branch["street"] == "Av. Constitución"
    assert branch["cross_streets"] == "Entre Ruperto Paliza y Domingo Rubí"
    assert branch["latitude"] == 24.8083
    assert branch["longitude"] == -107.3941


def test_update_branch_address_and_gps(client: TestClient, admin_headers: dict[str, str]):
    # Create first
    create_res = client.post(
        "/api/v1/branches",
        json={"name": "Guadalupe", "code": "SUC02", "business_unit_id": "unit-kiwi-01"},
        headers=admin_headers,
    )
    branch_id = create_res.json()["id"]

    # Update address and GPS
    update_payload = {
        "name": "Guadalupe",
        "code": "SUC02",
        "street": "Río Humaya",
        "exterior_number": "120",
        "neighborhood": "Col. Guadalupe",
        "postal_code": "80220",
        "city": "Culiacán",
        "state": "Sinaloa",
        "cross_streets": "Entre Río Sinaloa y Río San Lorenzo",
        "latitude": 24.7925,
        "longitude": -107.4012,
        "phone": "6679876543",
    }
    update_res = client.put(
        f"/api/v1/branches/{branch_id}", json=update_payload, headers=admin_headers
    )
    assert update_res.status_code == 200, update_res.text
    updated = update_res.json()
    assert updated["street"] == "Río Humaya"
    assert updated["cross_streets"] == "Entre Río Sinaloa y Río San Lorenzo"
    assert updated["latitude"] == 24.7925
    assert updated["longitude"] == -107.4012


def test_public_branches_nearest_calculation(client: TestClient, admin_headers: dict[str, str]):
    # Create two branches at different coordinates in Culiacan
    client.post(
        "/api/v1/branches",
        json={
            "name": "Centro",
            "code": "SUC01",
            "business_unit_id": "unit-kiwi-01",
            "street": "Av. Álvaro Obregón",
            "exterior_number": "100",
            "neighborhood": "Centro",
            "latitude": 24.8080,
            "longitude": -107.3940,
        },
        headers=admin_headers,
    )
    client.post(
        "/api/v1/branches",
        json={
            "name": "La Primavera",
            "code": "SUC06",
            "business_unit_id": "unit-kiwi-01",
            "street": "Paseo de la Primavera",
            "exterior_number": "500",
            "neighborhood": "La Primavera",
            "latitude": 24.7350,
            "longitude": -107.3550,
        },
        headers=admin_headers,
    )

    # 1. Query without location (returns all active branches)
    res = client.get("/api/v1/public/branches?identifier=test-restaurant")
    assert res.status_code == 200
    all_branches = res.json()
    assert len(all_branches) >= 2

    # 2. Query with location near Centro (24.8085, -107.3942)
    res_centro = client.get(
        "/api/v1/public/branches?identifier=test-restaurant&lat=24.8085&lng=-107.3942"
    )
    assert res_centro.status_code == 200
    sorted_branches = res_centro.json()
    assert len(sorted_branches) >= 2
    # Nearest must be Centro
    assert sorted_branches[0]["code"] == "SUC01"
    assert sorted_branches[0]["distance_km"] < 0.2  # less than 200 meters!


def test_legacy_public_order_routing_by_coords_is_fail_closed(
    client: TestClient, admin_headers: dict[str, str], test_db: Session
):
    now = datetime.now(timezone.utc)
    # Create product and price
    session = test_db
    session.execute(
        models.product_categories.insert().values(
            id="cat-01",
            organization_id=ORGANIZATION_ID,
            name="Bebidas",
            display_order=1,
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.products.insert().values(
            id="prod-01",
            organization_id=ORGANIZATION_ID,
            category_id="cat-01",
            sku="JUG-01",
            name="Jugo Verde",
            station="barra",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.price_versions.insert().values(
            id="price-01",
            organization_id=ORGANIZATION_ID,
            product_id="prod-01",
            price_cents=6500,
            currency="MXN",
            valid_from=now,
            created_at=now,
        )
    )
    session.commit()

    # Create two branches
    client.post(
        "/api/v1/branches",
        json={
            "name": "Sucursal Centro",
            "code": "SUC01",
            "business_unit_id": "unit-kiwi-01",
            "latitude": 24.8080,
            "longitude": -107.3940,
        },
        headers=admin_headers,
    )
    client.post(
        "/api/v1/branches",
        json={
            "name": "Sucursal Primavera",
            "code": "SUC06",
            "business_unit_id": "unit-kiwi-01",
            "latitude": 24.7350,
            "longitude": -107.3550,
        },
        headers=admin_headers,
    )

    # The legacy endpoint must not turn routing coordinates into an operational order.
    payload = {
        "owner_name": "Juan Perez",
        "customer_phone": "6671234567",
        "order_type": "dine-in",
        "customer_lat": 24.8082,
        "customer_lng": -107.3941,
        "lines": [{"product_id": "prod-01", "quantity": 2}],
    }
    order_res = client.post("/api/v1/public/orders", json=payload)
    assert order_res.status_code == 503
    assert order_res.json()["detail"]["code"] == "public_order_unavailable"
    assert test_db.execute(models.orders.select()).all() == []
