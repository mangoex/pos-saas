# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-recovery-test-uber-eats-integration-synthetic-v1
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.auth import create_session_token
from restaurant_os.config import get_settings
from restaurant_os.database import get_session
from restaurant_os.integrations import UberEatsAdapter, channel_service
from restaurant_os.main import create_app
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

app = create_app()

ORGANIZATION_ID = "018f6f73-2d0a-74f0-8f1c-000000000001"
BRANCH_ID = "018f6f73-2d0a-74f0-8f1c-000000000002"
USER_ID = "018f6f73-2d0a-74f0-8f1c-000000000003"
ROLE_ID = "018f6f73-2d0a-74f0-8f1c-000000000004"


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionFactory()

    # Seed base organization and branch
    now = datetime.now(timezone.utc)
    session.execute(
        models.organizations.insert().values(
            id=ORGANIZATION_ID,
            name="Kiwi Corporativo",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.legal_entities.insert().values(
            id=str(uuid.uuid4()),
            organization_id=ORGANIZATION_ID,
            name="Kiwi SA de CV",
            created_at=now,
            updated_at=now,
        )
    )
    legal_id = session.execute(models.legal_entities.select()).scalar_one()
    session.execute(
        models.business_units.insert().values(
            id=str(uuid.uuid4()),
            organization_id=ORGANIZATION_ID,
            legal_entity_id=legal_id,
            name="Kiwi Fast Food",
            code="KFF",
            unit_type="restaurant",
            created_at=now,
            updated_at=now,
        )
    )
    bu_id = session.execute(models.business_units.select()).scalar_one()
    session.execute(
        models.branches.insert().values(
            id=BRANCH_ID,
            organization_id=ORGANIZATION_ID,
            legal_entity_id=legal_id,
            business_unit_id=bu_id,
            name="Sucursal Principal",
            code="SUC01",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.users.insert().values(
            id=USER_ID,
            organization_id=ORGANIZATION_ID,
            email="admin@kiwi.com",
            display_name="Admin",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.roles.insert().values(
            id=ROLE_ID,
            organization_id=ORGANIZATION_ID,
            name="Dueño",
            scope="organization",
            created_at=now,
        )
    )
    session.execute(
        models.user_roles.insert().values(user_id=USER_ID, role_id=ROLE_ID, branch_id=BRANCH_ID)
    )
    for perm in ["admin.manage", "orders.read", "orders.create", "catalog.manage"]:
        perm_id = str(uuid.uuid4())
        session.execute(
            models.permissions.insert().values(
                id=perm_id, code=perm, description=perm, created_at=now
            )
        )
        session.execute(
            models.role_permissions.insert().values(role_id=ROLE_ID, permission_id=perm_id)
        )

    # Seed product category and product
    cat_id = str(uuid.uuid4())
    session.execute(
        models.product_categories.insert().values(
            id=cat_id,
            organization_id=ORGANIZATION_ID,
            name="Hamburguesas",
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
            name="Hamburguesa Clásica",
            sku="SKU-HAM-001",
            station="kitchen",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )

    session.commit()
    yield session
    session.close()


def test_uber_signature_validation():
    adapter = UberEatsAdapter()
    secret = "whsec_test_secret_12345"
    payload = b'{"event_type": "orders.notification", "order_id": "123"}'

    valid_signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert adapter.verify_webhook_signature(payload, valid_signature, secret) is True
    assert adapter.verify_webhook_signature(payload, f"sha256={valid_signature}", secret) is True

    # Altered signature or secret
    assert adapter.verify_webhook_signature(payload, "invalid_signature", secret) is False
    assert adapter.verify_webhook_signature(payload, valid_signature, "wrong_secret") is False
    assert adapter.verify_webhook_signature(payload, None, secret) is False


def test_uber_store_routing_and_order_creation(test_db):
    store_uuid = "d0e94168-bf1b-49cb-a49b-02df1ff9b68e"

    # Map store UUID to branch
    channel_service.save_config(
        test_db,
        ORGANIZATION_ID,
        "UBER_EATS",
        {"is_enabled": True, "webhook_secret": "uber-webhook-secret"},
    )
    channel_service.save_store_mapping(
        test_db, ORGANIZATION_ID, "UBER_EATS", BRANCH_ID, store_uuid, is_active=True
    )

    order_payload = {
        "id": "uber-order-001",
        "display_id": "A1B2",
        "event_type": "orders.notification",
        "store": {"id": store_uuid, "name": "Kiwi Test"},
        "eater": {"first_name": "Valeria", "last_name": "Gómez", "phone": "+526671112233"},
        "delivery": {"notes": "Casa blanca portón negro"},
        "cart": {
            "items": [
                {
                    "id": "item-1",
                    "title": "Hamburguesa Clásica",
                    "external_data": "SKU-HAM-001",
                    "quantity": 2,
                    "price": {"unit_price": {"amount": 9500, "currency_code": "MXN"}},
                    "special_instructions": "Bien dorada la carne",
                }
            ]
        },
        "payment": {"charges": {"total": {"amount": 19000, "currency_code": "MXN"}}},
        "currency": "MXN",
    }

    result = channel_service.process_webhook_order(
        test_db, ORGANIZATION_ID, "UBER_EATS", order_payload
    )
    assert result["status"] == "created"
    assert result["display_code"] == "#A1B2"
    assert result["branch_id"] == BRANCH_ID

    # Verify created order in DB
    order = (
        test_db.execute(models.orders.select().where(models.orders.c.id == result["order_id"]))
        .mappings()
        .first()
    )
    assert order is not None
    assert order["channel"] == "UBER_EATS"
    assert order["total_cents"] == 19000
    assert order["customer_snapshot"]["name"] == "Valeria Gómez"

    # Verify meta record
    meta = (
        test_db.execute(
            models.channel_orders_meta.select().where(
                models.channel_orders_meta.c.order_id == result["order_id"]
            )
        )
        .mappings()
        .first()
    )
    assert meta is not None
    assert meta["external_order_id"] == "uber-order-001"
    assert meta["display_code"] == "#A1B2"


def test_uber_webhook_idempotency(test_db):
    store_uuid = "d0e94168-bf1b-49cb-a49b-02df1ff9b68e"
    channel_service.save_config(
        test_db,
        ORGANIZATION_ID,
        "UBER_EATS",
        {"is_enabled": True, "webhook_secret": "uber-webhook-secret"},
    )
    channel_service.save_store_mapping(
        test_db, ORGANIZATION_ID, "UBER_EATS", BRANCH_ID, store_uuid, is_active=True
    )

    payload = {
        "id": "uber-idempotency-test",
        "display_id": "X99",
        "store": {"id": store_uuid},
        "eater": {"first_name": "Pedro"},
        "cart": {"items": [{"title": "Burger", "quantity": 1, "unit_price_cents": 5000}]},
        "total_cents": 5000,
    }

    first_res = channel_service.process_webhook_order(
        test_db, ORGANIZATION_ID, "UBER_EATS", payload
    )
    assert first_res["status"] == "created"

    # Re-process identical order
    second_res = channel_service.process_webhook_order(
        test_db, ORGANIZATION_ID, "UBER_EATS", payload
    )
    assert second_res["status"] == "already_processed"
    assert second_res["order_id"] == first_res["order_id"]


def test_uber_admin_configuration_api(test_db):
    def override_session():
        yield test_db

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)

    token = create_session_token({"sub": USER_ID}, get_settings().secret_key)
    headers = {"Authorization": f"Bearer {token}"}

    # Save config
    config_payload = {
        "is_enabled": True,
        "environment": "sandbox",
        "client_id": "uber_client_abc",
        "client_secret": "uber_secret_xyz",
        "webhook_secret": "uber_whsec_123",
        "auto_accept": True,
        "default_prep_time_minutes": 25,
    }
    put_res = client.put(
        "/api/v1/integrations/uber-eats/config", json=config_payload, headers=headers
    )
    assert put_res.status_code == 200
    data = put_res.json()
    assert data["is_enabled"] is True
    assert data["client_id"] == "uber_client_abc"
    assert data["default_prep_time_minutes"] == 25

    # Get config
    get_res = client.get("/api/v1/integrations/uber-eats/config", headers=headers)
    assert get_res.status_code == 200
    assert "client_secret" not in get_res.json()
    assert get_res.json()["has_client_secret"] is True

    # Add store mapping
    store_payload = {
        "branch_id": BRANCH_ID,
        "external_store_id": "uber-store-uuid-001",
        "is_active": True,
    }
    map_res = client.post(
        "/api/v1/integrations/uber-eats/stores", json=store_payload, headers=headers
    )
    assert map_res.status_code == 200

    list_maps = client.get("/api/v1/integrations/uber-eats/stores", headers=headers)
    assert list_maps.status_code == 200
    assert len(list_maps.json()) == 1
    assert list_maps.json()[0]["external_store_id"] == "uber-store-uuid-001"

    app.dependency_overrides.clear()


def test_non_order_webhooks_are_processed_before_ack_and_replay_cleanly(test_db):
    def override_session():
        yield test_db

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)
    cases = [
        (
            "UBER_EATS",
            "/api/v1/integrations/uber-eats/webhook",
            "X-Uber-Signature",
            {"store": {"id": "u"}},
        ),
        (
            "DIDI_FOOD",
            "/api/v1/integrations/didi-food/webhook",
            "X-DiDi-Signature",
            {"shop_id": "d"},
        ),
        ("RAPPI", "/api/v1/integrations/rappi/webhook", "X-Rappi-Signature", {"store_id": "r"}),
    ]
    for provider, url, header, store in cases:
        secret = f"secret-{provider}"
        store_id = next(iter(store.values()))
        if isinstance(store_id, dict):
            store_id = store_id["id"]
        channel_service.save_config(
            test_db, ORGANIZATION_ID, provider, {"is_enabled": True, "webhook_secret": secret}
        )
        channel_service.save_store_mapping(
            test_db, ORGANIZATION_ID, provider, BRANCH_ID, str(store_id)
        )
        payload = {"id": f"ignored-{provider}", "event_type": "store.status", **store}
        body = json.dumps(payload).encode()
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        first = client.post(
            url, content=body, headers={"Content-Type": "application/json", header: signature}
        )
        replay = client.post(
            url, content=body, headers={"Content-Type": "application/json", header: signature}
        )
        assert first.status_code == replay.status_code == 200
        row = (
            test_db.execute(
                models.integration_webhook_inbox.select().where(
                    models.integration_webhook_inbox.c.provider == provider,
                    models.integration_webhook_inbox.c.event_id == payload["id"],
                )
            )
            .mappings()
            .one()
        )
        assert row["status"] == "processed"
        assert row["lease_token"] is None
    app.dependency_overrides.clear()


def test_uber_pos_orders_lifecycle(test_db):
    def override_session():
        yield test_db

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)
    token = create_session_token({"sub": USER_ID}, get_settings().secret_key)
    headers = {"Authorization": f"Bearer {token}"}

    store_id = "test-store-uber"
    channel_service.save_config(
        test_db,
        ORGANIZATION_ID,
        "UBER_EATS",
        {"is_enabled": True, "webhook_secret": "uber-webhook-secret"},
    )
    channel_service.save_store_mapping(
        test_db, ORGANIZATION_ID, "UBER_EATS", BRANCH_ID, store_id, is_active=True
    )

    # Create a test order via simulation endpoint
    test_order_res = client.post(
        "/api/v1/integrations/uber-eats/test-order",
        json={"items_count": 2, "store_id": store_id},
        headers=headers,
    )
    assert test_order_res.status_code == 200
    order_id = test_order_res.json()["result"]["order_id"]

    # Query POS orders for this branch
    pos_orders_res = client.get(
        f"/api/v1/pos/uber-eats/orders?branch_id={BRANCH_ID}", headers=headers
    )
    assert pos_orders_res.status_code == 200
    orders = pos_orders_res.json()
    assert len(orders) >= 1
    target_order = next(o for o in orders if o["id"] == order_id)
    assert target_order["channel"] == "UBER_EATS"
    assert len(target_order["lines"]) == 2

    # Transition order status to READY
    status_res = client.post(
        f"/api/v1/pos/uber-eats/orders/{order_id}/status", json={"status": "READY"}, headers=headers
    )
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "READY"

    # Verify updated in POS list
    pos_orders_res_2 = client.get(
        f"/api/v1/pos/uber-eats/orders?branch_id={BRANCH_ID}", headers=headers
    )
    updated_order = next(o for o in pos_orders_res_2.json() if o["id"] == order_id)
    assert updated_order["status"] == "READY"
    assert updated_order["external_status"] == "READY"

    app.dependency_overrides.clear()
