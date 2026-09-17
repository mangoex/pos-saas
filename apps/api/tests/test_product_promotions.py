# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-test-product-promotions-synthetic-v1
"""TDD Test Suite for Product Promotions (is_promo, promo_price_cents, promo_badge_text)."""

from __future__ import annotations

import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.database import get_session
from restaurant_os.main import app
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def _client_with_db() -> tuple[TestClient, sessionmaker]:
    engine = sa.create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_session():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session
    return TestClient(app), TestingSessionLocal


def test_create_and_update_product_with_promotion() -> None:
    client, _ = _client_with_db()

    # 1. Sign up a tenant
    signup_resp = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Tacos El Pastor",
            "owner_name": "Carlos Gomez",
            "email": "carlos@tacos.com",
            "password": "Password123!",
            "business_type": "taqueria",
        },
    )
    assert signup_resp.status_code == 201
    token = signup_resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create product with promotion enabled
    create_resp = client.post(
        "/api/v1/catalog/products",
        headers=headers,
        json={
            "name": "Gringa al Pastor Especial",
            "sku": "GRI-PAS-01",
            "category_name": "Tacos",
            "station": "cocina",
            "price_cents": 6500,
            "delivery_price_cents": 7500,
            "is_promo": True,
            "promo_price_cents": 4900,
            "promo_badge_text": "PROMOCIÓN",
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    created = create_resp.json()
    product_id = created["id"]
    assert created.get("is_promo") is True
    assert created.get("promo_price_cents") == 4900
    assert created.get("promo_badge_text") == "PROMOCIÓN"

    # 3. List catalog products
    list_resp = client.get("/api/v1/catalog/products", headers=headers)
    assert list_resp.status_code == 200
    products = list_resp.json()
    item = next((p for p in products if p["id"] == product_id), None)
    assert item is not None
    assert item["is_promo"] is True
    assert item["promo_price_cents"] == 4900
    assert item["promo_badge_text"] == "PROMOCIÓN"

    # 4. Update product promotion (change badge to 2x1 and update promo price)
    update_resp = client.put(
        f"/api/v1/catalog/products/{product_id}",
        headers=headers,
        json={
            "name": "Gringa al Pastor Especial",
            "sku": "GRI-PAS-01",
            "category_name": "Tacos",
            "station": "cocina",
            "price_cents": 6500,
            "status": "active",
            "is_promo": True,
            "promo_price_cents": 5000,
            "promo_badge_text": "2x1",
        },
    )
    assert update_resp.status_code == 200, update_resp.text
    updated = update_resp.json()
    assert updated.get("is_promo") is True
    assert updated.get("promo_price_cents") == 5000
    assert updated.get("promo_badge_text") == "2x1"

    # 5. Disable promotion
    disable_resp = client.put(
        f"/api/v1/catalog/products/{product_id}",
        headers=headers,
        json={
            "name": "Gringa al Pastor Especial",
            "sku": "GRI-PAS-01",
            "category_name": "Tacos",
            "station": "cocina",
            "price_cents": 6500,
            "status": "active",
            "is_promo": False,
            "promo_price_cents": None,
            "promo_badge_text": None,
        },
    )
    assert disable_resp.status_code == 200
    disabled = disable_resp.json()
    assert disabled.get("is_promo") is False


def test_public_catalog_exposes_promotions() -> None:
    client, session_factory = _client_with_db()

    signup_resp = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Taquería Central",
            "owner_name": "Laura Mendez",
            "email": "laura@taqueria.com",
            "password": "Password123!",
            "business_type": "taqueria",
        },
    )
    assert signup_resp.status_code == 201
    data = signup_resp.json()
    token = data["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Get public branch key from database
    with session_factory() as session:
        public_key = session.scalar(
            sa.select(models.public_order_keys.c.public_key).where(
                models.public_order_keys.c.organization_id == data["organization"]["id"]
            )
        )
    assert public_key is not None

    # Create promo product
    create_resp = client.post(
        "/api/v1/catalog/products",
        headers=headers,
        json={
            "name": "Taco al Pastor Gigante",
            "sku": "TAC-PAS-01",
            "category_name": "Tacos",
            "station": "cocina",
            "price_cents": 3500,
            "is_promo": True,
            "promo_price_cents": 2500,
            "promo_badge_text": "OFERTA",
        },
    )
    assert create_resp.status_code == 200

    # Fetch public catalog
    catalog_resp = client.get(f"/api/v1/public/branches/{public_key}/catalog")
    assert catalog_resp.status_code == 200, catalog_resp.text
    catalog = catalog_resp.json()
    taco = next((i for i in catalog["items"] if i["name"] == "Taco al Pastor Gigante"), None)
    assert taco is not None
    assert taco["is_promo"] is True
    assert taco["promo_price_cents"] == 2500
    assert taco["promo_badge_text"] == "OFERTA"


def test_invalid_promo_price_rejected() -> None:
    client, _ = _client_with_db()

    signup_resp = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Burger Bar",
            "owner_name": "Roberto Diaz",
            "email": "roberto@burger.com",
            "password": "Password123!",
            "business_type": "hamburgueseria",
        },
    )
    assert signup_resp.status_code == 201
    token = signup_resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Invalid negative promo price
    bad_resp = client.post(
        "/api/v1/catalog/products",
        headers=headers,
        json={
            "name": "Hamburguesa Doble",
            "sku": "BUR-DOB-01",
            "category_name": "Burgers",
            "station": "cocina",
            "price_cents": 12000,
            "is_promo": True,
            "promo_price_cents": -500,
        },
    )
    assert bad_resp.status_code == 409
    assert "invalid_promo_price" in bad_resp.text
