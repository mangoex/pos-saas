"""Focused PCO-006 SQLite domain coverage (TDD-TC-113 through TDD-TC-116)."""
# ruff: noqa: E501

from __future__ import annotations

import json
import logging
from datetime import timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import AuthorizationError, BusinessError, UserCashCutService
from test_cash_concepts import OWNER_ID, OWNER_ROLE_ID, _cash_concept_client
from test_cash_ledger import BRANCH_A, CASHIER_ID, NOW, SHIFT_ID, _new_session


def _closed_shift(session, *, cashier: str | None = CASHIER_ID) -> dict[str, str]:
    session.execute(
        models.permissions.insert().values(
            id="permission-pco006-create",
            code="cash.user_cut.create",
            description="PCO-006 test permission",
            created_at=NOW,
        )
    )
    session.execute(
        models.role_permissions.insert().values(
            role_id=OWNER_ROLE_ID,
            permission_id="permission-pco006-create",
        )
    )
    end = NOW + timedelta(hours=1)
    session.execute(
        models.cash_shifts.update()
        .where(models.cash_shifts.c.id == SHIFT_ID)
        .values(status="OPERATIVELY_CLOSED", cashier_user_id=cashier, closed_at=end)
    )
    session.execute(
        models.cash_shift_closures.insert().values(
            id="closure-pco006",
            organization_id="018f6f73-2d0a-74f0-8f1c-000000000001",
            branch_id=BRANCH_A,
            cash_shift_id=SHIFT_ID,
            register_code_snapshot="CAJA-01",
            closed_by_user_id=OWNER_ID,
            summary_snapshot={},
            closed_at=end,
            created_at=end,
        )
    )
    session.commit()
    shift = (
        session.execute(sa.select(models.cash_shifts).where(models.cash_shifts.c.id == SHIFT_ID))
        .mappings()
        .one()
    )
    closure = (
        session.execute(
            sa.select(models.cash_shift_closures).where(
                models.cash_shift_closures.c.cash_shift_id == SHIFT_ID
            )
        )
        .mappings()
        .one()
    )
    start = shift["opened_at"].replace(tzinfo=NOW.tzinfo).isoformat()
    finish = closure["closed_at"].replace(tzinfo=NOW.tzinfo).isoformat()
    return {
        "branch_id": BRANCH_A,
        "register_id": "CAJA-01",
        "cash_shift_id": SHIFT_ID,
        "cashier_user_id": CASHIER_ID,
        "period_start": start,
        "period_end": finish,
    }


def test_tdd_tc_113_canonical_cashier_and_period() -> None:
    engine, session = _new_session()
    try:
        payload = _closed_shift(session, cashier=None)
        with pytest.raises(BusinessError, match="cashier"):
            UserCashCutService(session).create(payload, "tc113", OWNER_ID)
    finally:
        session.close()
        engine.dispose()


def test_tdd_tc_114_permission_is_real() -> None:
    engine, session = _new_session()
    try:
        payload = _closed_shift(session)
        with pytest.raises(AuthorizationError):
            UserCashCutService(session).create(payload, "tc114", CASHIER_ID)
    finally:
        session.close()
        engine.dispose()


def test_tdd_tc_115_lifecycle_and_python_difference() -> None:
    engine, session = _new_session()
    try:
        payload = _closed_shift(session)
        service = UserCashCutService(session)
        draft = service.create(payload, "tc115-create", OWNER_ID)["cash_cut"]
        counted = service.counted_cash(
            draft["id"], {"counted_cash_cents": 10_001, "version": 1}, "tc115-count", OWNER_ID
        )["cash_cut"]
        finalized = service.finalize(counted["id"], {"version": 2}, "tc115-finalize", OWNER_ID)[
            "cash_cut"
        ]
        assert finalized["expected_cash_cents"] == 10_000
        assert finalized["difference_cents"] == 1
    finally:
        session.close()
        engine.dispose()


def test_tdd_tc_116_replay_conflict_and_strict_payload() -> None:
    engine, session = _new_session()
    try:
        payload = _closed_shift(session)
        service = UserCashCutService(session)
        created = service.create(payload, "tc116-create", OWNER_ID)
        assert service.create(payload, "tc116-create", OWNER_ID) == created
        with pytest.raises(BusinessError) as conflict:
            service.create({**payload, "register_id": "OTHER"}, "tc116-create", OWNER_ID)
        assert conflict.value.code == "idempotency_conflict"
        with pytest.raises(BusinessError):
            service.counted_cash(
                created["cash_cut"]["id"],
                {"counted_cash_cents": True, "version": 1},
                "tc116-bool",
                OWNER_ID,
            )
    finally:
        session.close()
        engine.dispose()


def test_pco006_runtime_create_response_matches_contract() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = (
        Path(__file__).resolve().parents[3]
        / "packages/contracts/schemas/user-cash-cut-v1.schema.json"
    )
    validator = jsonschema.Draft202012Validator(json.loads(schema_path.read_text()))
    engine, session = _new_session()
    try:
        payload = _closed_shift(session)
        cut = UserCashCutService(session).create(payload, "contract-create", OWNER_ID)["cash_cut"]
        validator.validate(cut)
        for field in (
            "cash_payment_cents", "deposit_cents", "withdrawal_cents", "expected_cash_cents",
            "counted_cash_cents", "difference_cents", "counted_at", "finalized_at",
        ):
            invalid = {key: value for key, value in cut.items() if key != field}
            with pytest.raises(jsonschema.ValidationError):
                validator.validate(invalid)
    finally:
        session.close()
        engine.dispose()


def test_pco006_command_metrics_cover_success_replay_error_and_redact(caplog) -> None:
    engine, session = _new_session()
    try:
        payload = _closed_shift(session)
        caplog.set_level(logging.INFO, logger="restaurant_os.operations")
        service = UserCashCutService(session)
        created = service.create(payload, "metric-create", OWNER_ID)["cash_cut"]
        service.create(payload, "metric-create", OWNER_ID)
        counted = service.counted_cash(
            created["id"], {"counted_cash_cents": 10_000, "version": 1}, "metric-count", OWNER_ID
        )["cash_cut"]
        service.finalize(counted["id"], {"version": 2}, "metric-finalize", OWNER_ID)
        with pytest.raises(BusinessError):
            service.create({**payload, "period_end": "bad"}, "metric-error", OWNER_ID)
        records = [record for record in caplog.records if record.metric == "cash_cut_command_total"]
        assert [(record.action, record.result) for record in records] == [
            ("create", "success"), ("create", "replay"), ("count", "success"),
            ("finalize", "success"), ("create", "error"),
        ]
        assert records[-1].error_code == "cash_cut_period_invalid"
        rendered = " ".join(str(record.__dict__) for record in records)
        assert "metric-create" not in rendered
        assert "counted_cash_cents" not in rendered
    finally:
        session.close()
        engine.dispose()


def test_tdd_tc_118_http_cursor_is_forwarded_and_rejected_when_malformed() -> None:
    client = _cash_concept_client()
    try:
        with client.app.state.test_session_factory() as session:
            session.execute(
                models.permissions.insert().values(
                    id="permission-pco006-http-read",
                    code="cash.user_cut.read",
                    description="PCO-006 read",
                    created_at=NOW,
                )
            )
            session.execute(
                models.role_permissions.insert().values(
                    role_id=OWNER_ROLE_ID, permission_id="permission-pco006-http-read"
                )
            )
            session.commit()
        response = client.get(
            "/api/v1/cash/user-cuts",
            params={"branch_id": BRANCH_A, "cursor": "%not-base64%"},
            headers={"X-Actor-User-Id": OWNER_ID},
        )
        assert response.status_code == 409
        assert "cash_cut_scope_invalid" in str(response.json())
    finally:
        client.close()


def test_tdd_tc_119_http_reopen_decisions_reject_nonempty_bodies_without_side_effects() -> None:
    """Decision endpoints accept no body or {}, but never silently discard a body."""
    client = _cash_concept_client()
    try:
        with client.app.state.test_session_factory() as session:
            session.execute(
                models.permissions.insert().values(
                    id="permission-pco006-http-reopen-authorize",
                    code="cash.user_cut.reopen.authorize",
                    description="PCO-006 reopen authorization",
                    created_at=NOW,
                )
            )
            shifts = []
            cuts = []
            reopen_requests = []
            for index, status in enumerate(("REQUESTED", "REQUESTED", "APPROVED"), start=1):
                shift_id = f"pco006-http-shift-{index}"
                cut_id = f"pco006-http-cut-{index}"
                request_id = f"pco006-http-request-{index}"
                shifts.append(
                    {
                        "id": shift_id,
                        "organization_id": "018f6f73-2d0a-74f0-8f1c-000000000001",
                        "branch_id": BRANCH_A,
                        "register_code": f"HTTP-{index}",
                        "status": "OPERATIVELY_CLOSED",
                        "opening_cash_cents": 10_000,
                        "cashier_user_id": CASHIER_ID,
                        "opened_at": NOW,
                        "closed_at": NOW + timedelta(hours=1),
                        "created_at": NOW,
                    }
                )
                cuts.append(
                    {
                        "id": cut_id,
                        "organization_id": "018f6f73-2d0a-74f0-8f1c-000000000001",
                        "branch_id": BRANCH_A,
                        "cash_shift_id": shift_id,
                        "register_code_snapshot": f"HTTP-{index}",
                        "cashier_user_id": CASHIER_ID,
                        "timezone": "America/Mazatlan",
                        "period_start": NOW,
                        "period_end": NOW + timedelta(hours=1),
                        "status": "FINALIZED",
                        "opening_cash_cents": 10_000,
                        "cash_payment_cents": 0,
                        "deposit_cents": 0,
                        "withdrawal_cents": 0,
                        "expected_cash_cents": 10_000,
                        "counted_cash_cents": 10_001,
                        "difference_cents": 1,
                        "tolerance_cents": 0,
                        "created_by_user_id": OWNER_ID,
                        "finalized_by_user_id": OWNER_ID,
                        "version": 3,
                        "created_at": NOW,
                        "counted_at": NOW,
                        "finalized_at": NOW,
                    }
                )
                reopen_requests.append(
                    {
                        "id": request_id,
                        "organization_id": "018f6f73-2d0a-74f0-8f1c-000000000001",
                        "cash_cut_id": cut_id,
                        "proposed_counted_cash_cents": 10_002,
                        "reason": "Corrección HTTP",
                        "evidence_refs": ["evidence://pco006/http"],
                        "status": status,
                        "requested_by_user_id": OWNER_ID,
                        "decided_by_user_id": OWNER_ID if status == "APPROVED" else None,
                        "created_at": NOW,
                        "decided_at": NOW if status == "APPROVED" else None,
                    }
                )
            session.execute(models.cash_shifts.insert(), shifts)
            session.execute(models.user_cash_cuts.insert(), cuts)
            session.execute(models.user_cash_cut_reopen_requests.insert(), reopen_requests)
            session.commit()

        cases = (
            ("approve", "pco006-http-request-1", "REQUESTED", "reopen_approved"),
            ("reject", "pco006-http-request-2", "REQUESTED", "reopen_rejected"),
            ("compensate", "pco006-http-request-3", "APPROVED", "reopen_compensate"),
        )
        for endpoint, request_id, expected_status, command_type in cases:
            response = client.post(
                f"/api/v1/cash/user-cuts/reopen-requests/{request_id}/{endpoint}",
                headers={
                    "X-Actor-User-Id": OWNER_ID,
                    "Idempotency-Key": f"pco006-http-invalid-{endpoint}",
                },
                json={"unexpected": True},
            )
            assert response.status_code == 409
            assert response.json()["detail"]["code"] == "cash_cut_scope_invalid"
            with client.app.state.test_session_factory() as session:
                assert session.execute(
                    sa.select(models.user_cash_cut_reopen_requests.c.status).where(
                        models.user_cash_cut_reopen_requests.c.id == request_id
                    )
                ).scalar_one() == expected_status
                assert session.execute(
                    sa.select(sa.func.count()).select_from(models.user_cash_cut_commands).where(
                        models.user_cash_cut_commands.c.command_type == command_type
                    )
                ).scalar_one() == 0

        approved = client.post(
            "/api/v1/cash/user-cuts/reopen-requests/pco006-http-request-1/approve",
            headers={"X-Actor-User-Id": OWNER_ID, "Idempotency-Key": "pco006-http-approve"},
            json={},
        )
        assert approved.status_code == 200
        assert approved.json()["reopen_request"]["status"] == "APPROVED"

        rejected = client.post(
            "/api/v1/cash/user-cuts/reopen-requests/pco006-http-request-2/reject",
            headers={"X-Actor-User-Id": OWNER_ID, "Idempotency-Key": "pco006-http-reject"},
        )
        assert rejected.status_code == 200
        assert rejected.json()["reopen_request"]["status"] == "REJECTED"

        compensated = client.post(
            "/api/v1/cash/user-cuts/reopen-requests/pco006-http-request-3/compensate",
            headers={"X-Actor-User-Id": OWNER_ID, "Idempotency-Key": "pco006-http-compensate"},
            json={},
        )
        assert compensated.status_code == 200
        assert compensated.json()["compensation"]["reopen_request_id"] == "pco006-http-request-3"
    finally:
        client.close()


def test_tdd_tc_118_list_cursor_scope_and_redaction() -> None:
    engine, session = _new_session()
    try:
        session.execute(
            models.permissions.insert().values(
                id="permission-pco006-read",
                code="cash.user_cut.read",
                description="PCO-006 read",
                created_at=NOW,
            )
        )
        session.execute(
            models.role_permissions.insert().values(
                role_id=OWNER_ROLE_ID, permission_id="permission-pco006-read"
            )
        )
        for index in (1, 2):
            session.execute(
                models.user_cash_cuts.insert().values(
                    id=f"cut-{index}",
                    organization_id="018f6f73-2d0a-74f0-8f1c-000000000001",
                    branch_id=BRANCH_A,
                    cash_shift_id=f"shift-{index}",
                    register_code_snapshot="CAJA-01",
                    cashier_user_id=CASHIER_ID,
                    timezone="UTC",
                    period_start=NOW + timedelta(hours=index),
                    period_end=NOW + timedelta(hours=index + 1),
                    status="FINALIZED",
                    opening_cash_cents=0,
                    cash_payment_cents=0,
                    deposit_cents=0,
                    withdrawal_cents=0,
                    expected_cash_cents=0,
                    counted_cash_cents=0,
                    difference_cents=0,
                    tolerance_cents=0,
                    created_by_user_id=OWNER_ID,
                    finalized_by_user_id=OWNER_ID,
                    version=1,
                    created_at=NOW,
                    counted_at=NOW,
                    finalized_at=NOW,
                )
            )
        session.execute(
            models.user_cash_cut_operations.insert().values(
                id="operation-1",
                organization_id="018f6f73-2d0a-74f0-8f1c-000000000001",
                cash_cut_id="cut-1",
                operation_type="PAYMENT",
                operation_id="payment-1",
                signed_amount_cents=1,
                occurred_at=NOW,
            )
        )
        session.commit()
        service = UserCashCutService(session)
        first = service.list({"branch_id": BRANCH_A, "limit": 1}, OWNER_ID)
        second = service.list(
            {"branch_id": BRANCH_A, "limit": 1, "cursor": first["next_cursor"]}, OWNER_ID
        )
        assert first["items"][0]["id"] != second["items"][0]["id"]
        with pytest.raises(BusinessError):
            service.list(
                {"branch_id": BRANCH_A, "status": "FINALIZED", "cursor": first["next_cursor"]},
                OWNER_ID,
            )
        with pytest.raises(BusinessError, match="status"):
            service.list({"branch_id": BRANCH_A, "status": "UNKNOWN"}, OWNER_ID)
        with pytest.raises(BusinessError, match="range"):
            service.list(
                {
                    "branch_id": BRANCH_A,
                    "from_utc": (NOW + timedelta(hours=2)).isoformat(),
                    "to_utc": NOW.isoformat(),
                },
                OWNER_ID,
            )
        detail = service.detail("cut-1", OWNER_ID)
        assert detail["operations"][0]["operation_id"] == "payment-1"
        assert {"reason", "evidence_refs", "idempotency_key", "request_hash"}.isdisjoint(
            str(detail)
        )
    finally:
        session.close()
        engine.dispose()


def test_tdd_tc_119_reopen_compensation_is_append_only() -> None:
    engine, session = _new_session()
    try:
        payload = _closed_shift(session)
        for code in ("cash.user_cut.reopen.request", "cash.user_cut.reopen.authorize"):
            permission_id = "permission-" + code
            session.execute(
                models.permissions.insert().values(
                    id=permission_id, code=code, description=code, created_at=NOW
                )
            )
            session.execute(
                models.role_permissions.insert().values(
                    role_id=OWNER_ROLE_ID, permission_id=permission_id
                )
            )
        session.commit()
        service = UserCashCutService(session)
        draft = service.create(payload, "tc119-create", OWNER_ID)["cash_cut"]
        counted = service.counted_cash(
            draft["id"], {"counted_cash_cents": 10_001, "version": 1}, "tc119-count", OWNER_ID
        )["cash_cut"]
        finalized = service.finalize(counted["id"], {"version": 2}, "tc119-final", OWNER_ID)[
            "cash_cut"
        ]
        before = dict(
            session.execute(
                sa.select(models.user_cash_cuts).where(
                    models.user_cash_cuts.c.id == finalized["id"]
                )
            )
            .mappings()
            .one()
        )
        request_payload = {
            "counted_cash_cents": 10_002,
            "reason": "private",
            "evidence_refs": ["private://evidence"],
        }
        request = service.request_reopen(
            finalized["id"], request_payload, "tc119-request", OWNER_ID
        )
        assert (
            service.request_reopen(finalized["id"], request_payload, "tc119-request", OWNER_ID)
            == request
        )
        with pytest.raises(BusinessError):
            service.request_reopen(finalized["id"], request_payload, "tc119-other", OWNER_ID)
        approved = service.decide_reopen(
            request["reopen_request"]["id"], "APPROVED", "tc119-approve", OWNER_ID
        )
        compensation = service.compensate_reopen(
            approved["reopen_request"]["id"], "tc119-compensate", OWNER_ID
        )
        assert compensation["compensation"]["corrected_difference_cents"] == 2
        assert (
            dict(
                session.execute(
                    sa.select(models.user_cash_cuts).where(
                        models.user_cash_cuts.c.id == finalized["id"]
                    )
                )
                .mappings()
                .one()
            )
            == before
        )
    finally:
        session.close()
        engine.dispose()


def test_pco006_runtime_list_detail_reopen_and_compensation_match_contracts() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    referencing = pytest.importorskip("referencing")
    schema_dir = Path(__file__).resolve().parents[3] / "packages/contracts/schemas"
    names = (
        "user-cash-cut-v1.schema.json",
        "user-cash-cut-list-v1.schema.json",
        "user-cash-cut-detail-v1.schema.json",
        "user-cash-cut-reopen-response-v1.schema.json",
        "user-cash-cut-compensation-response-v1.schema.json",
    )
    schemas = [json.loads((schema_dir / name).read_text()) for name in names]
    registry = referencing.Registry().with_resources(
        (schema["$id"], referencing.Resource.from_contents(schema)) for schema in schemas
    )
    validators = {
        schema["$id"].rsplit("/", 1)[-1]: jsonschema.Draft202012Validator(schema, registry=registry)
        for schema in schemas
    }
    engine, session = _new_session()
    try:
        payload = _closed_shift(session)
        for code in ("cash.user_cut.read", "cash.user_cut.reopen.request", "cash.user_cut.reopen.authorize"):
            permission_id = f"contract-{code}"
            session.execute(models.permissions.insert().values(id=permission_id, code=code, description=code, created_at=NOW))
            session.execute(models.role_permissions.insert().values(role_id=OWNER_ROLE_ID, permission_id=permission_id))
        session.commit()
        service = UserCashCutService(session)
        draft = service.create(payload, "contract-all-create", OWNER_ID)["cash_cut"]
        counted = service.counted_cash(draft["id"], {"counted_cash_cents": 10_000, "version": 1}, "contract-all-count", OWNER_ID)["cash_cut"]
        finalized = service.finalize(counted["id"], {"version": 2}, "contract-all-final", OWNER_ID)["cash_cut"]
        listed = service.list({"branch_id": BRANCH_A}, OWNER_ID)
        detailed = service.detail(finalized["id"], OWNER_ID)
        request = service.request_reopen(finalized["id"], {"counted_cash_cents": 10_001, "reason": "Corrección", "evidence_refs": ["evidence://one"]}, "contract-all-request", OWNER_ID)
        approved = service.decide_reopen(request["reopen_request"]["id"], "APPROVED", "contract-all-approve", OWNER_ID)
        compensated = service.compensate_reopen(approved["reopen_request"]["id"], "contract-all-compensate", OWNER_ID)
        validators["user-cash-cut-list-v1.schema.json"].validate(listed)
        validators["user-cash-cut-detail-v1.schema.json"].validate(detailed)
        validators["user-cash-cut-reopen-response-v1.schema.json"].validate(request)
        validators["user-cash-cut-reopen-response-v1.schema.json"].validate(approved)
        validators["user-cash-cut-compensation-response-v1.schema.json"].validate(compensated)
    finally:
        session.close()
        engine.dispose()
