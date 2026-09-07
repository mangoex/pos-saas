# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-test-saas-self-invoicing-synthetic-v1
"""TDD tests for 1-Click Autofacturación CFDI 4.0 SAT through FacturAPI."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.database import get_session
from restaurant_os.main import app
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

    app.dependency_overrides[get_session] = override_get_session
    return TestClient(app)


def _public_key_for_branch(client: TestClient, branch_id: str) -> str:
    generator = client.app.dependency_overrides[get_session]()
    session = next(generator)
    try:
        return str(
            session.scalar(
                sa.select(models.public_order_keys.c.public_key).where(
                    models.public_order_keys.c.branch_id == branch_id,
                    models.public_order_keys.c.status == "active",
                )
            )
        )
    finally:
        session.close()


def _setup_tenant_and_order(
    client: TestClient, suffix: str = ""
) -> tuple[dict[str, str], dict[str, str], str]:
    # 1. Sign up tenant
    signup_resp = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": f"Tacos El Rey{suffix}",
            "owner_name": "Reynaldo Lopez",
            "email": f"rey{suffix}@tacoselrey.com",
            "password": "Password123!",
            "business_type": "taqueria",
        },
    )
    assert signup_resp.status_code == 201
    auth_data = signup_resp.json()
    token = auth_data["token"]
    headers = {"Authorization": f"Bearer {token}"}
    branch_id = auth_data["branch"]["id"]

    # 2. Configure FacturAPI
    cfg_resp = client.post(
        "/api/v1/integrations/facturapi/config",
        headers=headers,
        json={
            "is_enabled": True,
            "environment": "sandbox",
            "api_key": "mock_test_key_123",
            "organization_legal_name": "TACOS EL REY SA DE CV",
            "organization_rfc": "TER210101XYZ",
            "organization_tax_system": "601",
            "organization_zip": "06700",
            "series": "F",
            "enable_self_invoicing": True,
            "print_qr_on_ticket": True,
        },
    )
    assert cfg_resp.status_code == 200

    # 3. Create a paid order
    create_order_resp = client.post(
        "/api/v1/orders",
        headers=headers,
        json={
            "channel": "dine_in",
            "table_number": "4",
            "diners": 2,
            "items": [
                {
                    "name": "Orden de Pastor con Queso",
                    "quantity": 2,
                    "unit_price_cents": 8500,
                    "notes": "con todo",
                },
                {
                    "name": "Refresco Coca-Cola",
                    "quantity": 2,
                    "unit_price_cents": 3500,
                },
            ],
            "payment": {
                "method": "card_debit",
                "amount_cents": 24000,
            },
        },
    )
    # If order creation through /api/v1/orders requires specific payload, let's verify
    if create_order_resp.status_code != 200:
        # Fallback direct DB creation for clean test setup
        gen = client.app.dependency_overrides[get_session]()
        session = next(gen)
        try:
            order_id = f"self-invoice-order-{suffix or 'default'}"
            org_id = auth_data["organization"]["id"]
            now = sa.func.now()
            session.execute(
                models.orders.insert().values(
                    id=order_id,
                    organization_id=org_id,
                    branch_id=branch_id,
                    folio="FOL-0042",
                    order_type="dine_in",
                    channel="UBER_EATS",
                    status="completed",
                    total_cents=24000,
                    payment_method_intent="card_debit",
                    created_at=now,
                )
            )
            session.commit()
        finally:
            session.close()
        return headers, auth_data, "FOL-0042"

    order_data = create_order_resp.json()
    return headers, auth_data, order_data.get("folio", "FOL-0042")


def test_public_self_invoice_lookup_by_folio() -> None:
    client = _client_with_db()
    headers, auth_data, folio = _setup_tenant_and_order(client)

    # Public comensal queries ticket without auth token
    public_key = _public_key_for_branch(client, auth_data["branch"]["id"])
    lookup_resp = client.get(
        "/api/v1/self-invoice/lookup", params={"folio": folio, "public_key": public_key}
    )
    assert lookup_resp.status_code == 200
    ticket = lookup_resp.json()
    assert ticket["folio"] == folio
    assert ticket["total_cents"] == 24000
    assert ticket["is_invoiced"] is False
    assert "business_name" in ticket


def test_public_self_invoice_emit_and_idempotency() -> None:
    client = _client_with_db()
    headers, auth_data, folio = _setup_tenant_and_order(client)

    # 1. First emission by customer (CFDI 4.0)
    emit_payload = {
        "folio": folio,
        "public_key": _public_key_for_branch(client, auth_data["branch"]["id"]),
        "rfc": "GOMR880101ABC",
        "legal_name": "RODRIGO GOMEZ MARTINEZ",
        "zip": "06700",
        "tax_system": "612",  # Personas Físicas con Actividades Empresariales
        "use": "G03",  # Gastos en general
        "email": "rodrigo@empresa.com",
    }
    emit_resp = client.post("/api/v1/self-invoice/emit", json=emit_payload)
    assert emit_resp.status_code == 200
    inv_data = emit_resp.json()
    assert inv_data["status"] == "simulated"
    assert inv_data["provider_confirmed"] is False
    assert inv_data["folio"] == folio

    # 2. A sandbox simulation cannot create fiscal idempotency state.
    second_resp = client.post("/api/v1/self-invoice/emit", json=emit_payload)
    assert second_resp.status_code == 200
    assert second_resp.json()["status"] == "simulated"


def test_public_self_invoice_uses_uuid_sat_for_confirmed_and_existing_invoice(monkeypatch) -> None:
    client = _client_with_db()
    _, auth_data, folio = _setup_tenant_and_order(client, "sat")
    public_key = _public_key_for_branch(client, auth_data["branch"]["id"])
    payload = {
        "folio": folio,
        "public_key": public_key,
        "rfc": "GOMR880101ABC",
        "legal_name": "RODRIGO GOMEZ MARTINEZ",
        "zip": "06700",
        "tax_system": "612",
        "use": "G03",
    }
    sat_uuid = "12345678-1234-1234-1234-123456789ABC"

    monkeypatch.setattr(
        "restaurant_os.invoicing.self_invoicing.invoicing_service.issue_invoice",
        lambda **_kwargs: {
            "status": "issued",
            "uuid_sat": sat_uuid,
            "folio_number": "F-42",
            "pdf_url": "https://example.test/invoice.pdf",
            "xml_url": "https://example.test/invoice.xml",
        },
    )
    confirmed = client.post("/api/v1/self-invoice/emit", json=payload)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["uuid"] == sat_uuid

    generator = client.app.dependency_overrides[get_session]()
    session = next(generator)
    try:
        order = (
            session.execute(
                sa.select(models.orders).where(
                    models.orders.c.branch_id == auth_data["branch"]["id"],
                    models.orders.c.folio == folio,
                )
            )
            .mappings()
            .one()
        )
        session.execute(
            models.cfdi_invoices.insert().values(
                id=str(uuid4()),
                organization_id=auth_data["organization"]["id"],
                branch_id=auth_data["branch"]["id"],
                order_id=order["id"],
                facturapi_invoice_id="facturapi-existing-sat",
                uuid_sat=sat_uuid,
                folio_number="F-42",
                rfc_emisor="TER210101XYZ",
                rfc_receptor="GOMR880101ABC",
                nombre_receptor="RODRIGO GOMEZ MARTINEZ",
                codigo_postal_receptor="06700",
                regimen_fiscal_receptor="612",
                uso_cfdi="G03",
                forma_pago_sat="01",
                metodo_pago_sat="PUE",
                total_cents=order["total_cents"],
                currency="MXN",
                status="issued",
                created_at=datetime.now(UTC),
            )
        )
        session.commit()
    finally:
        session.close()

    lookup = client.get(
        "/api/v1/self-invoice/lookup", params={"folio": folio, "public_key": public_key}
    )
    assert lookup.status_code == 200
    assert lookup.json()["existing_invoice_uuid"] == sat_uuid
    duplicate = client.post("/api/v1/self-invoice/emit", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["sat_uuid"] == sat_uuid


def test_public_key_scopes_same_folio_to_its_tenant_and_never_emits_the_other(
    monkeypatch,
) -> None:
    client = _client_with_db()
    _, tenant_b, _ = _setup_tenant_and_order(client, "b")
    _, tenant_a, _ = _setup_tenant_and_order(client, "a")
    common_folio = "SHARED-FOLIO"
    generator = client.app.dependency_overrides[get_session]()
    session = next(generator)
    try:
        for tenant, total in ((tenant_b, 9876), (tenant_a, 1234)):
            session.execute(
                models.orders.update()
                .where(models.orders.c.branch_id == tenant["branch"]["id"])
                .values(
                    folio=common_folio,
                    total_cents=total,
                )
            )
        session.commit()
    finally:
        session.close()

    key_a = _public_key_for_branch(client, tenant_a["branch"]["id"])
    lookup = client.get(
        "/api/v1/self-invoice/lookup", params={"folio": common_folio, "public_key": key_a}
    )
    assert lookup.status_code == 200
    assert lookup.json()["total_cents"] == 1234

    emitted: dict[str, object] = {}

    def fake_issue_invoice(**kwargs):
        emitted.update(kwargs)
        return {"status": "simulated", "provider_confirmed": False}

    monkeypatch.setattr(
        "restaurant_os.invoicing.self_invoicing.invoicing_service.issue_invoice", fake_issue_invoice
    )
    response = client.post(
        "/api/v1/self-invoice/emit",
        json={
            "public_key": key_a,
            "folio": common_folio,
            "rfc": "GOMR880101ABC",
            "legal_name": "PERSONA A",
            "zip": "06700",
        },
    )
    assert response.status_code == 200
    assert emitted["org_id"] == tenant_a["organization"]["id"]
    assert emitted["branch_id"] == tenant_a["branch"]["id"]
    assert emitted["order_ids"] == ["self-invoice-order-a"]
    invalid = client.get(
        "/api/v1/self-invoice/lookup", params={"folio": common_folio, "public_key": "bad-key"}
    )
    assert invalid.status_code == 404
    assert "total_cents" not in invalid.text


def test_self_invoice_respects_disabled_and_expired_window(monkeypatch):
    from datetime import timedelta

    from restaurant_os.invoicing.self_invoicing import invoicing_service

    client = _client_with_db()
    _, tenant, folio = _setup_tenant_and_order(client)
    key = _public_key_for_branch(client, tenant["branch"]["id"])
    payload = {
        "folio": folio,
        "public_key": key,
        "rfc": "GOMR880101ABC",
        "legal_name": "Synthetic Customer",
        "zip": "06700",
    }

    def forbidden_call(**kwargs):
        raise AssertionError("Provider must not be called outside self-invoice policy")

    monkeypatch.setattr(invoicing_service, "issue_invoice", forbidden_call)
    for disabled in (True, False):
        gen = client.app.dependency_overrides[get_session]()
        session = next(gen)
        session.execute(
            models.facturapi_config.update().values(
                enable_self_invoicing=not disabled, self_invoicing_days_valid=1
            )
        )
        if not disabled:
            session.execute(
                models.orders.update().values(created_at=datetime.now(UTC) - timedelta(days=60))
            )
        session.commit()
        session.close()
        lookup = client.get(
            "/api/v1/self-invoice/lookup", params={"folio": folio, "public_key": key}
        )
        emit = client.post("/api/v1/self-invoice/emit", json=payload)
        assert lookup.status_code == 403
        assert emit.status_code == 403


def test_self_invoice_provider_errors_are_redacted(monkeypatch):
    from restaurant_os.invoicing.self_invoicing import invoicing_service

    client = _client_with_db()
    _, tenant, folio = _setup_tenant_and_order(client)

    def failure(**kwargs):
        raise RuntimeError("synthetic-private-provider-detail")

    monkeypatch.setattr(invoicing_service, "issue_invoice", failure)
    response = client.post(
        "/api/v1/self-invoice/emit",
        json={
            "folio": folio,
            "public_key": _public_key_for_branch(client, tenant["branch"]["id"]),
            "rfc": "GOMR880101ABC",
            "legal_name": "Synthetic Customer",
            "zip": "06700",
        },
    )
    assert response.status_code == 503
    assert "synthetic-private-provider-detail" not in response.text
    assert response.json()["detail"]["correlation_id"]


def test_self_invoice_blocks_suspended_and_expired_tenants(monkeypatch):
    from datetime import timedelta

    from restaurant_os.invoicing.self_invoicing import invoicing_service

    client = _client_with_db()
    _, tenant, folio = _setup_tenant_and_order(client)
    key = _public_key_for_branch(client, tenant["branch"]["id"])

    def forbidden_call(**kwargs):
        raise AssertionError("Provider must not be called for suspended tenants")

    monkeypatch.setattr(invoicing_service, "issue_invoice", forbidden_call)
    for status in ("suspended", "trialing"):
        gen = client.app.dependency_overrides[get_session]()
        session = next(gen)
        session.execute(
            models.organizations.update().values(
                subscription_status=status, trial_ends_at=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
        session.commit()
        session.close()
        params = {"folio": folio, "public_key": key}
        assert client.get("/api/v1/self-invoice/lookup", params=params).status_code == 403
        assert (
            client.post(
                "/api/v1/self-invoice/emit",
                json={
                    **params,
                    "rfc": "GOMR880101ABC",
                    "legal_name": "Synthetic Customer",
                    "zip": "06700",
                },
            ).status_code
            == 403
        )
