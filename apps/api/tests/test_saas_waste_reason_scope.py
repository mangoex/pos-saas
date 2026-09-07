# SEC001-SYNTHETIC-FIXTURE provenance=recovery-dbcbc1a38f1a
"""Waste reason catalog is owned by the authenticated restaurant."""
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.main import app
from restaurant_os.saas_onboarding import signup_tenant
from test_saas_cash_scope import _cash_scope_api_client


def test_waste_reasons_separate_create_list_and_update_by_tenant():
    client, factory = _cash_scope_api_client()
    try:
        with factory() as session:
            tenants = [signup_tenant(session, {
                "business_name": f"Waste {key}", "owner_name": key,
                "email": f"waste-{key}@example.test", "password": "synthetic-waste-password",
                "business_type": "blank",
            }) for key in ("a", "b")]
        headers = [{"Authorization": f"Bearer {tenant['token']}"} for tenant in tenants]
        reasons = []
        for tenant, auth in zip(tenants, headers, strict=True):
            created = client.post("/api/v1/inventory/waste-reasons", headers=auth, json={
                "code": "SPILL", "name": tenant["organization"]["id"],
                "classification": "operation",
            })
            assert created.status_code == 200, created.text
            assert created.json()["organization_id"] == tenant["organization"]["id"]
            reasons.append(created.json())
        for auth, own in zip(headers, reasons, strict=True):
            listed = client.get("/api/v1/inventory/waste-reasons", headers=auth)
            assert listed.status_code == 200, listed.text
            assert [row["id"] for row in listed.json()] == [own["id"]]
        with factory() as session:
            before = dict(session.execute(sa.select(models.waste_reasons).where(
                models.waste_reasons.c.id == reasons[0]["id"])).mappings().one())
        rejected = client.put(f"/api/v1/inventory/waste-reasons/{reasons[0]['id']}",
                              headers=headers[1], json={"name": "foreign", "status": "inactive"})
        assert rejected.status_code == 409, rejected.text
        assert rejected.json()["detail"]["code"] == "waste_reason_not_found"
        with factory() as session:
            after = dict(session.execute(sa.select(models.waste_reasons).where(
                models.waste_reasons.c.id == reasons[0]["id"])).mappings().one())
            assert after == before
        updated = client.put(f"/api/v1/inventory/waste-reasons/{reasons[0]['id']}",
                             headers=headers[0], json={"name": "Own edited reason"})
        assert updated.status_code == 200, updated.text
        assert updated.json()["name"] == "Own edited reason"
    finally:
        app.dependency_overrides.clear()
