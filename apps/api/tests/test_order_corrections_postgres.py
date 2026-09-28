"""TDD-TC-108: opt-in PostgreSQL races for PCO-005B corrections.

This module deliberately never falls back to ``DATABASE_URL``.  It is safe to
collect in every environment; the actual database races require a locally
provisioned database named ``pco005b_*``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from urllib.parse import urlparse

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import (
    BusinessError,
    apply_order_reopen_request,
    close_cash_shift_operationally,
    create_order_reopen_request,
    decide_order_reopen_request,
)
from sqlalchemy.orm import Session
from test_cash_concepts import OWNER_ID, _seed_cash_concept_scope
from test_cash_ledger import BRANCH_A, NOW, ORG_ID, SHIFT_ID, _insert_shift
from test_order_reopen_workflow import CHIEF_ID, _actors, _order

ROOT = Path(__file__).resolve().parents[3]
API_DIR = ROOT / "apps" / "api"
TEST_URL_ENV = "PCO005B_TEST_POSTGRES_URL"
REVISION_0040 = "0040_order_corrections"


def _postgres_url() -> str:
    """Read only the explicit opt-in URL and reject every protected target."""
    url = os.environ.get(TEST_URL_ENV)
    if not url:
        pytest.skip(f"{TEST_URL_ENV} is required for opt-in PostgreSQL tests")
    parsed = urlparse(url)
    database_name = parsed.path.lstrip("/")
    if not parsed.scheme.startswith("postgres"):
        raise RuntimeError("PCO-005B PostgreSQL tests require a PostgreSQL driver URL")
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("PCO-005B PostgreSQL tests require a local isolated database")
    if not database_name.startswith("pco005b_"):
        raise RuntimeError("PCO-005B PostgreSQL tests require a pco005b_* database")
    if "kiwi-postgres" in url.lower() or database_name == "restaurantos":
        raise RuntimeError("PCO-005B PostgreSQL tests reject protected database targets")
    return url


def _alembic(url: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "RESTAURANTOS_DATABASE_URL": url}
    environment.pop("DATABASE_URL", None)
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *arguments],
        cwd=API_DIR,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _truncate_isolated_database(engine: sa.Engine) -> None:
    """Clear only the already validated PCO-005B fixture database."""
    with engine.begin() as connection:
        tables = sa.inspect(connection).get_table_names(schema="public")
        required = {
            "orders", "order_reopen_requests", "order_corrections", "order_correction_lines",
            "order_payment_adjustments", "order_production_adjustments", "audit_events",
        }
        assert required.issubset(tables), "PCO-005B migrated tables are missing"
        preparer = connection.dialect.identifier_preparer
        table_names = ", ".join(
            f'public.{preparer.quote(table)}' for table in tables if table != "alembic_version"
        )
        connection.execute(sa.text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))


def _reset_isolated_schema(url: str) -> None:
    """Start a historical roundtrip without crossing later forward-only revisions."""
    engine = sa.create_engine(url, future=True)
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("DROP SCHEMA public CASCADE"))
            connection.execute(sa.text("CREATE SCHEMA public"))
    finally:
        engine.dispose()


@pytest.fixture()
def postgres_engine() -> sa.Engine:
    url = _postgres_url()
    upgraded = _alembic(url, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr
    engine = sa.create_engine(url, pool_pre_ping=True, pool_size=4, max_overflow=0)

    @sa.event.listens_for(engine, "connect")
    def configure_postgres_timeouts(dbapi_connection: object, _: object) -> None:
        """Bound real races at the driver connection, including blocked locks."""
        cursor = dbapi_connection.cursor()  # type: ignore[union-attr]
        try:
            cursor.execute("SET lock_timeout = '5s'")
            cursor.execute("SET statement_timeout = '15s'")
        finally:
            cursor.close()
        dbapi_connection.commit()  # type: ignore[union-attr]
    try:
        _truncate_isolated_database(engine)
        yield engine
    finally:
        _truncate_isolated_database(engine)
        engine.dispose()


def _approved_cash_refund_request(engine: sa.Engine, number: int) -> tuple[str, dict[str, object]]:
    """Create a paid closed order with the snapshot required by PCO-005B."""
    with Session(engine) as session:
        _seed_cash_concept_scope(session)
        session.execute(
            models.permissions.insert().values(
                id="018f6f73-2d0a-74f0-8f1c-000000009540",
                code="cash.shift.close",
                description="Cerrar turno de caja",
                created_at=NOW,
            )
        )
        _actors(session)
        _insert_shift(session)
        order_id = _order(session, number)
        payment_id = session.execute(
            sa.select(models.payments.c.id).where(models.payments.c.order_id == order_id)
        ).scalar_one()
        snapshot_id = f"018f6f73-2d0a-74f0-8f1c-{9800 + number:012d}"
        session.execute(
            models.sales_operation_snapshots.insert().values(
                id=snapshot_id,
                organization_id=ORG_ID,
                branch_id=BRANCH_A,
                payment_id=payment_id,
                order_id=order_id,
                cash_shift_id=SHIFT_ID,
                register_code_snapshot="CAJA-01",
                folio_snapshot=f"PCO005B-PG-{number}",
                service_type_snapshot="takeout",
                currency="MXN",
                gross_cents=500,
                net_cents=500,
                discount_cents=0,
                courtesy_cents=0,
                tax_cents=0,
                quality_status="captured",
                confirmed_at=NOW,
                created_at=NOW,
            )
        )
        session.commit()
        request = create_order_reopen_request(
            session,
            order_id,
            {"reason": "Corrección PostgreSQL concurrente", "evidence_refs": ["pg:005b"]},
            f"pco005b-pg-request-{number}",
            CHIEF_ID,
        )
        decide_order_reopen_request(
            session,
            request["id"],
            "APPROVED",
            {"decision_reason": "Dueño aprueba carrera PostgreSQL"},
            f"pco005b-pg-approve-{number}",
            OWNER_ID,
        )
        return order_id, request


def _refund_plan() -> dict[str, object]:
    return {
        "expected_order_version": 1,
        "lines": [],
        "production_dispositions": [],
        "settlement_method": "cash",
        "settlement_evidence_refs": [],
        "register_id": "CAJA-01",
    }


def _run_race(*actions: object) -> list[tuple[str, object]]:
    barrier = Barrier(len(actions))

    def run(action: object) -> tuple[str, object]:
        assert callable(action)
        barrier.wait(timeout=15)
        try:
            return "ok", action()
        except BusinessError as error:
            return "error", error.code

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        return list(pool.map(run, actions))


def _configure_race_timeout(session: Session) -> None:
    """Fail the gate rather than leave a PostgreSQL lock race hanging."""
    session.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    session.execute(sa.text("SET LOCAL statement_timeout = '10s'"))


def test_postgres_race_does_not_normalize_operational_errors() -> None:
    """A timeout/deadlock driver error must fail the gate, never look like a domain result."""
    with pytest.raises(sa.exc.OperationalError):
        _run_race(lambda: (_ for _ in ()).throw(
            sa.exc.OperationalError("SET LOCAL statement_timeout", {}, RuntimeError("timeout"))
        ))


def test_postgres_apply_race_has_one_correction_and_one_applied_request(
    postgres_engine: sa.Engine,
) -> None:
    """Different keys cannot turn one approved request into two corrections."""
    _, request = _approved_cash_refund_request(postgres_engine, 1)

    def apply(key: str) -> object:
        with Session(postgres_engine) as session:
            _configure_race_timeout(session)
            return apply_order_reopen_request(
                session, str(request["id"]), _refund_plan(), key, OWNER_ID
            )

    outcomes = _run_race(
        lambda: apply("pco005b-pg-apply-race-a"),
        lambda: apply("pco005b-pg-apply-race-b"),
    )
    assert sorted(state for state, _ in outcomes) == ["error", "ok"]
    assert [value for state, value in outcomes if state == "error"] == [
        "order_reopen_transition_invalid"
    ]
    with Session(postgres_engine) as session:
        assert session.execute(
            sa.select(sa.func.count()).select_from(models.order_corrections).where(
                models.order_corrections.c.request_id == request["id"]
            )
        ).scalar_one() == 1
        assert session.execute(
            sa.select(models.order_reopen_requests.c.status).where(
                models.order_reopen_requests.c.id == request["id"]
            )
        ).scalar_one() == "APPLIED"
        assert session.execute(
            sa.select(sa.func.count()).select_from(models.order_payment_adjustments)
        ).scalar_one() == 1
        assert session.execute(
            sa.select(sa.func.count()).select_from(models.cash_movements).where(
                models.cash_movements.c.source_type == "order_correction"
            )
        ).scalar_one() == 1


def test_postgres_apply_vs_operational_close_is_serializable(
    postgres_engine: sa.Engine,
) -> None:
    """Close wins cleanly or records the one correction movement in its summary."""
    _, request = _approved_cash_refund_request(postgres_engine, 2)

    def apply() -> object:
        with Session(postgres_engine) as session:
            _configure_race_timeout(session)
            return apply_order_reopen_request(
                session, str(request["id"]), _refund_plan(), "pco005b-pg-close-apply", OWNER_ID
            )

    def close() -> object:
        with Session(postgres_engine) as session:
            _configure_race_timeout(session)
            return close_cash_shift_operationally(
                session, SHIFT_ID, "pco005b-pg-close", OWNER_ID
            )

    apply_result, close_result = _run_race(apply, close)
    assert close_result[0] == "ok"
    with Session(postgres_engine) as session:
        movements = session.execute(
            sa.select(models.cash_movements).where(
                models.cash_movements.c.source_type == "order_correction"
            )
        ).mappings().all()
        status = session.execute(
            sa.select(models.order_reopen_requests.c.status).where(
                models.order_reopen_requests.c.id == request["id"]
            )
        ).scalar_one()
        closure = session.execute(
            sa.select(models.cash_shift_closures.c.summary_snapshot).where(
                models.cash_shift_closures.c.cash_shift_id == SHIFT_ID
            )
        ).scalar_one()
    if apply_result[0] == "ok":
        assert len(movements) == 1
        assert status == "APPLIED"
        assert closure["withdrawal_cents"] == 500
    else:
        assert apply_result == ("error", "cash_shift_not_open")
        assert movements == []
        assert status == "APPROVED"
        assert closure["withdrawal_cents"] == 0


def test_postgres_apply_vs_order_version_never_applies_a_stale_plan(
    postgres_engine: sa.Engine,
) -> None:
    """Whichever transaction wins, apply never writes from an obsolete version."""
    order_id, request = _approved_cash_refund_request(postgres_engine, 3)

    def apply() -> object:
        with Session(postgres_engine) as session:
            _configure_race_timeout(session)
            return apply_order_reopen_request(
                session, str(request["id"]), _refund_plan(), "pco005b-pg-version-apply", OWNER_ID
            )

    def update_version() -> object:
        with Session(postgres_engine) as session:
            _configure_race_timeout(session)
            session.execute(
                models.orders.update().where(models.orders.c.id == order_id).values(version=2)
            )
            session.commit()
            return "version_updated"

    apply_result, version_result = _run_race(apply, update_version)
    assert version_result == ("ok", "version_updated")
    with Session(postgres_engine) as session:
        correction_count = session.execute(
            sa.select(sa.func.count()).select_from(models.order_corrections).where(
                models.order_corrections.c.request_id == request["id"]
            )
        ).scalar_one()
        status = session.execute(
            sa.select(models.order_reopen_requests.c.status).where(
                models.order_reopen_requests.c.id == request["id"]
            )
        ).scalar_one()
    if apply_result[0] == "ok":
        assert correction_count == 1
        assert status == "APPLIED"
    else:
        assert apply_result == ("error", "order_version_conflict")
        assert correction_count == 0
        assert status == "APPROVED"


def test_postgres_pco005b_constraints_and_indexes_are_present(
    postgres_engine: sa.Engine,
) -> None:
    inspector = sa.inspect(postgres_engine)
    correction_indexes = {item["name"] for item in inspector.get_indexes("order_corrections")}
    correction_uniques = {
        item["name"] for item in inspector.get_unique_constraints("order_corrections")
    }
    payment_uniques = {
        item["name"] for item in inspector.get_unique_constraints("order_payment_adjustments")
    }
    assert "ix_order_corrections_org_branch_applied" in correction_indexes
    assert any("request" in str(name) for name in correction_uniques)
    assert any("correction" in str(name) for name in payment_uniques)
    with postgres_engine.connect() as connection:
        constraints = set(
            connection.execute(
                sa.text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = 'order_corrections'::regclass"
                )
            ).scalars()
        )
    assert {"ck_order_corrections_versions", "ck_order_corrections_status"} <= constraints


class _NoDatabaseUrlEnvironment(dict[str, str]):
    def get(self, key: str, default: str | None = None) -> str | None:
        if key == "DATABASE_URL":
            raise AssertionError("PCO-005B PostgreSQL tests must never read DATABASE_URL")
        return super().get(key, default)


def test_postgres_target_safety_never_reads_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = _NoDatabaseUrlEnvironment()
    monkeypatch.setattr(os, "environ", environment)
    with pytest.raises(pytest.skip.Exception):
        _postgres_url()
    for url in (
        "postgresql://user:pass@remote.example/pco005b_isolated",
        "postgresql://user:pass@localhost/not_pco005b",
        "postgresql://user:pass@localhost/restaurantos",
        "sqlite:///pco005b_isolated",
    ):
        environment[TEST_URL_ENV] = url
        with pytest.raises(RuntimeError):
            _postgres_url()
    environment[TEST_URL_ENV] = "postgresql://user:pass@localhost/pco005b_isolated"
    assert _postgres_url() == environment[TEST_URL_ENV]


def test_postgres_pco005b_0039_0040_empty_roundtrip_is_opt_in() -> None:
    url = _postgres_url()
    _reset_isolated_schema(url)
    baseline = _alembic(url, "upgrade", "0039_order_reopen_requests")
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr
    upgraded = _alembic(url, "upgrade", REVISION_0040)
    assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr
    downgraded = _alembic(url, "downgrade", "0039_order_reopen_requests")
    assert downgraded.returncode == 0, downgraded.stdout + downgraded.stderr
    reupgraded = _alembic(url, "upgrade", REVISION_0040)
    assert reupgraded.returncode == 0, reupgraded.stdout + reupgraded.stderr
