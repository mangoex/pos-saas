# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-test-sensitive-authorization-v1
"""Sensitive POS controls require an active, tenant-scoped authenticated actor."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.auth import create_session_token
from restaurant_os.config import get_settings
from restaurant_os.main import app
from restaurant_os.saas_onboarding import signup_tenant
from test_saas_cash_scope import _cash_scope_api_client


def _signup_pair(factory):
    with factory() as session:
        tenant_a = signup_tenant(
            session,
            {
                "business_name": "Sensitive A",
                "owner_name": "Owner A",
                "email": "sensitive-a@example.test",
                "password": "sensitive-owner-a-password",
                "business_type": "taqueria",
            },
        )
        tenant_b = signup_tenant(
            session,
            {
                "business_name": "Sensitive B",
                "owner_name": "Owner B",
                "email": "sensitive-b@example.test",
                "password": "sensitive-owner-b-password",
                "business_type": "sushi",
            },
        )
    return tenant_a, tenant_b


def test_supervisor_step_up_requires_session_tenant_scope_and_rate_limit() -> None:
    client, factory = _cash_scope_api_client()
    tenant_a, tenant_b = _signup_pair(factory)
    payload = {
        "pin": "sensitive-owner-b-password",
        "branch_id": tenant_b["branch"]["id"],
        "permission_code": "orders.discount.authorize",
    }

    try:
        anonymous = client.post("/api/v1/auth/supervisor-authorize", json=payload)
        assert anonymous.status_code == 401, anonymous.text

        cross_tenant = client.post(
            "/api/v1/auth/supervisor-authorize",
            headers={"Authorization": f"Bearer {tenant_a['token']}"},
            json=payload,
        )
        assert cross_tenant.status_code == 403, cross_tenant.text

        class DenyLimiter:
            def allow(self, _scope: str, _actor: str) -> bool:
                return False

        previous = app.state.supervisor_authorization_rate_limiter
        app.state.supervisor_authorization_rate_limiter = DenyLimiter()
        limited = client.post(
            "/api/v1/auth/supervisor-authorize",
            headers={"Authorization": f"Bearer {tenant_a['token']}"},
            json={
                "pin": "sensitive-owner-a-password",
                "branch_id": tenant_a["branch"]["id"],
            },
        )
        assert limited.status_code == 429, limited.text
        assert limited.json()["detail"]["code"] == "supervisor_authorization_rate_limited"
        app.state.supervisor_authorization_rate_limiter = previous
    finally:
        app.dependency_overrides.clear()


def test_kill_switch_rejects_unprivileged_cross_tenant_and_suspended_actors() -> None:
    client, factory = _cash_scope_api_client()
    tenant_a, tenant_b = _signup_pair(factory)
    product_id = client.get(
        "/api/v1/catalog/products",
        headers={"Authorization": f"Bearer {tenant_a['token']}"},
    ).json()[0]["id"]
    unprivileged_id = str(uuid4())
    now = datetime.now(timezone.utc)

    with factory() as session:
        session.execute(
            models.users.insert().values(
                id=unprivileged_id,
                organization_id=tenant_a["organization"]["id"],
                email="unprivileged-sensitive@example.test",
                display_name="Unprivileged",
                status="active",
                is_superadmin=False,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    low_token = create_session_token({"sub": unprivileged_id}, get_settings().secret_key)
    try:
        unprivileged = client.post(
            "/api/v1/integrations/kill-switch",
            headers={"Authorization": f"Bearer {low_token}"},
            json={"product_id": product_id, "is_available": False},
        )
        assert unprivileged.status_code == 403, unprivileged.text

        cross_tenant = client.post(
            "/api/v1/integrations/kill-switch",
            headers={"Authorization": f"Bearer {tenant_a['token']}"},
            json={
                "product_id": product_id,
                "branch_id": tenant_b["branch"]["id"],
                "is_available": False,
            },
        )
        assert cross_tenant.status_code == 403, cross_tenant.text
        with factory() as session:
            assert session.scalar(
                sa.select(sa.func.count())
                .select_from(models.branch_product_availability)
                .where(
                    models.branch_product_availability.c.branch_id
                    == tenant_b["branch"]["id"],
                    models.branch_product_availability.c.product_id == product_id,
                )
            ) == 0
            session.execute(
                models.organizations.update()
                .where(models.organizations.c.id == tenant_a["organization"]["id"])
                .values(status="suspended", subscription_status="suspended", updated_at=now)
            )
            session.commit()

        suspended = client.post(
            "/api/v1/integrations/kill-switch",
            headers={"Authorization": f"Bearer {tenant_a['token']}"},
            json={"product_id": product_id, "is_available": False},
        )
        assert suspended.status_code == 403, suspended.text
    finally:
        app.dependency_overrides.clear()
