# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-recovery-test-rappi-integration-synthetic-v1
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
from restaurant_os.integrations import RappiAdapter, channel_service
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
            name="Hamburguesa Rappi Supreme",
            sku="SKU-HAM-RAPPI",
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


def generate_rappi_signature(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def test_rappi_signature_validation(client, test_db):
    """
    TDD-TC-233: Validar firma HMAC-SHA256 en header Rappi-Signature / X-Rappi-Signature.
    """
    adapter = RappiAdapter()
    secret = "rappi_webhook_secret_xyz"
    body = b'{"event_type": "NEW_ORDER", "order_id": "123"}'
    valid_sig = generate_rappi_signature(secret, body)

    assert adapter.verify_webhook_signature(body, valid_sig, secret) is True
    assert adapter.verify_webhook_signature(body, f"sha256={valid_sig}", secret) is True
    assert adapter.verify_webhook_signature(body, "invalid_sig", secret) is False
    assert adapter.verify_webhook_signature(body, None, secret) is False

    channel_service.save_config(
        test_db,
        ORGANIZATION_ID,
        "RAPPI",
        {
            "is_enabled": True,
            "environment": "sandbox",
            "client_id": "rappi_client_123",
            "client_secret": "rappi_sec_456",
            "webhook_secret": secret,
        },
    )

    payload = {
        "event_type": "NEW_ORDER",
        "order_id": "rappi_ord_test_01",
        "store_id": "rappi_store_01",
        "customer": {"name": "Sofia Rappi", "phone": "+525511223344"},
        "items": [
            {"id": "item_1", "name": "Hamburguesa Rappi Supreme", "price": 135.0, "quantity": 1}
        ],
        "total_cents": 13500,
    }
    channel_service.save_store_mapping(
        test_db, ORGANIZATION_ID, "RAPPI", BRANCH_ID, "rappi_store_01"
    )
    body_bytes = json.dumps(payload).encode("utf-8")
    valid_sig = generate_rappi_signature(secret, body_bytes)

    # 1. Petición con firma válida
    resp = client.post(
        "/api/v1/integrations/rappi/webhook",
        content=body_bytes,
        headers={"Content-Type": "application/json", "Rappi-Signature": valid_sig},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"

    # 2. Petición con firma inválida
    resp_invalid = client.post(
        "/api/v1/integrations/rappi/webhook",
        content=body_bytes,
        headers={"Content-Type": "application/json", "Rappi-Signature": "invalid_sig_abc"},
    )
    assert resp_invalid.status_code == 401


def test_rappi_store_routing_and_order_creation(client, test_db):
    """
    TDD-TC-234: Enrutamiento mediante Store ID a sucursal Kiwi y
    creación de orden con canal RAPPI.
    """
    secret = "rappi_webhook_secret_xyz"
    store_id = "rappi_store_guadalajara_01"

    channel_service.save_config(
        test_db,
        ORGANIZATION_ID,
        "RAPPI",
        {"is_enabled": True, "webhook_secret": secret, "auto_accept": True},
    )
    channel_service.save_store_mapping(
        test_db,
        ORGANIZATION_ID,
        "RAPPI",
        BRANCH_ID,
        store_id,
        is_active=True,
    )

    payload = {
        "order_id": "rappi_order_live_1001",
        "display_id": "R101",
        "event_type": "NEW_ORDER",
        "store_id": store_id,
        "customer": {
            "first_name": "Valentina",
            "last_name": "López",
            "phone": "+523399887766",
        },
        "delivery": {"notes": "Timbre no sirve, favor de marcar."},
        "items": [
            {
                "id": "prod_rappi_1",
                "name": "Hamburguesa Rappi Supreme",
                "sku": "SKU-HAM-RAPPI",
                "quantity": 2,
                "price": 135.0,
                "special_instructions": "Papas bien doradas",
            }
        ],
        "total_cents": 27000,
        "currency": "MXN",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    sig = generate_rappi_signature(secret, body_bytes)

    resp = client.post(
        "/api/v1/integrations/rappi/webhook",
        content=body_bytes,
        headers={"Content-Type": "application/json", "Rappi-Signature": sig},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "ok"
    assert data["result"]["status"] == "created"

    # Verificar creación de orden en la BD
    created_order = (
        test_db.execute(
            models.orders.select().where(
                models.orders.c.branch_id == BRANCH_ID, models.orders.c.channel == "RAPPI"
            )
        )
        .mappings()
        .first()
    )
    assert created_order is not None
    assert created_order["total_cents"] == 27000
    assert created_order["status"] == "ACCEPTED"

    # Verificar metadatos de canal
    meta = (
        test_db.execute(
            models.channel_orders_meta.select().where(
                models.channel_orders_meta.c.order_id == created_order["id"]
            )
        )
        .mappings()
        .first()
    )
    assert meta is not None
    assert meta["provider"] == "RAPPI"
    assert meta["external_order_id"] == "rappi_order_live_1001"
    assert meta["display_code"] == "#R101"
    assert "Valentina" in meta["customer_name"]


def test_rappi_webhook_idempotency(client, test_db):
    """
    TDD-TC-235: Reintentos del webhook de Rappi no duplican órdenes.
    """
    secret = "rappi_sec"
    store_id = "rappi_store_02"

    channel_service.save_config(
        test_db, ORGANIZATION_ID, "RAPPI", {"is_enabled": True, "webhook_secret": secret}
    )
    channel_service.save_store_mapping(
        test_db, ORGANIZATION_ID, "RAPPI", BRANCH_ID, store_id, is_active=True
    )

    payload = {
        "order_id": "rappi_order_duplicate_test",
        "display_id": "R999",
        "event_type": "NEW_ORDER",
        "store_id": store_id,
        "customer": {"name": "Cliente Duplicado"},
        "items": [
            {"id": "item_1", "name": "Hamburguesa Rappi Supreme", "price": 135.0, "quantity": 1}
        ],
        "total_cents": 13500,
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    sig = generate_rappi_signature(secret, body_bytes)

    # Primer envío
    resp1 = client.post(
        "/api/v1/integrations/rappi/webhook",
        content=body_bytes,
        headers={"Content-Type": "application/json", "Rappi-Signature": sig},
    )
    assert resp1.status_code == 200
    assert resp1.json()["result"]["status"] == "created"

    # Segundo envío (reintento)
    resp2 = client.post(
        "/api/v1/integrations/rappi/webhook",
        content=body_bytes,
        headers={"Content-Type": "application/json", "Rappi-Signature": sig},
    )
    assert resp2.status_code == 200
    assert resp2.json()["result"]["status"] == "already_processed"

    # Conteo en BD debe ser exactamente 1
    orders_count = test_db.execute(
        models.orders.select().where(models.orders.c.channel == "RAPPI")
    ).all()
    assert len(orders_count) == 1


def test_rappi_admin_configuration_api(client, test_db, auth_headers):
    """
    TDD-TC-236: Endpoints de configuración, mapeo de sucursales y bitácora de Rappi.
    """
    # 1. Guardar Configuración
    put_resp = client.put(
        "/api/v1/integrations/rappi/config",
        json={
            "is_enabled": True,
            "environment": "production",
            "client_id": "rp_client_999",
            "client_secret": "rp_secret_999",
            "webhook_secret": "rp_whsec_999",
            "auto_accept": False,
            "default_prep_time_minutes": 25,
        },
        headers=auth_headers,
    )
    assert put_resp.status_code == 200, put_resp.text
    assert put_resp.json()["client_id"] == "rp_client_999"
    assert put_resp.json()["auto_accept"] is False

    # 2. Consultar Configuración
    get_resp = client.get("/api/v1/integrations/rappi/config", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["environment"] == "production"

    # 3. Mapeo de Sucursal
    map_resp = client.post(
        "/api/v1/integrations/rappi/stores",
        json={
            "branch_id": BRANCH_ID,
            "external_store_id": "rappi_shop_cdmx_01",
            "is_active": True,
        },
        headers=auth_headers,
    )
    assert map_resp.status_code == 200
    mapping_id = map_resp.json()["id"]

    # Listar Mapeos
    stores_resp = client.get("/api/v1/integrations/rappi/stores", headers=auth_headers)
    assert stores_resp.status_code == 200
    assert len(stores_resp.json()) == 1
    assert stores_resp.json()[0]["external_store_id"] == "rappi_shop_cdmx_01"

    # 4. Consultar Bitácora de Webhooks
    logs_resp = client.get("/api/v1/integrations/rappi/logs", headers=auth_headers)
    assert logs_resp.status_code == 200
    assert isinstance(logs_resp.json(), list)

    # 5. Eliminar Mapeo
    del_resp = client.delete(
        f"/api/v1/integrations/rappi/stores/{mapping_id}", headers=auth_headers
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True


def test_rappi_simulate_order_sandbox(client, test_db, auth_headers):
    """
    TDD-TC-237: Simulación de pedido de Rappi para pruebas en Sandbox.
    """
    channel_service.save_config(
        test_db,
        ORGANIZATION_ID,
        "RAPPI",
        {"is_enabled": True, "webhook_secret": "rappi-webhook-secret"},
    )
    channel_service.save_store_mapping(
        test_db,
        ORGANIZATION_ID,
        "RAPPI",
        BRANCH_ID,
        "rappi_store_sim_01",
        is_active=True,
    )

    sim_payload = {
        "branch_id": BRANCH_ID,
        "store_id": "rappi_store_sim_01",
        "customer_name": "Daniela Rappi Test",
        "customer_phone": "+523312345678",
        "items": [
            {
                "name": "Hamburguesa Rappi Supreme",
                "price": 135.0,
                "quantity": 2,
                "special_instructions": "Con aderezo extra",
            }
        ],
    }

    resp = client.post(
        "/api/v1/integrations/rappi/simulate",
        json=sim_payload,
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert "folio" in body["result"]
    assert body["result"]["folio"].startswith("RAPPI-R")


def test_rappi_pos_orders_lifecycle(client, test_db, auth_headers):
    """
    Listar y actualizar estados de pedidos Rappi en el endpoint POS.
    """
    channel_service.save_config(
        test_db,
        ORGANIZATION_ID,
        "RAPPI",
        {"is_enabled": True, "webhook_secret": "rappi-webhook-secret"},
    )
    channel_service.save_store_mapping(
        test_db,
        ORGANIZATION_ID,
        "RAPPI",
        BRANCH_ID,
        "rappi_store_pos_01",
        is_active=True,
    )

    # Simular una orden
    sim_resp = client.post(
        "/api/v1/integrations/rappi/simulate",
        json={"branch_id": BRANCH_ID, "store_id": "rappi_store_pos_01"},
        headers=auth_headers,
    )
    order_id = sim_resp.json()["result"]["order_id"]

    # 1. Consultar pedidos en POS
    pos_resp = client.get(f"/api/v1/pos/rappi/orders?branch_id={BRANCH_ID}", headers=auth_headers)
    assert pos_resp.status_code == 200
    orders = pos_resp.json()
    assert len(orders) >= 1
    found = next((o for o in orders if o["id"] == order_id), None)
    assert found is not None
    assert found["channel"] == "RAPPI"

    # 2. Actualizar estado operativo a READY_FOR_PICKUP
    status_resp = client.post(
        f"/api/v1/pos/rappi/orders/{order_id}/status",
        json={"status": "READY_FOR_PICKUP"},
        headers=auth_headers,
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "READY_FOR_PICKUP"
