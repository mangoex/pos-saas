"""Opt-in PCO-005A PostgreSQL verification; never reads DATABASE_URL."""

from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from urllib.parse import urlparse
from uuid import uuid4

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import (
    BusinessError,
    create_order_reopen_request,
    decide_order_reopen_request,
)
from sqlalchemy.orm import Session
from test_cash_concepts import OWNER_ID, _seed_cash_concept_scope
from test_cash_ledger import BRANCH_A, NOW, ORG_ID, SHIFT_ID
from test_order_reopen_workflow import CHIEF_ID, _actors, _order

ROOT = Path(__file__).resolve().parents[3]
API_DIR = ROOT / "apps" / "api"
TEST_URL_ENV = "PCO005_TEST_POSTGRES_URL"
ALLOW_REMOTE_ENV = "PCO005_TEST_POSTGRES_ALLOW_REMOTE"


def _postgres_url() -> str:
    url = os.environ.get(TEST_URL_ENV)
    if not url:
        pytest.skip(f"{TEST_URL_ENV} is required for opt-in PostgreSQL tests")
    parsed = urlparse(url)
    database_name = parsed.path.lstrip("/")
    lowered_url = url.lower()
    if parsed.scheme != "postgres" and not parsed.scheme.startswith("postgresql"):
        raise RuntimeError("PCO-005A PostgreSQL tests require a PostgreSQL driver URL")
    if not database_name.startswith("pco005_"):
        raise RuntimeError("PCO-005A PostgreSQL tests require a pco005_* database")
    if "kiwi-postgres" in lowered_url or database_name == "restaurantos":
        raise RuntimeError("PCO-005A PostgreSQL tests reject protected database targets")
    if parsed.hostname not in {"127.0.0.1", "localhost"} and os.environ.get(
        ALLOW_REMOTE_ENV
    ) != "1":
        pytest.skip(f"{ALLOW_REMOTE_ENV}=1 is required for non-local PCO-005 PostgreSQL tests")
    return url


def _alembic(url: str, command: str, revision: str) -> None:
    environment = {**os.environ, "RESTAURANTOS_DATABASE_URL": url}
    environment.pop("DATABASE_URL", None)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", command, revision],
        cwd=API_DIR,
        env=environment,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)


def _truncate(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        connection.execute(sa.text("TRUNCATE organizations, permissions CASCADE"))


@pytest.fixture()
def postgres_engine() -> sa.Engine:
    url = _postgres_url()
    engine = sa.create_engine(url, pool_pre_ping=True)
    ready = False
    try:
        _alembic(url, "upgrade", "head")
        ready = True
        _truncate(engine)
        yield engine
    finally:
        try:
            if ready:
                _truncate(engine)
        finally:
            engine.dispose()


def test_postgres_reopen_historical_empty_roundtrip() -> None:
    url = _postgres_url()
    schema = f"pco005_roundtrip_{uuid4().hex}"
    admin = sa.create_engine(url)
    try:
        with admin.begin() as connection:
            connection.execute(sa.schema.CreateSchema(schema))
        scoped_url = sa.engine.make_url(url).set(query={"options": f"-csearch_path={schema}"})
        scoped = scoped_url.render_as_string(hide_password=False)
        _alembic(scoped, "upgrade", "0038_cash_shift_closures_sales_monitor")
        _alembic(scoped, "upgrade", "0039_order_reopen_requests")
        inspection = sa.create_engine(scoped_url)
        try:
            assert sa.inspect(inspection).has_table("order_reopen_requests", schema=schema)
            _alembic(scoped, "downgrade", "0038_cash_shift_closures_sales_monitor")
            assert not sa.inspect(inspection).has_table("order_reopen_requests", schema=schema)
            _alembic(scoped, "upgrade", "0039_order_reopen_requests")
            assert sa.inspect(inspection).has_table("order_reopen_requests", schema=schema)
        finally:
            inspection.dispose()
    finally:
        with admin.begin() as connection:
            connection.execute(sa.schema.DropSchema(schema, cascade=True, if_exists=True))
        admin.dispose()


def test_reopen_alembic_preserves_os_environment_and_isolates_database(monkeypatch) -> None:
    monkeypatch.setenv("SYSTEMROOT", "synthetic-os-root")
    monkeypatch.setenv("DATABASE_URL", "postgresql://untrusted.example/not-used")
    monkeypatch.setenv("RESTAURANTOS_DATABASE_URL", "postgresql://untrusted.example/not-used")
    captured = {}

    def run(arguments, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(arguments, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    explicit = "postgresql+psycopg://test:test@127.0.0.1/pco005_test"
    _alembic(explicit, "upgrade", "head")
    assert captured["env"]["SYSTEMROOT"] == "synthetic-os-root"
    assert captured["env"]["RESTAURANTOS_DATABASE_URL"] == explicit
    assert "DATABASE_URL" not in captured["env"]


def _setup_order(engine: sa.Engine) -> str:
    with Session(engine) as session:
        _seed_cash_concept_scope(session)
        _actors(session)
        session.execute(
            models.cash_shifts.insert().values(
                id=SHIFT_ID,
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
        return _order(session)


def _order_and_payment_snapshot(session: Session, order_id: str) -> tuple[dict, list[dict]]:
    order = dict(
        session.execute(
            sa.select(models.orders).where(models.orders.c.id == order_id)
        ).mappings().one()
    )
    payments = [
        dict(row)
        for row in session.execute(
            sa.select(models.payments)
            .where(models.payments.c.order_id == order_id)
            .order_by(models.payments.c.id)
        ).mappings()
    ]
    return order, payments


def test_postgres_reopen_migrates_and_serializes_active_request_without_history_mutation(
    postgres_engine: sa.Engine,
) -> None:
    order_id = _setup_order(postgres_engine)
    with Session(postgres_engine) as session:
        before = _order_and_payment_snapshot(session, order_id)

    barrier = Barrier(2)

    def request(key: str) -> tuple[str, str]:
        with Session(postgres_engine) as session:
            barrier.wait(timeout=10)
            try:
                result = create_order_reopen_request(
                    session,
                    order_id,
                    {"reason": "Corrección PostgreSQL documentada", "evidence_refs": ["pg:1"]},
                    key,
                    CHIEF_ID,
                )
                return "ok", result["id"]
            except BusinessError as error:
                return "error", error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(request, ("pco005-pg-race-01", "pco005-pg-race-02")))
    assert sorted(state for state, _ in outcomes) == ["error", "ok"]
    assert [result for state, result in outcomes if state == "error"] == [
        "order_reopen_request_active"
    ]

    with Session(postgres_engine) as session:
        assert session.execute(
            sa.select(sa.func.count()).select_from(models.order_reopen_requests).where(
                models.order_reopen_requests.c.order_id == order_id,
                models.order_reopen_requests.c.status.in_(("REQUESTED", "APPROVED")),
            )
        ).scalar_one() == 1
        assert _order_and_payment_snapshot(session, order_id) == before


def test_postgres_version_conflict_keeps_request_and_history_unchanged(
    postgres_engine: sa.Engine,
) -> None:
    order_id = _setup_order(postgres_engine)
    with Session(postgres_engine) as session:
        before = _order_and_payment_snapshot(session, order_id)
        request = create_order_reopen_request(
            session,
            order_id,
            {"reason": "Corrección PostgreSQL documentada", "evidence_refs": ["pg:2"]},
            "pco005-pg-version-01",
            CHIEF_ID,
        )

    with Session(postgres_engine) as session:
        session.execute(
            models.orders.update().where(models.orders.c.id == order_id).values(version=2)
        )
        session.commit()

    with Session(postgres_engine) as session:
        with pytest.raises(BusinessError, match="version") as conflict:
            decide_order_reopen_request(
                session,
                request["id"],
                "APPROVED",
                {"decision_reason": "Decisión PostgreSQL documentada"},
                "pco005-pg-version-02",
                OWNER_ID,
            )
        assert conflict.value.code == "order_version_conflict"
        saved = session.execute(
            sa.select(models.order_reopen_requests.c.status).where(
                models.order_reopen_requests.c.id == request["id"]
            )
        ).scalar_one()
        assert saved == "REQUESTED"
        after_order, after_payments = _order_and_payment_snapshot(session, order_id)
        assert after_payments == before[1]
        assert {**after_order, "version": before[0]["version"]} == before[0]


class _NoDatabaseUrlEnvironment(dict[str, str]):
    def get(self, key: str, default: str | None = None) -> str | None:
        if key == "DATABASE_URL":
            raise AssertionError("PCO-005 PostgreSQL gate must never read DATABASE_URL")
        return super().get(key, default)


def test_postgres_url_opt_in_and_protected_targets_are_decided_without_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = _NoDatabaseUrlEnvironment()
    monkeypatch.setattr(os, "environ", environment)

    with pytest.raises(pytest.skip.Exception):
        _postgres_url()

    environment[TEST_URL_ENV] = "postgresql://user:pass@database-prueba/pco005_isolated"
    with pytest.raises(pytest.skip.Exception):
        _postgres_url()

    environment[ALLOW_REMOTE_ENV] = "1"
    assert _postgres_url() == environment[TEST_URL_ENV]

    for url in (
        "postgresql://user:pass@localhost/restaurantos",
        "postgresql://user:pass@kiwi-postgres/pco005_isolated",
        "postgresql://user:pass@localhost/not_pco005",
    ):
        environment[TEST_URL_ENV] = url
        with pytest.raises(RuntimeError):
            _postgres_url()
