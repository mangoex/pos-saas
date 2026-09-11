"""PCO-003 cash-ledger domain, API, and contract regressions."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from threading import Barrier

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import (
    AuthorizationError,
    BusinessError,
    archive_cash_concept,
    calculate_expected_cash,
    close_cash_shift_operationally,
    compensate_cash_movement,
    confirm_purchase_document,
    create_cash_concept,
    create_cash_movement,
    get_open_cash_shift,
    list_cash_movement_ledger,
    list_cash_movements,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from test_cash_concepts import (
    BRANCH_A,
    BRANCH_B,
    CASHIER_ID,
    CASHIER_ROLE_ID,
    ORG_ID,
    OWNER_ID,
    _cash_concept_client,
    _concept_payload,
    _seed_cash_concept_scope,
)
from test_platform_api import ADMIN_USER_ID, _seed

UTC = timezone.utc
SHIFT_ID = "018f6f73-2d0a-74f0-8f1c-000000009901"
NOW = datetime(2026, 8, 12, tzinfo=timezone.utc)


def _movement_payload(concept_id: str, **overrides: object) -> dict[str, object]:
    return {
        "branch_id": BRANCH_A,
        "register_id": "CAJA-01",
        "movement_type": "withdrawal",
        "concept_id": concept_id,
        "amount_cents": 2_000,
        "reference": "FOLIO-123",
        "evidence_refs": ["evidence://ticket/abc"],
        **overrides,
    }


def _grant_cash_permissions(session: Session, *codes: str) -> None:
    rows = []
    grants = []
    for offset, code in enumerate(codes, start=1):
        permission_id = f"018f6f73-2d0a-74f0-8f1c-0000000012{offset:02d}"
        rows.append(
            {
                "id": permission_id,
                "code": code,
                "description": code,
                "created_at": NOW,
            }
        )
        grants.append({"role_id": CASHIER_ROLE_ID, "permission_id": permission_id})
    session.execute(models.permissions.insert(), rows)
    session.execute(models.role_permissions.insert(), grants)
    session.commit()


def _insert_shift(session: Session, status: str = "OPEN") -> None:
    session.execute(
        models.cash_shifts.insert().values(
            id=SHIFT_ID,
            organization_id=ORG_ID,
            branch_id=BRANCH_A,
            register_code="CAJA-01",
            status=status,
            opening_cash_cents=10_000,
            opened_at=NOW,
            closed_at=None,
            created_at=NOW,
        )
    )
    session.commit()


def _insert_movement(
    session: Session,
    movement_id: str,
    movement_type: str,
    amount_cents: int,
    *,
    status: str = "confirmed",
    created_at: datetime = NOW,
    reversal_of_id: str | None = None,
    compensates_movement_id: str | None = None,
    source_type: str = "manual",
) -> None:
    session.execute(
        models.cash_movements.insert().values(
            id=movement_id,
            organization_id=ORG_ID,
            branch_id=BRANCH_A,
            cash_shift_id=SHIFT_ID,
            movement_type=movement_type,
            amount_cents=amount_cents,
            reason_code="TEST",
            reason="PCO-003 test",
            source_type=source_type,
            source_id=None,
            actor_user_id=OWNER_ID,
            idempotency_key=f"legacy-{movement_id}",
            status=status,
            reversal_of_id=reversal_of_id,
            concept_id=None,
            concept_version_id=None,
            concept_snapshot=None,
            reference="PRIVATE-REFERENCE",
            evidence_refs=["evidence://private"],
            compensates_movement_id=compensates_movement_id,
            created_at=created_at,
        )
    )


def _new_session() -> tuple[sa.Engine, Session]:
    engine = create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    session = Session(engine)
    _seed_cash_concept_scope(session)
    _grant_cash_permissions(
        session,
        "cash.movement.withdraw",
        "cash.movement.deposit",
        "cash.movement.compensate",
        "cash.movement.read",
        "cash.shift.close",
    )
    _insert_shift(session)
    return engine, session


def _withdrawal_concept(session: Session) -> dict[str, object]:
    return create_cash_concept(session, _concept_payload(), "concept-ledger", OWNER_ID)


def test_manual_movement_replay_compensates_and_redacts() -> None:
    engine, session = _new_session()
    try:
        concept = _withdrawal_concept(session)
        created = create_cash_movement(
            session,
            _movement_payload(str(concept["id"])),
            "movement-001",
            CASHIER_ID,
        )
        replay = create_cash_movement(
            session,
            _movement_payload(str(concept["id"])),
            "movement-001",
            CASHIER_ID,
        )
        assert replay == created
        assert created["summary_at_commit"]["expected_cash_cents"] == 8_000
        stored_key = session.execute(
            sa.select(models.cash_movements.c.idempotency_key).where(
                models.cash_movements.c.id == created["movement"]["id"]
            )
        ).scalar_one()
        assert stored_key == hashlib.sha256(
            f"cash-movement:{ORG_ID}:movement-001".encode()
        ).hexdigest()
        compensated = compensate_cash_movement(
            session,
            created["movement"]["id"],
            {"reason": "Captura errónea", "evidence_refs": ["evidence://owner/1"]},
            "compensation-001",
            OWNER_ID,
        )
        assert compensated["movement"]["source_type"] == "COMPENSATION"
        assert compensated["current_summary"]["expected_cash_cents"] == 10_000
        with pytest.raises(BusinessError, match="already compensated") as repeated:
            compensate_cash_movement(
                session,
                created["movement"]["id"],
                {"reason": "Otra", "evidence_refs": ["evidence://owner/2"]},
                "compensation-002",
                OWNER_ID,
            )
        assert repeated.value.code == "cash_movement_already_compensated"
        listed = list_cash_movement_ledger(
            session,
            CASHIER_ID,
            BRANCH_A,
            "CAJA-01",
            SHIFT_ID,
            None,
            None,
            None,
            10,
            None,
        )
        assert len(listed["items"]) == 2
        assert "idempotency_key" not in listed["items"][0]
        assert "evidence_refs" not in listed["items"][0]
        legacy = list_cash_movements(session, BRANCH_A)
        assert "idempotency_key" not in legacy[0]
        assert "evidence_refs" not in legacy[0]
        audit_payload = session.execute(
            sa.select(models.audit_events.c.payload).where(
                models.audit_events.c.action == "cash_movement.created"
            )
        ).scalar_one()
        rendered_audit = json.dumps(audit_payload)
        assert "PRIVATE-REFERENCE" not in rendered_audit
        assert "evidence://ticket/abc" not in rendered_audit
        assert "movement-001" not in rendered_audit
    finally:
        session.close()
        engine.dispose()


def test_compensation_requires_persisted_owner_authority_not_only_permission() -> None:
    engine, session = _new_session()
    try:
        concept = _withdrawal_concept(session)
        created = create_cash_movement(
            session, _movement_payload(str(concept["id"])), "owner-guard-create", CASHIER_ID
        )

        # CASHIER has cash.movement.compensate, but does not hold the persisted
        # organization authority grant and must be rejected before any append.
        with pytest.raises(AuthorizationError) as denied:
            compensate_cash_movement(
                session,
                created["movement"]["id"],
                {"reason": "No es Dueño", "evidence_refs": ["evidence://denied"]},
                "owner-guard-denied",
                CASHIER_ID,
            )
        assert denied.value.code == "permission_denied"
        session.rollback()
        assert session.execute(
            sa.select(sa.func.count()).select_from(models.cash_movements)
        ).scalar_one() == 1

        allowed = compensate_cash_movement(
            session,
            created["movement"]["id"],
            {"reason": "Dueño corrige", "evidence_refs": ["evidence://owner"]},
            "owner-guard-allowed",
            OWNER_ID,
        )
        assert allowed["movement"]["movement_type"] == "deposit"
        assert allowed["movement"]["amount_cents"] == 2_000
        assert allowed["current_summary"]["expected_cash_cents"] == 10_000
    finally:
        session.close()
        engine.dispose()


def test_ledger_projects_compensation_state_from_full_authorized_history() -> None:
    engine, session = _new_session()
    try:
        concept = _withdrawal_concept(session)
        original = create_cash_movement(
            session,
            _movement_payload(str(concept["id"])),
            "ledger-state-original",
            CASHIER_ID,
        )
        eligible = list_cash_movement_ledger(
            session, CASHIER_ID, BRANCH_A, None, SHIFT_ID, "withdrawal", None, None, 10, None
        )["items"]
        assert eligible[0]["compensation_state"] == "eligible"
        assert eligible[0]["compensated_by_movement_id"] is None

        compensation = compensate_cash_movement(
            session,
            original["movement"]["id"],
            {"reason": "Corrección UI", "evidence_refs": ["evidence://owner/ui"]},
            "ledger-state-compensation",
            OWNER_ID,
        )
        # The deposit compensation is not in this filtered page; the original must
        # still be projected as compensated from the complete authorized history.
        withdrawals = list_cash_movement_ledger(
            session, CASHIER_ID, BRANCH_A, None, SHIFT_ID, "withdrawal", None, None, 10, None
        )["items"]
        assert withdrawals[0]["compensation_state"] == "compensated"
        assert withdrawals[0]["compensated_by_movement_id"] == compensation["movement"]["id"]
        all_rows = list_cash_movement_ledger(
            session, CASHIER_ID, BRANCH_A, None, SHIFT_ID, None, None, None, 10, None
        )["items"]
        compensation_row = next(
            row for row in all_rows if row["id"] == compensation["movement"]["id"]
        )
        assert compensation_row["compensation_state"] == "compensation"
        assert compensation_row["compensated_by_movement_id"] is None

        legacy_reversal_id = "018f6f73-2d0a-74f0-8f1c-000000009918"
        legacy_withdrawal_id = "018f6f73-2d0a-74f0-8f1c-000000009919"
        _insert_movement(session, legacy_reversal_id, "cash_reversal", 100)
        _insert_movement(session, legacy_withdrawal_id, "withdrawal", 100)
        session.commit()
        open_rows = list_cash_movement_ledger(
            session, CASHIER_ID, BRANCH_A, None, SHIFT_ID, None, None, None, 10, None
        )["items"]
        assert next(row for row in open_rows if row["id"] == legacy_reversal_id)[
            "compensation_state"
        ] == "ineligible"
        assert next(row for row in open_rows if row["id"] == legacy_withdrawal_id)[
            "compensation_state"
        ] == "eligible"
        session.execute(
            models.cash_shifts.update()
            .where(models.cash_shifts.c.id == SHIFT_ID)
            .values(status="CLOSED")
        )
        session.commit()
        closed_rows = list_cash_movement_ledger(
            session, CASHIER_ID, BRANCH_A, None, SHIFT_ID, None, None, None, 10, None
        )["items"]
        assert next(row for row in closed_rows if row["id"] == legacy_withdrawal_id)[
            "compensation_state"
        ] == "ineligible"
    finally:
        session.close()
        engine.dispose()


def test_python_formula_excludes_unconfirmed_and_rejects_unknown_type() -> None:
    engine, session = _new_session()
    try:
        _insert_movement(session, "018f6f73-2d0a-74f0-8f1c-000000009911", "deposit", 1_000)
        _insert_movement(
            session,
            "018f6f73-2d0a-74f0-8f1c-000000009912",
            "withdrawal",
            2_000,
        )
        purchase_id = "018f6f73-2d0a-74f0-8f1c-000000009913"
        _insert_movement(session, purchase_id, "withdrawal", 3_000, source_type="purchase")
        _insert_movement(
            session,
            "018f6f73-2d0a-74f0-8f1c-000000009914",
            "deposit",
            999,
            status="pending",
        )
        session.execute(
            models.payments.insert(),
            [
                {
                    "id": "018f6f73-2d0a-74f0-8f1c-000000009921",
                    "organization_id": ORG_ID,
                    "branch_id": BRANCH_A,
                    "order_id": "018f6f73-2d0a-74f0-8f1c-000000009931",
                    "cash_shift_id": SHIFT_ID,
                    "method": "cash",
                    "status": "CONFIRMED",
                    "amount_cents": 5_000,
                    "currency": "MXN",
                    "confirmed_at": NOW,
                    "created_at": NOW,
                },
                {
                    "id": "018f6f73-2d0a-74f0-8f1c-000000009922",
                    "organization_id": ORG_ID,
                    "branch_id": BRANCH_A,
                    "order_id": "018f6f73-2d0a-74f0-8f1c-000000009932",
                    "cash_shift_id": SHIFT_ID,
                    "method": "cash",
                    "status": "PENDING",
                    "amount_cents": 7_000,
                    "currency": "MXN",
                    "confirmed_at": NOW,
                    "created_at": NOW,
                },
            ],
        )
        session.commit()
        summary = calculate_expected_cash(session, SHIFT_ID)
        assert summary["expected_cash_cents"] == 11_000
        assert summary["excluded_movement_count"] == 1
        source_projection = list_cash_movement_ledger(
            session,
            CASHIER_ID,
            BRANCH_A,
            None,
            SHIFT_ID,
            "withdrawal",
            None,
            None,
            10,
            None,
        )
        assert any(item["source_type"] == "PURCHASE" for item in source_projection["items"])
        compensation = compensate_cash_movement(
            session,
            purchase_id,
            {"reason": "Compra cancelada", "evidence_refs": ["evidence://purchase/1"]},
            "purchase-compensation",
            OWNER_ID,
        )
        assert compensation["current_summary"]["expected_cash_cents"] == 14_000
        _insert_movement(
            session,
            "018f6f73-2d0a-74f0-8f1c-000000009915",
            "mystery",
            1,
        )
        session.commit()
        with pytest.raises(BusinessError, match="unknown") as unknown:
            calculate_expected_cash(session, SHIFT_ID)
        assert unknown.value.code == "cash_ledger_unknown_type"
    finally:
        session.close()
        engine.dispose()


def test_validation_permissions_and_idempotency_conflicts_fail_closed() -> None:
    engine, session = _new_session()
    try:
        concept = _withdrawal_concept(session)
        payload = _movement_payload(
            str(concept["id"]),
            evidence_refs=["evidence://ticket/first", "evidence://ticket/second"],
        )
        created = create_cash_movement(session, payload, "stable-key", CASHIER_ID)
        assert created["movement"]["id"]
        for invalid_amount in (True, 0, -1):
            with pytest.raises(BusinessError) as invalid:
                create_cash_movement(
                    session,
                    _movement_payload(str(concept["id"]), amount_cents=invalid_amount),
                    f"invalid-{invalid_amount}",
                    CASHIER_ID,
                )
            assert invalid.value.code == "cash_movement_invalid"
        with pytest.raises(BusinessError) as extra:
            create_cash_movement(
                session,
                {**payload, "unexpected": True},
                "new-extra-key",
                CASHIER_ID,
            )
        assert extra.value.code == "cash_movement_invalid"
        for changed_payload in (
            {**payload, "amount_cents": 1},
            {
                **payload,
                "evidence_refs": list(reversed(payload["evidence_refs"])),
            },
            {**payload, "unexpected": True},
        ):
            with pytest.raises(BusinessError) as conflict:
                create_cash_movement(session, changed_payload, "stable-key", CASHIER_ID)
            assert conflict.value.code == "idempotency_conflict"
        with pytest.raises(BusinessError) as actor_conflict:
            create_cash_movement(session, payload, "stable-key", OWNER_ID)
        assert actor_conflict.value.code == "idempotency_conflict"
        with pytest.raises(AuthorizationError) as no_actor:
            create_cash_movement(session, payload, "actor-required", None)
        assert no_actor.value.code == "actor_required"
        with pytest.raises(AuthorizationError) as branch_denied:
            create_cash_movement(
                session,
                _movement_payload(str(concept["id"]), branch_id=BRANCH_B),
                "foreign-branch",
                CASHIER_ID,
            )
        assert branch_denied.value.code == "permission_denied"
    finally:
        session.close()
        engine.dispose()


def test_cashier_and_head_cashier_permissions_are_scoped_by_operation() -> None:
    engine = create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    session = Session(engine)
    try:
        _seed_cash_concept_scope(session)
        _grant_cash_permissions(
            session,
            "cash.movement.withdraw",
            "cash.movement.compensate",
        )
        _insert_shift(session)
        withdrawal = _withdrawal_concept(session)
        deposit = create_cash_concept(
            session,
            _concept_payload(
                code="OPERATING_DEPOSIT",
                name="Depósito operativo",
                allowed_movement_type="deposit",
            ),
            "deposit-concept",
            OWNER_ID,
        )
        withdrawal_result = create_cash_movement(
            session,
            _movement_payload(str(withdrawal["id"])),
            "cashier-withdrawal",
            CASHIER_ID,
        )
        with pytest.raises(AuthorizationError) as deposit_denied:
            create_cash_movement(
                session,
                _movement_payload(
                    str(deposit["id"]),
                    movement_type="deposit",
                    amount_cents=1_000,
                ),
                "cashier-deposit",
                CASHIER_ID,
            )
        assert deposit_denied.value.code == "permission_denied"
        session.rollback()
        head_id = "018f6f73-2d0a-74f0-8f1c-000000009981"
        head_role_id = "018f6f73-2d0a-74f0-8f1c-000000009982"
        deposit_permission_id = "018f6f73-2d0a-74f0-8f1c-000000009983"
        session.execute(
            models.permissions.insert().values(
                id=deposit_permission_id,
                code="cash.movement.deposit",
                description="Cash head deposits",
                created_at=NOW,
            )
        )
        session.execute(
            models.roles.insert().values(
                id=head_role_id,
                organization_id=ORG_ID,
                name="Cajero jefe",
                scope="branch",
                created_at=NOW,
            )
        )
        session.execute(
            models.users.insert().values(
                id=head_id,
                organization_id=ORG_ID,
                email="head-cashier@example.com",
                display_name="Head cashier",
                status="active",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.execute(
            models.user_roles.insert().values(
                user_id=head_id,
                role_id=head_role_id,
                branch_id=BRANCH_A,
            )
        )
        session.execute(
            models.role_permissions.insert().values(
                role_id=head_role_id,
                permission_id=deposit_permission_id,
            )
        )
        session.execute(
            models.role_permissions.insert().values(
                role_id=head_role_id,
                permission_id="018f6f73-2d0a-74f0-8f1c-000000001105",
            )
        )
        session.commit()
        deposit_result = create_cash_movement(
            session,
            _movement_payload(
                str(deposit["id"]),
                movement_type="deposit",
                amount_cents=1_000,
            ),
            "head-deposit",
            head_id,
        )
        assert deposit_result["movement"]["movement_type"] == "deposit"
        compensated = compensate_cash_movement(
            session,
            withdrawal_result["movement"]["id"],
            {"reason": "Dueño corrige", "evidence_refs": ["evidence://owner/correction"]},
            "owner-compensation",
            OWNER_ID,
        )
        assert compensated["movement"]["actor_user_id"] == OWNER_ID
    finally:
        session.close()
        engine.dispose()


def test_open_shift_guards_and_legacy_reversal_block_compensation() -> None:
    engine, session = _new_session()
    try:
        concept = _withdrawal_concept(session)
        session.execute(
            models.cash_shifts.update().where(models.cash_shifts.c.id == SHIFT_ID).values(
                status="CLOSED"
            )
        )
        session.commit()
        with pytest.raises(BusinessError) as closed:
            create_cash_movement(
                session,
                _movement_payload(str(concept["id"])),
                "closed",
                CASHIER_ID,
            )
        assert closed.value.code == "cash_shift_not_open"
        session.execute(
            models.cash_shifts.update().where(models.cash_shifts.c.id == SHIFT_ID).values(
                status="OPEN"
            )
        )
        _insert_movement(
            session,
            "018f6f73-2d0a-74f0-8f1c-000000009941",
            "cash_reversal",
            100,
            reversal_of_id="018f6f73-2d0a-74f0-8f1c-000000009942",
        )
        session.commit()
        with pytest.raises(BusinessError) as reversal:
            compensate_cash_movement(
                session,
                "018f6f73-2d0a-74f0-8f1c-000000009941",
                {"reason": "No", "evidence_refs": ["evidence://no"]},
                "cannot-compensate-reversal",
                OWNER_ID,
            )
        assert reversal.value.code == "cash_compensation_invalid"
        _insert_movement(
            session,
            "018f6f73-2d0a-74f0-8f1c-000000009943",
            "unknown_confirmed_type",
            100,
        )
        session.commit()
        with pytest.raises(BusinessError) as unknown_type:
            compensate_cash_movement(
                session,
                "018f6f73-2d0a-74f0-8f1c-000000009943",
                {"reason": "No", "evidence_refs": ["evidence://no"]},
                "cannot-compensate-unknown",
                OWNER_ID,
            )
        assert unknown_type.value.code == "cash_compensation_invalid"
    finally:
        session.close()
        engine.dispose()


def test_movement_rejects_future_archived_and_incompatible_concepts() -> None:
    engine, session = _new_session()
    try:
        future = create_cash_concept(
            session,
            _concept_payload(code="FUTURE_WITHDRAWAL", valid_from="2030-01-01T00:00:00Z"),
            "future-concept",
            OWNER_ID,
        )
        with pytest.raises(BusinessError) as future_error:
            create_cash_movement(
                session,
                _movement_payload(str(future["id"])),
                "future-movement",
                CASHIER_ID,
            )
        assert future_error.value.code == "cash_concept_invalid"
        session.rollback()
        deposit = create_cash_concept(
            session,
            _concept_payload(
                code="ONLY_DEPOSIT",
                name="Sólo depósito",
                allowed_movement_type="deposit",
            ),
            "deposit-only-concept",
            OWNER_ID,
        )
        with pytest.raises(BusinessError) as incompatible:
            create_cash_movement(
                session,
                _movement_payload(str(deposit["id"])),
                "incompatible-movement",
                CASHIER_ID,
            )
        assert incompatible.value.code == "cash_concept_invalid"
        session.rollback()
        active = _withdrawal_concept(session)
        archive_cash_concept(session, str(active["id"]), "archive-active-concept", OWNER_ID)
        with pytest.raises(BusinessError) as archived:
            create_cash_movement(
                session,
                _movement_payload(str(active["id"])),
                "archived-movement",
                CASHIER_ID,
            )
        assert archived.value.code == "cash_concept_invalid"
    finally:
        session.close()
        engine.dispose()


def test_open_shift_ambiguity_and_pagination_do_not_skip_rows() -> None:
    engine, session = _new_session()
    try:
        _insert_movement(
            session,
            "018f6f73-2d0a-74f0-8f1c-000000009951",
            "deposit",
            1,
            created_at=NOW,
        )
        _insert_movement(
            session,
            "018f6f73-2d0a-74f0-8f1c-000000009952",
            "deposit",
            2,
            created_at=NOW + timedelta(seconds=1),
        )
        _insert_movement(
            session,
            "018f6f73-2d0a-74f0-8f1c-000000009953",
            "deposit",
            3,
            created_at=NOW + timedelta(seconds=2),
        )
        session.commit()
        first = list_cash_movement_ledger(
            session,
            CASHIER_ID,
            BRANCH_A,
            "CAJA-01",
            SHIFT_ID,
            "deposit",
            NOW,
            NOW + timedelta(seconds=3),
            2,
            None,
        )
        second = list_cash_movement_ledger(
            session,
            CASHIER_ID,
            BRANCH_A,
            "CAJA-01",
            SHIFT_ID,
            "deposit",
            NOW,
            NOW + timedelta(seconds=3),
            2,
            first["next_cursor"],
        )
        ids = [item["id"] for item in first["items"] + second["items"]]
        assert ids == [
            "018f6f73-2d0a-74f0-8f1c-000000009953",
            "018f6f73-2d0a-74f0-8f1c-000000009952",
            "018f6f73-2d0a-74f0-8f1c-000000009951",
        ]
        with pytest.raises(BusinessError, match="not be after"):
            list_cash_movement_ledger(
                session,
                CASHIER_ID,
                BRANCH_A,
                None,
                SHIFT_ID,
                None,
                NOW + timedelta(days=1),
                NOW,
                2,
                None,
            )
        session.execute(sa.text("DROP INDEX uq_cash_shifts_open_register"))
        session.execute(
            models.cash_shifts.insert().values(
                id="018f6f73-2d0a-74f0-8f1c-000000009954",
                organization_id=ORG_ID,
                branch_id=BRANCH_A,
                register_code="CAJA-01",
                status="OPEN",
                opening_cash_cents=0,
                opened_at=NOW,
                closed_at=None,
                created_at=NOW,
            )
        )
        session.commit()
        with pytest.raises(BusinessError) as ambiguous:
            get_open_cash_shift(session, "CAJA-01", BRANCH_A)
        assert ambiguous.value.code == "cash_shift_ambiguous"
    finally:
        session.close()
        engine.dispose()


def test_close_uses_ledger_formula_and_prevents_later_movement() -> None:
    engine, session = _new_session()
    try:
        _insert_movement(session, "018f6f73-2d0a-74f0-8f1c-000000009961", "deposit", 1_000)
        session.commit()
        closed = close_cash_shift_operationally(session, SHIFT_ID, "ledger-close", CASHIER_ID)
        assert closed["closure"]["summary_snapshot"]["expected_cash_cents"] == 11_000
        assert session.execute(sa.select(models.cash_shift_cuts)).all() == []
        concept = _withdrawal_concept(session)
        with pytest.raises(BusinessError) as rejected:
            create_cash_movement(
                session,
                _movement_payload(str(concept["id"])),
                "after-close",
                CASHIER_ID,
            )
        assert rejected.value.code == "cash_shift_not_open"
    finally:
        session.close()
        engine.dispose()


def test_sqlite_concurrent_idempotency_and_close_race(tmp_path: Path) -> None:
    database_path = tmp_path / "pco003-concurrency.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    models.metadata.create_all(engine)
    with Session(engine) as setup:
        _seed_cash_concept_scope(setup)
        _grant_cash_permissions(
            setup,
            "cash.movement.withdraw",
            "cash.movement.deposit",
            "cash.movement.compensate",
            "cash.movement.read",
            "cash.shift.close",
        )
        _insert_shift(setup)
        concept = _withdrawal_concept(setup)
    payload = _movement_payload(str(concept["id"]))

    def create(key: str, amount_cents: int) -> tuple[str, object]:
        with Session(engine) as worker:
            try:
                return (
                    "ok",
                    create_cash_movement(
                        worker,
                        {**payload, "amount_cents": amount_cents},
                        key,
                        CASHIER_ID,
                    ),
                )
            except BusinessError as exc:
                return "error", exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        same_payload = list(pool.map(lambda _: create("sqlite-same", 2_000), range(2)))
    assert [state for state, _ in same_payload] == ["ok", "ok"]
    same_ids = {result["movement"]["id"] for _, result in same_payload}
    assert len(same_ids) == 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        different_payload = list(
            pool.map(
                lambda amount_cents: create("sqlite-different", amount_cents),
                (1_000, 2_000),
            )
        )
    states = sorted(result for state, result in different_payload if state == "error")
    assert states == ["idempotency_conflict"]
    with Session(engine) as verify:
        expected_before_close = calculate_expected_cash(verify, SHIFT_ID)["expected_cash_cents"]

    def close() -> tuple[str, object]:
        with Session(engine) as worker:
            try:
                return (
                    "ok",
                    close_cash_shift_operationally(
                        worker, SHIFT_ID, "sqlite-operational-close", CASHIER_ID
                    ),
                )
            except BusinessError as exc:
                return "error", exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        close_result, movement_result = list(
            pool.map(
                lambda action: action(),
                (close, lambda: create("sqlite-close-race", 1_000)),
            )
        )
    assert close_result[0] == "ok"
    if movement_result[0] == "ok":
        assert (
            close_result[1]["closure"]["summary_snapshot"]["expected_cash_cents"]
            == expected_before_close - 1_000
        )
    else:
        assert movement_result[1] == "cash_shift_not_open"
        assert (
            close_result[1]["closure"]["summary_snapshot"]["expected_cash_cents"]
            == expected_before_close
        )
    with Session(engine) as verify:
        cut_count = verify.execute(
            sa.select(sa.func.count()).select_from(models.cash_shift_cuts)
        ).scalar_one()
        assert cut_count == 0
    engine.dispose()


def test_sqlite_close_and_cash_purchase_race_share_the_open_shift_guard(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'pco003-purchase-race.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    models.metadata.create_all(engine)
    purchase_id = "018f6f73-2d0a-74f0-8f1c-000000009971"
    with Session(engine) as session:
        _seed(session)
        organization_id = session.execute(sa.select(models.organizations.c.id)).scalar_one()
        item = session.execute(
            sa.select(models.inventory_items).where(models.inventory_items.c.status == "active")
        ).mappings().first()
        assert item is not None
        supplier_id = "018f6f73-2d0a-74f0-8f1c-000000009972"
        presentation_id = "018f6f73-2d0a-74f0-8f1c-000000009973"
        session.execute(models.suppliers.insert().values(
            id=supplier_id, organization_id=organization_id, code="SQLITE-RACE",
            commercial_name="SQLite race supplier", delivery_days=[], payment_methods=["cash"],
            status="active", created_at=NOW, updated_at=NOW,
        ))
        session.execute(models.purchase_presentations.insert().values(
            id=presentation_id, organization_id=organization_id, supplier_id=supplier_id,
            item_id=item["id"], code="SQLITE-RACE-PRESENTATION", name="SQLite race presentation",
            package_type="unit", commercial_quantity=Decimal("1"),
            commercial_unit_id=item["base_unit_id"], base_unit_id=item["base_unit_id"],
            base_unit_yield=Decimal("1"), usable_content=Decimal("1"),
            yield_percent=Decimal("1"), tax_rate=Decimal("0"), last_net_price=Decimal("1"),
            cost_per_base_unit=Decimal("1"), status="active", created_at=NOW, updated_at=NOW,
        ))
        session.execute(models.cash_shifts.insert().values(
            id=SHIFT_ID, organization_id=organization_id, branch_id=BRANCH_A,
            register_code="CAJA-01", status="OPEN", opening_cash_cents=10_000,
            opened_at=NOW, closed_at=None, created_at=NOW,
        ))
        session.execute(models.purchase_documents.insert().values(
            id=purchase_id, organization_id=organization_id, branch_id=BRANCH_A,
            supplier_id=supplier_id, document_type="invoice", folio="SQLITE-RACE-001",
            document_date=NOW, subtotal=Decimal("1"), discount_total=Decimal("0"),
            tax_total=Decimal("0"), freight_total=Decimal("0"), total=Decimal("1"),
            payment_method="cash", paid_from_cash=True, cash_movement_id=None, evidence_url=None,
            notes=None, status="draft", created_by=ADMIN_USER_ID, confirmed_by=None,
            cancelled_by=None, confirmation_idempotency_key=None, cancellation_reason=None,
            created_at=NOW, confirmed_at=None, cancelled_at=None,
        ))
        session.execute(models.purchase_document_lines.insert().values(
            id="018f6f73-2d0a-74f0-8f1c-000000009974", purchase_document_id=purchase_id,
            presentation_id=presentation_id, item_id=item["id"],
            presentation_snapshot={"base_unit_id": item["base_unit_id"], "usable_content": "1"},
            presentation_quantity=Decimal("1"), base_quantity=Decimal("1"), unit_price=Decimal("1"),
            discount=Decimal("0"), tax=Decimal("0"), line_total=Decimal("1"),
            inventory_cost=Decimal("1"), cost_per_base_unit=Decimal("1"), created_at=NOW,
        ))
        session.commit()
    barrier = Barrier(2)

    def close() -> tuple[str, object]:
        with Session(engine) as session:
            barrier.wait()
            try:
                return "ok", close_cash_shift_operationally(
                    session, SHIFT_ID, "sqlite-purchase-operational-close", ADMIN_USER_ID
                )
            except BusinessError as exc:
                return "error", exc.code

    def confirm() -> tuple[str, object]:
        with Session(engine) as session:
            barrier.wait()
            try:
                return "ok", confirm_purchase_document(
                    session, purchase_id, "sqlite-purchase-race", "CAJA-01", ADMIN_USER_ID
                )
            except BusinessError as exc:
                return "error", exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        close_result, purchase_result = list(pool.map(lambda action: action(), (close, confirm)))
    assert close_result[0] == "ok"
    with Session(engine) as session:
        purchase = session.execute(sa.select(models.purchase_documents).where(
            models.purchase_documents.c.id == purchase_id
        )).mappings().one()
        cash_count = session.execute(
            sa.select(sa.func.count()).select_from(models.cash_movements).where(
                models.cash_movements.c.source_id == purchase_id
            )
        ).scalar_one()
        inventory_count = session.execute(
            sa.select(sa.func.count()).select_from(models.inventory_movements).where(
                models.inventory_movements.c.source_id == purchase_id
            )
        ).scalar_one()
    if purchase_result[0] == "ok":
        assert purchase["status"] == "confirmed"
        assert cash_count == 1 and inventory_count == 1
        assert close_result[1]["closure"]["summary_snapshot"]["expected_cash_cents"] == 9_900
    else:
        assert purchase_result[1] == "cash_shift_not_open"
        assert purchase["status"] == "draft"
        assert cash_count == 0 and inventory_count == 0
        assert close_result[1]["closure"]["summary_snapshot"]["expected_cash_cents"] == 10_000
    with Session(engine) as session:
        cut_count = session.execute(
            sa.select(sa.func.count()).select_from(models.cash_shift_cuts)
        ).scalar_one()
        assert cut_count == 0
    engine.dispose()


def test_cash_ledger_contracts_reject_extensions_and_validate_response() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schemas = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "schemas"
    command = json.loads((schemas / "cash-movement-command-v1.schema.json").read_text())
    compensation = json.loads(
        (schemas / "cash-compensation-command-v1.schema.json").read_text()
    )
    response = json.loads((schemas / "cash-movement-response-v1.schema.json").read_text())
    payload = _movement_payload("018f6f73-2d0a-74f0-8f1c-000000009100")
    command_validator = jsonschema.Draft202012Validator(command)
    command_validator.validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        command_validator.validate({**payload, "actor_user_id": "forbidden"})
    compensation_validator = jsonschema.Draft202012Validator(compensation)
    compensation_validator.validate(
        {"reason": "Error de captura", "evidence_refs": ["evidence://owner/1"]}
    )
    with pytest.raises(jsonschema.ValidationError):
        compensation_validator.validate(
            {"reason": "Error", "evidence_refs": ["evidence://owner/1"], "extra": True}
        )
    summary = {
        "opening_cash_cents": 0,
        "cash_payment_cents": 0,
        "deposit_cents": 0,
        "withdrawal_cents": 1,
        "excluded_movement_count": 0,
        "expected_cash_cents": -1,
    }
    jsonschema.Draft202012Validator(response).validate(
        {
            "movement": {
                "id": "movement",
                "organization_id": ORG_ID,
                "branch_id": BRANCH_A,
                "cash_shift_id": SHIFT_ID,
                "movement_type": "withdrawal",
                "amount_cents": 1,
                "reason_code": "MANUAL_WITHDRAWAL",
                "reason": "Retiro",
                "source_type": "manual",
                "source_id": None,
                "actor_user_id": CASHIER_ID,
                "status": "confirmed",
                "reversal_of_id": None,
                "concept_id": "concept",
                "concept_version_id": "version",
                "concept_snapshot": {
                    "concept_id": "concept",
                    "version_id": "version",
                    "code": "OPERATING_WITHDRAWAL",
                    "version": 1,
                    "name": "Retiro",
                    "allowed_movement_type": "withdrawal",
                    "requires_reference": True,
                    "requires_evidence": True,
                    "valid_from": "2026-08-12T00:00:00+00:00",
                },
                "reference": "FOLIO",
                "compensates_movement_id": None,
                "created_at": "2026-08-12T00:00:00+00:00",
            },
            "summary_at_commit": summary,
            "current_summary": summary,
        }
    )


def test_cash_movement_endpoint_matches_contract() -> None:
    client = _cash_concept_client()
    factory = client.app.state.test_session_factory
    with factory() as session:
        _grant_cash_permissions(session, "cash.movement.withdraw", "cash.movement.read")
        _insert_shift(session)
    concept_response = client.post(
        "/api/v1/cash/concepts",
        headers={"X-Actor-User-Id": OWNER_ID, "Idempotency-Key": "api-ledger-concept"},
        json=_concept_payload(),
    )
    assert concept_response.status_code == 200
    current_shift = client.get(
        "/api/v1/cash-shifts/current",
        headers={"X-Actor-User-Id": CASHIER_ID},
        params={"branch_id": BRANCH_A, "register_id": "CAJA-01"},
    )
    assert current_shift.status_code == 200
    assert current_shift.json()["cash_shift"]["id"] == SHIFT_ID
    movement_response = client.post(
        "/api/v1/cash/movements",
        headers={"X-Actor-User-Id": CASHIER_ID, "Idempotency-Key": "api-ledger-movement"},
        json=_movement_payload(concept_response.json()["id"]),
    )
    assert movement_response.status_code == 200
    assert "evidence_refs" not in movement_response.json()["movement"]
    ledger_response = client.get(
        "/api/v1/cash/movements",
        headers={"X-Actor-User-Id": CASHIER_ID},
        params={"branch_id": BRANCH_A, "register_id": "CAJA-01", "limit": 1},
    )
    assert ledger_response.status_code == 200
    assert ledger_response.json()["items"][0]["id"] == movement_response.json()["movement"]["id"]
    assert "idempotency_key" not in ledger_response.json()["items"][0]
    assert "evidence_refs" not in ledger_response.json()["items"][0]
    try:
        import jsonschema
    except ImportError:
        return
    schemas = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "schemas"
    response_schema = json.loads(
        (schemas / "cash-movement-response-v1.schema.json").read_text()
    )
    list_schema = json.loads((schemas / "cash-movement-list-v1.schema.json").read_text())
    jsonschema.Draft202012Validator(
        response_schema,
        format_checker=jsonschema.FormatChecker(),
    ).validate(movement_response.json())
    jsonschema.Draft202012Validator(
        list_schema,
        format_checker=jsonschema.FormatChecker(),
    ).validate(ledger_response.json())


def test_current_cash_shift_accepts_withdraw_only_and_legacy_read_only() -> None:
    client = _cash_concept_client()
    factory = client.app.state.test_session_factory
    with factory() as session:
        _grant_cash_permissions(
            session,
            "cash.movement.withdraw",
            "cash.shift.read",
        )
        _insert_shift(session)
        permission_ids = dict(
            session.execute(
                sa.select(models.permissions.c.code, models.permissions.c.id).where(
                    models.permissions.c.code.in_(
                        ["cash.movement.withdraw", "cash.shift.read"]
                    )
                )
            ).all()
        )
        session.execute(
            models.role_permissions.delete().where(
                models.role_permissions.c.role_id == CASHIER_ROLE_ID,
                models.role_permissions.c.permission_id == permission_ids["cash.shift.read"],
            )
        )
        session.commit()

    withdraw_only = client.get(
        "/api/v1/cash-shifts/current",
        headers={"X-Actor-User-Id": CASHIER_ID},
        params={"branch_id": BRANCH_A, "register_id": "CAJA-01"},
    )
    assert withdraw_only.status_code == 200

    with factory() as session:
        session.execute(
            models.role_permissions.delete().where(
                models.role_permissions.c.role_id == CASHIER_ROLE_ID,
                models.role_permissions.c.permission_id == permission_ids["cash.movement.withdraw"],
            )
        )
        session.execute(
            models.role_permissions.insert().values(
                role_id=CASHIER_ROLE_ID,
                permission_id=permission_ids["cash.shift.read"],
            )
        )
        session.commit()

    legacy_read_only = client.get(
        "/api/v1/cash-shifts/current",
        headers={"X-Actor-User-Id": CASHIER_ID},
        params={"branch_id": BRANCH_A, "register_id": "CAJA-01"},
    )
    assert legacy_read_only.status_code == 200
    assert legacy_read_only.json()["cash_shift"]["id"] == SHIFT_ID


def test_cash_movement_without_catalog_concept() -> None:
    client = _cash_concept_client()
    factory = client.app.state.test_session_factory
    with factory() as session:
        _grant_cash_permissions(session, "cash.movement.withdraw", "cash.movement.read")
        _insert_shift(session)

    response = client.post(
        "/api/v1/cash/movements",
        headers={
            "X-Actor-User-Id": CASHIER_ID,
            "Idempotency-Key": "key-no-catalog-concept-1",
        },
        json={
            "branch_id": BRANCH_A,
            "register_id": "CAJA-01",
            "movement_type": "withdrawal",
            "amount_cents": 1500,
            "concept": "Compra de verdura para cocina",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["movement"]["concept_id"] is None
    assert body["movement"]["reason"] == "Compra de verdura para cocina"
    assert body["movement"]["amount_cents"] == 1500
    assert body["movement"]["reference"] == "Compra de verdura para cocina"

    ledger_res = client.get(
        "/api/v1/cash/movements",
        headers={"X-Actor-User-Id": CASHIER_ID},
        params={"branch_id": BRANCH_A},
    )
    assert ledger_res.status_code == 200
    assert any(item["id"] == body["movement"]["id"] and item["concept_id"] is None for item in items)
