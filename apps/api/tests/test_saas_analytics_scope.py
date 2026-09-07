# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-test-analytics-scope-synthetic-v1
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
import sqlalchemy as sa
from restaurant_os import api, models
from restaurant_os.executive_ai import query_sales_overview
from restaurant_os.operations import (
    AuthorizationError,
    ReportingProjectionService,
    create_local_order,
    open_cash_shift,
    pay_order,
)
from restaurant_os.saas_onboarding import signup_tenant
from test_saas_cash_scope import _cash_scope_api_client


def _tenant_with_paid_sale(session, suffix: str, quantity: int) -> dict[str, Any]:
    tenant = signup_tenant(
        session,
        {
            "business_name": f"Analytics {suffix}",
            "owner_name": f"Owner {suffix}",
            "email": f"analytics-{suffix}@example.test",
            "password": "synthetic-analytics-password",
            "business_type": "taqueria",
        },
    )
    organization_id = tenant["organization"]["id"]
    branch_id = tenant["branch"]["id"]
    owner_id = tenant["user"]["id"]
    product = (
        session.execute(
            sa.select(models.products).where(
                models.products.c.organization_id == organization_id,
                models.products.c.sku == "TAC-PAS",
            )
        )
        .mappings()
        .one()
    )
    open_cash_shift(session, 0, branch_id=branch_id, actor_user_id=owner_id)
    order = create_local_order(
        session,
        [{"product_id": product["id"], "quantity": quantity}],
        branch_id=branch_id,
        actor_user_id=owner_id,
    )
    pay_order(
        session,
        order["id"],
        order["total_cents"],
        actor_user_id=owner_id,
        register_id="CAJA-01",
        idempotency_key=f"analytics-payment-{suffix}",
    )
    return {
        **tenant,
        "product_id": product["id"],
        "product_name_at_sale": product["name"],
        "total_cents": order["total_cents"],
    }


def test_executive_provider_receives_only_authorized_immutable_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, factory = _cash_scope_api_client()
    captured: list[dict[str, Any]] = []
    try:
        with factory() as session:
            tenant_a = _tenant_with_paid_sale(session, "a", 1)
            tenant_b = _tenant_with_paid_sale(session, "b", 3)
            session.execute(
                models.products.update()
                .where(models.products.c.id == tenant_a["product_id"])
                .values(name="Live name changed after sale")
            )
            session.commit()

        def fake_provider(_options, _prompt, sales, products, branches):
            captured.append({"sales": sales, "products": products, "branches": branches})
            return {"answer": "ok", "data_points": [], "sources": [], "suggested_actions": []}

        settings = api.get_settings().model_copy(
            update={
                "admin_ai_assistant_enabled": True,
                "openrouter_api_key": "synthetic-provider-key",
            }
        )
        monkeypatch.setattr(api, "get_settings", lambda: settings)
        monkeypatch.setattr("restaurant_os.executive_ai._call_external_provider", fake_provider)
        headers_a = {"Authorization": f"Bearer {tenant_a['token']}"}

        own = client.post(
            "/api/v1/admin-ai/executive-insights",
            headers=headers_a,
            json={"prompt": "ventas", "branch_id": tenant_a["branch"]["id"]},
        )
        assert own.status_code == 200, own.text
        assert len(captured) == 1
        assert captured[0]["sales"]["total_sales_cents"] == tenant_a["total_cents"]
        assert {item["product_id"] for item in captured[0]["products"]} == {
            tenant_a["product_id"]
        }
        assert captured[0]["products"][0]["product_name"] == tenant_a["product_name_at_sale"]
        assert [item["branch_id"] for item in captured[0]["branches"]] == [
            tenant_a["branch"]["id"]
        ]

        foreign = client.post(
            "/api/v1/admin-ai/executive-insights",
            headers=headers_a,
            json={"prompt": "ventas", "branch_id": tenant_b["branch"]["id"]},
        )
        assert foreign.status_code == 403, foreign.text
        assert len(captured) == 1
    finally:
        client.close()
        client.app.dependency_overrides.clear()


def test_reporting_summary_scopes_owner_and_explicit_superadmin_branch() -> None:
    client, factory = _cash_scope_api_client()
    try:
        with factory() as session:
            tenant_a = _tenant_with_paid_sale(session, "report-a", 1)
            tenant_b = _tenant_with_paid_sale(session, "report-b", 3)
            now = datetime.now(timezone.utc)
            period = {"from_utc": now - timedelta(days=1), "to_utc": now + timedelta(days=1)}

            owner_summary = ReportingProjectionService(
                session, tenant_a["user"]["id"]
            ).summary(period)
            assert owner_summary["summary"]["net"]["known_cents"] == tenant_a["total_cents"]
            with pytest.raises(AuthorizationError):
                ReportingProjectionService(session, tenant_a["user"]["id"]).summary(
                    {**period, "branch_id": tenant_b["branch"]["id"]}
                )

            session.execute(
                models.users.update()
                .where(models.users.c.id == tenant_a["user"]["id"])
                .values(is_superadmin=True)
            )
            session.commit()
            superadmin_summary = ReportingProjectionService(
                session, tenant_a["user"]["id"]
            ).summary({**period, "branch_id": tenant_b["branch"]["id"]})
            assert superadmin_summary["summary"]["net"]["known_cents"] == tenant_b[
                "total_cents"
            ]
            assert query_sales_overview(
                session,
                tenant_b["organization"]["id"],
                branch_id=tenant_b["branch"]["id"],
            )["total_sales_cents"] == tenant_b["total_cents"]
    finally:
        client.close()
        client.app.dependency_overrides.clear()
