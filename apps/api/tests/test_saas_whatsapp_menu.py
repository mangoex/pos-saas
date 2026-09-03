"""TDD Test Suite for POS-SaaS Sprint 5: Mobile Web Menu & Direct WhatsApp Ordering."""

from __future__ import annotations

import urllib.parse
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


def _setup_tenant(client: TestClient) -> tuple[dict[str, str], dict[str, Any], list[dict[str, Any]]]:
    signup_resp = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Taquería El Pastorcito",
            "owner_name": "Mateo Morales",
            "email": "mateo@pastorcito.com",
            "password": "Password123!",
            "business_type": "taqueria",
        },
    )
    assert signup_resp.status_code == 201
    auth_data = signup_resp.json()
    token = auth_data["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Fetch starter products
    prod_resp = client.get("/api/v1/catalog/products", headers=headers)
    assert prod_resp.status_code == 200
    products = prod_resp.json()

    return headers, auth_data, products


def test_public_menu_retrieval_by_branch() -> None:
    client = _client_with_db()
    headers, auth_data, products = _setup_tenant(client)
    branch_id = auth_data["branch"]["id"]

    # Public comensal queries menu without any auth token
    menu_resp = client.get(f"/api/v1/public/menu?branch_id={branch_id}")
    assert menu_resp.status_code == 200
    menu = menu_resp.json()

    assert "branch" in menu
    assert menu["branch"]["id"] == branch_id
    assert "products" in menu
    assert len(menu["products"]) >= 1
    # Check that price is present and positive
    p0 = menu["products"][0]
    assert p0["price_cents"] > 0
    assert "name" in p0


def test_submit_whatsapp_order_calculates_server_side_and_returns_wa_url() -> None:
    client = _client_with_db()
    headers, auth_data, products = _setup_tenant(client)
    branch_id = auth_data["branch"]["id"]

    target_product = products[0]
    product_id = target_product["id"]
    expected_unit_price = target_product["price_cents"]

    order_payload = {
        "branch_id": branch_id,
        "customer_name": "Diana Cazadora",
        "customer_phone": "5512345678",
        "order_type": "takeaway",
        "items": [
            {
                "product_id": product_id,
                "quantity": 3,
                "notes": "con mucha salsa verde",
            }
        ],
        "payment_method": "cash",
        "cash_amount": "500",
        "order_notes": "por favor agregar limones extra",
    }

    resp = client.post("/api/v1/public/whatsapp-orders", json=order_payload)
    assert resp.status_code == 200
    data = resp.json()

    # Total must be computed strictly on backend: 3 * unit_price
    assert data["total_cents"] == 3 * expected_unit_price
    assert "folio" in data
    assert "whatsapp_url" in data
    wa_url = data["whatsapp_url"]
    assert "wa.me" in wa_url

    # Check decoded message content
    parsed_url = urllib.parse.urlparse(wa_url)
    qs = urllib.parse.parse_qs(parsed_url.query)
    assert "text" in qs
    text = qs["text"][0]
    assert "Diana Cazadora" in text
    assert target_product["name"] in text
    assert data["folio"] in text


def test_whatsapp_order_rejects_unavailable_product() -> None:
    client = _client_with_db()
    headers, auth_data, products = _setup_tenant(client)
    branch_id = auth_data["branch"]["id"]

    target_product = products[0]
    product_id = target_product["id"]

    # 1. Activate Kill-Switch on this product
    kill_resp = client.post(
        "/api/v1/integrations/kill-switch",
        headers=headers,
        json={"product_id": product_id, "is_available": False, "branch_id": branch_id},
    )
    assert kill_resp.status_code == 200

    # 2. Customer tries to submit WhatsApp order with unavailable product
    order_payload = {
        "branch_id": branch_id,
        "customer_name": "Luis Miguel",
        "customer_phone": "5599887766",
        "order_type": "takeaway",
        "items": [
            {
                "product_id": product_id,
                "quantity": 1,
            }
        ],
        "payment_method": "card",
    }

    resp = client.post("/api/v1/public/whatsapp-orders", json=order_payload)
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "product_unavailable"
