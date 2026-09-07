# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-test-saas-invoicing-scope-synthetic-v1
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.api import invoicing_service
from restaurant_os.database import get_session
from restaurant_os.invoicing.service import InvoicingService
from restaurant_os.main import app
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def _client_with_db() -> tuple[TestClient, sessionmaker[Session]]:
    engine = sa.create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_session():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    return TestClient(app), factory


def _signup(client: TestClient, email: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": f"Restaurante {email}",
            "owner_name": "Dueño",
            "email": email,
            "password": "Password123!",
            "business_type": "general",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _insert_order(session: Session, organization_id: str, branch_id: str, order_id: str) -> None:
    now = datetime.now(timezone.utc)
    session.execute(
        models.orders.insert().values(
            id=order_id,
            organization_id=organization_id,
            branch_id=branch_id,
            folio=f"F-{order_id}",
            order_type="dine_in",
            channel="UBER_EATS",
            status="completed",
            total_cents=10000,
            currency="MXN",
            payment_method_intent="cash",
            version=1,
            created_at=now,
        )
    )


def _insert_invoice(
    session: Session, organization_id: str, branch_id: str, invoice_id: str
) -> None:
    now = datetime.now(timezone.utc)
    session.execute(
        models.cfdi_invoices.insert().values(
            id=invoice_id,
            organization_id=organization_id,
            branch_id=branch_id,
            order_id=None,
            facturapi_invoice_id=f"remote-{invoice_id}",
            folio_number=f"F-{invoice_id}",
            rfc_emisor="AAA010101AAA",
            rfc_receptor="XAXX010101000",
            nombre_receptor="PUBLICO EN GENERAL",
            codigo_postal_receptor="00000",
            regimen_fiscal_receptor="616",
            uso_cfdi="S01",
            forma_pago_sat="01",
            metodo_pago_sat="PUE",
            total_cents=10000,
            currency="MXN",
            status="issued",
            created_at=now,
        )
    )


def test_tenant_a_cannot_read_or_command_tenant_b_invoices(monkeypatch: pytest.MonkeyPatch) -> None:
    client, factory = _client_with_db()
    tenant_a = _signup(client, "owner-a@invoicing.test")
    tenant_b = _signup(client, "owner-b@invoicing.test")
    headers_a = {"Authorization": f"Bearer {tenant_a['token']}"}
    org_a = str(tenant_a["organization"]["id"])
    org_b = str(tenant_b["organization"]["id"])
    branch_a = str(tenant_a["branch"]["id"])
    branch_b = str(tenant_b["branch"]["id"])
    with factory() as session:
        _insert_order(session, org_a, branch_a, "order-a")
        _insert_order(session, org_b, branch_b, "order-b")
        _insert_invoice(session, org_b, branch_b, "invoice-b")
        session.commit()

    provider_calls: list[str] = []
    monkeypatch.setattr(
        invoicing_service,
        "issue_invoice",
        lambda *_args, **_kwargs: provider_calls.append("issue") or {},
    )
    monkeypatch.setattr(
        invoicing_service,
        "cancel_invoice",
        lambda *_args, **_kwargs: provider_calls.append("cancel") or {},
    )
    monkeypatch.setattr(
        invoicing_service,
        "create_receipt_for_order",
        lambda *_args, **_kwargs: provider_calls.append("receipt") or {},
    )

    listed = client.get("/api/v1/invoicing/invoices", headers=headers_a)
    assert listed.status_code == 200
    assert all(invoice["organization_id"] == org_a for invoice in listed.json())
    assert client.get("/api/v1/invoicing/invoices/invoice-b", headers=headers_a).status_code == 404
    assert (
        client.post(
            "/api/v1/invoicing/invoices/invoice-b/cancel", headers=headers_a, json={}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/invoicing/orders/order-b/receipt", headers=headers_a, json={}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/invoicing/invoices/issue",
            headers=headers_a,
            json={"branch_id": branch_b, "order_ids": ["order-b"], "receptor": {}},
        ).status_code
        == 404
    )
    assert provider_calls == []
    with factory() as session:
        invoice_b = session.execute(
            sa.select(models.cfdi_invoices.c.status).where(models.cfdi_invoices.c.id == "invoice-b")
        ).scalar_one()
    assert invoice_b == "issued"
    app.dependency_overrides.clear()


def test_facturapi_config_and_connection_use_the_authenticated_organization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, factory = _client_with_db()
    tenant_a = _signup(client, "owner-a-config@invoicing.test")
    tenant_b = _signup(client, "owner-b-config@invoicing.test")
    headers_a = {"Authorization": f"Bearer {tenant_a['token']}"}
    org_a = str(tenant_a["organization"]["id"])
    org_b = str(tenant_b["organization"]["id"])
    with factory() as session:
        rfc_b_before = session.execute(
            sa.select(models.facturapi_config.c.organization_rfc).where(
                models.facturapi_config.c.organization_id == org_b
            )
        ).scalar_one()
    saved = client.post(
        "/api/v1/integrations/facturapi/config",
        headers=headers_a,
        json={"is_enabled": True, "organization_rfc": "AAA010101AAA"},
    )
    assert saved.status_code == 200
    assert (
        client.get("/api/v1/integrations/facturapi/config", headers=headers_a).json()[
            "organization_id"
        ]
        == org_a
    )
    with factory() as session:
        assert (
            session.execute(
                sa.select(models.facturapi_config.c.organization_rfc).where(
                    models.facturapi_config.c.organization_id == org_b
                )
            ).scalar_one()
            == rfc_b_before
        )

    seen_organizations: list[str] = []
    monkeypatch.setattr(
        invoicing_service,
        "test_connection",
        lambda _session, organization_id: (
            seen_organizations.append(organization_id) or {"ok": True}
        ),
    )
    checked = client.post("/api/v1/integrations/facturapi/test-connection", headers=headers_a)
    assert checked.status_code == 200
    assert seen_organizations == [org_a]
    app.dependency_overrides.clear()


def test_service_rejects_cross_tenant_order_before_provider_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = sa.create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    service = InvoicingService()
    with Session(engine) as session:
        _insert_order(session, "org-b", "branch-b", "order-b")
        session.commit()
        monkeypatch.setattr(
            service, "get_client", lambda *_args: pytest.fail("provider was created")
        )
        with pytest.raises(ValueError, match="organización o sucursal"):
            service.issue_invoice(session, "org-a", "branch-a", ["order-b"], {})


def test_missing_facturapi_configuration_never_calls_provider_or_issues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = sa.create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    service = InvoicingService()
    with Session(engine) as session:
        _insert_order(session, "org-a", "branch-a", "order-a")
        session.commit()

        monkeypatch.setattr(
            service, "get_client", lambda *_args: pytest.fail("provider was created")
        )
        with pytest.raises(ValueError, match="configuración|API key"):
            service.issue_invoice(session, "org-a", "branch-a", ["order-a"], {})

        assert session.execute(sa.select(models.cfdi_invoices.c.id)).all() == []


def test_explicit_sandbox_simulation_does_not_issue_or_cancel_locally() -> None:
    engine = sa.create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    service = InvoicingService()
    with Session(engine) as session:
        _insert_order(session, "org-a", "branch-a", "order-a")
        _insert_invoice(session, "org-a", "branch-a", "invoice-a")
        service.save_config(
            session,
            "org-a",
            {
                "is_enabled": True,
                "environment": "sandbox",
                "api_key": "sk_test_mock_explicit",
            },
        )

        issued = service.issue_invoice(session, "org-a", "branch-a", ["order-a"], {})
        cancelled = service.cancel_invoice(session, "org-a", "invoice-a")

        assert issued["status"] == "simulated"
        assert issued["provider_confirmed"] is False
        assert cancelled["status"] == "simulated"
        assert cancelled["provider_confirmed"] is False
        assert (
            session.execute(
                sa.select(models.cfdi_invoices.c.status).where(
                    models.cfdi_invoices.c.id == "invoice-a"
                )
            ).scalar_one()
            == "issued"
        )
        assert session.execute(sa.select(models.cfdi_invoices.c.id)).all() == [("invoice-a",)]
