# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-recovery-test-saas-lean-erp-boundary-synthetic-v1
"""Historical ERP routes fail closed for the POS-SaaS product."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.main import app
from restaurant_os.saas_onboarding import signup_tenant
from test_saas_cash_scope import _cash_scope_api_client


@pytest.mark.parametrize(
    ("method", "path", "payload", "table"),
    [
        ("get", "/api/v1/recipes", None, models.recipes),
        ("post", "/api/v1/production-batches", {}, models.production_batches),
        ("post", "/api/v1/inventory/transfers", {}, models.inventory_transfers),
        ("post", "/api/v1/inventory/physical-counts", {}, models.physical_count_sessions),
    ],
)
def test_historical_erp_route_fails_closed_before_domain_access(
    method: str, path: str, payload: dict[str, object] | None, table: sa.Table
) -> None:
    client, factory = _cash_scope_api_client()
    try:
        with factory() as session:
            tenant = signup_tenant(
                session,
                {
                    "business_name": f"Lean boundary {path}",
                    "owner_name": "Owner",
                    "email": f"lean-boundary-{abs(hash(path))}@example.test",
                    "password": "synthetic-password",
                    "business_type": "blank",
                },
            )
        with factory() as session:
            before = session.scalar(sa.select(sa.func.count()).select_from(table))
        response = client.request(
            method.upper(),
            path,
            json=payload,
            headers={"Authorization": f"Bearer {tenant['token']}"},
        )
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "feature_out_of_saas_scope"
        with factory() as session:
            assert session.scalar(sa.select(sa.func.count()).select_from(table)) == before
    finally:
        app.dependency_overrides.clear()
