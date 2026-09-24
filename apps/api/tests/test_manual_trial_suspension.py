from __future__ import annotations

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.config import get_settings
from test_saas_onboarding import _client_with_db


def test_tenant_past_trial_remains_active_and_only_manual_suspension_blocks(monkeypatch) -> None:
    monkeypatch.setenv(
        "RESTAURANTOS_PLATFORM_HOSTS",
        "testserver,mimenu.onl,app.mimenu.onl,platform.example.com",
    )
    monkeypatch.setenv("RESTAURANTOS_STOREFRONT_WILDCARD_DOMAIN", "mimenu.onl")
    get_settings.cache_clear()

    client = _client_with_db()

    # 1. Signup creates organization in trialing status
    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Marimba Cafe",
            "owner_name": "Marimba Owner",
            "email": "marimba@example.test",
            "password": "test-password-1234",
            "business_type": "general",
        },
    )
    assert signup.status_code == 201
    data = signup.json()
    org_id = data["organization"]["id"]
    token = data["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Setup branch and public slug
    branches_resp = client.get("/api/v1/branches", headers=headers)
    assert branches_resp.status_code == 200
    branches = branches_resp.json()
    assert len(branches) > 0
    branch_id = branches[0]["id"]

    with client.app.state.test_session_factory() as session:
        branch_public_key = session.scalar(
            sa.select(models.public_order_keys.c.public_key).where(
                models.public_order_keys.c.branch_id == branch_id
            )
        )

        session.execute(
            models.organizations.update()
            .where(models.organizations.c.id == org_id)
            .values(
                slug="marimba",
                subscription_status="trialing",
                # Simular trial vencido hace 5 días (pasaron los 14 días)
                trial_ends_at=datetime.now(timezone.utc) - timedelta(days=5),
            )
        )
        session.commit()

    # 2. Verify authenticated operations remain ACTIVE past trial date
    profile_resp = client.get("/api/v1/organization/profile", headers=headers)
    assert profile_resp.status_code == 200
    profile = profile_resp.json()
    assert profile["subscription_status"] == "trialing"
    assert profile["access_block_reason"] is None, "Access must not be blocked automatically past trial date"

    # Branch list
    assert client.get("/api/v1/branches", headers=headers).status_code == 200
    # Catalog
    assert client.get("/api/v1/catalog/products", headers=headers).status_code == 200

    # 3. Verify public storefront remains ACTIVE and functional
    storefront_resp = client.get(
        "/api/v1/public/storefront-context",
        headers={"Host": "marimba.mimenu.onl"},
    )
    assert storefront_resp.status_code == 200, f"Storefront must remain accessible past 14 days: {storefront_resp.text}"
    assert storefront_resp.json()["organization"]["slug"] == "marimba"

    # Public catalog by key
    public_catalog = client.get(f"/api/v1/public/branches/{branch_public_key}/catalog")
    assert public_catalog.status_code == 200, "Public catalog must remain accessible past 14 days"

    # 4. Verify manual suspension by superadmin blocks access
    with client.app.state.test_session_factory() as session:
        session.execute(
            models.organizations.update()
            .where(models.organizations.c.id == org_id)
            .values(subscription_status="suspended")
        )
        session.commit()

    # Authenticated operations blocked
    blocked_resp = client.get("/api/v1/branches", headers=headers)
    assert blocked_resp.status_code == 403
    assert blocked_resp.json()["detail"]["code"] == "tenant_suspended"

    # Direct public storefront blocked with 403
    direct_storefront = client.get("/api/v1/public/storefronts/marimba")
    assert direct_storefront.status_code == 403
    assert direct_storefront.json()["detail"]["code"] == "storefront_unavailable"

    # Wildcard storefront domain concealed with 404 domain_unavailable for security
    blocked_storefront = client.get(
        "/api/v1/public/storefront-context",
        headers={"Host": "marimba.mimenu.onl"},
    )
    assert blocked_storefront.status_code == 404
    assert blocked_storefront.json()["detail"]["code"] == "domain_unavailable"

    # Public catalog by key blocked
    blocked_catalog = client.get(f"/api/v1/public/branches/{branch_public_key}/catalog")
    assert blocked_catalog.status_code == 404
