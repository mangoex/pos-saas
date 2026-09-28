# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-public-pickup-schedule-tests-v1
"""Scheduled public capture uses the branch clock and keeps replay recoverable."""

from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from restaurant_os import models, operations
from restaurant_os.saas_onboarding import signup_tenant
from test_platform_api import BRANCH_ID, _client_with_seeded_database, _test_session_factory
from test_public_order_intents import (
    PUBLIC_KEY,
    _enable_public_order_capture,
    _payload,
    _post_intent,
)
from test_saas_cash_scope import cash_scope_session as cash_scope_session

NOW = datetime(2026, 9, 28, 22, 0, tzinfo=timezone.utc)
SCHEDULE = [{"day_index": 0, "is_open": True, "open_time": "16:00", "close_time": "18:00"}]


@pytest.fixture()
def pickup_client(monkeypatch):
    clock = [NOW]
    monkeypatch.setattr(operations, "_now", lambda: clock[0])
    client = _client_with_seeded_database()
    _enable_public_order_capture(client)
    with _test_session_factory(client)() as session:
        session.execute(
            models.branches.update()
            .where(models.branches.c.id == BRANCH_ID)
            .values(
                timezone="America/Chihuahua",
                service_schedule=SCHEDULE,
            )
        )
        session.commit()
    yield client, clock
    client.app.dependency_overrides.clear()
    client.close()


def test_domain_rejects_expired_pickup_before_persistence(pickup_client):
    client, _clock = pickup_client
    with _test_session_factory(client)() as session:
        with pytest.raises(operations.BusinessError) as rejected:
            operations.create_public_order_intent(
                session,
                PUBLIC_KEY,
                _payload(pickup_date="2026-09-28", pickup_time="16:00"),
                "expired-pickup-request",
            )
        assert rejected.value.code == "pickup_slot_unavailable"
        for table in (models.public_order_intents, models.public_order_intent_commands):
            assert session.scalar(sa.select(sa.func.count()).select_from(table)) == 0


def test_public_options_use_branch_clock_and_reject_invalid_key(pickup_client):
    client, _clock = pickup_client
    endpoint = f"/api/v1/public/branches/{PUBLIC_KEY}/pickup-options"
    response = client.get(endpoint)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    projection = response.json()
    assert projection["timezone"] == "America/Chihuahua"
    assert projection["generated_at"] == NOW.isoformat()
    assert projection["days"][0]["date"] == "2026-09-28"
    assert projection["days"][0]["slots"][0] == {
        "value": "16:15",
        "scheduled_at": "2026-09-28T22:15:00+00:00",
    }
    assert client.get("/api/v1/public/branches/unknown/pickup-options").status_code == 503
    with _test_session_factory(client)() as session:
        session.execute(
            models.branches.update()
            .where(models.branches.c.id == BRANCH_ID)
            .values(
                status="inactive",
            )
        )
        session.commit()
    assert client.get(endpoint).status_code == 503


def test_scheduled_capture_persists_and_replays_after_clock_expiry(pickup_client):
    client, clock = pickup_client
    payload = _payload(pickup_date="2026-09-28", pickup_time="16:30")
    response = _post_intent(client, payload, key="scheduled-pickup-command")
    assert response.status_code == 201, response.text
    with _test_session_factory(client)() as session:
        customer = session.scalar(sa.select(models.public_order_intents.c.customer_snapshot))
        assert customer["pickup"] == {
            "local_date": "2026-09-28",
            "local_time": "16:30",
            "timezone": "America/Chihuahua",
            "scheduled_at": "2026-09-28T22:30:00+00:00",
        }
    clock[0] = datetime(2026, 10, 1, 2, 0, tzinfo=timezone.utc)
    replay = _post_intent(client, payload, key="scheduled-pickup-command")
    assert replay.status_code == 200, replay.text
    assert replay.json() == response.json()
    conflict = _post_intent(
        client,
        _payload(pickup_date="2026-09-28", pickup_time="16:45"),
        key="scheduled-pickup-command",
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["detail"]["code"] == "idempotency_conflict"


@pytest.mark.parametrize(
    "extra",
    [
        {"pickup_date": "2026-09-28"},
        {"pickup_time": "16:30"},
        {"pickup_date": "2026-09-28", "pickup_time": "25:00"},
        {"pickup_date": "2026-09-28", "pickup_time": "16:30", "order_type": "dine-in"},
    ],
)
def test_pickup_pair_rejected_at_http_boundary(pickup_client, extra):
    client, _clock = pickup_client
    assert _post_intent(client, _payload(**extra)).status_code == 422


def test_pickup_snapshot_survives_acceptance_and_tenant_scope(cash_scope_session, monkeypatch):
    session = cash_scope_session
    monkeypatch.setattr(operations, "_now", lambda: NOW)
    tenants = [
        signup_tenant(
            session,
            {
                "business_name": f"Pickup {label}",
                "owner_name": f"Owner {label}",
                "email": f"pickup-{label}@example.test",
                "password": "synthetic-pickup-password",
                "business_type": "taqueria",
            },
        )
        for label in ("a", "b")
    ]
    keys = []
    products = []
    for index, tenant in enumerate(tenants):
        branch_id = tenant["branch"]["id"]
        organization_id = tenant["organization"]["id"]
        session.execute(
            models.branches.update()
            .where(models.branches.c.id == branch_id)
            .values(
                timezone="America/Chihuahua" if index == 0 else "America/New_York",
                service_schedule=SCHEDULE,
            )
        )
        keys.append(
            session.scalar(
                sa.select(models.public_order_keys.c.public_key).where(
                    models.public_order_keys.c.organization_id == organization_id,
                )
            )
        )
        products.append(
            session.scalar(
                sa.select(models.products.c.id).where(
                    models.products.c.organization_id == organization_id,
                )
            )
        )
    session.commit()
    assert operations.get_public_pickup_options(session, keys[0])["timezone"] == "America/Chihuahua"
    assert operations.get_public_pickup_options(session, keys[1])["timezone"] == "America/New_York"
    session.execute(
        models.products.update()
        .where(models.products.c.id == products[1])
        .values(
            sku="PICKUP-OTHER-ONLY",
            name="Pickup exclusivo del otro tenant",
        )
    )
    session.commit()
    for reference in (products[1], "PICKUP-OTHER-ONLY", "Pickup exclusivo del otro tenant"):
        assert (
            operations._get_available_product(session, reference, tenants[0]["branch"]["id"])
            is None
        )
    session.execute(
        models.products.update()
        .where(models.products.c.id == products[0])
        .values(
            sku="PICKUP-OTHER-ONLY",
            name="Pickup exclusivo del otro tenant",
        )
    )
    session.commit()
    for reference in ("PICKUP-OTHER-ONLY", "Pickup exclusivo del otro tenant"):
        resolved = operations._get_available_product(session, reference, tenants[0]["branch"]["id"])
        assert resolved is not None and resolved["id"] == products[0]
    payload = _payload(
        pickup_date="2026-09-28",
        pickup_time="16:30",
        lines=[{"product_id": products[0], "quantity": 1}],
    )
    sensitive_tables = (
        models.public_order_intents,
        models.public_order_intent_commands,
        models.orders,
        models.inventory_movements,
        models.recipes,
    )
    before = [
        session.scalar(sa.select(sa.func.count()).select_from(table)) for table in sensitive_tables
    ]
    with pytest.raises(operations.BusinessError) as rejected:
        operations.create_public_order_intent(
            session,
            keys[0],
            {**payload, "lines": [{"product_id": products[1], "quantity": 1}]},
            "pickup-cross-product",
        )
    assert rejected.value.code == "product_unavailable"
    assert [
        session.scalar(sa.select(sa.func.count()).select_from(table)) for table in sensitive_tables
    ] == before
    assert session.scalar(sa.select(sa.func.count()).select_from(models.public_order_intents)) == 0
    result, created = operations.create_public_order_intent(
        session, keys[0], payload, "pickup-owned-request"
    )
    assert created
    intent = (
        session.execute(
            sa.select(models.public_order_intents).where(
                models.public_order_intents.c.public_reference == result["public_reference"],
            )
        )
        .mappings()
        .one()
    )
    assert intent["organization_id"] == tenants[0]["organization"]["id"]
    snapshot = intent["customer_snapshot"]["pickup"]
    with pytest.raises(operations.AuthorizationError):
        operations.accept_public_order_intent(
            session, intent["id"], 1, "pickup-cross-accept", tenants[1]["user"]["id"]
        )
    operations.accept_public_order_intent(
        session, intent["id"], 1, "pickup-owned-accept", tenants[0]["user"]["id"]
    )
    orders = session.execute(sa.select(models.orders)).mappings().all()
    assert len(orders) == 1
    assert orders[0]["organization_id"] == tenants[0]["organization"]["id"]
    assert orders[0]["customer_snapshot"]["pickup"] == snapshot
    assert snapshot["scheduled_at"] == "2026-09-28T22:30:00+00:00"
    session.execute(
        models.products.update()
        .where(models.products.c.id == products[0])
        .values(
            catalog_scope="branch",
            source_branch_id=tenants[1]["branch"]["id"],
        )
    )
    session.commit()
    assert (
        operations._get_available_product(session, products[0], tenants[0]["branch"]["id"]) is None
    )
    session.execute(
        models.products.update()
        .where(models.products.c.id == products[0])
        .values(
            source_branch_id=tenants[0]["branch"]["id"],
        )
    )
    session.commit()
    assert (
        operations._get_available_product(session, products[0], tenants[0]["branch"]["id"])
        is not None
    )
