"""Tests for Social Proof, Trending Dishes, and UGC Community Photos."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.auth import create_session_token
from restaurant_os.config import get_settings
from restaurant_os.database import get_session
from restaurant_os.main import create_app
from restaurant_os.operations import ORGANIZATION_ID
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

app = create_app()

USER_ID = "018f6f73-2d0a-74f0-8f1c-000000000003"
ROLE_ID = "018f6f73-2d0a-74f0-8f1c-000000000004"
BRANCH_ID = "018f6f73-2d0a-74f0-8f1c-000000000005"
PUBLIC_KEY = "pk_test_branch_social_123"

PRODUCT_A_ID = "018f6f73-2d0a-74f0-8f1c-000000000010"
PRODUCT_B_ID = "018f6f73-2d0a-74f0-8f1c-000000000020"


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    now = datetime.now(timezone.utc)
    session.execute(
        models.organizations.insert().values(
            id=ORGANIZATION_ID,
            slug="taqueria-mexico",
            name="Taquería México",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    legal_id = str(uuid.uuid4())
    session.execute(
        models.legal_entities.insert().values(
            id=legal_id,
            organization_id=ORGANIZATION_ID,
            name="Taquería México SA de CV",
            created_at=now,
            updated_at=now,
        )
    )
    bu_id = str(uuid.uuid4())
    session.execute(
        models.business_units.insert().values(
            id=bu_id,
            organization_id=ORGANIZATION_ID,
            legal_entity_id=legal_id,
            name="Restaurantes",
            code="REST",
            unit_type="restaurant",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.branches.insert().values(
            id=BRANCH_ID,
            organization_id=ORGANIZATION_ID,
            legal_entity_id=legal_id,
            business_unit_id=bu_id,
            code="SC",
            name="Sucursal Centro",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.public_order_keys.insert().values(
            public_key=PUBLIC_KEY,
            organization_id=ORGANIZATION_ID,
            branch_id=BRANCH_ID,
            status="active",
            created_at=now,
        )
    )
    session.execute(
        models.users.insert().values(
            id=USER_ID,
            organization_id=ORGANIZATION_ID,
            email="owner@taqueria.com",
            display_name="Dueño Taquería",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.roles.insert().values(
            id=ROLE_ID,
            organization_id=ORGANIZATION_ID,
            name="Administrador",
            scope="organization",
            created_at=now,
        )
    )
    session.execute(models.user_roles.insert().values(user_id=USER_ID, role_id=ROLE_ID))
    for perm in ["admin.manage", "catalog.manage", "orders.read", "orders.create"]:
        perm_id = str(uuid.uuid4())
        session.execute(
            models.permissions.insert().values(
                id=perm_id, code=perm, description=perm, created_at=now
            )
        )
        session.execute(
            models.role_permissions.insert().values(role_id=ROLE_ID, permission_id=perm_id)
        )

    # Categories and Products
    cat_id = str(uuid.uuid4())
    session.execute(
        models.product_categories.insert().values(
            id=cat_id,
            organization_id=ORGANIZATION_ID,
            name="Tacos y Especialidades",
            display_order=1,
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.products.insert().values(
            id=PRODUCT_A_ID,
            organization_id=ORGANIZATION_ID,
            category_id=cat_id,
            name="Tacos al Pastor Deluxe",
            sku="TAC-001",
            station="cocina",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.price_versions.insert().values(
            id=str(uuid.uuid4()),
            organization_id=ORGANIZATION_ID,
            product_id=PRODUCT_A_ID,
            price_cents=12000,
            currency="MXN",
            valid_from=now,
            valid_to=None,
            created_at=now,
        )
    )
    session.execute(
        models.products.insert().values(
            id=PRODUCT_B_ID,
            organization_id=ORGANIZATION_ID,
            category_id=cat_id,
            name="Gringa Especial",
            sku="TAC-002",
            station="cocina",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.price_versions.insert().values(
            id=str(uuid.uuid4()),
            organization_id=ORGANIZATION_ID,
            product_id=PRODUCT_B_ID,
            price_cents=9500,
            currency="MXN",
            valid_from=now,
            valid_to=None,
            created_at=now,
        )
    )

    session.commit()
    yield session
    session.close()


@pytest.fixture
def client(test_db):
    def override_get_session():
        yield test_db

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_headers(test_db):
    settings = get_settings()
    token = create_session_token(
        {"sub": USER_ID, "org_id": ORGANIZATION_ID, "role": "owner"},
        settings.secret_key,
    )
    return {"Authorization": f"Bearer {token}"}


def test_trending_dishes_with_orders_and_social_proof(test_db, client):
    now = datetime.now(timezone.utc)
    # Create orders to establish popularity: 3 orders for Product A, 1 for Product B
    for i in range(3):
        order_id = str(uuid.uuid4())
        test_db.execute(
            models.orders.insert().values(
                id=order_id,
                organization_id=ORGANIZATION_ID,
                branch_id=BRANCH_ID,
                folio=f"ORD-A-{i}",
                channel="UBER_EATS",
                status="COMPLETED",
                total_cents=12000,
                created_at=now,
            )
        )
        test_db.execute(
            models.order_lines.insert().values(
                id=str(uuid.uuid4()),
                order_id=order_id,
                product_id=PRODUCT_A_ID,
                product_name="Tacos al Pastor Deluxe",
                quantity=2,
                unit_price_cents=6000,
                line_total_cents=12000,
                station="cocina",
                family_id_snapshot="tacos",
                family_name_snapshot="Tacos",
                family_snapshot_source="captured",
                created_at=now,
            )
        )

    order_id_b = str(uuid.uuid4())
    test_db.execute(
        models.orders.insert().values(
            id=order_id_b,
            organization_id=ORGANIZATION_ID,
            branch_id=BRANCH_ID,
            folio="ORD-B-1",
            channel="UBER_EATS",
            status="COMPLETED",
            total_cents=9500,
            created_at=now,
        )
    )
    test_db.execute(
        models.order_lines.insert().values(
            id=str(uuid.uuid4()),
            order_id=order_id_b,
            product_id=PRODUCT_B_ID,
            product_name="Gringa Especial",
            quantity=1,
            unit_price_cents=9500,
            line_total_cents=9500,
            station="cocina",
            family_id_snapshot="tacos",
            family_name_snapshot="Tacos",
            family_snapshot_source="captured",
            created_at=now,
        )
    )
    test_db.commit()

    resp = client.get(f"/api/v1/public/branches/{PUBLIC_KEY}/trending-dishes")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "trending_dishes" in data
    dishes = data["trending_dishes"]
    assert len(dishes) >= 2

    # Product A must be ranked #1
    top_dish = dishes[0]
    assert top_dish["id"] == PRODUCT_A_ID
    assert top_dish["order_count"] >= 6  # 3 orders * 2 quantity
    assert "🔥" in top_dish["badge"]
    assert top_dish["rank"] == 1

    # Product B must be ranked #2
    second_dish = dishes[1]
    assert second_dish["id"] == PRODUCT_B_ID
    assert second_dish["rank"] == 2


def test_customer_submits_ugc_photo_and_admin_moderates(test_db, client, admin_headers):
    # 1. Customer submits photo after checkout
    payload = {
        "product_id": PRODUCT_A_ID,
        "order_folio": "FOLIO-7890",
        "customer_name": "Sofía Morales",
        "customer_phone": "5544332211",
        "image_url": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD...",
        "caption": "¡Increíble sazón, 100% recomendados!",
    }
    submit_resp = client.post(
        f"/api/v1/public/branches/{PUBLIC_KEY}/community-photos",
        json=payload,
    )
    assert submit_resp.status_code in (200, 201), submit_resp.text
    submit_data = submit_resp.json()
    assert submit_data["status"] == "pending"
    assert submit_data["discount_code"] == "MIMENU-GRACIAS10"
    photo_id = submit_data["id"]

    # 2. Public product photo feed must NOT show pending photo
    public_photos_resp = client.get(
        f"/api/v1/public/branches/{PUBLIC_KEY}/products/{PRODUCT_A_ID}/community-photos"
    )
    assert public_photos_resp.status_code == 200
    assert len(public_photos_resp.json()) == 0

    # 3. Admin lists pending photos
    admin_list_resp = client.get(
        "/api/v1/admin/community-photos?status=pending",
        headers=admin_headers,
    )
    assert admin_list_resp.status_code == 200
    pending_photos = admin_list_resp.json()
    assert any(p["id"] == photo_id for p in pending_photos)

    # 4. Admin approves the photo
    moderate_resp = client.patch(
        f"/api/v1/admin/community-photos/{photo_id}/status",
        headers=admin_headers,
        json={"status": "approved"},
    )
    assert moderate_resp.status_code == 200
    assert moderate_resp.json()["status"] == "approved"

    # 5. Public product photo feed now returns the approved photo
    approved_photos_resp = client.get(
        f"/api/v1/public/branches/{PUBLIC_KEY}/products/{PRODUCT_A_ID}/community-photos"
    )
    assert approved_photos_resp.status_code == 200
    approved_list = approved_photos_resp.json()
    assert len(approved_list) == 1
    assert approved_list[0]["id"] == photo_id
    assert approved_list[0]["customer_name"] == "Sofía Morales"
    assert approved_list[0]["caption"] == "¡Increíble sazón, 100% recomendados!"


def test_cross_tenant_isolation_for_community_photos(test_db, client):
    # Create Tenant B
    now = datetime.now(timezone.utc)
    tenant_b_org_id = str(uuid.uuid4())
    tenant_b_user_id = str(uuid.uuid4())
    test_db.execute(
        models.organizations.insert().values(
            id=tenant_b_org_id,
            slug="pizzeria-roma",
            name="Pizzería Roma",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.users.insert().values(
            id=tenant_b_user_id,
            organization_id=tenant_b_org_id,
            email="owner@roma.com",
            display_name="Dueño Roma",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.commit()

    token_b = create_session_token(
        {"sub": tenant_b_user_id, "org_id": tenant_b_org_id, "role": "owner"},
        get_settings().secret_key,
    )
    tenant_b_headers = {"Authorization": f"Bearer {token_b}"}

    # Tenant B should see 0 photos from Tenant A
    list_resp = client.get("/api/v1/admin/community-photos", headers=tenant_b_headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 0

