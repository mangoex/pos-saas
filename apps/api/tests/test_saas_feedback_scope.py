# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-recovery-test-saas-feedback-scope-synthetic-v1
"""Restaurant feedback is listed only inside the authenticated tenant."""
from restaurant_os.main import app
from restaurant_os.saas_onboarding import signup_tenant
from test_saas_cash_scope import _cash_scope_api_client


def test_feedback_admin_list_stays_in_own_organization_and_branch():
    client, factory = _cash_scope_api_client()
    try:
        with factory() as session:
            tenants = [signup_tenant(session, {
                "business_name": f"Feedback {key}", "owner_name": key,
                "email": f"feedback-{key}@example.test", "password": "synthetic-feedback-password",
                "business_type": "blank",
            }) for key in ("a", "b")]
        for key, tenant in zip(("A", "B"), tenants, strict=True):
            saved = client.post("/api/v1/public/feedback", json={
                "branch_id": tenant["branch"]["id"], "rating": 5,
                "customer_name": key, "comment": f"comment-{key}",
            })
            assert saved.status_code == 201, saved.text
        for key, tenant in zip(("A", "B"), tenants, strict=True):
            auth = {"Authorization": f"Bearer {tenant['token']}"}
            own = client.get("/api/v1/admin/feedbacks", headers=auth)
            assert own.status_code == 200, own.text
            assert [row["customer_name"] for row in own.json()] == [key]
            foreign = client.get(
                "/api/v1/admin/feedbacks",
                headers=auth,
                params={"branch_id": tenants[1 if key == "A" else 0]["branch"]["id"]},
            )
            assert foreign.status_code == 403, foreign.text
    finally:
        app.dependency_overrides.clear()
