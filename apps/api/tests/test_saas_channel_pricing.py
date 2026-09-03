"""TDD Test Suite for POS-SaaS Sprint 2: Differentiated Pricing (Dine-in vs Delivery Apps)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from restaurant_os.main import app
from restaurant_os.database import get_session
from restaurant_os import models


def _client_with_db() -> TestClient:
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
    return TestClient(app)


def test_create_and_update_product_with_delivery_price() -> None:
    client = _client_with_db()

    # 1. Sign up a tenant
    signup_resp = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Pizzería Bella",
            "owner_name": "Mario Rossi",
            "email": "mario@pizzeria.com",
            "password": "Password123!",
            "business_type": "pizzeria",
        },
    )
    assert signup_resp.status_code == 201
    token = signup_resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create a new product with salon price ($150 = 15000 cents) and delivery price ($185 = 18500 cents)
    create_resp = client.post(
        "/api/v1/catalog/products",
        headers=headers,
        json={
            "name": "Pizza Margarita Artesanal",
            "sku": "PIZ-MAR-01",
            "category_name": "Pizzas",
            "station": "cocina",
            "price_cents": 15000,
            "delivery_price_cents": 18500,
        },
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    product_id = created["id"]
    assert created.get("delivery_price_cents") == 18500

    # 3. Retrieve catalog products and verify delivery_price_cents is exposed
    list_resp = client.get("/api/v1/catalog/products", headers=headers)
    assert list_resp.status_code == 200
    products = list_resp.json()
    piz = next((p for p in products if p["id"] == product_id), None)
    assert piz is not None
    assert piz["price_cents"] == 15000
    assert piz["delivery_price_cents"] == 18500

    # 4. Update product delivery price
    update_resp = client.put(
        f"/api/v1/catalog/products/{product_id}",
        headers=headers,
        json={
            "name": "Pizza Margarita Artesanal Especial",
            "sku": "PIZ-MAR-01",
            "price_cents": 16000,
            "delivery_price_cents": 19900,
            "category_name": "Pizzas",
            "station": "cocina",
            "status": "active",
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated.get("delivery_price_cents") == 19900

    # 5. Verify catalog reflects the updated delivery price
    list_resp2 = client.get("/api/v1/catalog/products", headers=headers)
    piz2 = next((p for p in list_resp2.json() if p["id"] == product_id), None)
    assert piz2 is not None
    assert piz2["price_cents"] == 16000
    assert piz2["delivery_price_cents"] == 19900


def test_product_without_delivery_price_defaults_or_allows_none() -> None:
    client = _client_with_db()

    signup_resp = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Café Tradicional",
            "owner_name": "Elena Torres",
            "email": "elena@cafe.com",
            "password": "Password123!",
            "business_type": "cafeteria",
        },
    )
    assert signup_resp.status_code == 201
    token = signup_resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = client.post(
        "/api/v1/catalog/products",
        headers=headers,
        json={
            "name": "Té Verde Matcha",
            "sku": "TE-MAT-01",
            "category_name": "Bebidas",
            "station": "barra",
            "price_cents": 5000,
            # No delivery_price_cents specified
        },
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created.get("delivery_price_cents") is None

    # In catalog list, delivery_price_cents is None
    list_resp = client.get("/api/v1/catalog/products", headers=headers)
    assert list_resp.status_code == 200
    item = next((p for p in list_resp.json() if p["id"] == created["id"]), None)
    assert item is not None
    assert item["price_cents"] == 5000
    assert item["delivery_price_cents"] is None
