# SEC001-SYNTHETIC-FIXTURE provenance=saas-mapping-remediation-20260928
"""Mappings cannot combine a tenant with another restaurant's branch."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.integrations import channel_service
from test_saas_onboarding import _client_with_db


@pytest.fixture
def mapping_tenants():
    client = _client_with_db()
    factory = client.app.state.test_session_factory
    with factory() as session:
        session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
    tenants = []
    for suffix in ("a", "b"):
        response = client.post(
            "/api/v1/auth/signup",
            json={
                "business_name": f"Mapping {suffix}",
                "owner_name": f"Owner {suffix}",
                "email": f"mapping-{suffix}@example.test",
                "password": "synthetic-mapping-password",
                "business_type": "blank",
            },
        )
        assert response.status_code == 201, response.text
        tenants.append(response.json())
    try:
        yield client, factory, tenants[0], tenants[1]
    finally:
        client.close()
        client.app.dependency_overrides.clear()
        factory.kw["bind"].dispose()


@pytest.mark.parametrize("provider", ["uber-eats", "didi-food", "rappi"])
def test_mapping_http_rejects_foreign_branch_without_effects(mapping_tenants, provider):
    client, factory, tenant_a, tenant_b = mapping_tenants
    headers = {"Authorization": f"Bearer {tenant_a['token']}"}
    path = f"/api/v1/integrations/{provider}/stores"
    own = client.post(path, headers=headers, json={
        "branch_id": tenant_a["branch"]["id"], "external_store_id": "own-store",
    })
    assert own.status_code == 200, own.text
    denied = client.post(path, headers=headers, json={
        "branch_id": tenant_b["branch"]["id"], "external_store_id": "foreign-store",
    })
    assert denied.status_code == 403, denied.text
    with factory() as session:
        mappings = session.execute(sa.select(models.channel_store_mappings)).mappings().all()
        assert len(mappings) == 1
        assert mappings[0]["external_store_id"] == "own-store"
        assert mappings[0]["organization_id"] == tenant_a["organization"]["id"]
        assert session.scalar(sa.select(sa.func.count()).select_from(models.orders)) == 0


@pytest.mark.parametrize("invalid", ["foreign", "missing", "inactive"])
def test_mapping_service_revalidates_branch(mapping_tenants, invalid):
    _, factory, tenant_a, tenant_b = mapping_tenants
    branch_id = tenant_b["branch"]["id"] if invalid == "foreign" else tenant_a["branch"]["id"]
    if invalid == "missing":
        branch_id = str(uuid4())
    with factory() as session:
        if invalid == "inactive":
            session.execute(models.branches.update().where(
                models.branches.c.id == branch_id,
            ).values(status="inactive"))
            session.commit()
        with pytest.raises(ValueError, match="integration_branch_scope_invalid"):
            channel_service.save_store_mapping(
                session, tenant_a["organization"]["id"], "UBER_EATS", branch_id, "bad-store",
            )
        assert session.scalar(sa.select(sa.func.count()).select_from(
            models.channel_store_mappings,
        )) == 0


def test_mapping_composite_foreign_key_rejects_direct_cross_tenant_insert(mapping_tenants):
    _, factory, tenant_a, tenant_b = mapping_tenants
    now = datetime.now(timezone.utc)
    with factory() as session:
        assert session.scalar(sa.text("PRAGMA foreign_keys")) == 1
        with pytest.raises(sa.exc.IntegrityError):
            session.execute(models.channel_store_mappings.insert().values(
                id=str(uuid4()), organization_id=tenant_a["organization"]["id"],
                branch_id=tenant_b["branch"]["id"], provider="UBER_EATS",
                external_store_id="crossed", is_active=True, created_at=now, updated_at=now,
            ))
            session.commit()
        session.rollback()


@pytest.mark.parametrize("provider", ["uber-eats", "didi-food", "rappi"])
@pytest.mark.parametrize("invalid", ["foreign", "missing", "inactive", "revoked"])
def test_mapping_update_rejects_invalid_scope_and_replay(mapping_tenants, provider, invalid):
    client, factory, tenant_a, tenant_b = mapping_tenants
    headers = {"Authorization": f"Bearer {tenant_a['token']}"}
    path = f"/api/v1/integrations/{provider}/stores"
    own_branch = tenant_a["branch"]["id"]
    payload = {"branch_id": own_branch, "external_store_id": "original"}
    assert client.post(path, headers=headers, json=payload).status_code == 200
    with factory() as session:
        before = dict(session.execute(
            sa.select(models.channel_store_mappings),
        ).mappings().one())
        if invalid == "inactive":
            session.execute(models.branches.update().where(
                models.branches.c.id == own_branch,
            ).values(status="inactive"))
        elif invalid == "revoked":
            session.execute(models.users.update().where(
                models.users.c.id == tenant_a["user"]["id"],
            ).values(status="inactive"))
        session.commit()
    if invalid == "foreign":
        payload["branch_id"] = tenant_b["branch"]["id"]
    elif invalid == "missing":
        payload["branch_id"] = str(uuid4())
    payload["external_store_id"] = "replacement"
    for _ in range(2):
        assert client.post(path, headers=headers, json=payload).status_code == 403
    with factory() as session:
        assert dict(session.execute(
            sa.select(models.channel_store_mappings),
        ).mappings().one()) == before
        for table in (models.orders, models.channel_availability_sync_jobs):
            assert session.scalar(sa.select(sa.func.count()).select_from(table)) == 0


def test_inactive_branch_cannot_enqueue_outbound_availability():
    from test_uber_availability_outbox import _factory, _seed

    factory = _factory()
    with factory() as session:
        _seed(session)
        session.execute(models.branches.update().values(status="inactive"))
        session.commit()
        assert channel_service.enqueue_uber_availability_sync(
            session, "org", "product", False, "branch",
        ) == 0
        assert session.scalar(sa.select(sa.func.count()).select_from(
            models.channel_availability_sync_jobs,
        )) == 0


@pytest.mark.parametrize("invalidated", ["branch", "store", "item"])
def test_pending_outbound_rechecks_target_before_network(monkeypatch, invalidated):
    from restaurant_os.integrations.service import ChannelIntegrationService
    from test_uber_availability_outbox import _factory, _seed

    factory = _factory()
    service = ChannelIntegrationService()
    with factory() as session:
        _seed(session)
        assert service.enqueue_uber_availability_sync(
            session, "org", "product", False, "branch",
        ) == 1
        if invalidated == "branch":
            session.execute(models.branches.update().values(status="inactive"))
        elif invalidated == "store":
            session.execute(models.channel_store_mappings.update().values(is_active=False))
        else:
            session.execute(models.channel_product_mappings.update().values(is_active=False))
        session.commit()
    calls = []
    monkeypatch.setattr(
        service.uber_adapter, "update_item_availability", lambda **kw: calls.append(kw),
    )
    results = service.dispatch_due_uber_availability_syncs(factory)
    assert calls == []
    assert [result["status"] for result in results] == ["FAILED"]


def test_webhook_resolver_rechecks_branch_after_mapping(mapping_tenants):
    _, factory, tenant_a, _ = mapping_tenants
    with factory() as session:
        org_id, branch_id = tenant_a["organization"]["id"], tenant_a["branch"]["id"]
        channel_service.save_config(session, org_id, "UBER_EATS", {
            "is_enabled": True, "webhook_secret": "synthetic-secret",
        })
        channel_service.save_store_mapping(session, org_id, "UBER_EATS", branch_id, "own-store")
        session.execute(models.branches.update().where(
            models.branches.c.id == branch_id,
        ).values(status="inactive"))
        session.commit()
        with pytest.raises(ValueError, match="integration_branch_scope_invalid"):
            channel_service.resolve_webhook_target(session, "UBER_EATS", {"store_id": "own-store"})


def test_kill_switch_keeps_mapping_enabled_to_send_sold_out(mapping_tenants):
    client, factory, tenant_a, _ = mapping_tenants
    now = datetime.now(timezone.utc)
    org_id, branch_id = tenant_a["organization"]["id"], tenant_a["branch"]["id"]
    product_id, category_id = str(uuid4()), str(uuid4())
    second_branch = str(uuid4())
    with factory() as session:
        branch = dict(session.execute(sa.select(models.branches).where(
            models.branches.c.id == branch_id,
        )).mappings().one())
        branch.update(id=second_branch, code="SECOND", name="Second branch")
        session.execute(models.branches.insert().values(**branch))
        session.execute(models.product_categories.insert().values(
            id=category_id, organization_id=org_id, name="Synthetic",
            created_at=now, updated_at=now,
        ))
        session.execute(models.products.insert().values(
            id=product_id, organization_id=org_id, category_id=category_id,
            name="Synthetic taco", sku="SYN", station="kitchen", created_at=now, updated_at=now,
        ))
        channel_service.save_config(session, org_id, "UBER_EATS", {"is_enabled": True})
        channel_service.save_store_mapping(session, org_id, "UBER_EATS", branch_id, "own-store")
        channel_service.save_store_mapping(
            session, org_id, "UBER_EATS", second_branch, "second-store",
        )
        session.execute(models.branch_product_availability.insert().values(
            branch_id=second_branch, product_id=product_id, is_available=True, updated_at=now,
        ))
        session.execute(models.channel_product_mappings.insert().values(
            id=str(uuid4()), organization_id=org_id, product_id=product_id,
            provider="UBER_EATS", external_item_id="own-item", is_active=True, created_at=now,
        ))
        session.commit()
    headers = {"Authorization": f"Bearer {tenant_a['token']}"}
    response = client.post("/api/v1/integrations/kill-switch", headers=headers, json={
        "product_id": product_id, "branch_id": branch_id, "is_available": False,
    })
    assert response.status_code == 200, response.text
    assert response.json()["channel_statuses"]["uber_eats"]["status"] == "pending_confirmation"
    with factory() as session:
        assert session.scalar(sa.select(models.channel_product_mappings.c.is_active)) is True
        job = session.execute(sa.select(models.channel_availability_sync_jobs)).mappings().one()
        assert job["branch_id"] == branch_id
        assert job["is_available"] is False
        assert session.scalar(sa.select(models.branch_product_availability.c.is_available).where(
            models.branch_product_availability.c.branch_id == second_branch,
        )) is True
        session.execute(models.channel_product_mappings.update().values(is_active=False))
        session.commit()
    response = client.post("/api/v1/integrations/kill-switch", headers=headers, json={
        "product_id": product_id, "branch_id": branch_id, "is_available": True,
    })
    assert response.status_code == 200, response.text
    with factory() as session:
        assert session.scalar(sa.select(models.channel_product_mappings.c.is_active)) is False
