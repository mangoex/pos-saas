# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-recovery-test-saas-simulation-scope-synthetic-v1
"""Sandbox order commands keep authenticated tenant and branch authority."""
import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.integrations import channel_service
from restaurant_os.main import app
from restaurant_os.saas_onboarding import signup_tenant
from test_saas_cash_scope import _cash_scope_api_client


@pytest.mark.parametrize("provider,path", [
    ("UBER_EATS", "uber-eats/test-order"),
    ("DIDI_FOOD", "didi-food/simulate"),
    ("RAPPI", "rappi/simulate"),
])
def test_simulation_uses_own_tenant_and_rejects_foreign_store_and_branch(provider, path):
    client, factory = _cash_scope_api_client()
    try:
        tenants = []
        with factory() as session:
            for suffix in ("a", "b"):
                tenant = signup_tenant(session, {
                    "business_name": f"Simulator {suffix}", "owner_name": suffix,
                    "email": f"simulation-{suffix}@example.test",
                    "password": "synthetic-simulation-password", "business_type": "taqueria",
                })
                tenants.append(tenant)
                org = tenant["organization"]["id"]
                channel_service.save_config(session, org, provider, {
                    "is_enabled": True, "webhook_secret": "synthetic-webhook-secret",
                })
                channel_service.save_store_mapping(
                    session, org, provider, tenant["branch"]["id"], f"store-{suffix}"
                )
        first, other = tenants
        headers = {"Authorization": f"Bearer {first['token']}"}
        response = client.post(f"/api/v1/integrations/{path}", headers=headers, json={
            "store_id": "store-a", "branch_id": first["branch"]["id"],
        })
        assert response.status_code == 200, response.text
        with factory() as session:
            orders = list(session.execute(sa.select(models.orders)).mappings())
            assert len(orders) == 1
            assert orders[0]["organization_id"] == first["organization"]["id"]
            assert orders[0]["branch_id"] == first["branch"]["id"]
            before_logs = session.scalar(sa.select(sa.func.count()).select_from(
                models.integration_webhook_logs))
        for payload in (
            {"store_id": "store-b", "branch_id": first["branch"]["id"]},
            {"store_id": "store-a", "branch_id": other["branch"]["id"]},
        ):
            rejected = client.post(f"/api/v1/integrations/{path}", headers=headers, json=payload)
            assert rejected.status_code == 403, rejected.text
        with factory() as session:
            assert session.scalar(sa.select(sa.func.count()).select_from(models.orders)) == 1
            assert session.scalar(sa.select(sa.func.count()).select_from(
                models.integration_webhook_logs)) == before_logs
        if provider != "UBER_EATS":
            with factory() as session:
                session.execute(models.channel_store_mappings.delete().where(
                    models.channel_store_mappings.c.organization_id == first["organization"]["id"]
                ))
                session.commit()
            missing = client.post(f"/api/v1/integrations/{path}", headers=headers, json={
                "branch_id": first["branch"]["id"], "items": [{"quantity": "invalid"}],
            })
            assert missing.status_code == 409, missing.text
            assert missing.json()["detail"] == "simulation_store_not_configured"
            with factory() as session:
                assert session.scalar(sa.select(sa.func.count()).select_from(
                    models.channel_store_mappings).where(
                        models.channel_store_mappings.c.organization_id
                        == first["organization"]["id"]
                    )) == 0
    finally:
        app.dependency_overrides.clear()
