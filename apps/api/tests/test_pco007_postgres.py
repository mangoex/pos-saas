"""Opt-in TDD-TC-122/128 PostgreSQL guard and migration evidence."""
# ruff: noqa: E501

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
from restaurant_os.operations import BusinessError, update_product_recipe_versioned
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from test_cash_concepts import BRANCH_A, CASHIER_ID, OWNER_ID, OWNER_ROLE_ID
from test_pco007_recipe_reports import ITEM_ID, PRODUCT_ID, UNIT_ID, _seed_recipe_scope

TEST_URL_ENV = "PCO007_TEST_POSTGRES_URL"
API_DIR = Path(__file__).resolve().parents[1]


def _postgres_url() -> str:
    url = os.environ.get(TEST_URL_ENV)
    if not url:
        pytest.skip(f"{TEST_URL_ENV} is required for opt-in PostgreSQL tests")
    parsed = urlparse(url)
    database = parsed.path.lstrip("/")
    if not parsed.scheme.startswith("postgres") or parsed.hostname not in {
        "localhost",
        "127.0.0.1",
    }:
        raise RuntimeError("PCO-007 requires a local PostgreSQL URL")
    if not database.startswith("pco007_") or database in {"restaurantos", "kiwi-postgres"}:
        raise RuntimeError("PCO-007 requires a pco007_* isolated database")
    if "kiwi-postgres" in url.lower() or "restaurantos" in url.lower():
        raise RuntimeError("PCO-007 rejects protected PostgreSQL targets")
    return url


def _postgres_engine() -> sa.Engine:
    """Destructive reset is possible only for the explicit local pco007 database."""
    url = _postgres_url()
    reset_engine = create_engine(url, future=True)
    try:
        with reset_engine.begin() as connection:
            connection.execute(sa.text("DROP SCHEMA public CASCADE"))
            connection.execute(sa.text("CREATE SCHEMA public"))
    finally:
        reset_engine.dispose()
    environment = {**os.environ, "RESTAURANTOS_DATABASE_URL": url}
    environment.pop("DATABASE_URL", None)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=API_DIR, env=environment, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    engine = create_engine(url, future=True)
    with engine.begin() as connection:
        tables = connection.execute(sa.text(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
        )).scalars().all()
        if tables:
            preparer = connection.dialect.identifier_preparer
            quoted = ", ".join(preparer.quote(table) for table in tables)
            connection.execute(sa.text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))
    return engine


def _seed_recipe_postgres(engine: sa.Engine) -> None:
    with Session(engine) as session:
        from test_cash_concepts import _seed_cash_concept_scope

        _seed_cash_concept_scope(session)
        _seed_recipe_scope(session)


def _recipe_payload() -> dict[str, object]:
    return {
        "yield_quantity": "1",
        "yield_unit_id": UNIT_ID,
        "components": [
            {
                "item_id": ITEM_ID,
                "unit_id": UNIT_ID,
                "net_quantity": "1",
                "waste_rate": "0",
            }
        ],
    }


def test_pco007_postgres_guard_and_migration_head() -> None:
    url = _postgres_url()
    environment = {**os.environ, "RESTAURANTOS_DATABASE_URL": url}
    environment.pop("DATABASE_URL", None)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "0042_recipe_reports"],
        cwd=API_DIR,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_recipe_same_key_is_single_command_and_replays_concurrently() -> None:
    engine = _postgres_engine()
    try:
        _seed_recipe_postgres(engine)
        barrier = Barrier(2)

        def worker() -> dict[str, object]:
            with Session(engine) as session:
                barrier.wait(timeout=10)
                return update_product_recipe_versioned(
                    session, PRODUCT_ID, _recipe_payload(), BRANCH_A, None,
                    "pco007-concurrent", CASHIER_ID,
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = list(pool.map(lambda _: worker(), range(2)))
        assert first["id"] == second["id"]
        with Session(engine) as session:
            assert session.execute(sa.select(sa.func.count()).select_from(
                models.recipe_version_commands
            )).scalar_one() == 1
            assert session.execute(sa.select(sa.func.count()).select_from(
                models.recipes
            )).scalar_one() == 1
    finally:
        engine.dispose()


def test_pco007_postgres_report_indexes_are_present() -> None:
    engine = _postgres_engine()
    try:
        with engine.connect() as connection:
            indexes = set(connection.execute(sa.text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()"
            )).scalars())
            required = {
                "ix_pco007_purchase_report", "ix_pco007_cash_report", "ix_pco007_recipe_snapshot",
            }
            assert required <= indexes
    finally:
        engine.dispose()


def test_recipe_same_key_different_payload_has_one_winner() -> None:
    engine = _postgres_engine()
    try:
        _seed_recipe_postgres(engine)
        barrier = Barrier(2)

        def worker(quantity: str) -> str:
            with Session(engine) as session:
                payload = _recipe_payload()
                payload["components"] = [{
                    "item_id": ITEM_ID, "unit_id": UNIT_ID,
                    "net_quantity": quantity, "waste_rate": "0",
                }]
                barrier.wait(timeout=10)
                try:
                    update_product_recipe_versioned(
                        session, PRODUCT_ID, payload, BRANCH_A, None,
                        "pco007-different-payload", CASHIER_ID,
                    )
                    return "success"
                except BusinessError as exc:
                    return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = set(pool.map(worker, ("1", "2")))
        assert outcomes == {"success", "idempotency_conflict"}
        with Session(engine) as session:
            assert session.execute(
                sa.select(sa.func.count()).select_from(models.recipes)
            ).scalar_one() == 1
            assert session.execute(
                sa.select(sa.func.count()).select_from(models.recipe_version_commands)
            ).scalar_one() == 1
    finally:
        engine.dispose()


def test_branch_and_corporate_recipe_writers_are_serialized() -> None:
    engine = _postgres_engine()
    try:
        _seed_recipe_postgres(engine)
        with Session(engine) as session:
            permission_id = session.execute(sa.select(models.permissions.c.id).where(
                models.permissions.c.code == "recipes.manage"
            )).scalar_one()
            session.execute(models.role_permissions.insert().values(
                role_id=OWNER_ROLE_ID, permission_id=permission_id,
            ))
            session.commit()
        barrier = Barrier(2)

        def worker(actor_id: str, branch_id: str | None, key: str) -> dict[str, object]:
            with Session(engine) as session:
                barrier.wait(timeout=10)
                return update_product_recipe_versioned(
                    session, PRODUCT_ID, _recipe_payload(), branch_id, None, key, actor_id,
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            branch, corporate = list(pool.map(
                lambda values: worker(*values),
                ((CASHIER_ID, BRANCH_A, "pco007-branch"), (OWNER_ID, None, "pco007-corporate")),
            ))
        assert branch["id"] != corporate["id"]
        assert {branch["version"], corporate["version"]} == {1, 2}
        with Session(engine) as session:
            active_branch = session.execute(sa.select(sa.func.count()).select_from(models.recipes).where(
                models.recipes.c.branch_id == BRANCH_A, models.recipes.c.status == "active",
            )).scalar_one()
            active_corporate = session.execute(sa.select(sa.func.count()).select_from(models.recipes).where(
                models.recipes.c.branch_id.is_(None), models.recipes.c.status == "active",
            )).scalar_one()
            assert active_branch == 1
            assert active_corporate == 1
            assert session.execute(
                sa.select(sa.func.count()).select_from(models.recipe_version_commands)
            ).scalar_one() == 2
    finally:
        engine.dispose()


def test_report_query_plans_are_indexed_and_bounded() -> None:
    engine = _postgres_engine()
    try:
        _seed_recipe_postgres(engine)
        with engine.begin() as connection:
            indexes = set(connection.execute(sa.text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()"
            )).scalars())
            required = {
                "ix_pco007_purchase_report", "ix_pco007_purchase_cancelled_report",
                "ix_pco007_cash_report", "ix_pco007_recipe_snapshot",
                "ix_order_corrections_org_branch_applied",
            }
            assert required <= indexes
            connection.execute(sa.text("SET LOCAL enable_seqscan = off"))
            statements = (
                "SELECT * FROM sales_operation_snapshots WHERE organization_id = :org AND branch_id = :branch AND confirmed_at >= :start AND confirmed_at < :end",
                "SELECT * FROM order_corrections WHERE organization_id = :org AND branch_id = :branch AND applied_at >= :start AND applied_at < :end",
                "SELECT * FROM purchase_documents WHERE organization_id = :org AND branch_id = :branch AND confirmed_at >= :start AND confirmed_at < :end",
                "SELECT * FROM purchase_documents WHERE organization_id = :org AND branch_id = :branch AND cancelled_at >= :start AND cancelled_at < :end",
                "SELECT * FROM cash_movements WHERE organization_id = :org AND branch_id = :branch AND created_at >= :start AND created_at < :end",
            )
            parameters = {"org": "018f6f73-2d0a-74f0-8f1c-000000000001", "branch": BRANCH_A,
                          "start": "2026-01-01T00:00:00+00:00", "end": "2026-02-01T00:00:00+00:00"}
            for statement in statements:
                plan = connection.execute(sa.text(f"EXPLAIN (FORMAT JSON) {statement}"), parameters).scalar_one()
                serialized = str(plan)
                assert "Index" in serialized or "Bitmap" in serialized
    finally:
        engine.dispose()
