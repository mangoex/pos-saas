# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-whatsapp-business-integration-test-v1
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.auth import create_session_token
from restaurant_os.config import get_settings
from restaurant_os.database import get_session
from restaurant_os.main import create_app
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

app = create_app()

ORGANIZATION_ID = "018f6f73-2d0a-74f0-8f1c-000000000001"
BRANCH_ID = "018f6f73-2d0a-74f0-8f1c-000000000002"
USER_ID = "018f6f73-2d0a-74f0-8f1c-000000000003"
ROLE_ID = "018f6f73-2d0a-74f0-8f1c-000000000004"

TEST_VERIFY_TOKEN = "mimenu_verify_secret_123"
TEST_APP_SECRET = "meta_app_secret_test_xyz"
TEST_PHONE_NUMBER_ID = "109876543210987"
TEST_WABA_ID = "waba_9988776655"


def _compute_signature(secret: str, payload_bytes: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), msg=payload_bytes, digestmod=hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionFactory()

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
    # Seed Branch
    session.execute(
        models.branches.insert().values(
            id=BRANCH_ID,
            organization_id=ORGANIZATION_ID,
            legal_entity_id=legal_id,
            business_unit_id=bu_id,
            name="Sucursal Roma",
            code="ROM",
            slug="sucursal-roma",
            status="active",
            phone="5512345678",
            created_at=now,
            updated_at=now,
        )
    )

    # Seed User, Role, Permissions for Admin
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
    for perm_code in [
        "admin.manage",
        "orders.read",
        "catalog.manage",
        "integrations.manage",
    ]:
        perm_id = str(uuid.uuid4())
        session.execute(
            models.permissions.insert().values(
                id=perm_id,
                code=perm_code,
                description=perm_code,
                created_at=now,
            )
        )
        session.execute(
            models.role_permissions.insert().values(
                role_id=ROLE_ID,
                permission_id=perm_id,
            )
        )

    # Seed Categories and Products
    cat_id = str(uuid.uuid4())
    session.execute(
        models.product_categories.insert().values(
            id=cat_id,
            organization_id=ORGANIZATION_ID,
            name="Tacos y Antojitos",
            created_at=now,
            updated_at=now,
        )
    )
    prod_available_id = str(uuid.uuid4())
    session.execute(
        models.products.insert().values(
            id=prod_available_id,
            organization_id=ORGANIZATION_ID,
            category_id=cat_id,
            name="Tacos al Pastor (Orden)",
            sku="SKU-TAC-PAS",
            station="kitchen",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.price_versions.insert().values(
            id=str(uuid.uuid4()),
            organization_id=ORGANIZATION_ID,
            product_id=prod_available_id,
            price_cents=9500,
            currency="MXN",
            valid_from=now,
            created_at=now,
        )
    )
    session.execute(
        models.branch_product_availability.insert().values(
            branch_id=BRANCH_ID,
            product_id=prod_available_id,
            is_available=True,
            updated_at=now,
        )
    )

    prod_unavailable_id = str(uuid.uuid4())
    session.execute(
        models.products.insert().values(
            id=prod_unavailable_id,
            organization_id=ORGANIZATION_ID,
            category_id=cat_id,
            name="Gringa Especial",
            sku="SKU-GRI-ESP",
            station="kitchen",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.price_versions.insert().values(
            id=str(uuid.uuid4()),
            organization_id=ORGANIZATION_ID,
            product_id=prod_unavailable_id,
            price_cents=12000,
            currency="MXN",
            valid_from=now,
            created_at=now,
        )
    )
    session.execute(
        models.branch_product_availability.insert().values(
            branch_id=BRANCH_ID,
            product_id=prod_unavailable_id,
            is_available=False,  # 86'd / no disponible
            updated_at=now,
        )
    )

    # Configure WhatsApp integration for this org
    session.execute(
        models.channel_integrations.insert().values(
            id=str(uuid.uuid4()),
            organization_id=ORGANIZATION_ID,
            provider="WHATSAPP_BUSINESS",
            is_enabled=True,
            environment="sandbox",
            client_id="app_123456789",
            client_secret=TEST_APP_SECRET,
            webhook_secret=TEST_VERIFY_TOKEN,
            auto_accept=True,
            default_prep_time_minutes=15,
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.channel_store_mappings.insert().values(
            id=str(uuid.uuid4()),
            organization_id=ORGANIZATION_ID,
            branch_id=BRANCH_ID,
            provider="WHATSAPP_BUSINESS",
            external_store_id=TEST_PHONE_NUMBER_ID,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
    )

    session.commit()
    yield session
    session.close()


@pytest.fixture
def auth_headers(test_db):
    settings = get_settings()
    token = create_session_token(
        {"sub": USER_ID, "org": ORGANIZATION_ID},
        settings.secret_key,
    )
    return {"Authorization": f"Bearer {token}"}


def test_whatsapp_webhook_verification_handshake(test_db):
    """TDD-TC-321: Meta Webhook GET challenge verification."""

    def override_get_session():
        yield test_db

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)

    # Valid challenge
    resp = client.get(
        f"/integrations/whatsapp/webhook?hub.mode=subscribe&hub.verify_token={TEST_VERIFY_TOKEN}&hub.challenge=challenge_token_abc"
    )
    assert resp.status_code == 200
    assert resp.text == "challenge_token_abc"

    # Invalid verify token -> 403 Forbidden
    resp_invalid = client.get(
        "/integrations/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=wrong_token&hub.challenge=challenge_token_abc"
    )
    assert resp_invalid.status_code == 403


def test_whatsapp_webhook_signature_and_raw_log(test_db):
    """TDD-TC-322: Inbound webhook HMAC-SHA256 signature validation and immutable raw logging."""

    def override_get_session():
        yield test_db

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": TEST_WABA_ID,
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "5215512345678",
                                "phone_number_id": TEST_PHONE_NUMBER_ID,
                            },
                            "contacts": [
                                {"profile": {"name": "Juan Perez"}, "wa_id": "5215599887766"}
                            ],
                            "messages": [
                                {
                                    "from": "5215599887766",
                                    "id": "wamid.HBgLMTIzNDU2Nzg5AA==",
                                    "timestamp": "1710000000",
                                    "text": {
                                        "body": "Hola, ¿cuál es el menú y qué tienen de comer?"
                                    },
                                    "type": "text",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    body_bytes = json.dumps(payload).encode("utf-8")

    # Invalid signature -> 401
    bad_sig = "sha256=invalid_signature_hex_00000000000000000000000000000000000000000000"
    resp_bad = client.post(
        "/integrations/whatsapp/webhook",
        content=body_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": bad_sig},
    )
    assert resp_bad.status_code == 401

    # Valid signature -> 200 OK
    valid_sig = _compute_signature(TEST_APP_SECRET, body_bytes)
    resp_ok = client.post(
        "/integrations/whatsapp/webhook",
        content=body_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": valid_sig},
    )
    assert resp_ok.status_code == 200

    # Verify that payload was stored in integration_webhook_logs
    log_row = (
        test_db.execute(
            models.integration_webhook_logs.select().where(
                models.integration_webhook_logs.c.provider == "WHATSAPP_BUSINESS"
            )
        )
        .mappings()
        .first()
    )
    assert log_row is not None
    assert log_row["provider"] == "WHATSAPP_BUSINESS"
    assert log_row["event_type"] == "messages"
    assert log_row["organization_id"] == ORGANIZATION_ID


def test_whatsapp_embedded_signup_exchange(test_db, auth_headers):
    """TDD-TC-320: Embedded signup OAuth code exchange and credential persistence."""

    def override_get_session():
        yield test_db

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)

    exchange_payload = {
        "code": "meta_auth_code_sample_12345",
        "waba_id": "new_waba_55443322",
        "phone_number_id": "new_phone_num_998877",
        "branch_id": BRANCH_ID,
    }

    with patch("restaurant_os.integrations.whatsapp.adapter.exchange_meta_code") as mock_exchange:
        mock_exchange.return_value = {
            "access_token": "EAAB_mock_long_lived_system_token_xyz",
            "token_type": "bearer",
        }

        resp = client.post(
            "/integrations/whatsapp/embedded-signup/exchange",
            json=exchange_payload,
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "CONNECTED"
        assert data["phone_number_id"] == "new_phone_num_998877"

    # Query config endpoint to confirm persistence
    cfg_resp = client.get("/integrations/whatsapp/config", headers=auth_headers)
    assert cfg_resp.status_code == 200
    cfg_data = cfg_resp.json()
    assert cfg_data["is_enabled"] is True


def test_whatsapp_bot_menu_and_hours_context(test_db):
    """TDD-TC-323: Bot response with active menu items, omitting unavailable items,
    and including store link.
    """
    from restaurant_os.integrations.whatsapp.bot import WhatsAppBot
    from restaurant_os.integrations.whatsapp.knowledge import WhatsAppKnowledgeService

    knowledge = WhatsAppKnowledgeService(test_db, ORGANIZATION_ID, BRANCH_ID)
    summary = knowledge.get_branch_knowledge_summary()

    # Active items should be present
    assert "Tacos al Pastor (Orden)" in summary["available_products_text"]
    assert "$95.00" in summary["available_products_text"]

    # 86'd / unavailable items must be strictly excluded
    assert "Gringa Especial" not in summary["available_products_text"]

    # Storefront link must follow canonical wildcard format: https://{slug}.mimenu.onl
    assert summary["storefront_url"] == "https://sucursal-roma.mimenu.onl"

    # Bot answer generation for a menu inquiry
    bot = WhatsAppBot(knowledge)
    reply = bot.generate_reply("Hola, ¿qué venden y qué me recomiendas?")
    assert "Tacos al Pastor" in reply
    assert "Gringa Especial" not in reply
    assert summary["storefront_url"] in reply


def test_whatsapp_multitenant_isolation_and_unmapped_number(test_db):
    """TDD-TC-324: Messages for an unknown or unmapped phone_number_id fail closed safely."""

    def override_get_session():
        yield test_db

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)

    unmapped_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba_unknown",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "5215500000000",
                                "phone_number_id": "unmapped_number_99999",
                            },
                            "messages": [
                                {
                                    "from": "5215599887766",
                                    "id": "wamid.UNKNOWN==",
                                    "text": {"body": "Hola"},
                                    "type": "text",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    body_bytes = json.dumps(unmapped_payload).encode("utf-8")
    valid_sig = _compute_signature(TEST_APP_SECRET, body_bytes)

    resp = client.post(
        "/integrations/whatsapp/webhook",
        content=body_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": valid_sig},
    )
    # Should acknowledge Meta with 200 OK so Meta doesn't retry infinitely,
    # but must log and not crash or expose other tenant info
    assert resp.status_code == 200


def test_whatsapp_store_mappings_and_logs_endpoints(test_db):
    """Verify listing and creating store mappings and listing logs for WhatsApp Business."""

    def override_get_session():
        yield test_db

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)

    # 1. List stores
    resp = client.get("/integrations/whatsapp/stores", headers={"X-Actor-User-Id": USER_ID})
    assert resp.status_code == 200
    stores = resp.json()
    assert len(stores) >= 1
    assert stores[0]["external_store_id"] == TEST_PHONE_NUMBER_ID

    # 2. List webhook logs
    resp_logs = client.get("/integrations/whatsapp/logs", headers={"X-Actor-User-Id": USER_ID})
    assert resp_logs.status_code == 200
    logs = resp_logs.json()
    assert isinstance(logs, list)


def test_whatsapp_knowledge_preview_endpoint(test_db):
    """Verify knowledge preview endpoint returns active menu, hours, and storefront url."""

    def override_get_session():
        yield test_db

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)

    resp = client.get(
        f"/integrations/whatsapp/knowledge-preview?branch_id={BRANCH_ID}",
        headers={"X-Actor-User-Id": USER_ID},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["branch_name"] == "Sucursal Roma"
    assert "Tacos al Pastor" in data["available_products_text"]
    assert "Gringa Especial" not in data["available_products_text"]
    assert data["storefront_url"] == "https://sucursal-roma.mimenu.onl"


def test_whatsapp_order_parser_intent_and_cart_link(test_db):
    """TDD-TC-325: Verify parser detects order intent, quantities, cents arithmetic,
    and cart link.
    """
    from restaurant_os.integrations.whatsapp.knowledge import WhatsAppKnowledgeService
    from restaurant_os.integrations.whatsapp.order_parser import WhatsAppOrderParser

    knowledge = WhatsAppKnowledgeService(test_db, ORGANIZATION_ID, BRANCH_ID)
    parser = WhatsAppOrderParser(knowledge)

    result = parser.parse_order_intent(
        "Hola buenas tardes, quiero 2 órdenes de tacos al pastor por favor"
    )

    assert result["is_order_intent"] is True
    assert len(result["matched_items"]) == 1
    item = result["matched_items"][0]
    assert item["product_name"] == "Tacos al Pastor (Orden)"
    assert item["quantity"] == 2
    assert item["unit_price_cents"] == 9500
    assert item["subtotal_cents"] == 19000
    assert result["total_cents"] == 19000
    assert result["cart_url"].startswith("https://sucursal-roma.mimenu.onl/cart?items=")
    assert "SKU-TAC-PAS" in result["cart_url"] or item["product_id"] in result["cart_url"]


def test_whatsapp_order_parser_handles_86d_unavailable_items(test_db):
    """TDD-TC-326: Verify parser flags 86'd (is_available=False) items and
    excludes them from total.
    """
    from restaurant_os.integrations.whatsapp.knowledge import WhatsAppKnowledgeService
    from restaurant_os.integrations.whatsapp.order_parser import WhatsAppOrderParser

    knowledge = WhatsAppKnowledgeService(test_db, ORGANIZATION_ID, BRANCH_ID)
    parser = WhatsAppOrderParser(knowledge)

    # Gringa Especial is is_available=False in test_db fixture
    result = parser.parse_order_intent("Quiero 2 tacos al pastor y una gringa especial")

    assert result["is_order_intent"] is True
    assert len(result["matched_items"]) == 1
    assert result["matched_items"][0]["product_name"] == "Tacos al Pastor (Orden)"
    assert len(result["unavailable_items"]) == 1
    unavail = result["unavailable_items"][0]
    assert unavail["product_name"] == "Gringa Especial"
    assert unavail["quantity"] == 1
    assert result["total_cents"] == 19000  # Only pastor tacos are charged


def test_whatsapp_order_parser_handles_unmatched_items(test_db):
    """TDD-TC-327: Verify items not in catalog are collected in unmatched_items without crashing."""
    from restaurant_os.integrations.whatsapp.knowledge import WhatsAppKnowledgeService
    from restaurant_os.integrations.whatsapp.order_parser import WhatsAppOrderParser

    knowledge = WhatsAppKnowledgeService(test_db, ORGANIZATION_ID, BRANCH_ID)
    parser = WhatsAppOrderParser(knowledge)

    result = parser.parse_order_intent("Me traes una orden de sushi roll y dos tacos al pastor")

    assert result["is_order_intent"] is True
    assert len(result["matched_items"]) == 1
    assert result["matched_items"][0]["product_name"] == "Tacos al Pastor (Orden)"
    assert any("sushi" in u.lower() for u in result["unmatched_items"])


def test_whatsapp_bot_conversational_order_proposal(test_db):
    """TDD-TC-328: Verify bot outputs itemized proposal with MXN formatting,
    86'd warning, and cart link.
    """
    from restaurant_os.integrations.whatsapp.bot import WhatsAppBot
    from restaurant_os.integrations.whatsapp.knowledge import WhatsAppKnowledgeService

    knowledge = WhatsAppKnowledgeService(test_db, ORGANIZATION_ID, BRANCH_ID)
    bot = WhatsAppBot(knowledge)

    reply = bot.generate_reply("Hola, me gustaría pedir 2 tacos al pastor y una gringa especial")

    # Verify itemized list and prices
    assert "Tacos al Pastor" in reply
    assert "$190.00" in reply
    # Verify 86'd warning
    assert "Gringa Especial" in reply
    assert "agotado" in reply.lower() or "no disponible" in reply.lower()
    # Verify prefilled storefront link
    assert "https://sucursal-roma.mimenu.onl/cart?items=" in reply


def _seed_test_order(
    session,
    order_id: str,
    status: str,
    order_type: str = "delivery",
    phone: str = "5512345678",
    name: str = "Juan Perez",
    branch_id: str = BRANCH_ID,
    folio: str | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    cust_snapshot = {"name": name, "phone": phone} if phone else {"name": name}
    order_folio = folio or f"FOL-{uuid.uuid4().hex[:6].upper()}"
    session.execute(
        models.orders.insert().values(
            id=order_id,
            organization_id=ORGANIZATION_ID,
            branch_id=branch_id,
            folio=order_folio,
            channel="PUBLIC_INTENT",
            public_order_intent_id=str(uuid.uuid4()),
            public_order_intent_status="ACCEPTED",
            status=status,
            total_cents=19000,
            currency="MXN",
            order_type=order_type,
            customer_snapshot=cust_snapshot,
            version=1,
            created_at=now,
        )
    )
    session.commit()
    return order_id


def test_whatsapp_notification_order_accepted(test_db):
    """TDD-TC-329: Verify WhatsApp notification is sent when order is accepted/in_production."""
    from restaurant_os.integrations.whatsapp.notifications import WhatsAppNotificationService

    order_id = str(uuid.uuid4())
    _seed_test_order(
        test_db, order_id, "ACCEPTED", name="Juan Perez", phone="5512345678", folio="FOL-1042"
    )

    service = WhatsAppNotificationService(test_db, ORGANIZATION_ID, BRANCH_ID)
    result = service.notify_order_status_update(order_id, "ACCEPTED")

    assert result["status"] == "sent"
    assert result["to_phone"] == "5512345678"
    assert "Juan Perez" in result["message"]
    assert "FOL-1042" in result["message"]
    assert "preparar" in result["message"].lower() or "aceptado" in result["message"].lower()
    assert "https://sucursal-roma.mimenu.onl/orders/" in result["message"]


def test_whatsapp_notification_ready_and_in_delivery(test_db):
    """TDD-TC-330: Verify READY notification for pickup and IN_DELIVERY for courier delivery."""
    from restaurant_os.integrations.whatsapp.notifications import WhatsAppNotificationService

    service = WhatsAppNotificationService(test_db, ORGANIZATION_ID, BRANCH_ID)

    # 1. Takeout order READY
    takeout_id = str(uuid.uuid4())
    _seed_test_order(test_db, takeout_id, "READY", order_type="takeout")
    res_takeout = service.notify_order_status_update(takeout_id, "READY")
    assert res_takeout["status"] == "sent"
    assert (
        "recoger" in res_takeout["message"].lower() or "mostrador" in res_takeout["message"].lower()
    )

    # 2. Delivery order IN_DELIVERY
    delivery_id = str(uuid.uuid4())
    _seed_test_order(test_db, delivery_id, "IN_DELIVERY", order_type="delivery")
    res_delivery = service.notify_order_status_update(delivery_id, "IN_DELIVERY")
    assert res_delivery["status"] == "sent"
    assert (
        "repartidor" in res_delivery["message"].lower()
        or "camino" in res_delivery["message"].lower()
    )


def test_whatsapp_notification_delivered_smart_rating(test_db):
    """TDD-TC-331: Verify DELIVERED notification includes delivery confirmation
    and Smart Rating link.
    """
    from restaurant_os.integrations.whatsapp.notifications import WhatsAppNotificationService

    order_id = str(uuid.uuid4())
    _seed_test_order(test_db, order_id, "DELIVERED")

    service = WhatsAppNotificationService(test_db, ORGANIZATION_ID, BRANCH_ID)
    result = service.notify_order_status_update(order_id, "DELIVERED")

    assert result["status"] == "sent"
    assert "entregado" in result["message"].lower()
    assert "calificar" in result["message"].lower() or "experiencia" in result["message"].lower()
    assert (
        "rating" in result["message"]
        or "review" in result["message"]
        or "feedback" in result["message"]
    )


def test_whatsapp_notification_skipped_safely(test_db):
    """TDD-TC-332: Verify service skips safely without errors if no phone or WhatsApp disabled."""
    from restaurant_os.integrations.whatsapp.notifications import WhatsAppNotificationService

    # 1. Order without phone
    order_no_phone = str(uuid.uuid4())
    _seed_test_order(test_db, order_no_phone, "ACCEPTED", phone="")
    service = WhatsAppNotificationService(test_db, ORGANIZATION_ID, BRANCH_ID)
    res_no_phone = service.notify_order_status_update(order_no_phone, "ACCEPTED")
    assert res_no_phone["status"] == "skipped"
    assert res_no_phone["reason"] == "no_customer_phone"

    # 2. Unmapped branch
    unmapped_branch = str(uuid.uuid4())
    service_unmapped = WhatsAppNotificationService(test_db, ORGANIZATION_ID, unmapped_branch)
    res_unmapped = service_unmapped.notify_order_status_update(order_no_phone, "ACCEPTED")
    assert res_unmapped["status"] == "skipped"
    assert res_unmapped["reason"] == "whatsapp_not_connected"


def test_whatsapp_notify_and_simulate_endpoints(test_db):
    """Verify HTTP endpoints for proactive notifications and simulation preview."""

    def override_get_session():
        yield test_db

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)

    # 1. Test POST /integrations/whatsapp/simulate-notification
    sim_resp = client.post(
        "/integrations/whatsapp/simulate-notification",
        json={
            "status": "DELIVERED",
            "customer_name": "Ana Sofia",
            "folio": "FOL-777",
            "branch_name": "Tacos El Guero",
        },
        headers={"X-Actor-User-Id": USER_ID},
    )
    assert sim_resp.status_code == 200
    sim_data = sim_resp.json()
    assert sim_data["status"] == "DELIVERED"
    assert "Ana Sofia" in sim_data["message"] or "FOL-777" in sim_data["message"]
    assert sim_data["smart_rating_url"] is not None

    # 2. Test POST /integrations/whatsapp/orders/{order_id}/notify
    order_id = str(uuid.uuid4())
    _seed_test_order(test_db, order_id, "ACCEPTED", name="Carlos", phone="5599887766")

    notify_resp = client.post(
        f"/integrations/whatsapp/orders/{order_id}/notify",
        json={"status": "READY"},
        headers={"X-Actor-User-Id": USER_ID},
    )
    assert notify_resp.status_code == 200
    notify_data = notify_resp.json()
    assert notify_data["status"] == "sent"
    assert notify_data["to_phone"] == "5599887766"


def _seed_test_customer(
    session,
    customer_id: str,
    phone: str,
    name: str = "Maria Lopez",
    orders_count: int = 1,
    days_inactive: int = 40,
) -> str:
    now = datetime.now(timezone.utc)
    from datetime import timedelta

    order_date = now - timedelta(days=days_inactive)

    session.execute(
        models.customers.insert().values(
            id=customer_id,
            organization_id=ORGANIZATION_ID,
            name=name,
            origin_branch_id=BRANCH_ID,
            status="active",
            created_at=order_date,
            updated_at=now,
        )
    )
    phone_id = str(uuid.uuid4())
    session.execute(
        models.customer_phones.insert().values(
            id=phone_id,
            customer_id=customer_id,
            captured_number=phone,
            normalized_number=phone,
            phone_type="mobile",
            is_primary=True,
            whatsapp_enabled=True,
            status="active",
            created_at=order_date,
            updated_at=now,
        )
    )
    for _ in range(orders_count):
        order_id = str(uuid.uuid4())
        session.execute(
            models.orders.insert().values(
                id=order_id,
                organization_id=ORGANIZATION_ID,
                branch_id=BRANCH_ID,
                folio=f"FOL-{uuid.uuid4().hex[:6].upper()}",
                channel="PUBLIC_INTENT",
                public_order_intent_id=str(uuid.uuid4()),
                public_order_intent_status="ACCEPTED",
                status="CLOSED",
                total_cents=19000,
                currency="MXN",
                order_type="delivery",
                customer_id=customer_id,
                customer_snapshot={"name": name, "phone": phone},
                version=1,
                created_at=order_date,
            )
        )
    session.commit()
    return customer_id


def test_whatsapp_campaign_segmentation_and_preview(test_db):
    """TDD-TC-333: Campaign segmentation and preview with coupon and opt-out clause."""
    from restaurant_os.integrations.whatsapp.campaigns import WhatsAppCampaignService

    cid = str(uuid.uuid4())
    _seed_test_customer(test_db, cid, phone="5533221100", name="Laura Garcia", days_inactive=35)

    service = WhatsAppCampaignService(test_db, ORGANIZATION_ID, BRANCH_ID)
    preview = service.preview_campaign(segment="churn_risk", discount_code="VUELVE10")

    assert preview["total_eligible"] >= 1
    assert "VUELVE10" in preview["sample_message"]
    assert "STOP" in preview["sample_message"] or "BAJA" in preview["sample_message"]
    assert "https://sucursal-roma.mimenu.onl" in preview["sample_message"]


def test_whatsapp_campaign_dispatch_to_segment(test_db):
    """TDD-TC-334: Dispatch campaign to target segment with metrics."""
    from restaurant_os.integrations.whatsapp.campaigns import WhatsAppCampaignService

    cid = str(uuid.uuid4())
    _seed_test_customer(test_db, cid, phone="5544332211", name="Pedro Sola", days_inactive=45)

    service = WhatsAppCampaignService(test_db, ORGANIZATION_ID, BRANCH_ID)
    result = service.dispatch_campaign(segment="churn_risk", discount_code="DESCUENTO15")

    assert result["status"] == "completed"
    assert result["total_targets"] >= 1
    assert result["sent_count"] >= 1
    assert result["discount_code"] == "DESCUENTO15"


def test_whatsapp_opt_out_registration_on_stop(test_db):
    """TDD-TC-335: Automatic opt-out registration when customer sends STOP or BAJA."""
    from restaurant_os.integrations.whatsapp.bot import WhatsAppBot
    from restaurant_os.integrations.whatsapp.campaigns import WhatsAppCampaignService
    from restaurant_os.integrations.whatsapp.knowledge import WhatsAppKnowledgeService

    service = WhatsAppCampaignService(test_db, ORGANIZATION_ID, BRANCH_ID)
    phone = "5555667788"

    assert service.is_opted_out(phone) is False
    service.record_opt_out(phone, reason="user_requested")
    assert service.is_opted_out(phone) is True

    # Test bot reply handling
    knowledge = WhatsAppKnowledgeService(test_db, ORGANIZATION_ID, BRANCH_ID)
    bot = WhatsAppBot(knowledge, campaign_service=service)
    reply = bot.generate_reply("Por favor STOP ya no me envien nada")
    assert "baja" in reply.lower() or "desuscrito" in reply.lower()
    assert "promociones" in reply.lower()


def test_whatsapp_opted_out_numbers_excluded_from_campaign(test_db):
    """TDD-TC-336: Exclude opted-out numbers from marketing campaigns
    while keeping order notifications.
    """
    from restaurant_os.integrations.whatsapp.campaigns import WhatsAppCampaignService
    from restaurant_os.integrations.whatsapp.notifications import WhatsAppNotificationService

    opt_out_phone = "5588990011"
    cid = str(uuid.uuid4())
    _seed_test_customer(test_db, cid, phone=opt_out_phone, name="Roberto M.", days_inactive=50)

    service = WhatsAppCampaignService(test_db, ORGANIZATION_ID, BRANCH_ID)
    service.record_opt_out(opt_out_phone, reason="user_stop")

    # Marketing campaign dispatch must skip opted-out customer
    result = service.dispatch_campaign(segment="churn_risk", discount_code="REGRESA20")
    assert result["skipped_count"] >= 1

    # But transactional order notification must still succeed (utility exemption)
    order_id = str(uuid.uuid4())
    _seed_test_order(test_db, order_id, "ACCEPTED", name="Roberto M.", phone=opt_out_phone)
    notifier = WhatsAppNotificationService(test_db, ORGANIZATION_ID, BRANCH_ID)
    notif_res = notifier.notify_order_status_update(order_id, "ACCEPTED")
    assert notif_res["status"] == "sent"


def test_whatsapp_campaign_http_endpoints(test_db):
    """Verify HTTP endpoints for campaign segments, preview, and send."""

    def override_get_session():
        yield test_db

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)

    cid = str(uuid.uuid4())
    _seed_test_customer(test_db, cid, phone="5522334455", name="Claudia V.", days_inactive=40)

    # 1. GET /integrations/whatsapp/campaigns/segments
    seg_resp = client.get(
        f"/integrations/whatsapp/campaigns/segments?branch_id={BRANCH_ID}",
        headers={"X-Actor-User-Id": USER_ID},
    )
    assert seg_resp.status_code == 200
    seg_data = seg_resp.json()
    assert "churn_risk" in seg_data["segments"]
    assert "vip" in seg_data["segments"]

    # 2. POST /integrations/whatsapp/campaigns/preview
    prev_resp = client.post(
        "/integrations/whatsapp/campaigns/preview",
        json={"branch_id": BRANCH_ID, "segment": "churn_risk", "discount_code": "PROMO10"},
        headers={"X-Actor-User-Id": USER_ID},
    )
    assert prev_resp.status_code == 200
    prev_data = prev_resp.json()
    assert "PROMO10" in prev_data["sample_message"]
    assert "STOP" in prev_data["sample_message"] or "BAJA" in prev_data["sample_message"]

    # 3. POST /integrations/whatsapp/campaigns/send
    send_resp = client.post(
        "/integrations/whatsapp/campaigns/send",
        json={"branch_id": BRANCH_ID, "segment": "churn_risk", "discount_code": "PROMO10"},
        headers={"X-Actor-User-Id": USER_ID},
    )
    assert send_resp.status_code == 200
    send_data = send_resp.json()
    assert send_data["status"] == "completed"
    assert send_data["sent_count"] >= 1


def test_whatsapp_templates_sync_and_list(test_db):
    """TDD-TC-337: Verify HSM template synchronization and listing via
    WhatsAppTemplateService and HTTP endpoints.
    """
    from restaurant_os.integrations.whatsapp.templates import WhatsAppTemplateService

    # 1. Service direct unit verification
    templates = WhatsAppTemplateService.list_waba_templates(TEST_WABA_ID, environment="sandbox")
    assert len(templates) >= 2
    template_names = [t["name"] for t in templates]
    assert "restaurantos_order_update" in template_names
    assert "restaurantos_reengagement_offer" in template_names

    sync_result = WhatsAppTemplateService.register_standard_templates(
        TEST_WABA_ID, environment="sandbox"
    )
    assert sync_result["status"] == "success"
    assert sync_result["waba_id"] == TEST_WABA_ID

    summary = WhatsAppTemplateService.get_template_status_summary(
        TEST_WABA_ID, environment="sandbox"
    )
    assert summary["total_standard"] == 2
    assert all(t["status"] == "APPROVED" for t in summary["templates"])

    # 2. HTTP endpoints verification
    def override_get_session():
        yield test_db

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)

    get_resp = client.get(
        f"/integrations/whatsapp/templates?branch_id={BRANCH_ID}",
        headers={"X-Actor-User-Id": USER_ID},
    )
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert "templates" in get_data
    assert len(get_data["templates"]) == 2

    post_resp = client.post(
        f"/integrations/whatsapp/templates/sync?branch_id={BRANCH_ID}",
        headers={"X-Actor-User-Id": USER_ID},
    )
    assert post_resp.status_code == 200
    post_data = post_resp.json()
    assert post_data["status"] == "success"


def test_whatsapp_order_notification_via_template(test_db):
    """TDD-TC-338: Structured utility template dispatch for 24h window bypass."""
    import restaurant_os.integrations.whatsapp.adapter as wa_adapter
    from restaurant_os.integrations.whatsapp.notifications import WhatsAppNotificationService

    order_id = str(uuid.uuid4())
    _seed_test_order(
        test_db, order_id, "ACCEPTED", name="Mauricio G.", phone="5511223344", folio="FOL-9988"
    )

    service = WhatsAppNotificationService(test_db, ORGANIZATION_ID, BRANCH_ID)

    with patch(
        "restaurant_os.integrations.whatsapp.adapter.send_whatsapp_template_message",
        wraps=wa_adapter.send_whatsapp_template_message,
    ) as mock_send:
        result = service.notify_order_status_update(order_id, "ACCEPTED", use_template=True)
        assert result["status"] == "sent"
        assert result["template_used"] == "restaurantos_order_update"
        assert mock_send.called
        call_kwargs = mock_send.call_args[1]
        assert call_kwargs["template_name"] == "restaurantos_order_update"
        assert call_kwargs["language_code"] == "es_MX"
        # 5 positional parameters: [customer_name, folio, branch_name, status, tracking_url]
        assert "Mauricio G." in call_kwargs["body_parameters"]
        assert "FOL-9988" in call_kwargs["body_parameters"]


def test_whatsapp_campaign_dispatch_via_template(test_db):
    """TDD-TC-339: Structured marketing template dispatch with discount code and opt-out."""
    import restaurant_os.integrations.whatsapp.adapter as wa_adapter
    from restaurant_os.integrations.whatsapp.campaigns import WhatsAppCampaignService

    cid = str(uuid.uuid4())
    _seed_test_customer(test_db, cid, phone="5566778899", name="Mariana R.", days_inactive=30)

    service = WhatsAppCampaignService(test_db, ORGANIZATION_ID, BRANCH_ID)

    with patch(
        "restaurant_os.integrations.whatsapp.adapter.send_whatsapp_template_message",
        wraps=wa_adapter.send_whatsapp_template_message,
    ) as mock_send:
        result = service.dispatch_campaign(
            segment="churn_risk", discount_code="REGRESA15", use_template=True
        )
        assert result["status"] == "completed"
        assert result["sent_count"] >= 1
        assert mock_send.called
        call_kwargs = mock_send.call_args[1]
        assert call_kwargs["template_name"] == "restaurantos_reengagement_offer"
        assert call_kwargs["language_code"] == "es_MX"
        assert "REGRESA15" in call_kwargs["body_parameters"]


def test_whatsapp_embedded_signup_config_and_sdk_params(test_db):
    """TDD-TC-340: Configure and persist Meta Configuration ID for Embedded Signup SDK popup."""

    def override_get_session():
        yield test_db

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)

    # 1. Update config with config_id
    payload = {
        "branch_id": BRANCH_ID,
        "app_id": "app_987654321",
        "config_id": "meta_cfg_778899",
        "waba_id": TEST_WABA_ID,
        "phone_number_id": TEST_PHONE_NUMBER_ID,
        "app_secret": TEST_APP_SECRET,
        "access_token": "EAAB_test_token_hsm",
        "verify_token": TEST_VERIFY_TOKEN,
        "environment": "sandbox",
        "is_enabled": True,
    }
    put_resp = client.put(
        "/integrations/whatsapp/config",
        json=payload,
        headers={"X-Actor-User-Id": USER_ID},
    )
    assert put_resp.status_code == 200

    # 2. Retrieve config and verify config_id is returned
    get_resp = client.get(
        f"/integrations/whatsapp/config?branch_id={BRANCH_ID}",
        headers={"X-Actor-User-Id": USER_ID},
    )
    assert get_resp.status_code == 200
    cfg_data = get_resp.json()
    assert cfg_data["app_id"] == "app_987654321"
    assert cfg_data["config_id"] == "meta_cfg_778899"


def test_whatsapp_storefront_url_never_returns_raw_uuid(test_db):
    """TDD-TC-341: Verify storefront URL resolution NEVER returns a raw UUID even if
    branch.slug is NULL or contains a UUID string.
    """
    from restaurant_os.integrations.whatsapp.urls import (
        is_uuid_string,
        resolve_storefront_slug,
        resolve_storefront_url,
    )

    # 1. Update branch to have slug = None
    test_db.execute(
        models.branches.update()
        .where(models.branches.c.id == BRANCH_ID)
        .values(slug=None)
    )
    test_db.commit()

    url, slug = resolve_storefront_url(test_db, ORGANIZATION_ID, BRANCH_ID)
    assert not is_uuid_string(slug)
    assert not is_uuid_string(url.split("//")[1].split(".")[0])
    # Resolves to slugified organization name "Kiwi Corporativo" -> "kiwi-corporativo"
    assert slug == "kiwi-corporativo"
    assert resolve_storefront_slug(test_db, ORGANIZATION_ID, BRANCH_ID) == "kiwi-corporativo"
    assert url == "https://kiwi-corporativo.mimenu.onl"

    # 2. Update branch to have a raw UUID string as slug
    raw_uuid = str(uuid.uuid4())
    test_db.execute(
        models.branches.update()
        .where(models.branches.c.id == BRANCH_ID)
        .values(slug=raw_uuid)
    )
    test_db.commit()

    url, slug = resolve_storefront_url(test_db, ORGANIZATION_ID, BRANCH_ID)
    assert slug != raw_uuid
    assert not is_uuid_string(slug)
    assert slug == "kiwi-corporativo"
    assert url == "https://kiwi-corporativo.mimenu.onl"


def test_whatsapp_storefront_url_prefers_organization_preferred_slug(test_db):
    """TDD-TC-342: Verify preferred_public_slug takes precedence when configured."""
    from restaurant_os.integrations.whatsapp.urls import resolve_storefront_url

    test_db.execute(
        models.organizations.update()
        .where(models.organizations.c.id == ORGANIZATION_ID)
        .values(preferred_public_slug="don-taco")
    )
    test_db.commit()

    url, slug = resolve_storefront_url(test_db, ORGANIZATION_ID, BRANCH_ID)
    assert slug == "don-taco"
    assert url == "https://don-taco.mimenu.onl"


def test_whatsapp_url_builders_and_slugify():
    """TDD-TC-343: Verify URL builders produce canonical links and slugify handles accents."""
    from restaurant_os.integrations.whatsapp.urls import (
        build_cart_url,
        build_rating_url,
        build_tracking_url,
        slugify,
    )

    base = "https://elguero.mimenu.onl"
    assert build_tracking_url(base, "ORD-456") == "https://elguero.mimenu.onl/orders/ORD-456"
    assert build_rating_url(base, "ORD-456") == "https://elguero.mimenu.onl/orders/ORD-456/review"

    items = [{"product_id": "p1", "quantity": 2}]
    cart = build_cart_url(base, items)
    assert cart.startswith("https://elguero.mimenu.onl/cart?items=")
    assert "from=wa" in cart

    # Accents, punctuation, multiple spaces
    assert slugify("Taquería El Güero & Cervecería!") == "taqueria-el-guero-cerveceria"
    assert slugify("Los 3 Hermanos (Matriz)") == "los-3-hermanos-matriz"
