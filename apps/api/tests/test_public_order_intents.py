"""MOB-ORD-001 RED contracts for public order-intent capture and acceptance."""

from __future__ import annotations

# ruff: noqa: E501
from datetime import datetime, timezone
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import database, models
from restaurant_os.config import Settings
from restaurant_os.operations import BusinessError, _recover_public_order_command
from test_platform_api import (
    BRANCH_ID,
    _admin_headers,
    _client_with_seeded_database,
    _open_shift,
    _test_session_factory,
)

PRODUCT_ID = "018f6f73-2d0a-74f0-8f1c-000000000111"
PUBLIC_KEY = "pk_test_public_order_piloto"


class _AvailableRateLimiter:
    """Deterministic fake expected by the public-order boundary."""

    def allow(self, *_args: object, **_kwargs: object) -> bool:
        return True


class _BrokenRateLimiter:
    def allow(self, *_args: object, **_kwargs: object) -> bool:
        raise TimeoutError("redis unavailable")


class _RecordingRateLimiter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def allow(self, public_key: str, client_signal: str) -> bool:
        self.calls.append((public_key, client_signal))
        return True


def _payload(*, quantity: int = 1, **overrides: object) -> dict[str, object]:
    return {
        "customer_name": "Cliente marcador",
        "customer_phone": "+526141234567",
        "order_type": "takeout",
        "lines": [{"product_id": PRODUCT_ID, "quantity": quantity, "notes": "sin cebolla"}],
        **overrides,
    }


def _enable_public_order_capture(client: TestClient) -> None:
    """Seed a rotatable, server-side key: public input never carries a branch UUID."""
    keys = models.metadata.tables["public_order_keys"]
    with _test_session_factory(client)() as session:
        session.execute(
            keys.insert().values(
                public_key=PUBLIC_KEY,
                organization_id="018f6f73-2d0a-74f0-8f1c-000000000001",
                branch_id=BRANCH_ID,
                status="active",
            )
        )
        session.commit()
    client.app.state.public_order_intents_enabled = True
    client.app.state.public_order_rate_limiter = _AvailableRateLimiter()


def _post_intent(
    client: TestClient, payload: dict[str, object], key: str | None = "public-order-key-001", public_key: str = PUBLIC_KEY,
) -> Any:
    headers = {} if key is None else {"Idempotency-Key": key}
    return client.post(
        f"/api/v1/public/branches/{public_key}/order-intents",
        headers=headers,
        json=payload,
    )


def _count(session: Any, table_name: str) -> int:
    table = models.metadata.tables[table_name]
    return int(session.execute(sa.select(sa.func.count()).select_from(table)).scalar_one())


def _capture_counts(client: TestClient) -> dict[str, int]:
    with _test_session_factory(client)() as session:
        return {
            table_name: _count(session, table_name)
            for table_name in (
                "orders",
                "cash_shifts",
                "payments",
                "production_tasks",
                "inventory_movements",
            )
        }


def _intent_id(client: TestClient, public_reference: str) -> str:
    with _test_session_factory(client)() as session:
        return str(session.execute(
            sa.select(models.public_order_intents.c.id).where(
                models.public_order_intents.c.public_reference == public_reference
            )
        ).scalar_one())


def _accept_effect_counts(client: TestClient) -> dict[str, int]:
    with _test_session_factory(client)() as session:
        return {
            table_name: _count(session, table_name)
            for table_name in (
                "orders", "order_lines", "production_tasks", "inventory_movements",
                "order_events", "order_outbox_events", "public_order_intent_commands",
            )
        }


def test_public_order_intent_requires_idempotency_key_and_strict_body() -> None:
    client = _client_with_seeded_database()
    _enable_public_order_capture(client)

    assert _post_intent(client, _payload(), key=None).status_code == 422
    for forbidden_name, forbidden_value in (
        ("branch_id", BRANCH_ID),
        ("total_cents", 1),
        ("price_cents", 1),
        ("folio", "KIWI-FAKE"),
        ("actor_user_id", "forged-actor"),
        ("shift", "forged-shift"),
        ("cash_shift_id", "forged-shift"),
        ("unexpected", "field"),
    ):
        response = _post_intent(client, _payload(**{forbidden_name: forbidden_value}))
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "public_order_schema_invalid"
    nested = _post_intent(client, _payload(delivery_address={"address_text": "Calle 1", "unexpected": "x"}))
    assert nested.status_code == 422
    too_long = _post_intent(client, _payload(lines=[{"product_id": "x" * 37, "quantity": 1}]))
    assert too_long.status_code == 422


def test_public_intent_is_exactly_once_and_total_is_derived_in_python() -> None:
    client = _client_with_seeded_database()
    _enable_public_order_capture(client)
    payload = _payload(quantity=2)

    first = _post_intent(client, payload)
    assert first.status_code == 201
    assert first.json() == {
        "public_reference": first.json()["public_reference"],
        "status": "PENDING_REVIEW",
        "version": 1,
        "total_cents": 19_000,
    }

    replay = _post_intent(client, payload)
    assert replay.status_code == 200
    assert replay.json() == first.json()

    conflict = _post_intent(client, _payload(quantity=3))
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_conflict"

    with _test_session_factory(client)() as session:
        assert _count(session, "public_order_intents") == 1
        assert _count(session, "public_order_intent_commands") == 1


def test_public_capture_never_mutates_operational_cash_or_production() -> None:
    client = _client_with_seeded_database()
    _enable_public_order_capture(client)
    before = _capture_counts(client)

    created = _post_intent(client, _payload())
    assert created.status_code == 201
    assert _capture_counts(client) == before

    with _test_session_factory(client)() as session:
        intent = session.execute(
            sa.select(models.metadata.tables["public_order_intents"])
        ).mappings().one()
        assert intent["status"] == "PENDING_REVIEW"
        assert "cash_shift_id" not in intent
        assert "cash_shift_id" not in models.metadata.tables["public_order_intents"].c


def test_legacy_public_order_write_is_always_fail_closed() -> None:
    client = _client_with_seeded_database()
    before = _capture_counts(client)

    for enabled in (False, True):
        client.app.state.public_order_intents_enabled = enabled
        response = client.post(
            "/api/v1/public/orders",
            json={"branch_id": BRANCH_ID, "lines": []},
        )
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "public_order_unavailable"
        assert _capture_counts(client) == before


def test_public_reference_read_is_redacted() -> None:
    client = _client_with_seeded_database()
    _enable_public_order_capture(client)
    created = _post_intent(client, _payload())
    assert created.status_code == 201

    response = client.get(
        f"/api/v1/public/order-intents/{created.json()['public_reference']}"
    )
    assert response.status_code == 200
    assert response.json() == {
        "public_reference": created.json()["public_reference"],
        "status": "PENDING_REVIEW",
        "version": 1,
        "total_cents": 9_500,
    }


def test_public_capture_fails_closed_without_rate_limiter_or_configuration() -> None:
    client = _client_with_seeded_database()
    before = _capture_counts(client)

    # Default-off feature flag rejects the public write before any persistence.
    response = _post_intent(client, _payload())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "public_order_unavailable"
    assert _capture_counts(client) == before

    client.app.state.public_order_intents_enabled = True
    client.app.state.public_order_rate_limiter = _AvailableRateLimiter()
    missing_key = _post_intent(client, _payload(), public_key="not-a-key")
    assert missing_key.status_code == 503
    assert _capture_counts(client) == before

    _enable_public_order_capture(client)
    del client.app.state.public_order_rate_limiter
    missing_limiter = _post_intent(client, _payload())
    assert missing_limiter.status_code == 503
    assert _capture_counts(client) == before


def test_invalid_public_key_never_consumes_a_limiter_bucket_or_persists() -> None:
    client = _client_with_seeded_database()
    _enable_public_order_capture(client)
    limiter = _RecordingRateLimiter()
    client.app.state.public_order_rate_limiter = limiter
    before = _capture_counts(client)
    response = _post_intent(client, _payload(), public_key="x" * 161)
    assert response.status_code == 503
    assert limiter.calls == []
    assert _capture_counts(client) == before


def test_public_intent_uses_canonical_selections_and_direct_client_signal() -> None:
    client = _client_with_seeded_database()
    _enable_public_order_capture(client)
    limiter = _RecordingRateLimiter()
    client.app.state.public_order_rate_limiter = limiter

    rejected_by_domain = _post_intent(
        client,
        _payload(lines=[{"product_id": PRODUCT_ID, "quantity": 1, "modifiers": [{"option_id": "unknown-option"}]}]),
        key="public-order-modifier-001",
    )
    assert rejected_by_domain.status_code == 409
    # The strict boundary accepts the documented selection shape but still rejects client prices.
    rejected_shape = _post_intent(
        client,
        _payload(lines=[{"product_id": PRODUCT_ID, "quantity": 1, "modifiers": [{"option_id": "x", "price_cents": 1}]}]),
        key="public-order-modifier-002",
    )
    assert rejected_shape.status_code == 422
    assert limiter.calls and limiter.calls[0][0] == PUBLIC_KEY
    assert limiter.calls[0][1] != "Cliente marcador"


def test_public_catalog_modifier_can_be_captured_with_python_price() -> None:
    client = _client_with_seeded_database()
    _enable_public_order_capture(client)
    now = datetime.now(timezone.utc)
    group_id = "mobord001-public-modifier-group"
    option_id = "mobord001-public-modifier-option"
    with _test_session_factory(client)() as session:
        session.execute(models.modifier_groups.insert().values(
            id=group_id,
            organization_id="018f6f73-2d0a-74f0-8f1c-000000000001",
            product_id=PRODUCT_ID,
            name="Temperatura",
            is_required=True,
            minimum_selections=1,
            maximum_selections=1,
            station="barra",
            display_order=1,
            status="active",
            created_at=now,
            updated_at=now,
        ))
        session.execute(models.modifier_options.insert().values(
            id=option_id,
            group_id=group_id,
            name="Muy frio",
            effect_type="instruction",
            price_delta_cents=250,
            affected_item_id=None,
            replacement_item_id=None,
            remove_quantity="0",
            add_quantity="0",
            inventory_effect=False,
            kitchen_text="Muy frio",
            station="barra",
            display_order=1,
            status="active",
            created_at=now,
            updated_at=now,
        ))
        session.commit()

    catalog = client.get(f"/api/v1/public/branches/{PUBLIC_KEY}/catalog")
    assert catalog.status_code == 200
    product = next(item for item in catalog.json()["items"] if item["id"] == PRODUCT_ID)
    assert product["modifier_groups"] == [{
        "id": group_id,
        "name": "Temperatura",
        "is_required": True,
        "minimum_selections": 1,
        "maximum_selections": 1,
        "options": [{
            "id": option_id,
            "name": "Muy frio",
            "price_delta_cents": 250,
            "selection_kind": "modifier",
        }],
    }]
    created = _post_intent(
        client,
        _payload(lines=[{
            "product_id": PRODUCT_ID,
            "quantity": 1,
            "modifiers": [{"option_id": option_id, "text": "con hielo"}],
        }]),
        key="public-order-valid-modifier-001",
    )
    assert created.status_code == 201
    assert created.json()["total_cents"] == 9_750
    with _test_session_factory(client)() as session:
        line = session.execute(sa.select(models.public_order_intent_lines)).mappings().one()
        assert line["modifier_total_cents"] == 250
        assert line["line_total_cents"] == 9_750
        assert line["selected_modifiers"][0]["option_id"] == option_id


def test_expired_state_remains_reserved_in_the_data_model() -> None:
    check = next(
        constraint.sqltext
        for constraint in models.public_order_intents.constraints
        if constraint.name == "ck_public_order_intents_status"
    )
    assert "EXPIRED" in str(check)


def test_runtime_sqlite_engine_enforces_foreign_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    database.get_engine.cache_clear()
    monkeypatch.setattr(database, "get_settings", lambda: Settings(database_url="sqlite://"))
    try:
        with database.get_engine().connect() as connection:
            assert connection.execute(sa.text("PRAGMA foreign_keys")).scalar_one() == 1
    finally:
        database.get_engine.cache_clear()

def test_catalog_key_and_limiter_fail_closed() -> None:
    client = _client_with_seeded_database()
    legacy_branches = client.get("/api/v1/public/branches")
    assert legacy_branches.status_code == 422
    _enable_public_order_capture(client)
    with _test_session_factory(client)() as session:
        session.execute(models.organizations.update().where(
            models.organizations.c.id == "018f6f73-2d0a-74f0-8f1c-000000000001"
        ).values(slug="public-test-restaurant"))
        session.commit()
    intent_branches = client.get("/api/v1/public/branches", params={"identifier": "public-test-restaurant"})
    assert intent_branches.status_code == 200
    assert intent_branches.json()[0]["public_key"] == PUBLIC_KEY
    catalog = client.get(f"/api/v1/public/branches/{PUBLIC_KEY}/catalog")
    assert catalog.status_code == 200
    assert catalog.json()["branch_id"] == BRANCH_ID
    assert client.get("/api/v1/public/branches/not-a-key/catalog").status_code == 404
    client.app.state.public_order_rate_limiter = _BrokenRateLimiter()
    failed = _post_intent(client, _payload(), key="public-order-limiter-timeout-001")
    assert failed.status_code == 503
    assert failed.json()["detail"]["code"] == "public_order_unavailable"


def test_public_catalog_key_projects_its_own_branch_without_invented_prices() -> None:
    client = _client_with_seeded_database()
    second_branch_id = "018f6f73-2d0a-74f0-8f1c-000000000099"
    second_key = "pk_test_public_order_second_branch"
    with _test_session_factory(client)() as session:
        now = datetime.now(timezone.utc)
        session.execute(models.branches.insert().values(
            id=second_branch_id,
            organization_id="018f6f73-2d0a-74f0-8f1c-000000000001",
            legal_entity_id="018f6f73-2d0a-74f0-8f1c-000000000002",
            business_unit_id="018f6f73-2d0a-74f0-8f1c-000000000015",
            name="Sucursal Dos", code="DOS", timezone="America/Mazatlan", status="active",
            created_at=now, updated_at=now,
        ))
        session.execute(models.public_order_keys.insert().values(
            public_key=second_key, organization_id="018f6f73-2d0a-74f0-8f1c-000000000001",
            branch_id=second_branch_id, status="active", created_at=now,
        ))
        session.execute(models.branch_product_availability.insert().values(
            branch_id=second_branch_id, product_id=PRODUCT_ID, is_available=False, updated_at=now,
        ))
        session.execute(models.price_versions.delete().where(
            models.price_versions.c.product_id == "018f6f73-2d0a-74f0-8f1c-000000000112"
        ))
        session.commit()
    response = client.get(f"/api/v1/public/branches/{second_key}/catalog")
    assert response.status_code == 200
    catalog = response.json()
    assert catalog["branch_id"] == second_branch_id
    assert PRODUCT_ID not in {item["id"] for item in catalog["items"]}
    assert "018f6f73-2d0a-74f0-8f1c-000000000112" not in {item["id"] for item in catalog["items"]}
    assert all(isinstance(item["price_cents"], int) for item in catalog["items"])


def test_post_commit_failure_recovers_the_same_intent_by_idempotency_key() -> None:
    client = _client_with_seeded_database()
    _enable_public_order_capture(client)

    def fail_after_commit() -> None:
        raise RuntimeError("public-order-after-commit")

    client.app.state.public_order_after_commit_hook = fail_after_commit
    with pytest.raises(RuntimeError, match="public-order-after-commit"):
        _post_intent(client, _payload(), key="public-order-after-commit-001")
    del client.app.state.public_order_after_commit_hook

    recovered = _post_intent(client, _payload(), key="public-order-after-commit-001")
    assert recovered.status_code == 200
    assert recovered.json()["status"] == "PENDING_REVIEW"
    with _test_session_factory(client)() as session:
        assert _count(session, "public_order_intents") == 1
        assert _count(session, "public_order_intent_commands") == 1


def test_authenticated_acceptance_creates_canonical_order_once_without_cash_shift() -> None:
    client = _client_with_seeded_database()
    _enable_public_order_capture(client)
    created = _post_intent(client, _payload())
    assert created.status_code == 201
    reference = created.json()["public_reference"]
    assert reference.startswith("PI-") and len(reference) == 35
    with _test_session_factory(client)() as session:
        intent_id = session.execute(
            sa.select(models.metadata.tables["public_order_intents"].c.id).where(
                models.metadata.tables["public_order_intents"].c.public_reference == reference
            )
        ).scalar_one()

    payload = {"expected_version": 1}
    before = _capture_counts(client)
    missing_actor = client.post(f"/api/v1/order-intents/{intent_id}/accept", json=payload)
    assert missing_actor.status_code == 401
    assert _capture_counts(client) == before
    headers = {**_admin_headers(), "Idempotency-Key": "public-order-accept-001"}
    accepted = client.post(
        f"/api/v1/order-intents/{intent_id}/accept",
        headers=headers,
        json=payload,
    )
    assert accepted.status_code == 201
    assert accepted.json()["cash_shift_id"] is None

    replay = client.post(
        f"/api/v1/order-intents/{intent_id}/accept",
        headers=headers,
        json=payload,
    )
    assert replay.status_code == 200
    assert replay.json() == accepted.json()

    with _test_session_factory(client)() as session:
        assert _count(session, "orders") == 1
        assert _count(session, "order_lines") == 1
        assert _count(session, "order_line_consumption_snapshots") == 1
        reservations = session.execute(
            sa.select(sa.func.count())
            .select_from(models.inventory_movements)
            .where(models.inventory_movements.c.movement_type == "SALE_RESERVATION")
        ).scalar_one()
        assert reservations >= 1
        assert _count(session, "production_tasks") >= 1
        assert _count(session, "order_events") >= 1
        assert _count(session, "order_outbox_events") >= 1
        assert _count(session, "public_order_intent_commands") == 2
        assert _count(session, "payments") == 0
        order = session.execute(sa.select(models.orders)).mappings().one()
        assert order["cash_shift_id"] is None
        assert order["public_order_intent_id"] == intent_id
        assert order["public_order_intent_status"] == "ACCEPTED"
        intent = session.execute(sa.select(models.public_order_intents).where(models.public_order_intents.c.id == intent_id)).mappings().one()
        assert intent["accepted_order_id"] == order["id"]
        assert intent["correlation_id"] and len(intent["correlation_id"]) >= 32
        intent_line = session.execute(sa.select(models.public_order_intent_lines).where(models.public_order_intent_lines.c.intent_id == intent_id)).mappings().one()
        order_line = session.execute(sa.select(models.order_lines).where(models.order_lines.c.order_id == order["id"])).mappings().one()
        assert order_line["family_id_snapshot"] == intent_line["family_id_snapshot"]
        assert order_line["family_name_snapshot"] == intent_line["family_name_snapshot"]
        audits = session.execute(sa.select(models.audit_events).where(models.audit_events.c.entity_id == intent_id)).mappings().all()
        assert {row["action"] for row in audits} == {"public_order_intent.captured", "public_order_intent.accepted"}
        rendered = repr([row["payload"] for row in audits])
        assert "Cliente marcador" not in rendered and "+526141234567" not in rendered and "public-order-accept-001" not in rendered


def test_public_dine_in_intent_is_accepted() -> None:
    client = _client_with_seeded_database()
    _enable_public_order_capture(client)
    created = _post_intent(client, _payload(order_type="dine-in"), key="public-order-dine-in-001")
    assert created.status_code == 201


def test_authenticated_rejection_is_idempotent_and_has_no_operational_effects() -> None:
    client = _client_with_seeded_database()
    _enable_public_order_capture(client)
    created = _post_intent(client, _payload(), key="public-order-reject-create-001")
    intent_id = _intent_id(client, created.json()["public_reference"])
    payload = {"expected_version": 1, "reason": "Producto no disponible hoy"}
    before = _accept_effect_counts(client)

    missing_actor = client.post(
        f"/api/v1/order-intents/{intent_id}/reject", json=payload
    )
    assert missing_actor.status_code == 401
    rejected = client.post(
        f"/api/v1/order-intents/{intent_id}/reject",
        headers={**_admin_headers(), "Idempotency-Key": "public-order-reject-001"},
        json=payload,
    )
    assert rejected.status_code == 201
    assert rejected.json() == {
        "public_reference": created.json()["public_reference"],
        "status": "REJECTED",
        "version": 2,
    }
    replay = client.post(
        f"/api/v1/order-intents/{intent_id}/reject",
        headers={**_admin_headers(), "Idempotency-Key": "public-order-reject-001"},
        json=payload,
    )
    assert replay.status_code == 200
    assert replay.json() == rejected.json()
    conflict = client.post(
        f"/api/v1/order-intents/{intent_id}/reject",
        headers={**_admin_headers(), "Idempotency-Key": "public-order-reject-001"},
        json={**payload, "reason": "Otra razon suficientemente larga"},
    )
    assert conflict.status_code == 409

    public_status = client.get(
        f"/api/v1/public/order-intents/{created.json()['public_reference']}"
    )
    assert public_status.status_code == 200
    assert public_status.json()["status"] == "REJECTED"
    assert "reason" not in public_status.json()
    after = _accept_effect_counts(client)
    assert after == {**before, "public_order_intent_commands": before["public_order_intent_commands"] + 1}
    with _test_session_factory(client)() as session:
        intent = session.execute(
            sa.select(models.public_order_intents).where(
                models.public_order_intents.c.id == intent_id
            )
        ).mappings().one()
        assert intent["decision_reason"] == payload["reason"]
        assert intent["decided_at"] is not None
        assert intent["decided_by_user_id"] is not None
        actions = set(
            session.scalars(
                sa.select(models.audit_events.c.action).where(
                    models.audit_events.c.entity_id == intent_id
                )
            ).all()
        )
        assert actions == {
            "public_order_intent.captured",
            "public_order_intent.rejected",
        }

    cannot_accept = client.post(
        f"/api/v1/order-intents/{intent_id}/accept",
        headers={**_admin_headers(), "Idempotency-Key": "public-order-after-reject-001"},
        json={"expected_version": 2},
    )
    assert cannot_accept.status_code == 409


def test_public_acceptance_revalidates_operational_state_without_repricing() -> None:
    client = _client_with_seeded_database()
    _enable_public_order_capture(client)
    created = _post_intent(client, _payload(), key="public-order-operational-revalidate-001")
    assert created.status_code == 201
    intent_id = _intent_id(client, created.json()["public_reference"])
    with _test_session_factory(client)() as session:
        # A later price is deliberately irrelevant: the accepted order keeps the captured price.
        session.execute(models.price_versions.update().where(
            models.price_versions.c.product_id == PRODUCT_ID,
            models.price_versions.c.valid_to.is_(None),
        ).values(price_cents=12_345))
        session.commit()
    accepted = client.post(
        f"/api/v1/order-intents/{intent_id}/accept",
        headers={**_admin_headers(), "Idempotency-Key": "public-order-operational-accept-001"},
        json={"expected_version": 1},
    )
    assert accepted.status_code == 201
    assert accepted.json()["total_cents"] == created.json()["total_cents"]

    blocked = _post_intent(client, _payload(), key="public-order-operational-revalidate-002")
    blocked_id = _intent_id(client, blocked.json()["public_reference"])
    with _test_session_factory(client)() as session:
        session.execute(models.branch_product_availability.update().where(
            models.branch_product_availability.c.branch_id == BRANCH_ID,
            models.branch_product_availability.c.product_id == PRODUCT_ID,
        ).values(is_available=False, updated_at=datetime.now(timezone.utc)))
        session.commit()
    denied = client.post(
        f"/api/v1/order-intents/{blocked_id}/accept",
        headers={**_admin_headers(), "Idempotency-Key": "public-order-operational-denied-001"},
        json={"expected_version": 1},
    )
    assert denied.status_code == 409
    with _test_session_factory(client)() as session:
        intent = session.execute(sa.select(models.public_order_intents).where(
            models.public_order_intents.c.id == blocked_id
        )).mappings().one()
        assert intent["status"] == "PENDING_REVIEW"
        assert session.execute(sa.select(sa.func.count()).select_from(models.orders)).scalar_one() == 1


def test_public_intent_order_is_collected_in_the_later_open_cash_shift() -> None:
    client = _client_with_seeded_database()
    _enable_public_order_capture(client)
    created = _post_intent(client, _payload(), key="public-order-later-payment-001")
    intent_id = _intent_id(client, created.json()["public_reference"])
    accepted = client.post(
        f"/api/v1/order-intents/{intent_id}/accept",
        headers={**_admin_headers(), "Idempotency-Key": "public-order-later-accept-001"},
        json={"expected_version": 1},
    )
    assert accepted.status_code == 201
    order_id = accepted.json()["id"]
    opened = _open_shift(client, 0)
    assert opened.status_code == 200
    payment = client.post(
        f"/api/v1/orders/{order_id}/payments",
        headers=_admin_headers(),
        json={"amount_cents": accepted.json()["total_cents"], "method": "cash", "register_id": "CAJA-01"},
    )
    assert payment.status_code == 200
    with _test_session_factory(client)() as session:
        order = session.execute(sa.select(models.orders).where(models.orders.c.id == order_id)).mappings().one()
        persisted_payment = session.execute(sa.select(models.payments).where(models.payments.c.order_id == order_id)).mappings().one()
        snapshot = session.execute(sa.select(models.sales_operation_snapshots).where(models.sales_operation_snapshots.c.order_id == order_id)).mappings().one()
    assert order["cash_shift_id"] is None
    assert persisted_payment["cash_shift_id"] == opened.json()["id"]
    assert snapshot["cash_shift_id"] == opened.json()["id"]


def test_public_phone_normalizes_allowed_separators_without_inventing_country() -> None:
    client = _client_with_seeded_database()
    _enable_public_order_capture(client)
    created = _post_intent(client, _payload(customer_phone="614 123-4567"), key="public-order-phone-normalized-001")
    assert created.status_code == 201
    with _test_session_factory(client)() as session:
        phone = session.execute(sa.select(models.public_order_intents.c.customer_snapshot)).scalar_one()["phone"]
    assert phone == "6141234567"


def test_sqlite_foreign_keys_reject_null_cash_shift_without_an_accepted_intent() -> None:
    client = _client_with_seeded_database()
    _enable_public_order_capture(client)
    created = _post_intent(client, _payload())
    assert created.status_code == 201
    pending_intent_id = _intent_id(client, created.json()["public_reference"])
    now = datetime.now(timezone.utc)

    with _test_session_factory(client)() as session:
        session.connection().exec_driver_sql("PRAGMA foreign_keys = ON")
        base = {
            "organization_id": "018f6f73-2d0a-74f0-8f1c-000000000001",
            "branch_id": BRANCH_ID,
            "cash_shift_id": None,
            "customer_id": None,
            "customer_snapshot": None,
            "delivery_address_snapshot": None,
            "channel": "PUBLIC_INTENT",
            "status": "ACCEPTED",
            "total_cents": 0,
            "currency": "MXN",
            "owner_name": None,
            "order_type": "takeout",
            "payment_method_intent": None,
            "version": 1,
            "created_at": now,
            "accepted_at": now,
        }
        with pytest.raises(sa.exc.IntegrityError):
            session.execute(models.orders.insert().values(
                **base, id="mobord001-no-intent", folio="MOB-001",
                public_order_intent_id=None, public_order_intent_status=None,
            ))
            session.commit()
        session.rollback()
        with pytest.raises(sa.exc.IntegrityError):
            session.execute(models.orders.insert().values(
                **base, id="mobord001-pending", folio="MOB-002",
                public_order_intent_id=pending_intent_id,
                # CHECK permits this shape; the composite FK must reject the pending intent.
                public_order_intent_status="ACCEPTED",
            ))
            session.commit()
        session.rollback()


def test_wrong_scope_acceptance_and_revoked_replay_have_no_acceptance_effects() -> None:
    client = _client_with_seeded_database()
    _enable_public_order_capture(client)
    first = _post_intent(client, _payload(), key="public-order-scope-001")
    assert first.status_code == 201
    first_id = _intent_id(client, first.json()["public_reference"])
    with _test_session_factory(client)() as session:
        session.execute(models.roles.update().where(models.roles.c.id == "018f6f73-2d0a-74f0-8f1c-000000000005").values(scope="branch"))
        session.execute(models.user_roles.update().where(models.user_roles.c.user_id == "018f6f73-2d0a-74f0-8f1c-000000000006").values(branch_id="wrong-branch"))
        session.commit()
    before_wrong_scope = _accept_effect_counts(client)
    denied = client.post(
        f"/api/v1/order-intents/{first_id}/accept",
        headers={**_admin_headers(), "Idempotency-Key": "public-order-scope-accept-001"},
        json={"expected_version": 1},
    )
    assert denied.status_code == 403
    assert _accept_effect_counts(client) == before_wrong_scope

    with _test_session_factory(client)() as session:
        session.execute(models.roles.update().where(models.roles.c.id == "018f6f73-2d0a-74f0-8f1c-000000000005").values(scope="organization"))
        session.execute(models.user_roles.update().where(models.user_roles.c.user_id == "018f6f73-2d0a-74f0-8f1c-000000000006").values(branch_id=None))
        session.commit()
    accepted = client.post(
        f"/api/v1/order-intents/{first_id}/accept",
        headers={**_admin_headers(), "Idempotency-Key": "public-order-scope-accept-001"},
        json={"expected_version": 1},
    )
    assert accepted.status_code == 201
    before_revoked_replay = _accept_effect_counts(client)
    with _test_session_factory(client)() as session:
        permission_id = session.execute(sa.select(models.permissions.c.id).where(models.permissions.c.code == "orders.create")).scalar_one()
        session.execute(models.role_permissions.delete().where(
            models.role_permissions.c.role_id == "018f6f73-2d0a-74f0-8f1c-000000000005",
            models.role_permissions.c.permission_id == permission_id,
        ))
        session.commit()
    replay_denied = client.post(
        f"/api/v1/order-intents/{first_id}/accept",
        headers={**_admin_headers(), "Idempotency-Key": "public-order-scope-accept-001"},
        json={"expected_version": 1},
    )
    assert replay_denied.status_code == 403
    assert _accept_effect_counts(client) == before_revoked_replay


def test_public_order_configuration_defaults_off_and_can_be_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings(_env_file=None).public_order_intents_enabled is False
    monkeypatch.setenv("RESTAURANTOS_PUBLIC_ORDER_INTENTS_ENABLED", "true")
    assert Settings(_env_file=None).public_order_intents_enabled is True


def test_public_command_race_recovery_returns_winner_or_conflict() -> None:
    client = _client_with_seeded_database()
    now = datetime.now(timezone.utc)
    with _test_session_factory(client)() as session:
        session.execute(models.public_order_intent_commands.insert().values(
            id="mobord001-race-command",
            organization_id="018f6f73-2d0a-74f0-8f1c-000000000001",
            intent_id=None,
            command_type="create",
            idempotency_key="mobord001-race-key",
            request_hash="same-request-hash",
            result={"public_reference": "PI-RACE", "status": "PENDING_REVIEW"},
            actor_user_id=None,
            created_at=now,
        ))
        session.commit()
        recovered = _recover_public_order_command(
            session,
            "018f6f73-2d0a-74f0-8f1c-000000000001",
            "create",
            "mobord001-race-key",
            "same-request-hash",
        )
        assert recovered == ({"public_reference": "PI-RACE", "status": "PENDING_REVIEW"}, False)
        with pytest.raises(BusinessError) as exc_info:
            _recover_public_order_command(
                session,
                "018f6f73-2d0a-74f0-8f1c-000000000001",
                "create",
                "mobord001-race-key",
                "different-request-hash",
            )
        assert exc_info.value.code == "idempotency_conflict"


def test_get_order_detail_for_public_order_intent_in_pos() -> None:
    client = _client_with_seeded_database()
    _enable_public_order_capture(client)
    created = _post_intent(client, _payload(customer_name="Valeria Morales"), key="pos-open-intent-test-001")
    assert created.status_code == 201
    intent_id = _intent_id(client, created.json()["public_reference"])

    # 1. Fetch detail as pending public order intent
    detail = client.get(f"/api/v1/orders/{intent_id}", headers=_admin_headers())
    assert detail.status_code == 200
    detail_data = detail.json()
    assert detail_data["id"] == intent_id
    assert detail_data["status"] == "PENDING"
    assert detail_data["customer_label"] == "Valeria Morales"
    assert len(detail_data["lines"]) == 1
    assert detail_data["is_public_intent"] is True

    # 2. Accept the order intent via POS accept endpoint
    accepted = client.post(f"/api/v1/orders/{intent_id}/accept", headers=_admin_headers())
    assert accepted.status_code == 200
    accepted_data = accepted.json()
    assert accepted_data["status"] == "ACCEPTED"
    assert "000001" in accepted_data["folio"]

    # 3. Fetch detail again using the intent id, verifying delegation to accepted order
    detail_after = client.get(f"/api/v1/orders/{intent_id}", headers=_admin_headers())
    assert detail_after.status_code == 200
    detail_after_data = detail_after.json()
    assert detail_after_data["status"] == "ACCEPTED"
    assert detail_after_data["folio"] == accepted_data["folio"]


def test_public_order_intent_persists_and_projects_notes_and_payment_details() -> None:
    client = _client_with_seeded_database()
    _enable_public_order_capture(client)
    payload = _payload(
        customer_name="Miguel Espino",
        order_notes="Sin cebolla en nada, voy para allá",
        table_number="Mesa 5",
        payment_method="cash",
        cash_amount="500",
        lines=[{"product_id": PRODUCT_ID, "quantity": 2, "notes": "Sin lechuga"}],
    )
    created = _post_intent(client, payload, key="pos-notes-intent-test-001")
    assert created.status_code == 201
    intent_id = _intent_id(client, created.json()["public_reference"])

    # 1. Check intent detail before acceptance
    detail = client.get(f"/api/v1/orders/{intent_id}", headers=_admin_headers())
    assert detail.status_code == 200
    d1 = detail.json()
    assert d1["order_notes"] == "Sin cebolla en nada, voy para allá"
    assert d1["table_number"] == "Mesa 5"
    assert d1["cash_amount"] == "500"
    assert d1["payment_method_intent"] == "cash"
    assert d1["lines"][0]["line_notes"] == "Sin lechuga"

    # 2. Check accounts list before acceptance
    accounts_resp = client.get(f"/api/v1/orders/accounts?branch_id={BRANCH_ID}", headers=_admin_headers())
    assert accounts_resp.status_code == 200
    account_item = next(item for item in accounts_resp.json()["items"] if item["id"] == intent_id)
    assert account_item["order_notes"] == "Sin cebolla en nada, voy para allá"
    assert account_item["table_number"] == "Mesa 5"
    assert account_item["cash_amount"] == "500"

    # 3. Accept the order intent
    accepted = client.post(f"/api/v1/orders/{intent_id}/accept", headers=_admin_headers())
    assert accepted.status_code == 200

    # 4. Check order detail after acceptance
    detail_after = client.get(f"/api/v1/orders/{intent_id}", headers=_admin_headers())
    assert detail_after.status_code == 200
    d2 = detail_after.json()
    assert d2["order_notes"] == "Sin cebolla en nada, voy para allá"
    assert d2["table_number"] == "Mesa 5"
    assert d2["cash_amount"] == "500"
    assert d2["payment_method_intent"] == "cash"
    assert d2["lines"][0]["line_notes"] == "Sin lechuga"

    # 5. Check accounts list after acceptance
    accounts_after = client.get(f"/api/v1/orders/accounts?branch_id={BRANCH_ID}", headers=_admin_headers())
    assert accounts_after.status_code == 200
    acc_after = next(item for item in accounts_after.json()["items"] if item["id"] == d2["id"])
    assert acc_after["order_notes"] == "Sin cebolla en nada, voy para allá"
    assert acc_after["table_number"] == "Mesa 5"
    assert acc_after["cash_amount"] == "500"
