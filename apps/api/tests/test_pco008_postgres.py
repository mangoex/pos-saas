"""Opt-in PostgreSQL gate for PCO-008; never reads DATABASE_URL."""

from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier
from urllib.parse import urlparse

import pytest
import sqlalchemy as sa
from restaurant_os import models, operations
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from test_cash_concepts import (
    BRANCH_A,
    BRANCH_B,
    CASHIER_ROLE_ID,
    ORG_ID,
    OWNER_ID,
    _seed_cash_concept_scope,
)

ROOT = Path(__file__).resolve().parents[3]
API_DIR = ROOT / "apps" / "api"
TEST_URL_ENV = "PCO008_TEST_POSTGRES_URL"
REVISION_0052 = "0052_pos_handoff_and_idempotency"
REVISION_0053 = "0053_cash_offline_sync"
UTC = timezone.utc
DEVICE_A = "018f6f73-2d0a-74f0-8f1c-000000000401"
DEVICE_B = "018f6f73-2d0a-74f0-8f1c-000000000402"


def _postgres_url() -> str:
    url = os.environ.get(TEST_URL_ENV)
    if not url:
        pytest.skip(f"{TEST_URL_ENV} is required for opt-in PostgreSQL tests")
    parsed = urlparse(url)
    database_name = parsed.path.lstrip("/")
    if not parsed.scheme.startswith("postgres"):
        raise RuntimeError("PCO-008 tests require a PostgreSQL driver URL")
    if parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise RuntimeError("PCO-008 tests require a local isolated database")
    if not database_name.startswith("pco008_") or database_name in {
        "restaurantos",
        "kiwi-postgres",
    }:
        raise RuntimeError("PCO-008 tests reject protected database targets")
    return url


def _alembic(url: str, action: str, revision: str) -> None:
    environment = {**os.environ, "RESTAURANTOS_DATABASE_URL": url}
    environment.pop("DATABASE_URL", None)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", action, revision],
        cwd=API_DIR,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _reset_schema(url: str) -> None:
    engine = create_engine(url, future=True)
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("DROP SCHEMA public CASCADE"))
            connection.execute(sa.text("CREATE SCHEMA public"))
    finally:
        engine.dispose()


def _postgres_engine() -> sa.Engine:
    url = _postgres_url()
    _reset_schema(url)
    # Current runtime guards require the current schema; the dedicated migration
    # test below still exercises the historical 0052/0053 roundtrip.
    _alembic(url, "upgrade", "head")
    engine = create_engine(url, future=True)
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


def _seed_sync_scope(engine: sa.Engine) -> tuple[datetime, str]:
    concept_id = "018f6f73-2d0a-74f0-8f1c-000000009501"
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        _seed_cash_concept_scope(session)
        permission_id = "018f6f73-2d0a-74f0-8f1c-000000009502"
        session.execute(
            models.permissions.insert().values(
                id=permission_id,
                code="cash.movement.deposit",
                description="PCO-008",
                created_at=now,
            )
        )
        session.execute(
            models.role_permissions.insert().values(
                role_id=CASHIER_ROLE_ID, permission_id=permission_id
            )
        )
        session.execute(
            models.cash_movement_concepts.insert().values(
                id=concept_id,
                organization_id=ORG_ID,
                code="PCO008_DEPOSIT",
                status="active",
                created_by_user_id=OWNER_ID,
                created_at=now,
                archived_at=None,
            )
        )
        session.execute(
            models.cash_movement_concept_versions.insert().values(
                id="018f6f73-2d0a-74f0-8f1c-000000009503",
                concept_id=concept_id,
                version=1,
                name="PCO-008 Deposit",
                allowed_movement_type="deposit",
                requires_reference=True,
                requires_evidence=True,
                valid_from=now,
                created_by_user_id=OWNER_ID,
                created_at=now,
            )
        )
        session.execute(
            models.cash_shifts.insert(),
            [
                {
                    "id": "pco008-shift-a",
                    "organization_id": ORG_ID,
                    "branch_id": BRANCH_A,
                    "register_code": "CAJA-01",
                    "status": "OPEN",
                    "opening_cash_cents": 1_000,
                    "opened_at": now,
                    "closed_at": None,
                    "created_at": now,
                },
                {
                    "id": "pco008-shift-b",
                    "organization_id": ORG_ID,
                    "branch_id": BRANCH_B,
                    "register_code": "CAJA-02",
                    "status": "OPEN",
                    "opening_cash_cents": 1_000,
                    "opened_at": now,
                    "closed_at": None,
                    "created_at": now,
                },
            ],
        )
        session.commit()
    return now, concept_id


def _envelope(
    now: datetime,
    concept_id: str,
    suffix: int,
    branch_id: str,
    device_id: str,
    register_code: str,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "command_id": f"018f6f73-2d0a-74f0-8f1c-{suffix:012d}",
        "idempotency_key": f"pco008-postgres-command-{suffix}",
        "organization_id": ORG_ID,
        "branch_id": branch_id,
        "source_device_id": device_id,
        "actor_user_id": OWNER_ID,
        "command_type": "cash.movement.create.v1",
        "occurred_at": now.isoformat(),
        "accepted_at": now.isoformat(),
        "offline_grant": "synthetic.offline.grant.for.postgres",
        "payload": {
            "register_id": register_code,
            "movement_type": "deposit",
            "concept_id": concept_id,
            "amount_cents": 100 * suffix,
            "reference": f"PCO008-PG-{suffix}",
            "evidence_refs": [f"synthetic-pco008-{suffix}"],
        },
    }


def test_tc136_postgres_migration_roundtrip_and_head() -> None:
    url = _postgres_url()
    _reset_schema(url)
    _alembic(url, "upgrade", REVISION_0052)
    _alembic(url, "upgrade", REVISION_0053)
    _alembic(url, "downgrade", REVISION_0052)
    _alembic(url, "upgrade", REVISION_0053)
    engine = create_engine(url, future=True)
    try:
        with engine.connect() as connection:
            assert (
                connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
                == REVISION_0053
            )
    finally:
        engine.dispose()


def test_tc134_postgres_serializes_branch_checkpoints() -> None:
    engine = _postgres_engine()
    try:
        now, concept_id = _seed_sync_scope(engine)
        barrier = Barrier(3)
        cases = (
            (1, BRANCH_A, DEVICE_A, "CAJA-01"),
            (2, BRANCH_A, DEVICE_A, "CAJA-01"),
            (3, BRANCH_B, DEVICE_B, "CAJA-02"),
        )

        def worker(case: tuple[int, str, str, str]) -> dict[str, object]:
            suffix, branch_id, device_id, register = case
            with Session(engine) as session:
                barrier.wait(timeout=10)
                return operations.receive_sync_command(
                    session,
                    _envelope(now, concept_id, suffix, branch_id, device_id, register),
                    actor_device_id=device_id,
                    grant_verifier=lambda _command: None,
                )

        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(worker, cases))
        assert {result["status"] for result in results} == {"CONFIRMED"}, results
        assert {results[index]["checkpoint"] for index in (0, 1)} == {1, 2}
        assert results[2]["checkpoint"] == 1
        with Session(engine) as session:
            checkpoints = dict(
                session.execute(
                    sa.select(
                        models.sync_branch_checkpoints.c.branch_id,
                        models.sync_branch_checkpoints.c.last_checkpoint,
                    )
                ).all()
            )
            assert checkpoints == {BRANCH_A: 2, BRANCH_B: 1}
            for table in (
                models.cash_movements,
                models.cash_movement_commands,
                models.sync_commands,
                models.sync_events,
            ):
                assert (
                    session.execute(sa.select(sa.func.count()).select_from(table)).scalar_one() == 3
                )

        replay_barrier = Barrier(2)
        repeated = _envelope(now, concept_id, 4, BRANCH_A, DEVICE_A, "CAJA-01")

        def replay_worker(_case: int) -> dict[str, object]:
            with Session(engine) as session:
                replay_barrier.wait(timeout=10)
                return operations.receive_sync_command(
                    session,
                    repeated,
                    actor_device_id=DEVICE_A,
                    grant_verifier=lambda _command: None,
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            replay_results = list(pool.map(replay_worker, range(2)))
        assert {result["status"] for result in replay_results} == {"CONFIRMED"}
        assert {result["checkpoint"] for result in replay_results} == {3}
        assert sum(bool(result["replayed"]) for result in replay_results) == 1
        with Session(engine) as session:
            assert (
                session.execute(
                    sa.select(models.sync_branch_checkpoints.c.last_checkpoint).where(
                        models.sync_branch_checkpoints.c.organization_id == ORG_ID,
                        models.sync_branch_checkpoints.c.branch_id == BRANCH_A,
                    )
                ).scalar_one()
                == 3
            )
            for table in (
                models.cash_movements,
                models.cash_movement_commands,
                models.sync_commands,
                models.sync_events,
            ):
                assert (
                    session.execute(sa.select(sa.func.count()).select_from(table)).scalar_one() == 4
                )
    finally:
        engine.dispose()
