# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-test-facturapi-integration-synthetic-v1
"""Tests for Facturapi and CFDI 4.0 Invoicing Integration (PRD-FR-234)."""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.auth import create_session_token
from restaurant_os.config import get_settings
from restaurant_os.database import get_session
from restaurant_os.invoicing.facturapi_client import FacturapiClient
from restaurant_os.invoicing.service import InvoicingService
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

    session.commit()
    yield engine, session
    session.close()


@pytest.fixture
def client(test_db):
    engine, _ = test_db
    SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_session():
        s = SessionFactory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    token = create_session_token({"sub": USER_ID}, get_settings().secret_key)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def invoicing_svc():
    return InvoicingService()


def test_facturapi_config_crud(test_db, invoicing_svc):
    _, session = test_db

    # Initially None
    cfg = invoicing_svc.get_config(session, ORGANIZATION_ID)
    assert cfg is None

    # Save config
    saved = invoicing_svc.save_config(
        session,
        ORGANIZATION_ID,
        {
            "is_enabled": True,
            "environment": "sandbox",
            "api_key": "sk_test_mock_key_12345",
            "organization_legal_name": "RESTAURANTE KIWI SA DE CV",
            "organization_rfc": "KIW210101ABC",
            "organization_tax_system": "601",
            "organization_zip": "80000",
            "default_product_sat_key": "90101501",
            "default_unit_sat_key": "E48",
            "series": "F",
            "enable_self_invoicing": True,
            "self_invoicing_domain": "kiwirest",
            "self_invoicing_days_valid": 7,
            "print_qr_on_ticket": True,
        },
    )
    assert saved["is_enabled"] is True
    assert saved["organization_rfc"] == "KIW210101ABC"
    assert saved["environment"] == "sandbox"

    # Fetch again
    fetched = invoicing_svc.get_config(session, ORGANIZATION_ID)
    assert fetched is not None
    assert fetched["organization_legal_name"] == "RESTAURANTE KIWI SA DE CV"


def test_create_receipt_for_order(test_db, invoicing_svc):
    _, session = test_db
    order_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    # Create test order with UBER_EATS channel to satisfy check constraint
    session.execute(
        models.orders.insert().values(
            id=order_id,
            organization_id=ORGANIZATION_ID,
            branch_id=BRANCH_ID,
            folio="UBER-U100",
            channel="UBER_EATS",
            status="COMPLETED",
            total_cents=25000,
            currency="MXN",
            created_at=now,
        )
    )
    session.commit()

    # Save config
    invoicing_svc.save_config(
        session,
        ORGANIZATION_ID,
        {
            "is_enabled": True,
            "environment": "sandbox",
            "api_key": "sk_test_mock",
            "organization_rfc": "KIW210101ABC",
            "organization_legal_name": "RESTAURANTE KIWI SA DE CV",
            "enable_self_invoicing": True,
            "self_invoicing_domain": "kiwirest",
        },
    )

    # Generate receipt for order
    receipt = invoicing_svc.create_receipt_for_order(session, ORGANIZATION_ID, BRANCH_ID, order_id)
    assert receipt is not None
    assert "receipt_id" in receipt
    assert receipt["status"] == "simulated"
    assert receipt["provider_confirmed"] is False


def test_issue_invoice_for_orders(test_db, invoicing_svc, monkeypatch):
    _, session = test_db
    order_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    # Create order
    session.execute(
        models.orders.insert().values(
            id=order_id,
            organization_id=ORGANIZATION_ID,
            branch_id=BRANCH_ID,
            folio="UBER-U101",
            channel="UBER_EATS",
            status="COMPLETED",
            total_cents=35000,
            currency="MXN",
            created_at=now,
        )
    )
    session.commit()

    invoicing_svc.save_config(
        session,
        ORGANIZATION_ID,
        {"is_enabled": True, "environment": "sandbox", "api_key": "sandbox_real_test_key"},
    )
    monkeypatch.setattr(
        FacturapiClient,
        "create_invoice",
        lambda *_args: {
            "id": "confirmed-invoice-101",
            "status": "valid",
            "uuid": "CONFIRMED-UUID-101",
            "folio_number": "101",
        },
    )
    monkeypatch.setattr(FacturapiClient, "send_email", lambda *_args: {"status": "queued"})

    receptor_data = {
        "rfc": "XAXX010101000",
        "legal_name": "PUBLICO EN GENERAL",
        "zip": "80000",
        "tax_system": "616",
        "use": "S01",
        "payment_form": "01",
        "payment_method": "PUE",
        "email": "cliente@example.com",
    }

    invoice = invoicing_svc.issue_invoice(
        session,
        org_id=ORGANIZATION_ID,
        branch_id=BRANCH_ID,
        order_ids=[order_id],
        receptor=receptor_data,
    )

    assert invoice is not None
    assert invoice["status"] == "issued"
    assert invoice["uuid_sat"] is not None
    assert invoice["total_cents"] == 35000
    assert invoice["pdf_url"] is not None
    assert invoice["xml_url"] is not None

    # List invoices
    invoices = invoicing_svc.list_invoices(session, ORGANIZATION_ID, BRANCH_ID)
    assert len(invoices) >= 1
    assert any(i["id"] == invoice["id"] for i in invoices)


def test_cancel_invoice(test_db, invoicing_svc, monkeypatch):
    _, session = test_db
    order_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    session.execute(
        models.orders.insert().values(
            id=order_id,
            organization_id=ORGANIZATION_ID,
            branch_id=BRANCH_ID,
            folio="UBER-U102",
            channel="UBER_EATS",
            status="COMPLETED",
            total_cents=18000,
            currency="MXN",
            created_at=now,
        )
    )
    session.commit()

    invoicing_svc.save_config(
        session,
        ORGANIZATION_ID,
        {"is_enabled": True, "environment": "sandbox", "api_key": "sandbox_real_test_key"},
    )
    monkeypatch.setattr(
        FacturapiClient,
        "create_invoice",
        lambda *_args: {
            "id": "confirmed-invoice-102",
            "status": "valid",
            "uuid": "CONFIRMED-UUID-102",
            "folio_number": "102",
        },
    )
    monkeypatch.setattr(FacturapiClient, "cancel_invoice", lambda *_args: {"status": "canceled"})

    invoice = invoicing_svc.issue_invoice(
        session,
        org_id=ORGANIZATION_ID,
        branch_id=BRANCH_ID,
        order_ids=[order_id],
        receptor={
            "rfc": "XAXX010101000",
            "legal_name": "PUBLICO EN GENERAL",
            "zip": "80000",
            "tax_system": "616",
            "use": "S01",
            "payment_form": "04",
            "payment_method": "PUE",
        },
    )

    # Cancel invoice with SAT reason '02'
    cancelled = invoicing_svc.cancel_invoice(
        session,
        org_id=ORGANIZATION_ID,
        invoice_id=invoice["id"],
        motive="02",
    )
    assert cancelled["status"] == "cancelled"
    assert cancelled["cancellation_reason"] == "02"


def test_api_facturapi_endpoints(client, auth_headers):
    # GET default config
    resp = client.get("/api/v1/integrations/facturapi/config", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["is_enabled"] is False

    # POST save config
    resp_save = client.post(
        "/api/v1/integrations/facturapi/config",
        json={
            "is_enabled": True,
            "environment": "sandbox",
            "api_key": "sk_test_mock_123",
            "organization_rfc": "KIW210101ABC",
            "organization_legal_name": "RESTAURANTE KIWI SA DE CV",
            "enable_self_invoicing": True,
        },
        headers=auth_headers,
    )
    assert resp_save.status_code == 200
    assert resp_save.json()["is_enabled"] is True

    # Test connection
    resp_test = client.post(
        "/api/v1/integrations/facturapi/test-connection",
        headers=auth_headers,
    )
    assert resp_test.status_code == 200
    assert resp_test.json()["status"] == "simulated"
    assert resp_test.json()["provider_confirmed"] is False
