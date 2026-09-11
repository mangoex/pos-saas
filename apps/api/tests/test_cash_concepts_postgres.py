"""Opt-in PostgreSQL verification for PCO-002; never reads DATABASE_URL."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.database import get_session
from restaurant_os.main import create_app
from restaurant_os.operations import (
    BusinessError,
    archive_cash_concept,
    create_cash_concept,
    create_cash_concept_version,
    list_cash_concepts,
    list_effective_cash_concepts,
)
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker
from test_cash_concepts import (
    BRANCH_A,
    CASHIER_ID,
    OWNER_ID,
    UTC,
    _concept_payload,
    _seed_cash_concept_scope,
    _version_payload,
)

ROOT = Path(__file__).resolve().parents[3]
API_DIR = ROOT / "apps" / "api"
TEST_URL_ENV = "PCO002_TEST_POSTGRES_URL"


def _test_url() -> str:
    url = os.environ.get(TEST_URL_ENV)
    if not url:
        pytest.skip(f"{TEST_URL_ENV} is required for opt-in PostgreSQL tests")
    parsed = urlparse(url)
    if parsed.hostname not in {"127.0.0.1", "localhost"} or not parsed.path.startswith(
        "/pco002_"
    ):
        raise RuntimeError("PCO-002 PostgreSQL tests require a local pco002_* database")
    return url


@pytest.fixture()
def postgres_factory() -> Generator[sessionmaker[Session], None, None]:
    engine = sa.create_engine(_test_url(), pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "TRUNCATE audit_events, cash_concept_commands, "
                "cash_movement_concept_versions, cash_movement_concepts, "
                "role_authority_grants, role_permissions, user_roles, permissions, "
                "users, roles, branches, business_units, legal_entities, organizations CASCADE"
            )
        )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        _seed_cash_concept_scope(session)
    try:
        yield factory
    finally:
        engine.dispose()


def test_postgres_domain_and_api_preserve_catalog_history(
    postgres_factory: sessionmaker[Session],
) -> None:
    with postgres_factory() as session:
        created = create_cash_concept(session, _concept_payload(), "pg-create", OWNER_ID)
        assert create_cash_concept(session, _concept_payload(), "pg-create", OWNER_ID) == created
        versioned = create_cash_concept_version(
            session,
            created["id"],
            _version_payload(name="Retiro PostgreSQL", valid_from="2026-09-01T00:00:00Z"),
            "pg-version",
            OWNER_ID,
        )
        assert [version["version"] for version in versioned["versions"]] == [1, 2]
        assert [item["version"] for item in list_effective_cash_concepts(
            session, "withdrawal", datetime(2026, 8, 20, tzinfo=UTC), CASHIER_ID, BRANCH_A
        )] == [1]
        archived = archive_cash_concept(session, created["id"], "pg-archive", OWNER_ID)
        assert archived["status"] == "archived"
        assert len(list_cash_concepts(session, OWNER_ID)[0]["versions"]) == 2
        assert session.execute(
            sa.select(sa.func.count()).select_from(models.audit_events).where(
                models.audit_events.c.action.in_(
                    ["cash_concept.created", "cash_concept.versioned", "cash_concept.archived"]
                )
            )
        ).scalar_one() == 3

    app = create_app()

    def override_session() -> Generator[Session, None, None]:
        with postgres_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    response = TestClient(app).get(
        "/api/v1/cash/concepts", headers={"X-Actor-User-Id": OWNER_ID}
    )
    assert response.status_code == 200
    assert response.json()[0]["status"] == "archived"


def test_postgres_concurrent_versions_return_domain_outcome(
    postgres_factory: sessionmaker[Session],
) -> None:
    engine = postgres_factory.kw["bind"]
    with postgres_factory() as session:
        concept = create_cash_concept(session, _concept_payload(), "pg-race-create", OWNER_ID)
    barrier = threading.Barrier(2)
    gate_lock = threading.Lock()
    entered = 0

    @event.listens_for(engine, "before_cursor_execute")
    def gate_version_insert(*args: object) -> None:
        nonlocal entered
        statement = str(args[2])
        if "INSERT INTO cash_movement_concept_versions" not in statement:
            return
        with gate_lock:
            entered += 1
            wait = entered <= 2
        if wait:
            barrier.wait(timeout=5)

    outcomes: list[dict[str, object] | BusinessError] = []

    def publish(key: str) -> None:
        with postgres_factory() as session:
            try:
                outcomes.append(
                    create_cash_concept_version(
                        session, concept["id"], _version_payload(name="Carrera PG"), key, OWNER_ID
                    )
                )
            except BusinessError as error:
                outcomes.append(error)

    workers = [threading.Thread(target=publish, args=(key,)) for key in ("pg-race-1", "pg-race-2")]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)
    event.remove(engine, "before_cursor_execute", gate_version_insert)
    assert not any(worker.is_alive() for worker in workers)
    assert len(outcomes) == 2
    assert all(
        not isinstance(result, BusinessError)
        or result.code == "cash_concept_version_conflict"
        for result in outcomes
    )
    with postgres_factory() as session:
        assert session.execute(
            sa.select(models.cash_movement_concept_versions.c.version)
            .where(models.cash_movement_concept_versions.c.concept_id == concept["id"])
            .order_by(models.cash_movement_concept_versions.c.version)
        ).scalars().all() == [1, 2]


def test_postgres_downgrade_is_blocked_with_pco002_history(
    postgres_factory: sessionmaker[Session],
) -> None:
    with postgres_factory() as session:
        create_cash_concept(session, _concept_payload(), "pg-downgrade-history", OWNER_ID)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic.ini",
            "downgrade",
            "0035_cumulative_profiles_rbac",
        ],
        cwd=API_DIR,
        env={**os.environ, "RESTAURANTOS_DATABASE_URL": _test_url()},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Safe downgrade blocked: cash concept history exists" in result.stdout + result.stderr
    with postgres_factory() as session:
        revision = session.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        assert revision == "0036_cash_concepts"
