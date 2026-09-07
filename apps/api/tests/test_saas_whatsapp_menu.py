# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-test-saas-whatsapp-menu-synthetic-v1
"""TDD Test Suite for POS-SaaS Sprint 5: Mobile Web Menu & Direct WhatsApp Ordering."""

from __future__ import annotations

import urllib.parse
from typing import Any

import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.database import get_session
from restaurant_os.main import create_app
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


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

    app = create_app()
    app.state.public_order_intents_enabled = True
    from restaurant_os.public_order_rate_limit import InMemoryPublicOrderRateLimiter

    app.state.public_order_rate_limiter = InMemoryPublicOrderRateLimiter(
        100, 100, "synthetic-qa-only-rate-limit-secret"
    )
    app.state.test_session_factory = TestingSessionLocal
    app.dependency_overrides[get_session] = override_get_session
    return TestClient(app)


def _setup_tenant(
    client: TestClient,
) -> tuple[dict[str, str], dict[str, Any], list[dict[str, Any]]]:
    signup_resp = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Taquería El Pastorcito",
            "owner_name": "Mateo Morales",
            "email": "mateo@pastorcito.com",
            "password": "Password123!",
            "business_type": "taqueria",
            "phone": "525512345678",
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
    storefront = client.get(
        f"/api/v1/public/storefronts/{auth_data['organization']['slug']}"
    ).json()
    public_key = storefront["branches"][0]["public_key"]

    target_product = products[0]
    product_id = target_product["id"]
    expected_unit_price = target_product["price_cents"]

    order_payload = {
        "branch_id": branch_id,
        "public_key": public_key,
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

    resp = client.post(
        "/api/v1/public/whatsapp-orders",
        json=order_payload,
        headers={"Idempotency-Key": "whatsapp-fixture-unique-order"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    replay = client.post(
        "/api/v1/public/whatsapp-orders",
        json=order_payload,
        headers={"Idempotency-Key": "whatsapp-fixture-unique-order"},
    )
    assert replay.status_code == 200
    assert replay.json()["public_reference"] == data["public_reference"]
    with client.app.state.test_session_factory() as session:
        assert (
            session.scalar(sa.select(sa.func.count()).select_from(models.public_order_intents)) == 1
        )
        lines = session.execute(sa.select(models.public_order_intent_lines)).mappings().all()
        assert len(lines) == 1
        assert lines[0]["quantity"] == 3
        assert lines[0]["product_id"] == product_id

    # Total must be computed strictly on backend: 3 * unit_price
    assert data["total_cents"] == 3 * expected_unit_price
    assert "public_reference" in data
    assert data["status"] == "PENDING_REVIEW"
    assert "folio" not in data
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
    assert data["public_reference"] in text

    # The persisted request must continue into POS and kitchen without a recipe.
    with client.app.state.test_session_factory() as session:
        intent_id = session.scalar(sa.select(models.public_order_intents.c.id))
    accepted = client.post(
        f"/api/v1/order-intents/{intent_id}/accept",
        headers={**headers, "Idempotency-Key": "whatsapp-accept-fixture"},
        json={"expected_version": 1},
    )
    assert accepted.status_code == 201, accepted.text
    kitchen = client.get("/api/v1/kds/tasks", headers=headers, params={"branch_id": branch_id})
    assert kitchen.status_code == 200, kitchen.text
    assert kitchen.json(), "Accepted request must appear in its kitchen"
    with client.app.state.test_session_factory() as session:
        order = session.execute(sa.select(models.orders)).mappings().one()
        assert order["organization_id"] == auth_data["organization"]["id"]
        assert order["branch_id"] == branch_id
        assert order["public_order_intent_id"] == intent_id


def test_whatsapp_order_rejects_unavailable_product() -> None:
    client = _client_with_db()
    headers, auth_data, products = _setup_tenant(client)
    branch_id = auth_data["branch"]["id"]
    storefront = client.get(
        f"/api/v1/public/storefronts/{auth_data['organization']['slug']}"
    ).json()
    public_key = storefront["branches"][0]["public_key"]

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
        "public_key": public_key,
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

    resp = client.post(
        "/api/v1/public/whatsapp-orders",
        json=order_payload,
        headers={"Idempotency-Key": "whatsapp-fixture-unique-order"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "product_unavailable"


def test_whatsapp_requires_exact_key_idempotency_and_preserves_empty_state_on_rejection() -> None:
    client = _client_with_db()
    _, auth_data, products = _setup_tenant(client)
    storefront = client.get(
        f"/api/v1/public/storefronts/{auth_data['organization']['slug']}"
    ).json()
    payload = {
        "public_key": storefront["branches"][0]["public_key"],
        "customer_name": "Synthetic customer",
        "customer_phone": "5512345678",
        "items": [{"product_id": products[0]["id"], "quantity": 1}],
    }
    missing_key = client.post("/api/v1/public/whatsapp-orders", json=payload)
    assert missing_key.status_code == 422
    assert missing_key.json()["detail"]["code"] == "public_order_schema_invalid"
    wrong_branch = client.post(
        "/api/v1/public/whatsapp-orders",
        json={**payload, "branch_id": "another-branch"},
        headers={"Idempotency-Key": "whatsapp-scope-fixture"},
    )
    assert wrong_branch.status_code == 404
    with client.app.state.test_session_factory() as session:
        assert (
            session.scalar(sa.select(sa.func.count()).select_from(models.public_order_intents)) == 0
        )
    created = client.post(
        "/api/v1/public/whatsapp-orders",
        json=payload,
        headers={"Idempotency-Key": "whatsapp-scope-fixture"},
    )
    assert created.status_code == 201
    conflict = client.post(
        "/api/v1/public/whatsapp-orders",
        json={**payload, "items": [{"product_id": products[0]["id"], "quantity": 2}]},
        headers={"Idempotency-Key": "whatsapp-scope-fixture"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_conflict"
    with client.app.state.test_session_factory() as session:
        assert (
            session.scalar(sa.select(sa.func.count()).select_from(models.public_order_intents)) == 1
        )
        assert session.scalar(sa.select(sa.func.count()).select_from(models.orders)) == 0
        assert session.scalar(sa.select(sa.func.count()).select_from(models.payments)) == 0
