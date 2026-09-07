# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-recovery-test-didi-food-integration-synthetic-v1
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
from restaurant_os.integrations import DiDiFoodAdapter, channel_service
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
            name="Hamburguesa DiDi Especial",
            sku="SKU-HAM-DIDI",
            station="kitchen",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )

    session.commit()
    yield session
    session.close()


@pytest.fixture
def auth_headers():
    token = create_session_token({"sub": USER_ID}, get_settings().secret_key)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(test_db):
    def override_get_session():
        yield test_db

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def generate_didi_signature(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def test_didi_signature_validation(client, test_db):
    """
    TDD-TC-226: Validar firma HMAC-SHA256 en header sign / X-DiDi-Signature.
    """
    adapter = DiDiFoodAdapter()
    secret = "didi_webhook_secret_xyz"
    body = b'{"event_type": "order.created", "order_id": "123"}'
    valid_sig = generate_didi_signature(secret, body)

    assert adapter.verify_webhook_signature(body, valid_sig, secret) is True
    assert adapter.verify_webhook_signature(body, f"sha256={valid_sig}", secret) is True
    assert adapter.verify_webhook_signature(body, "invalid_sig", secret) is False
    assert adapter.verify_webhook_signature(body, None, secret) is False

    channel_service.save_config(
        test_db,
        ORGANIZATION_ID,
        "DIDI_FOOD",
        {
            "is_enabled": True,
            "environment": "sandbox",
            "client_id": "didi_app_123",
            "client_secret": "didi_sec_456",
            "webhook_secret": secret,
        },
    )

    payload = {
        "event_type": "order.created",
        "order_id": "didi_ord_test_01",
        "shop_id": "didi_shop_01",
        "customer": {"name": "Carlos DiDi", "phone": "+523311223344"},
        "items": [
            {"id": "item_1", "name": "Hamburguesa DiDi Especial", "price": 120.0, "quantity": 1}
        ],
        "total_cents": 12000,
    }
    channel_service.save_store_mapping(
        test_db, ORGANIZATION_ID, "DIDI_FOOD", BRANCH_ID, "didi_shop_01"
    )
    body_bytes = json.dumps(payload).encode("utf-8")
    valid_sig = generate_didi_signature(secret, body_bytes)

    # 1. Petición con firma válida
    resp = client.post(
        "/api/v1/integrations/didi-food/webhook",
        content=body_bytes,
        headers={"Content-Type": "application/json", "X-DiDi-Signature": valid_sig},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"

    # 2. Petición con firma inválida
    resp_invalid = client.post(
        "/api/v1/integrations/didi-food/webhook",
        content=body_bytes,
        headers={"Content-Type": "application/json", "X-DiDi-Signature": "invalid_sig_abc"},
    )
    assert resp_invalid.status_code == 401


def test_didi_store_routing_and_order_creation(client, test_db):
    """
    TDD-TC-227: Enrutamiento mediante Shop ID a sucursal Kiwi y
    creación de orden con canal DIDI_FOOD.
    """
    secret = "didi_webhook_secret_xyz"
    shop_id = "didi_shop_guadalajara_01"

    channel_service.save_config(
        test_db,
        ORGANIZATION_ID,
        "DIDI_FOOD",
        {"is_enabled": True, "webhook_secret": secret, "auto_accept": True},
    )
    channel_service.save_store_mapping(
        test_db,
        ORGANIZATION_ID,
        "DIDI_FOOD",
        BRANCH_ID,
        shop_id,
        is_active=True,
    )

    payload = {
        "event_type": "order.created",
        "order_id": "didi_ord_route_101",
        "display_id": "D-101",
        "shop_id": shop_id,
        "customer": {"name": "Ana Gómez", "phone": "3399887766"},
        "delivery_notes": "Dejar en recepción",
        "items": [
            {
                "item_id": "SKU-HAM-DIDI",
                "name": "Hamburguesa DiDi Especial",
                "quantity": 2,
                "unit_price_cents": 12000,
            }
        ],
        "total_cents": 24000,
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    sig = generate_didi_signature(secret, body_bytes)

    resp = client.post(
        "/api/v1/integrations/didi-food/webhook",
        content=body_bytes,
        headers={"Content-Type": "application/json", "X-DiDi-Signature": sig},
    )
    assert resp.status_code == 200

    # Verificar registro en base de datos
    order_row = (
        test_db.execute(models.orders.select().where(models.orders.c.branch_id == BRANCH_ID))
        .mappings()
        .first()
    )
    assert order_row is not None
    assert order_row["channel"] == "DIDI_FOOD"
    assert order_row["status"] == "ACCEPTED"
    assert order_row["total_cents"] == 24000

    # Meta de canal
    meta_row = (
        test_db.execute(
            models.channel_orders_meta.select().where(
                models.channel_orders_meta.c.external_order_id == "didi_ord_route_101"
            )
        )
        .mappings()
        .first()
    )
    assert meta_row is not None
    assert meta_row["provider"] == "DIDI_FOOD"
    assert meta_row["customer_name"] == "Ana Gómez"


def test_didi_webhook_idempotency(client, test_db):
    """
    TDD-TC-228: Idempotencia en reintentos de webhook DiDi Food.
    """
    secret = "didi_webhook_secret_xyz"
    channel_service.save_config(
        test_db,
        ORGANIZATION_ID,
        "DIDI_FOOD",
        {"is_enabled": True, "webhook_secret": secret},
    )
    channel_service.save_store_mapping(test_db, ORGANIZATION_ID, "DIDI_FOOD", BRANCH_ID, "any_shop")

    payload = {
        "event_type": "order.created",
        "order_id": "didi_ord_idempotent_99",
        "shop_id": "any_shop",
        "customer": {"name": "Cliente DiDi", "phone": "1234567890"},
        "items": [{"name": "Hamburguesa DiDi Especial", "price": 100.0, "quantity": 1}],
        "total_cents": 10000,
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    sig = generate_didi_signature(secret, body_bytes)

    # Primer envío
    resp1 = client.post(
        "/api/v1/integrations/didi-food/webhook",
        content=body_bytes,
        headers={"Content-Type": "application/json", "X-DiDi-Signature": sig},
    )
    assert resp1.status_code == 200
    assert resp1.json()["result"]["status"] == "created"

    # Segundo envío (reintento con mismo payload)
    resp2 = client.post(
        "/api/v1/integrations/didi-food/webhook",
        content=body_bytes,
        headers={"Content-Type": "application/json", "X-DiDi-Signature": sig},
    )
    assert resp2.status_code == 200
    assert resp2.json()["result"]["status"] == "already_processed"


def test_didi_admin_configuration_api(client, auth_headers):
    """
    TDD-TC-229: Endpoints de configuración, mapeo de tiendas y simulador sandbox DiDi Food.
    """
    # 1. Guardar Configuración
    save_resp = client.put(
        "/api/v1/integrations/didi-food/config",
        json={
            "is_enabled": True,
            "environment": "sandbox",
            "client_id": "didi_app_abc",
            "client_secret": "didi_sec_123",
            "webhook_secret": "didi_wh_999",
            "auto_accept": True,
            "default_prep_time_minutes": 25,
        },
        headers=auth_headers,
    )
    assert save_resp.status_code == 200
    config_data = save_resp.json()
    assert config_data["client_id"] == "didi_app_abc"
    assert config_data["provider"] == "DIDI_FOOD"

    # 2. Consultar Configuración
    get_resp = client.get("/api/v1/integrations/didi-food/config", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["is_enabled"] is False
    assert get_resp.json()["integration_status"] == "PENDING_VALIDATION"
    assert "client_secret" not in get_resp.json()
    assert "webhook_secret" not in get_resp.json()

    # 3. Vincular Tienda DiDi
    store_resp = client.post(
        "/api/v1/integrations/didi-food/stores",
        json={
            "branch_id": BRANCH_ID,
            "external_store_id": "didi_shop_gdl_center",
            "is_active": True,
        },
        headers=auth_headers,
    )
    assert store_resp.status_code == 200

    # 4. Listar Tiendas
    list_stores = client.get("/api/v1/integrations/didi-food/stores", headers=auth_headers)
    assert list_stores.status_code == 200
    assert len(list_stores.json()) == 1

    mapping_id = list_stores.json()[0]["id"]

    # 5. Simular Orden DiDi Sandbox
    sim_resp = client.post(
        "/api/v1/integrations/didi-food/simulate",
        json={
            "branch_id": BRANCH_ID,
            "customer_name": "Simulador DiDi User",
            "customer_phone": "3312345678",
            "items": [{"name": "Hamburguesa DiDi Sim", "quantity": 1, "unit_price": 135.0}],
            "total": 135.0,
        },
        headers=auth_headers,
    )
    assert sim_resp.status_code == 409
    assert sim_resp.json()["detail"] == "integration_pending_validation"

    # 6. Consultar Logs de Webhooks
    logs_resp = client.get("/api/v1/integrations/didi-food/logs", headers=auth_headers)
    assert logs_resp.status_code == 200
    assert logs_resp.json() == []

    # 7. Eliminar Mapeo de Tienda
    del_resp = client.delete(
        f"/api/v1/integrations/didi-food/stores/{mapping_id}", headers=auth_headers
    )
    assert del_resp.status_code == 200


def test_didi_pos_orders_lifecycle(client, auth_headers, test_db):
    channel_service.save_config(
        test_db,
        ORGANIZATION_ID,
        "DIDI_FOOD",
        {"is_enabled": True, "webhook_secret": "didi-webhook-secret"},
    )
    channel_service.save_store_mapping(
        test_db, ORGANIZATION_ID, "DIDI_FOOD", BRANCH_ID, "didi_shop_gdl_center"
    )
    """
    TDD-TC-230: Consulta de pedidos DiDi Food y actualización de ciclo de vida.
    """
    # Crear orden simulada
    sim_resp = client.post(
        "/api/v1/integrations/didi-food/simulate",
        json={
            "branch_id": BRANCH_ID,
            "customer_name": "Pedro DiDi",
            "customer_phone": "3399112233",
            "items": [{"name": "Hamburguesa DiDi Especial", "quantity": 1, "unit_price": 150.0}],
            "total": 150.0,
        },
        headers=auth_headers,
    )
    assert sim_resp.status_code == 200
    order_id = sim_resp.json()["result"]["order_id"]

    # Consultar pedidos de DiDi Food en POS
    pos_orders_resp = client.get(
        f"/api/v1/pos/didi-food/orders?branch_id={BRANCH_ID}", headers=auth_headers
    )
    assert pos_orders_resp.status_code == 200
    orders = pos_orders_resp.json()
    assert len(orders) >= 1
    didi_order = next((o for o in orders if o["id"] == order_id), None)
    assert didi_order is not None
    assert didi_order["channel"] == "DIDI_FOOD"
    assert didi_order["customer_name"] == "Pedro DiDi"

    # Actualizar estado a READY
    status_resp = client.post(
        f"/api/v1/pos/didi-food/orders/{order_id}/status",
        json={"status": "READY"},
        headers=auth_headers,
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "READY"
