# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-admin-ai-postgres-tests-v1
"""Opt-in PostgreSQL locking and migration gates for AIA-001/AIA-002A/AIA-002C.

The suite never reads DATABASE_URL and may reset only a local database whose
name starts with ``aia001_``.
"""

from __future__ import annotations

import json
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
from restaurant_os.admin_ai import (
    AdminAiError,
    AdminAiProviderOptions,
    create_admin_ai_response,
    review_proposal,
)
from restaurant_os.operations import BusinessError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from test_platform_api import ADMIN_USER_ID, BRANCH_ID

TEST_URL_ENV = "AIA001_TEST_POSTGRES_URL"
API_DIR = Path(__file__).resolve().parents[1]
PRODUCT_ID = "018f6f73-2d0a-74f0-8f1c-000000000111"
OPTIONS = AdminAiProviderOptions(
    api_key="synthetic-admin-ai-postgres-key",
    model="synthetic/model",
    base_url="https://provider.invalid/api/v1",
    timeout_seconds=3,
)


def _conversation_key(sequence: int) -> str:
    return f"018f6f73-2d0a-74f0-8f1c-{sequence:012d}"


def _validate_postgres_url(url: str) -> str:
    parsed = urlparse(url)
    database = parsed.path.lstrip("/")
    if (
        not parsed.scheme.startswith("postgres")
        or parsed.hostname not in {"localhost", "127.0.0.1"}
        or not database.startswith("aia001_")
        or database in {"restaurantos", "kiwi-postgres"}
    ):
        raise RuntimeError(
            "AIA001_TEST_POSTGRES_URL must target a local isolated aia001_* database"
        )
    return url


def _postgres_url() -> str:
    url = os.environ.get(TEST_URL_ENV)
    if not url:
        pytest.skip(f"{TEST_URL_ENV} is required for opt-in PostgreSQL tests")
    return _validate_postgres_url(url)


def _alembic_environment(url: str) -> dict[str, str]:
    environment = dict(os.environ)
    environment.pop("DATABASE_URL", None)
    environment["RESTAURANTOS_DATABASE_URL"] = url
    return environment


def _alembic(url: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *arguments],
        cwd=API_DIR,
        env=_alembic_environment(url),
        capture_output=True,
        text=True,
        timeout=60,
    )


def _reset_and_upgrade_revision(url: str, revision: str) -> sa.Engine:
    reset_engine = create_engine(url, future=True)
    try:
        with reset_engine.begin() as connection:
            connection.execute(sa.text("DROP SCHEMA public CASCADE"))
            connection.execute(sa.text("CREATE SCHEMA public"))
    finally:
        reset_engine.dispose()
    upgraded = _alembic(url, "upgrade", revision)
    assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr
    return create_engine(url, future=True, pool_pre_ping=True)


def _reset_and_upgrade(url: str) -> sa.Engine:
    return _reset_and_upgrade_revision(url, "head")


def _provider_result() -> dict[str, object]:
    return {
        "answer": "Preparé una propuesta revisable.",
        "sources": ["PRD-FR-010", "SDD §43"],
        "questions": [],
        "warnings": [],
        "change_set": [
            {
                "kind": "product.update",
                "target_id": PRODUCT_ID,
                "payload_json": json.dumps({"name": "HAMBURGUESA CONCURRENTE"}),
                "evidence": [
                    {"field": "target_id", "quote": "Hamburguesa Kiwi"},
                    {"field": "name", "quote": "HAMBURGUESA CONCURRENTE"},
                ],
            }
        ],
    }


def _seed_proposal(engine: sa.Engine) -> str:
    with Session(engine) as session:
        proposal = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "Actualiza Hamburguesa Kiwi a HAMBURGUESA CONCURRENTE",
            BRANCH_ID,
            OPTIONS,
            lambda *_args: _provider_result(),
        )
        return str(proposal["id"])


def _seed_historical_proposal(engine: sa.Engine) -> None:
    """Use the migration's canonical seed rows to exercise the 0055 downgrade guard."""
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO admin_ai_proposals
                    (id, organization_id, branch_id, actor_user_id, status, base_fingerprint,
                     payload, created_at, updated_at, expires_at)
                VALUES (:proposal_id, :organization_id, :branch_id, :actor_user_id, 'DRAFT',
                        'historical-fixture', '{}'::json, now(), now(), now());
                """
            ),
            {
                "organization_id": "018f6f73-2d0a-74f0-8f1c-000000000001",
                "branch_id": BRANCH_ID,
                "actor_user_id": ADMIN_USER_ID,
                "proposal_id": "018f6f73-2d0a-74f0-8f1c-000000009999",
            },
        )


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:p@example.test/aia001_safe",
        "postgresql+psycopg://u:p@localhost/restaurantos",
        "sqlite:///aia001_safe",
    ],
)
def test_tdd_tc_203_postgres_url_guard_rejects_protected_targets(url: str) -> None:
    with pytest.raises(RuntimeError):
        _validate_postgres_url(url)


def test_tdd_tc_203_postgres_same_key_acceptance_applies_once() -> None:
    engine = _reset_and_upgrade(_postgres_url())
    try:
        proposal_id = _seed_proposal(engine)
        barrier = Barrier(2)

        def accept() -> tuple[str, str | None]:
            with Session(engine) as session:
                barrier.wait(timeout=10)
                try:
                    result = review_proposal(
                        session,
                        proposal_id,
                        ADMIN_USER_ID,
                        True,
                        "aia001-same-key",
                    )
                    return str(result["status"]), str(result["result"]["id"])
                except BusinessError as exc:
                    return exc.code, None

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _index: accept(), range(2)))

        assert outcomes == [("APPLIED", PRODUCT_ID), ("APPLIED", PRODUCT_ID)]
        with Session(engine) as session:
            assert (
                session.execute(
                    sa.select(sa.func.count())
                    .select_from(models.audit_events)
                    .where(models.audit_events.c.action == "admin_ai.proposal_applied")
                ).scalar_one()
                == 1
            )
            assert (
                session.execute(
                    sa.select(models.products.c.name).where(models.products.c.id == PRODUCT_ID)
                ).scalar_one()
                == "HAMBURGUESA CONCURRENTE"
            )
    finally:
        engine.dispose()


def test_tdd_tc_203_postgres_different_keys_have_one_winner() -> None:
    engine = _reset_and_upgrade(_postgres_url())
    try:
        proposal_id = _seed_proposal(engine)
        barrier = Barrier(2)

        def accept(key: str) -> str:
            with Session(engine) as session:
                barrier.wait(timeout=10)
                try:
                    return str(
                        review_proposal(session, proposal_id, ADMIN_USER_ID, True, key)["status"]
                    )
                except BusinessError as exc:
                    return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = set(pool.map(accept, ("aia001-key-a", "aia001-key-b")))

        assert outcomes == {"APPLIED", "idempotency_conflict"}
        with Session(engine) as session:
            assert (
                session.execute(
                    sa.select(sa.func.count())
                    .select_from(models.audit_events)
                    .where(models.audit_events.c.action == "admin_ai.proposal_applied")
                ).scalar_one()
                == 1
            )
    finally:
        engine.dispose()


def test_tdd_tc_203_postgres_migration_roundtrip_and_history_guard() -> None:
    url = _postgres_url()
    engine = _reset_and_upgrade_revision(url, "0055_admin_ai_proposals")
    engine.dispose()

    downgraded = _alembic(url, "downgrade", "0054_seed_standard_cash_movement_concepts")
    assert downgraded.returncode == 0, downgraded.stdout + downgraded.stderr
    upgraded = _alembic(url, "upgrade", "0055_admin_ai_proposals")
    assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr
    engine = create_engine(url, future=True)
    try:
        _seed_historical_proposal(engine)
    finally:
        engine.dispose()

    blocked = _alembic(url, "downgrade", "0054_seed_standard_cash_movement_concepts")
    assert blocked.returncode != 0
    assert "admin AI proposal history blocks downgrade" in blocked.stdout + blocked.stderr


def test_tdd_tc_207_postgres_price_diagnostics_are_portable() -> None:
    engine = _reset_and_upgrade(_postgres_url())
    try:
        with Session(engine) as session:
            purchase = create_admin_ai_response(
                session,
                ADMIN_USER_ID,
                "¿Qué insumos no tienen precio de compra?",
                BRANCH_ID,
                OPTIONS,
                lambda *_args: pytest.fail("Canonical purchase diagnostic reached provider"),
            )
            average_cost = create_admin_ai_response(
                session,
                ADMIN_USER_ID,
                "¿Qué insumos no tienen costo promedio?",
                BRANCH_ID,
                OPTIONS,
                lambda *_args: pytest.fail("Canonical cost diagnostic reached provider"),
            )

            assert purchase["status"] == "DRAFT"
            assert purchase["payload"]["diagnostic"]["kind"] == "missing_purchase_price"
            assert average_cost["status"] == "DRAFT"
            assert average_cost["payload"]["diagnostic"]["kind"] == "missing_average_cost"
            assert purchase["payload"]["change_set"] == []
            assert average_cost["payload"]["change_set"] == []
    finally:
        engine.dispose()


def test_tdd_tc_209_postgres_parent_allows_only_one_concurrent_follow_up() -> None:
    engine = _reset_and_upgrade(_postgres_url())
    try:
        with Session(engine) as session:
            parent = create_admin_ai_response(
                session,
                ADMIN_USER_ID,
                "¿Qué insumos no tienen precio?",
                BRANCH_ID,
            )
        barrier = Barrier(2)

        def continue_conversation(choice: str) -> str:
            with Session(engine) as session:
                barrier.wait(timeout=10)
                try:
                    reply = (
                        "Precio de compra"
                        if choice == "missing_purchase_price"
                        else "Costo promedio"
                    )
                    child = create_admin_ai_response(
                        session,
                        ADMIN_USER_ID,
                        reply,
                        BRANCH_ID,
                        parent_proposal_id=str(parent["id"]),
                        clarification_choice=choice,
                        conversation_idempotency_key=_conversation_key(
                            201 if choice == "missing_purchase_price" else 202
                        ),
                    )
                    return str(child["payload"]["diagnostic"]["kind"])
                except AdminAiError as exc:
                    return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(
                pool.map(
                    continue_conversation,
                    ("missing_purchase_price", "missing_average_cost"),
                )
            )

        assert outcomes.count("admin_ai_conversation_invalid") == 1
        assert len(set(outcomes) & {"missing_purchase_price", "missing_average_cost"}) == 1
    finally:
        engine.dispose()


def test_tdd_tc_209_postgres_follow_up_serializes_against_parent_review() -> None:
    engine = _reset_and_upgrade(_postgres_url())
    try:
        with Session(engine) as session:
            parent = create_admin_ai_response(
                session,
                ADMIN_USER_ID,
                "¿Qué insumos no tienen precio?",
                BRANCH_ID,
            )
        barrier = Barrier(2)

        def continue_conversation() -> str:
            with Session(engine) as session:
                barrier.wait(timeout=10)
                try:
                    child = create_admin_ai_response(
                        session,
                        ADMIN_USER_ID,
                        "Precio de compra",
                        BRANCH_ID,
                        parent_proposal_id=str(parent["id"]),
                        clarification_choice="missing_purchase_price",
                        conversation_idempotency_key=_conversation_key(203),
                    )
                    return str(child["payload"]["diagnostic"]["kind"])
                except AdminAiError as exc:
                    return exc.code

        def reject_parent() -> str:
            with Session(engine) as session:
                barrier.wait(timeout=10)
                try:
                    return str(
                        review_proposal(
                            session,
                            str(parent["id"]),
                            ADMIN_USER_ID,
                            False,
                        )["status"]
                    )
                except BusinessError as exc:
                    return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            continuation = pool.submit(continue_conversation)
            rejection = pool.submit(reject_parent)
            outcomes = {continuation.result(), rejection.result()}

        assert outcomes in (
            {"missing_purchase_price", "admin_ai_proposal_expired"},
            {"admin_ai_conversation_invalid", "REJECTED"},
        )
    finally:
        engine.dispose()
