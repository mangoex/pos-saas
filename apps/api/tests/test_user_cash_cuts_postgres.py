"""TDD-TC-117 isolated PostgreSQL concurrency evidence for PCO-006."""
# ruff: noqa: E501

from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone
from pathlib import Path
from threading import Barrier
from urllib.parse import urlparse

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import BusinessError, UserCashCutService
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_cash_concepts import (
    BRANCH_A,
    CASHIER_ID,
    ORG_ID,
    OWNER_ID,
    OWNER_ROLE_ID,
    _seed_cash_concept_scope,
)
from test_cash_ledger import NOW, SHIFT_ID

ROOT = Path(__file__).resolve().parents[3]
API_DIR = ROOT / "apps" / "api"
TEST_URL_ENV = "PCO006_TEST_POSTGRES_URL"
CURRENT_TEST_REVISION = "0051_public_order_intents"
UTC = timezone.utc


def _postgres_url() -> str:
    """Never read DATABASE_URL; reject unsafe targets before any connection."""
    url = os.environ.get(TEST_URL_ENV)
    if not url:
        pytest.skip(f"{TEST_URL_ENV} is required for opt-in PostgreSQL tests")
    parsed = urlparse(url)
    database_name = parsed.path.lstrip("/")
    if not parsed.scheme.startswith("postgres"):
        raise RuntimeError("PCO-006 PostgreSQL tests require a PostgreSQL driver URL")
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("PCO-006 PostgreSQL tests require a local isolated database")
    if not database_name.startswith("pco006_"):
        raise RuntimeError("PCO-006 PostgreSQL tests require a pco006_* database")
    if "kiwi-postgres" in url.lower() or database_name == "restaurantos":
        raise RuntimeError("PCO-006 PostgreSQL tests reject protected database targets")
    return url


def test_tdd_tc_117_postgres_url_guard_and_alembic_head() -> None:
    url = _postgres_url()
    environment = {**os.environ, "RESTAURANTOS_DATABASE_URL": url}
    environment.pop("DATABASE_URL", None)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", CURRENT_TEST_REVISION],
        cwd=API_DIR, env=environment, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _postgres_engine() -> sa.Engine:
    url = _postgres_url()
    engine = create_engine(url, future=True)
    # The pco006_* target is guarded above and dedicated to this test module.
    with engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))
    environment = {**os.environ, "RESTAURANTOS_DATABASE_URL": url}
    environment.pop("DATABASE_URL", None)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=API_DIR, env=environment, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    with engine.begin() as connection:
        tables = connection.execute(
            sa.text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
            )
        ).scalars().all()
        if tables:
            preparer = connection.dialect.identifier_preparer
            quoted = ", ".join(preparer.quote(table) for table in tables)
            connection.execute(sa.text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))
    return engine


def _seed_counted_cut(engine: sa.Engine) -> str:
    end = NOW + timedelta(hours=1)
    with Session(engine) as session:
        _seed_cash_concept_scope(session)
        session.execute(models.permissions.insert(), [
            {"id": "pco006-create", "code": "cash.user_cut.create", "description": "create", "created_at": NOW},
            {"id": "pco006-read", "code": "cash.user_cut.read", "description": "read", "created_at": NOW},
        ])
        session.execute(models.role_permissions.insert(), [
            {"role_id": OWNER_ROLE_ID, "permission_id": "pco006-create"},
            {"role_id": OWNER_ROLE_ID, "permission_id": "pco006-read"},
        ])
        session.execute(models.cash_shifts.insert().values(
            id=SHIFT_ID, organization_id=ORG_ID, branch_id=BRANCH_A, register_code="CAJA-01",
            status="OPERATIVELY_CLOSED", opening_cash_cents=10_000,
            cashier_user_id=CASHIER_ID, opened_at=NOW, closed_at=end, created_at=NOW,
        ))
        session.execute(models.cash_shift_closures.insert().values(
            id="pco006-closure", organization_id=ORG_ID, branch_id=BRANCH_A,
            cash_shift_id=SHIFT_ID, register_code_snapshot="CAJA-01", closed_by_user_id=OWNER_ID,
            summary_snapshot={}, closed_at=end, created_at=end,
        ))
        session.commit()
        payload = {
            "branch_id": BRANCH_A, "register_id": "CAJA-01", "cash_shift_id": SHIFT_ID,
            "cashier_user_id": CASHIER_ID, "period_start": NOW.isoformat(),
            "period_end": end.isoformat(),
        }
        draft = UserCashCutService(session).create(payload, "pco006-pg-create", OWNER_ID)["cash_cut"]
        counted = UserCashCutService(session).counted_cash(
            draft["id"], {"counted_cash_cents": 10_000, "version": 1}, "pco006-pg-count", OWNER_ID,
        )["cash_cut"]
        return str(counted["id"])


def test_tdd_tc_117_finalize_race_has_one_winner_and_no_partial_write() -> None:
    engine = _postgres_engine()
    try:
        cut_id = _seed_counted_cut(engine)
        barrier = Barrier(2)

        def finalize(key: str) -> str:
            with Session(engine) as session:
                barrier.wait(timeout=10)
                try:
                    UserCashCutService(session).finalize(cut_id, {"version": 2}, key, OWNER_ID)
                    return "finalized"
                except BusinessError as exc:
                    return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(finalize, ("pco006-final-a", "pco006-final-b")))
        assert outcomes.count("finalized") == 1
        assert outcomes.count("cash_cut_transition_invalid") == 1
        with Session(engine) as session:
            cut = session.execute(sa.select(models.user_cash_cuts).where(models.user_cash_cuts.c.id == cut_id)).mappings().one()
            commands = session.execute(sa.select(sa.func.count()).select_from(models.user_cash_cut_commands).where(models.user_cash_cut_commands.c.command_type == "finalize")).scalar_one()
            assert cut["status"] == "FINALIZED"
            assert commands == 1
    finally:
        engine.dispose()


def test_tdd_tc_117_global_operation_association_is_one_winner_without_partial_rows() -> None:
    engine = _postgres_engine()
    try:
        cut_id = _seed_counted_cut(engine)
        with Session(engine) as session:
            session.execute(models.cash_shifts.insert().values(
                id="pco006-shift-two", organization_id=ORG_ID, branch_id=BRANCH_A,
                register_code="CAJA-02", status="OPERATIVELY_CLOSED", opening_cash_cents=0,
                cashier_user_id=CASHIER_ID, opened_at=NOW, closed_at=NOW + timedelta(hours=1), created_at=NOW,
            ))
            session.execute(models.user_cash_cuts.insert().values(
                id="pco006-second-cut", organization_id=ORG_ID, branch_id=BRANCH_A,
                cash_shift_id="pco006-shift-two", register_code_snapshot="CAJA-02",
                cashier_user_id=CASHIER_ID, timezone="timezone.utc", period_start=NOW,
                period_end=NOW + timedelta(hours=1), status="COUNTED", opening_cash_cents=0,
                cash_payment_cents=None, deposit_cents=None, withdrawal_cents=None,
                expected_cash_cents=None, counted_cash_cents=0, difference_cents=None,
                tolerance_cents=0, created_by_user_id=OWNER_ID, finalized_by_user_id=None,
                version=2, created_at=NOW, counted_at=NOW, finalized_at=None,
            ))
            session.commit()
        barrier = Barrier(2)

        def associate(target_cut_id: str) -> str:
            with Session(engine) as session:
                barrier.wait(timeout=10)
                try:
                    session.execute(models.user_cash_cut_operations.insert().values(
                        id="pco006-op-one" if target_cut_id == cut_id else "pco006-op-two",
                        organization_id=ORG_ID,
                        cash_cut_id=target_cut_id, operation_type="PAYMENT", operation_id="pco006-shared-payment",
                        signed_amount_cents=100, occurred_at=NOW,
                    ))
                    session.commit()
                    return "associated"
                except IntegrityError:
                    session.rollback()
                    return "cash_cut_operation_conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(associate, (cut_id, "pco006-second-cut")))
        assert outcomes.count("associated") == 1
        assert outcomes.count("cash_cut_operation_conflict") == 1
        with Session(engine) as session:
            count = session.execute(sa.select(sa.func.count()).select_from(models.user_cash_cut_operations).where(models.user_cash_cut_operations.c.operation_id == "pco006-shared-payment")).scalar_one()
            assert count == 1
    finally:
        engine.dispose()


def test_tdd_tc_117_finalize_maps_existing_operation_race_and_rolls_back() -> None:
    engine = _postgres_engine()
    try:
        cut_id = _seed_counted_cut(engine)
        with Session(engine) as session:
            session.execute(models.cash_movements.insert().values(
                id="pco006-race-movement", organization_id=ORG_ID, branch_id=BRANCH_A,
                cash_shift_id=SHIFT_ID, movement_type="deposit", amount_cents=100,
                reason_code="TEST", reason="test", source_type="manual", source_id=None,
                actor_user_id=OWNER_ID, idempotency_key="pco006-race-movement-key",
                status="confirmed", reversal_of_id=None, concept_id=None,
                concept_version_id=None, concept_snapshot=None, reference=None,
                evidence_refs=None, compensates_movement_id=None, created_at=NOW,
            ))
            session.execute(models.cash_shifts.insert().values(
                id="pco006-race-shift", organization_id=ORG_ID, branch_id=BRANCH_A,
                register_code="CAJA-02", status="OPERATIVELY_CLOSED", opening_cash_cents=0,
                cashier_user_id=CASHIER_ID, opened_at=NOW, closed_at=NOW + timedelta(hours=1), created_at=NOW,
            ))
            session.execute(models.user_cash_cuts.insert().values(
                id="pco006-race-other-cut", organization_id=ORG_ID, branch_id=BRANCH_A,
                cash_shift_id="pco006-race-shift", register_code_snapshot="CAJA-02",
                cashier_user_id=CASHIER_ID, timezone="timezone.utc", period_start=NOW,
                period_end=NOW + timedelta(hours=1), status="FINALIZED", opening_cash_cents=0,
                cash_payment_cents=0, deposit_cents=0, withdrawal_cents=0, expected_cash_cents=0,
                counted_cash_cents=0, difference_cents=0, tolerance_cents=0,
                created_by_user_id=OWNER_ID, finalized_by_user_id=OWNER_ID, version=3,
                created_at=NOW, counted_at=NOW, finalized_at=NOW,
            ))
            session.execute(models.user_cash_cut_operations.insert().values(
                id="pco006-race-occupied", organization_id=ORG_ID,
                cash_cut_id="pco006-race-other-cut", operation_type="MOVEMENT",
                operation_id="pco006-race-movement", signed_amount_cents=100, occurred_at=NOW,
            ))
            session.commit()
        with Session(engine) as session:
            with pytest.raises(BusinessError) as error:
                UserCashCutService(session).finalize(cut_id, {"version": 2}, "pco006-race-final", OWNER_ID)
            assert error.value.code == "cash_cut_operation_conflict"
        with Session(engine) as session:
            cut = session.execute(sa.select(models.user_cash_cuts).where(models.user_cash_cuts.c.id == cut_id)).mappings().one()
            commands = session.execute(sa.select(sa.func.count()).select_from(models.user_cash_cut_commands).where(models.user_cash_cut_commands.c.idempotency_key == "pco006-race-final")).scalar_one()
            associated = session.execute(sa.select(sa.func.count()).select_from(models.user_cash_cut_operations).where(models.user_cash_cut_operations.c.cash_cut_id == cut_id)).scalar_one()
            assert cut["status"] == "COUNTED"
            assert commands == 0
            assert associated == 0
    finally:
        engine.dispose()


def test_tdd_tc_117_global_idempotency_key_has_one_counted_winner() -> None:
    engine = _postgres_engine()
    try:
        first_cut = _seed_counted_cut(engine)
        end = NOW + timedelta(hours=1)
        with Session(engine) as session:
            session.execute(models.user_cash_cuts.update().where(models.user_cash_cuts.c.id == first_cut).values(status="DRAFT", counted_cash_cents=None, counted_at=None, version=1))
            session.execute(models.cash_shifts.insert().values(id="pco006-idem-shift", organization_id=ORG_ID, branch_id=BRANCH_A, register_code="CAJA-02", status="OPERATIVELY_CLOSED", opening_cash_cents=0, cashier_user_id=CASHIER_ID, opened_at=NOW, closed_at=end, created_at=NOW))
            session.execute(models.cash_shift_closures.insert().values(id="pco006-idem-close", organization_id=ORG_ID, branch_id=BRANCH_A, cash_shift_id="pco006-idem-shift", register_code_snapshot="CAJA-02", closed_by_user_id=OWNER_ID, summary_snapshot={}, closed_at=end, created_at=end))
            session.commit()
            second_cut = UserCashCutService(session).create({"branch_id": BRANCH_A, "register_id": "CAJA-02", "cash_shift_id": "pco006-idem-shift", "cashier_user_id": CASHIER_ID, "period_start": NOW.isoformat(), "period_end": end.isoformat()}, "pco006-idem-create", OWNER_ID)["cash_cut"]["id"]
        barrier = Barrier(2)

        def count(cut_id: str, amount: int) -> str:
            with Session(engine) as session:
                barrier.wait(timeout=10)
                try:
                    UserCashCutService(session).counted_cash(cut_id, {"counted_cash_cents": amount, "version": 1}, "pco006-same-key", OWNER_ID)
                    return "counted"
                except BusinessError as exc:
                    return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda args: count(*args), ((first_cut, 10_000), (second_cut, 0))))
        assert outcomes.count("counted") == 1
        assert outcomes.count("idempotency_conflict") == 1
        with Session(engine) as session:
            commands = session.execute(sa.select(sa.func.count()).select_from(models.user_cash_cut_commands).where(models.user_cash_cut_commands.c.idempotency_key == "pco006-same-key")).scalar_one()
            states = session.execute(sa.select(models.user_cash_cuts.c.status, models.user_cash_cuts.c.version).where(models.user_cash_cuts.c.id.in_((first_cut, second_cut)))).all()
            assert commands == 1
            assert sorted(states) == [("COUNTED", 2), ("DRAFT", 1)]
    finally:
        engine.dispose()
