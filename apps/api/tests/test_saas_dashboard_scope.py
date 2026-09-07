# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-recovery-test-saas-dashboard-scope-synthetic-v1
"""Organization-wide dashboard aggregates never include another restaurant."""

import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.main import app
from restaurant_os.operations import create_local_order, open_cash_shift, pay_order
from restaurant_os.saas_onboarding import signup_tenant
from test_saas_cash_scope import _cash_scope_api_client


def test_dashboard_sales_products_and_cash_activity_stay_in_own_organization():
    client, factory = _cash_scope_api_client()
    try:
        tenants = []
        with factory() as session:
            for suffix, template in (("a", "taqueria"), ("b", "blank")):
                tenants.append(
                    signup_tenant(
                        session,
                        {
                            "business_name": f"Dashboard {suffix}",
                            "owner_name": suffix,
                            "email": f"dashboard-{suffix}@example.test",
                            "password": "synthetic-dashboard-password",
                            "business_type": template,
                        },
                    )
                )
            first, other = tenants
            owner = first["user"]["id"]
            branch = first["branch"]["id"]
            product = session.scalar(
                sa.select(models.products.c.id).where(
                    models.products.c.organization_id == first["organization"]["id"]
                )
            )
            open_cash_shift(session, 0, branch_id=branch, actor_user_id=owner)
            order = create_local_order(
                session,
                [{"product_id": product, "quantity": 1}],
                branch_id=branch,
                actor_user_id=owner,
            )
            pay_order(
                session,
                order["id"],
                order["total_cents"],
                actor_user_id=owner,
                register_id="CAJA-01",
                idempotency_key="dashboard-payment",
            )
        first_result = client.get(
            "/api/v1/dashboard/overview", headers={"Authorization": f"Bearer {first['token']}"}
        )
        assert first_result.status_code == 200, first_result.text
        assert first_result.json()["total_orders"] == 1
        assert first_result.json()["total_revenue_cents"] == order["total_cents"]
        second_result = client.get(
            "/api/v1/dashboard/overview", headers={"Authorization": f"Bearer {other['token']}"}
        )
        assert second_result.status_code == 200, second_result.text
        data = second_result.json()
        assert data["total_orders"] == 0
        assert data["total_revenue_cents"] == 0
        assert data["total_products"] == 0
        assert data["recent_transactions"] == []
        assert data["recent_notifications"] == []
        assert data["popular_categories"] == []
    finally:
        app.dependency_overrides.clear()
