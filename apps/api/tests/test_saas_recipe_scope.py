# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-recovery-test-saas-recipe-scope-synthetic-v1
"""Recipe costing remains unavailable in the lean POS-SaaS product."""
from restaurant_os.main import app
from restaurant_os.saas_onboarding import signup_tenant
from test_saas_cash_scope import _cash_scope_api_client


def test_recipe_ai_costing_is_explicitly_out_of_saas_scope():
    client, factory = _cash_scope_api_client()
    try:
        with factory() as session:
            tenant = signup_tenant(session, {
                "business_name": "Lean recipe", "owner_name": "Owner",
                "email": "lean-recipe@example.test", "password": "synthetic-recipe-password",
                "business_type": "blank",
            })
        response = client.post("/api/v1/recipes/ai-parse", json={
            "raw_text": "Receta sintética con veinte gramos de insumo",
        }, headers={"Authorization": f"Bearer {tenant['token']}"})
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "feature_out_of_saas_scope"
    finally:
        app.dependency_overrides.clear()
