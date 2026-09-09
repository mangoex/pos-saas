from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from restaurant_os import models, operations
from restaurant_os.auth import create_session_token
from restaurant_os.database import get_session
from restaurant_os.main import create_app
from restaurant_os.operations import ORGANIZATION_ID
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

app = create_app()

USER_ID = "018f6f73-2d0a-74f0-8f1c-000000000099"
ROLE_ID = "018f6f73-2d0a-74f0-8f1c-000000000098"


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
            slug="test-restaurant",
            name="Restaurante Móvil",
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
    branch_id = operations.BRANCH_ID
    session.execute(
        models.branches.insert().values(
            id=branch_id,
            organization_id=ORGANIZATION_ID,
            legal_entity_id=legal_id,
            business_unit_id=bu_id,
            name="Sucursal Centro",
            code="SUC-01",
            timezone="UTC",
            status="active",
            street="Av Central 123",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.warehouses.insert().values(
            id=str(uuid.uuid4()),
            organization_id=ORGANIZATION_ID,
            branch_id=branch_id,
            name="Almacén Principal",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.users.insert().values(
            id=USER_ID,
            organization_id=ORGANIZATION_ID,
            email="admin.movil@example.com",
            display_name="Admin Móvil",
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
    for perm in [
        "admin.manage",
        "cash.shift.read",
        "cash.shift.open",
        "cash.shift.close",
        "cash.shift.read_all",
        "cash.movement.create",
        "cash.movement.read",
        "cash.movement.deposit",
        "cash.movement.withdraw",
        "cash.concept.manage",
        "orders.read",
        "orders.update",
        "catalog.product.create",
        "catalog.product.update",
        "catalog.product.delete",
        "catalog.manage",
        "catalog.read",
        "branch.manage",
        "branch.update",
    ]:
        perm_id = str(uuid.uuid4())
        session.execute(
            models.permissions.insert().values(
                id=perm_id, code=perm, description=perm, created_at=now
            )
        )
        session.execute(
            models.role_permissions.insert().values(role_id=ROLE_ID, permission_id=perm_id)
        )

    operations.create_cash_concept(
        session,
        {
            "code": "APOR_CAMBIO",
            "name": "Aportación de cambio",
            "allowed_movement_type": "deposit",
            "requires_reference": True,
            "requires_evidence": True,
            "valid_from": now.isoformat(),
        },
        "idemp-concept-001",
        USER_ID,
    )

    # Insert sample category and product
    cat_id = str(uuid.uuid4())
    session.execute(
        models.product_categories.insert().values(
            id=cat_id,
            organization_id=ORGANIZATION_ID,
            name="Tacos",
            display_order=1,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    prod_id = str(uuid.uuid4())
    session.execute(
        models.products.insert().values(
            id=prod_id,
            organization_id=ORGANIZATION_ID,
            category_id=cat_id,
            name="Taco de Asada",
            sku="TACO-01",
            station="kitchen",
            status="active",
            image_url="https://images.unsplash.com/photo-sample",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.price_versions.insert().values(
            id=str(uuid.uuid4()),
            organization_id=ORGANIZATION_ID,
            product_id=prod_id,
            price_cents=4500,
            currency="MXN",
            valid_from=now,
            created_at=now,
        )
    )

    session.commit()
    yield session
    session.close()


from restaurant_os.config import get_settings


def _auth_headers(session):
    token = create_session_token(
        {"sub": USER_ID, "org_id": ORGANIZATION_ID, "role": "owner"},
        get_settings().secret_key,
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Actor-User-Id": USER_ID,
        "Content-Type": "application/json",
    }


def test_mobile_admin_tabs_and_contracts(test_db):
    """TDD-TC-246: Check backend endpoints supporting mobile admin tabs."""
    def override_get_session():
        yield test_db

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)
    headers = _auth_headers(test_db)

    # 1. Orders tab endpoint
    orders_resp = client.get(
        f"/api/v1/orders?branch_id={operations.BRANCH_ID}",
        headers=headers,
    )
    assert orders_resp.status_code == 200

    # 2. Cash shift tab endpoint
    cash_resp = client.get(
        f"/api/v1/cash/shifts/current?branch_id={operations.BRANCH_ID}&register_id=CAJA-01",
        headers=headers,
    )
    assert cash_resp.status_code == 200
    assert cash_resp.json().get("cash_shift") is None

    # 3. Categories and Products tab endpoint
    cats_resp = client.get("/api/v1/categories", headers=headers)
    assert cats_resp.status_code == 200
    assert len(cats_resp.json()) >= 1

    prods_resp = client.get("/api/v1/catalog/products", headers=headers)
    assert prods_resp.status_code == 200
    assert len(prods_resp.json()) >= 1

    # 4. Branches endpoint
    branches_resp = client.get("/api/v1/branches", headers=headers)
    assert branches_resp.status_code == 200
    assert len(branches_resp.json()) >= 1


def test_mobile_cash_shift_open_close_and_movements(test_db):
    """TDD-TC-247: Validate cash shift opening with float, movements and operational close."""
    def override_get_session():
        yield test_db

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)
    headers = _auth_headers(test_db)
    register_id = "CAJA-01"

    # Open shift with $500.00 MXN (50000 cents)
    open_resp = client.post(
        "/api/v1/cash/shifts/open",
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "branch_id": operations.BRANCH_ID,
            "register_id": register_id,
            "opening_cash_cents": 50000,
        },
    )
    assert open_resp.status_code == 200
    shift_data = open_resp.json()
    assert shift_data["status"].upper() == "OPEN"
    assert shift_data["opening_cash_cents"] == 50000
    shift_id = shift_data["id"]

    # Verify current shift is returned as open
    current_resp = client.get(
        f"/api/v1/cash/shifts/current?branch_id={operations.BRANCH_ID}&register_id={register_id}",
        headers=headers,
    )
    assert current_resp.status_code == 200
    assert current_resp.json()["cash_shift"]["id"] == shift_id

    # Fetch effective cash concepts
    concepts_resp = client.get(
        f"/api/v1/cash/concepts/effective?branch_id={operations.BRANCH_ID}&movement_type=deposit",
        headers=headers,
    )
    assert concepts_resp.status_code == 200
    concepts = concepts_resp.json()
    assert len(concepts) >= 1
    concept_id = concepts[0]["concept_id"]

    # Register a cash movement (deposit)
    movement_resp = client.post(
        "/api/v1/cash/movements",
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "branch_id": operations.BRANCH_ID,
            "register_id": register_id,
            "movement_type": "deposit",
            "concept_id": concept_id,
            "amount_cents": 10000,
            "reference": "Aportación de cambio",
            "evidence_refs": ["ticket-01.jpg"],
        },
    )
    assert movement_resp.status_code in (200, 201)

    # Operational close
    close_resp = client.post(
        f"/api/v1/cash/shifts/{shift_id}/close-operationally",
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        json={},
    )
    assert close_resp.status_code == 200
    assert close_resp.json()["cash_shift"]["status"].upper() == "OPERATIVELY_CLOSED"

    # Current cash shift should now be closed / none
    after_close_resp = client.get(
        f"/api/v1/cash/shifts/current?branch_id={operations.BRANCH_ID}&register_id={register_id}",
        headers=headers,
    )
    assert after_close_resp.status_code == 200
    assert after_close_resp.json().get("cash_shift") is None


def test_mobile_catalog_toggle_availability_and_product_image(test_db):
    """TDD-TC-248: Validate toggling availability and creating/updating product with image."""
    def override_get_session():
        yield test_db

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)
    headers = _auth_headers(test_db)

    # Fetch products
    prods = client.get("/api/v1/catalog/products", headers=headers).json()
    assert len(prods) >= 1
    target_product = prods[0]
    prod_id = target_product["id"]

    # Toggle to inactive (Agotado)
    update_resp = client.put(
        f"/api/v1/catalog/products/{prod_id}",
        headers=headers,
        json={
            "name": target_product["name"],
            "sku": target_product["sku"],
            "price_cents": target_product["price_cents"],
            "station": target_product["station"],
            "status": "inactive",
            "image_url": "https://images.unsplash.com/photo-updated",
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "inactive"
    assert "photo-updated" in update_resp.json()["image_url"]

    # Toggle back to active (Disponible)
    reactivate_resp = client.put(
        f"/api/v1/catalog/products/{prod_id}",
        headers=headers,
        json={
            "name": target_product["name"],
            "sku": target_product["sku"],
            "price_cents": target_product["price_cents"],
            "station": target_product["station"],
            "status": "active",
            "image_url": "https://images.unsplash.com/photo-updated",
        },
    )
    assert reactivate_resp.status_code == 200
    assert reactivate_resp.json()["status"] == "active"


def test_mobile_branch_settings_and_links(test_db):
    """TDD-TC-249: Check updating branch settings and querying SaaS links."""
    def override_get_session():
        yield test_db

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)
    headers = _auth_headers(test_db)

    # Query links
    links_resp = client.get("/api/v1/saas/links", headers=headers)
    assert links_resp.status_code == 200
    links = links_resp.json()
    assert "links" in links
    assert "menu" in links["links"]

    # Update branch WhatsApp ordering and google review URL
    branch_update_resp = client.put(
        f"/api/v1/branches/{operations.BRANCH_ID}",
        headers=headers,
        json={
            "name": "Sucursal Centro Móvil",
            "phone": "+526671234567",
            "whatsapp_ordering_enabled": True,
            "google_review_url": "https://g.page/r/test-review",
        },
    )
    assert branch_update_resp.status_code == 200
    updated_branch = branch_update_resp.json()
    assert updated_branch["whatsapp_ordering_enabled"] is True
