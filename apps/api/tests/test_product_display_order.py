"""Tests for product display_order persistence, reordering endpoint, and catalog projections."""

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

ORGANIZATION_ID = "org-reorder-test"
BRANCH_ID = "branch-reorder-test"
USER_ID = "user-reorder-test"
ROLE_ID = "role-reorder-test"


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

    now = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)

    # 1. Organization, Legal Entity, Business Unit
    session.execute(
        models.organizations.insert().values(
            id=ORGANIZATION_ID,
            name="Restaurante Reorder Test",
            slug="reorder-test",
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
            name="Restaurante SA de CV",
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
            name="Unidad Restaurante",
            code="UR-01",
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
            name="Sucursal Principal",
            code="SUC-01",
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
            email="admin@reorder.test",
            display_name="Admin Reorder",
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
    public_key = "pubkey-reorder-123"
    session.execute(
        models.public_order_keys.insert().values(
            public_key=public_key,
            organization_id=ORGANIZATION_ID,
            branch_id=BRANCH_ID,
            status="active",
            created_at=now,
        )
    )


    # 5. Category "Roles"
    cat_id = str(uuid.uuid4())
    session.execute(
        models.product_categories.insert().values(
            id=cat_id,
            organization_id=ORGANIZATION_ID,
            name="Roles",
            display_order=10,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )

    # 6. Two products in "Roles":
    # Alphabetical: "Dulce de leche" (A) before "Frutos rojos" (B).
    # But initially "Frutos rojos" has display_order=10 and "Dulce de leche" has display_order=20!
    prod_frutos_id = str(uuid.uuid4())
    prod_dulce_id = str(uuid.uuid4())

    session.execute(
        models.products.insert().values(
            id=prod_frutos_id,
            organization_id=ORGANIZATION_ID,
            category_id=cat_id,
            name="Frutos rojos",
            sku="ROL-FRUTOS",
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
            product_id=prod_frutos_id,
            price_cents=9000,
            currency="MXN",
            valid_from=now,
            created_at=now,
        )
    )

    session.execute(
        models.products.insert().values(
            id=prod_dulce_id,
            organization_id=ORGANIZATION_ID,
            category_id=cat_id,
            name="Dulce de leche con nuez",
            sku="ROL-DULCE",
            station="kitchen",
            status="active",
            display_order=20,
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.price_versions.insert().values(
            id=str(uuid.uuid4()),
            organization_id=ORGANIZATION_ID,
            product_id=prod_dulce_id,
            price_cents=9500,
            currency="MXN",
            valid_from=now,
            created_at=now,
        )
    )

    session.commit()
    yield {
        "session": session,
        "cat_id": cat_id,
        "prod_frutos_id": prod_frutos_id,
        "prod_dulce_id": prod_dulce_id,
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


def test_products_ordered_by_display_order_in_admin_and_public_catalog(test_db):
    """TDD-TC-984: Verify products project by display_order instead of alphabetical."""
    session = test_db["session"]

    def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)
    headers = _auth_headers()

    # 1. Fetch admin products. Frutos rojos (order=10) appears before Dulce de leche (order=20),
    # even though "Dulce" comes alphabetically before "Frutos"!
    res = client.get("/api/v1/catalog/products", headers=headers)
    assert res.status_code == 200
    prods = res.json()
    assert len(prods) == 2
    assert prods[0]["id"] == test_db["prod_frutos_id"]
    assert prods[0]["name"] == "Frutos rojos"
    assert prods[0]["display_order"] == 10
    assert prods[1]["id"] == test_db["prod_dulce_id"]
    assert prods[1]["name"] == "Dulce de leche con nuez"
    assert prods[1]["display_order"] == 20

    # 2. Fetch public catalog: must also be ordered by display_order
    pub_res = client.get(f"/api/v1/public/branches/{test_db['public_key']}/catalog")
    assert pub_res.status_code == 200
    pub_prods = pub_res.json()["items"]
    assert len(pub_prods) == 2
    assert pub_prods[0]["id"] == test_db["prod_frutos_id"]
    assert pub_prods[1]["id"] == test_db["prod_dulce_id"]


def test_reorder_catalog_products_endpoint(test_db):
    """TDD-TC-984: Reorder via PUT /catalog/products/reorder updates display_order atomically."""
    session = test_db["session"]

    def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)
    headers = _auth_headers()

    # Swap orders: Dulce de leche -> 10, Frutos rojos -> 20
    reorder_payload = {
        "items": [
            {"id": test_db["prod_dulce_id"], "display_order": 10},
            {"id": test_db["prod_frutos_id"], "display_order": 20},
        ]
    }
    reorder_res = client.put(
        "/api/v1/catalog/products/reorder",
        headers=headers,
        json=reorder_payload,
    )
    assert reorder_res.status_code == 200


    # Verify new order in admin catalog
    res = client.get("/api/v1/catalog/products", headers=headers)
    assert res.status_code == 200
    prods = res.json()
    assert prods[0]["id"] == test_db["prod_dulce_id"]
    assert prods[0]["display_order"] == 10
    assert prods[1]["id"] == test_db["prod_frutos_id"]
    assert prods[1]["display_order"] == 20

    # Verify new order in public catalog
    pub_res = client.get(f"/api/v1/public/branches/{test_db['public_key']}/catalog")
    assert pub_res.status_code == 200
    pub_prods = pub_res.json()["items"]
    assert pub_prods[0]["id"] == test_db["prod_dulce_id"]
    assert pub_prods[1]["id"] == test_db["prod_frutos_id"]



def test_reorder_rejects_foreign_or_missing_product(test_db):
    """TDD-TC-984: Reordering rejects products from other tenants or non-existent IDs."""
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
    res = client.put("/api/v1/catalog/products/reorder", headers=headers, json=reorder_payload)
    assert res.status_code in (404, 400, 422)
