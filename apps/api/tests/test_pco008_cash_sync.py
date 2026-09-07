# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-pco008-cash-sync-tests-v1
"""PCO-008 atomic central reconciliation regressions (crypto injected)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
import sqlalchemy as sa
from restaurant_os import api as api_module
from restaurant_os import models, operations
from restaurant_os.auth import create_session_token
from restaurant_os.config import get_settings
from restaurant_os.operations import AuthorizationError, BusinessError, receive_sync_command
from test_cash_concepts import BRANCH_A, CASHIER_ID, ORG_ID, _cash_concept_client
from test_cash_ledger import _movement_payload, _new_session, _withdrawal_concept

DEVICE_ID = "018f6f73-2d0a-74f0-8f1c-000000000401"
UTC = timezone.utc


def test_offline_grant_rejects_organization_different_from_persisted_actor() -> None:
    client = _cash_concept_client()
    session_factory = client.app.state.test_session_factory
    with session_factory() as session, pytest.raises(AuthorizationError) as rejected:
        operations.issue_offline_cash_grant(
            session,
            actor_user_id=CASHIER_ID,
            organization_id="018f6f73-2d0a-74f0-8f1c-999999999999",
            branch_id=BRANCH_A,
            source_device_id=DEVICE_ID,
        )
    assert rejected.value.code == "permission_denied"


def _envelope(concept_id: str, **overrides: Any) -> dict[str, Any]:
    command: dict[str, Any] = {
        "schema_version": "1.0",
        "command_id": "018f6f73-2d0a-74f0-8f1c-000000008001",
        "idempotency_key": "pco008-offline-cash-0001",
        "organization_id": ORG_ID,
        "branch_id": BRANCH_A,
        "source_device_id": DEVICE_ID,
        "actor_user_id": CASHIER_ID,
        "command_type": "cash.movement.create.v1",
        "occurred_at": "2026-08-12T12:00:00Z",
        "accepted_at": "2026-08-12T12:00:01Z",
        "offline_grant": "synthetic.offline.grant.for.injected.verifier",
        "payload": {
            key: value for key, value in _movement_payload(concept_id).items() if key != "branch_id"
        },
    }
    command.update(overrides)
    return command


def _valid_grant(_envelope: dict[str, Any]) -> str | None:
    return None


def test_confirmed_command_is_atomic_redacted_and_replayable() -> None:
    engine, session = _new_session()
    try:
        concept = _withdrawal_concept(session)
        command = _envelope(str(concept["id"]))

        first = receive_sync_command(
            session,
            command,
            actor_device_id=DEVICE_ID,
            grant_verifier=_valid_grant,
        )
        replay = receive_sync_command(
            session,
            command,
            actor_device_id=DEVICE_ID,
            grant_verifier=_valid_grant,
        )

        assert first["status"] == "CONFIRMED"
        assert first["checkpoint"] == 1
        assert replay["replayed"] is True
        assert replay["movement"]["id"] == first["movement"]["id"]
        assert "evidence_refs" not in first["movement"]
        assert first["movement"].keys() == {"id", "status"}
        assert first.keys() == {"status", "checkpoint", "replayed", "movement"}
        stored = session.execute(sa.select(models.sync_commands)).mappings().one()
        assert stored["payload"] == {
            "register_id": "CAJA-01",
            "movement_type": "withdrawal",
            "concept_id": concept["id"],
            "amount_cents": 2_000,
        }
        assert len(stored["request_hash"]) == 64
        assert (
            session.execute(sa.select(sa.func.count()).select_from(models.sync_events)).scalar_one()
            == 1
        )
        assert (
            session.execute(
                sa.select(sa.func.count()).select_from(models.cash_movements)
            ).scalar_one()
            == 1
        )
    finally:
        session.close()
        engine.dispose()


def test_confirmed_replay_does_not_depend_on_retired_grant_key() -> None:
    engine, session = _new_session()
    try:
        concept = _withdrawal_concept(session)
        command = _envelope(str(concept["id"]))
        first = receive_sync_command(
            session,
            command,
            actor_device_id=DEVICE_ID,
            grant_verifier=_valid_grant,
        )

        def retired_key_must_not_be_read(_command: dict[str, Any]) -> str | None:
            pytest.fail("confirmed replay attempted to verify a retired grant key")

        replay = receive_sync_command(
            session,
            command,
            actor_device_id=DEVICE_ID,
            grant_verifier=retired_key_must_not_be_read,
        )

        assert replay == {**first, "replayed": True}
        assert session.execute(
            sa.select(sa.func.count()).select_from(models.cash_movements)
        ).scalar_one() == 1
    finally:
        session.close()
        engine.dispose()


def test_invalid_grant_and_domain_denial_are_terminal_conflicts() -> None:
    engine, session = _new_session()
    try:
        concept = _withdrawal_concept(session)
        invalid_grant = _envelope(str(concept["id"]))
        result = receive_sync_command(
            session,
            invalid_grant,
            actor_device_id=DEVICE_ID,
            grant_verifier=lambda _command: "offline_grant_expired",
        )
        assert result == {
            "status": "CONFLICT",
            "code": "offline_grant_expired",
            "checkpoint": 1,
        }
        replay = receive_sync_command(
            session,
            invalid_grant,
            actor_device_id=DEVICE_ID,
            grant_verifier=_valid_grant,
        )
        assert replay["status"] == "CONFLICT"
        assert replay["code"] == "offline_grant_expired"
        assert replay["replayed"] is True
        assert (
            session.execute(
                sa.select(sa.func.count()).select_from(models.cash_movements)
            ).scalar_one()
            == 0
        )
        assert (
            session.execute(sa.select(sa.func.count()).select_from(models.sync_events)).scalar_one()
            == 0
        )
    finally:
        session.close()
        engine.dispose()


@pytest.mark.parametrize(
    ("obsolete_authority", "expected_code"),
    (
        ("inactive_actor", "actor_not_authorized"),
        ("revoked_permission", "permission_denied"),
        ("closed_shift", "cash_shift_not_open"),
        ("inactive_concept", "cash_concept_invalid"),
    ),
)
def test_obsolete_authority_is_a_terminal_conflict_without_financial_effect(
    obsolete_authority: str,
    expected_code: str,
) -> None:
    engine, session = _new_session()
    try:
        concept = _withdrawal_concept(session)
        if obsolete_authority == "inactive_actor":
            session.execute(
                models.users.update()
                .where(models.users.c.id == CASHIER_ID)
                .values(status="suspended")
            )
        elif obsolete_authority == "revoked_permission":
            permission_id = session.execute(
                sa.select(models.permissions.c.id).where(
                    models.permissions.c.code == "cash.movement.withdraw"
                )
            ).scalar_one()
            session.execute(
                models.role_permissions.delete().where(
                    models.role_permissions.c.permission_id == permission_id
                )
            )
        elif obsolete_authority == "closed_shift":
            session.execute(models.cash_shifts.update().values(status="OPERATIVELY_CLOSED"))
        elif obsolete_authority == "inactive_concept":
            session.execute(
                models.cash_movement_concepts.update()
                .where(models.cash_movement_concepts.c.id == concept["id"])
                .values(status="archived")
            )
        session.commit()

        result = receive_sync_command(
            session,
            _envelope(str(concept["id"])),
            actor_device_id=DEVICE_ID,
            grant_verifier=_valid_grant,
        )

        assert result["status"] == "CONFLICT"
        assert result["code"] == expected_code
        assert session.execute(
            sa.select(sa.func.count()).select_from(models.cash_movements)
        ).scalar_one() == 0
    finally:
        session.close()
        engine.dispose()


def test_http_routes_accept_bearer_and_persisted_scoped_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _cash_concept_client()
    token = "pco008-device-secret-for-route-test"
    now = datetime.now(UTC)
    session_factory = client.app.state.test_session_factory
    with session_factory() as session:
        session.execute(
            models.device_credentials.insert().values(
                id=DEVICE_ID,
                organization_id=ORG_ID,
                branch_id=BRANCH_A,
                capability="gateway.sync",
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                key_version="test-v1",
                expires_at=now + timedelta(hours=1),
                revoked_at=None,
                created_at=now,
            )
        )
        session.commit()

    observed: dict[str, Any] = {}

    def fake_issue(
        _session: Any,
        *,
        actor_user_id: str,
        organization_id: str,
        branch_id: str,
        source_device_id: str,
    ) -> dict[str, Any]:
        observed["grant"] = (
            actor_user_id,
            organization_id,
            branch_id,
            source_device_id,
        )
        return {
            "offline_grant": "route.test.synthetic.offline.grant",
            "expires_at": (now + timedelta(minutes=30)).isoformat(),
        }

    def fake_receive(
        _session: Any,
        payload: dict[str, Any],
        *,
        actor_device_id: str | None = None,
    ) -> dict[str, Any]:
        observed["sync"] = (payload["command_id"], actor_device_id)
        return {"status": "CONFIRMED", "checkpoint": 7, "replayed": False}

    monkeypatch.setattr(api_module, "issue_offline_cash_grant", fake_issue)
    monkeypatch.setattr(api_module, "receive_sync_command", fake_receive)
    bearer = create_session_token({"sub": CASHIER_ID}, get_settings().secret_key)
    grant_response = client.post(
        "/api/v1/auth/offline-grants",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"branch_id": BRANCH_A, "source_device_id": DEVICE_ID},
    )
    assert grant_response.status_code == 200
    assert observed["grant"] == (CASHIER_ID, ORG_ID, BRANCH_A, DEVICE_ID)

    command = _envelope("018f6f73-2d0a-74f0-8f1c-000000009777")
    sync_response = client.post(
        "/api/v1/sync/commands",
        headers={"X-Device-Token": token},
        json=command,
    )
    assert sync_response.status_code == 200
    assert sync_response.json() == {"status": "CONFIRMED", "checkpoint": 7, "replayed": False}
    assert observed["sync"] == (command["command_id"], DEVICE_ID)

    with session_factory() as session:
        session.execute(
            models.device_credentials.update()
            .where(models.device_credentials.c.id == DEVICE_ID)
            .values(revoked_at=now)
        )
        session.commit()
    revoked = client.post(
        "/api/v1/sync/commands",
        headers={"X-Device-Token": token},
        json=command,
    )
    assert revoked.status_code == 403
    assert revoked.json()["detail"]["code"] == "device_scope_denied"


def test_changed_intent_and_device_scope_fail_closed() -> None:
    engine, session = _new_session()
    try:
        concept = _withdrawal_concept(session)
        command = _envelope(str(concept["id"]))
        with pytest.raises(BusinessError) as denied:
            receive_sync_command(
                session,
                command,
                actor_device_id="018f6f73-2d0a-74f0-8f1c-000000000499",
                grant_verifier=_valid_grant,
            )
        assert denied.value.code == "gateway_scope_denied"

        receive_sync_command(
            session,
            command,
            actor_device_id=DEVICE_ID,
            grant_verifier=_valid_grant,
        )
        changed = {
            **command,
            "payload": {**command["payload"], "amount_cents": 2_001},
        }
        with pytest.raises(BusinessError) as conflict:
            receive_sync_command(
                session,
                changed,
                actor_device_id=DEVICE_ID,
                grant_verifier=_valid_grant,
            )
        assert conflict.value.code == "idempotency_conflict"
    finally:
        session.close()
        engine.dispose()


@pytest.mark.parametrize(
    "fault_point",
    ("after_cash_core", "after_sync_command", "after_sync_event", "after_audit"),
)
def test_fault_rolls_back_cash_inbox_event_audit_and_checkpoint(
    monkeypatch: pytest.MonkeyPatch, fault_point: str
) -> None:
    engine, session = _new_session()
    try:
        concept = _withdrawal_concept(session)
        command = _envelope(str(concept["id"]))

        def fail_at(point: str) -> None:
            if point == fault_point:
                raise RuntimeError(fault_point)

        monkeypatch.setattr(operations, "_pco008_fault", fail_at)
        with pytest.raises(RuntimeError, match=fault_point):
            receive_sync_command(
                session,
                command,
                actor_device_id=DEVICE_ID,
                grant_verifier=_valid_grant,
            )

        assert (
            session.execute(
                sa.select(sa.func.count()).select_from(models.cash_movements)
            ).scalar_one()
            == 0
        )
        assert (
            session.execute(
                sa.select(sa.func.count()).select_from(models.cash_movement_commands)
            ).scalar_one()
            == 0
        )
        assert (
            session.execute(
                sa.select(sa.func.count()).select_from(models.sync_commands)
            ).scalar_one()
            == 0
        )
        assert (
            session.execute(sa.select(sa.func.count()).select_from(models.sync_events)).scalar_one()
            == 0
        )
        assert (
            session.execute(
                sa.select(sa.func.count()).select_from(models.sync_branch_checkpoints)
            ).scalar_one()
            == 0
        )
        assert (
            session.execute(
                sa.select(sa.func.count())
                .select_from(models.audit_events)
                .where(
                    models.audit_events.c.action.in_(
                        ("cash_movement.created", "sync_command.confirmed")
                    )
                )
            ).scalar_one()
            == 0
        )
    finally:
        session.close()
        engine.dispose()
