"""Tests for category display_order persistence, reordering endpoint, and digital menu projections."""

import uuid
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.auth import create_session_token
from restaurant_os.config import get_settings
from restaurant_os.database import get_session
from restaurant_os.main import create_app
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

app = create_app()

ORGANIZATION_ID = "org-cat-reorder-test"
BRANCH_ID = "branch-cat-reorder-test"
USER_ID = "user-cat-reorder-test"
ROLE_ID = "role-cat-reorder-test"


@pytest.fixture
def test_db():
    engine = sa.create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    now = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)

    # 1. Organization, Legal Entity, Business Unit
    session.execute(
        models.organizations.insert().values(
            id=ORGANIZATION_ID,
            name="Restaurante Categoria Reorder Test",
            slug="cat-reorder-test",
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
            name="Restaurante Cat SA de CV",
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
            name="Unidad Cat Restaurante",
            code="UCR-01",
            unit_type="restaurant",
            created_at=now,
            updated_at=now,
        )
    )

    # 2. Branch
    session.execute(
        models.branches.insert().values(
            id=BRANCH_ID,
            organization_id=ORGANIZATION_ID,
            legal_entity_id=legal_id,
            business_unit_id=bu_id,
            name="Sucursal Principal Cat",
            code="SUC-CAT-01",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )

    # 3. User & Role with catalog.manage
    session.execute(
        models.users.insert().values(
            id=USER_ID,
            organization_id=ORGANIZATION_ID,
            email="admin@cat-reorder.test",
            display_name="Admin Cat Reorder",
            status="active",
            is_superadmin=False,
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.roles.insert().values(
            id=ROLE_ID,
            organization_id=ORGANIZATION_ID,
            name="Administrator",
            scope="organization",
            created_at=now,
        )
    )
    session.execute(
        models.user_roles.insert().values(
            user_id=USER_ID,
            role_id=ROLE_ID,
        )
    )
    session.execute(
        models.role_authority_grants.insert().values(
            role_id=ROLE_ID,
            authority_kind="organization_all_permissions",
            created_at=now,
        )
    )

    # 4. Public branch key for public catalog
    public_key = "pubkey-cat-reorder-123"
    session.execute(
        models.public_order_keys.insert().values(
            public_key=public_key,
            organization_id=ORGANIZATION_ID,
            branch_id=BRANCH_ID,
            status="active",
            created_at=now,
        )
    )

    # 5. Three Categories:
    # Alphabetical order: Bebidas (A) -> Postres (B) -> Tacos (C).
    # But initial display_order: Tacos (10) -> Bebidas (20) -> Postres (30)!
    cat_tacos_id = str(uuid.uuid4())
    cat_bebidas_id = str(uuid.uuid4())
    cat_postres_id = str(uuid.uuid4())

    session.execute(
        models.product_categories.insert().values(
            id=cat_tacos_id,
            organization_id=ORGANIZATION_ID,
            name="Tacos al Pastor",
            display_order=10,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.product_categories.insert().values(
            id=cat_bebidas_id,
            organization_id=ORGANIZATION_ID,
            name="Bebidas Frías",
            display_order=20,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.product_categories.insert().values(
            id=cat_postres_id,
            organization_id=ORGANIZATION_ID,
            name="Postres Caseros",
            display_order=30,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )

    # Products for testing category ordering in public catalog:
    # 1 taco, 1 bebida, 1 postre
    prod_taco_id = str(uuid.uuid4())
    session.execute(
        models.products.insert().values(
            id=prod_taco_id,
            organization_id=ORGANIZATION_ID,
            category_id=cat_tacos_id,
            name="Orden de Tacos",
            sku="TAC-01",
            station="kitchen",
            status="active",
            display_order=10,
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.price_versions.insert().values(
            id=str(uuid.uuid4()),
            organization_id=ORGANIZATION_ID,
            product_id=prod_taco_id,
            price_cents=8500,
            currency="MXN",
            valid_from=now,
            created_at=now,
        )
    )

    prod_bebida_id = str(uuid.uuid4())
    session.execute(
        models.products.insert().values(
            id=prod_bebida_id,
            organization_id=ORGANIZATION_ID,
            category_id=cat_bebidas_id,
            name="Agua de Horchata",
            sku="BEB-01",
            station="kitchen",
            status="active",
            display_order=10,
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.price_versions.insert().values(
            id=str(uuid.uuid4()),
            organization_id=ORGANIZATION_ID,
            product_id=prod_bebida_id,
            price_cents=3500,
            currency="MXN",
            valid_from=now,
            created_at=now,
        )
    )

    session.commit()
    yield {
        "session": session,
        "cat_tacos_id": cat_tacos_id,
        "cat_bebidas_id": cat_bebidas_id,
        "cat_postres_id": cat_postres_id,
        "public_key": public_key,
    }
    session.close()


def _auth_headers():
    token = create_session_token(
        {"sub": USER_ID, "org_id": ORGANIZATION_ID, "role": "admin"},
        get_settings().secret_key,
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Actor-User-Id": USER_ID,
        "Content-Type": "application/json",
    }


def test_categories_ordered_by_display_order_in_admin_and_public_catalog(test_db):
    """Verify categories project by display_order instead of alphabetical."""
    session = test_db["session"]

    def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)
    headers = _auth_headers()

    # 1. Fetch admin categories: Tacos (10) -> Bebidas (20) -> Postres (30)
    res = client.get("/api/v1/catalog/categories", headers=headers)
    assert res.status_code == 200
    cats = res.json()
    assert len(cats) == 3
    assert cats[0]["id"] == test_db["cat_tacos_id"]
    assert cats[0]["name"] == "Tacos al Pastor"
    assert cats[0]["display_order"] == 10
    assert cats[1]["id"] == test_db["cat_bebidas_id"]
    assert cats[1]["display_order"] == 20
    assert cats[2]["id"] == test_db["cat_postres_id"]
    assert cats[2]["display_order"] == 30

    # 2. Fetch public catalog: categories array must follow display_order
    pub_res = client.get(f"/api/v1/public/branches/{test_db['public_key']}/catalog")
    assert pub_res.status_code == 200
    pub_cats = pub_res.json()["categories"]
    assert len(pub_cats) == 3
    assert pub_cats[0]["id"] == test_db["cat_tacos_id"]
    assert pub_cats[1]["id"] == test_db["cat_bebidas_id"]
    assert pub_cats[2]["id"] == test_db["cat_postres_id"]


def test_reorder_catalog_categories_endpoint(test_db):
    """Reorder via PUT /catalog/categories/reorder updates display_order atomically."""
    session = test_db["session"]

    def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)
    headers = _auth_headers()

    # Move Postres to 10, Bebidas to 20, Tacos to 30
    reorder_payload = {
        "items": [
            {"id": test_db["cat_postres_id"], "display_order": 10},
            {"id": test_db["cat_bebidas_id"], "display_order": 20},
            {"id": test_db["cat_tacos_id"], "display_order": 30},
        ]
    }
    reorder_res = client.put(
        "/api/v1/catalog/categories/reorder",
        headers=headers,
        json=reorder_payload,
    )
    assert reorder_res.status_code == 200
    assert reorder_res.json()["status"] == "ok"
    assert reorder_res.json()["updated_count"] == 3

    # Verify new order in admin categories
    res = client.get("/api/v1/catalog/categories", headers=headers)
    assert res.status_code == 200
    cats = res.json()
    assert cats[0]["id"] == test_db["cat_postres_id"]
    assert cats[0]["display_order"] == 10
    assert cats[1]["id"] == test_db["cat_bebidas_id"]
    assert cats[1]["display_order"] == 20
    assert cats[2]["id"] == test_db["cat_tacos_id"]
    assert cats[2]["display_order"] == 30

    # Verify new order in public catalog
    pub_res = client.get(f"/api/v1/public/branches/{test_db['public_key']}/catalog")
    assert pub_res.status_code == 200
    pub_cats = pub_res.json()["categories"]
    assert pub_cats[0]["id"] == test_db["cat_postres_id"]
    assert pub_cats[1]["id"] == test_db["cat_bebidas_id"]
    assert pub_cats[2]["id"] == test_db["cat_tacos_id"]

    # Also test alias route /api/v1/categories/reorder
    alias_payload = {
        "items": [
            {"id": test_db["cat_bebidas_id"], "display_order": 10},
            {"id": test_db["cat_postres_id"], "display_order": 20},
            {"id": test_db["cat_tacos_id"], "display_order": 30},
        ]
    }
    alias_res = client.put(
        "/api/v1/categories/reorder",
        headers=headers,
        json=alias_payload,
    )
    assert alias_res.status_code == 200
    cats = client.get("/api/v1/catalog/categories", headers=headers).json()
    assert cats[0]["id"] == test_db["cat_bebidas_id"]


def test_reorder_categories_rejects_foreign_or_missing_category(test_db):
    """Reordering rejects categories from other tenants or non-existent IDs."""
    session = test_db["session"]

    def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)
    headers = _auth_headers()

    foreign_id = str(uuid.uuid4())
    reorder_payload = {
        "items": [
            {"id": foreign_id, "display_order": 10},
        ]
    }
    res = client.put("/api/v1/catalog/categories/reorder", headers=headers, json=reorder_payload)
    assert res.status_code in (404, 400, 422)
