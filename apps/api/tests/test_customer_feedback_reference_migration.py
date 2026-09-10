from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

API_DIR = Path(__file__).resolve().parents[1]


def _migration():
    path = API_DIR / "alembic/versions/202609091900_0086_secure_customer_feedback_reference.py"
    spec = spec_from_file_location("customer_feedback_reference_migration", path)
    assert spec and spec.loader
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _prepare(connection: sa.Connection) -> None:
    connection.execute(
        sa.text(
            """
            CREATE TABLE customer_feedbacks (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                branch_id TEXT NOT NULL,
                order_folio TEXT,
                rating INTEGER NOT NULL,
                created_at DATETIME NOT NULL
            )
            """
        )
    )


def _insert_feedback(
    connection: sa.Connection,
    order_folio: str,
    *,
    created_at: str = "2026-09-09 12:00:00",
) -> str:
    feedback_id = str(uuid4())
    connection.execute(
        sa.text(
            """
            INSERT INTO customer_feedbacks (
                id, organization_id, branch_id, order_folio, rating, created_at
            ) VALUES (:id, 'org', 'branch', :order_folio, 4, :created_at)
            """
        ),
        {"id": feedback_id, "order_folio": order_folio, "created_at": created_at},
    )
    return feedback_id


def test_feedback_reference_upgrade_adds_unique_index() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        _prepare(connection)
        with Operations.context(MigrationContext.configure(connection)):
            _migration().upgrade()
        indexes = {
            index["name"]: index
            for index in sa.inspect(connection).get_indexes("customer_feedbacks")
        }
        assert indexes["uq_customer_feedbacks_order_reference"]["unique"] == 1
        _insert_feedback(connection, "PI-UNIQUE-1")
        with pytest.raises(sa.exc.IntegrityError):
            with connection.begin_nested():
                _insert_feedback(connection, "PI-UNIQUE-1")


def test_feedback_reference_upgrade_remediates_historical_duplicates() -> None:
    """Auto-remediation keeps the most recent feedback and deletes older duplicates."""
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        _prepare(connection)
        # Insert two duplicates with different timestamps — older first.
        _insert_feedback(connection, "PI-DUPLICATE-1", created_at="2026-09-08 10:00:00")
        newest_id = _insert_feedback(
            connection, "PI-DUPLICATE-1", created_at="2026-09-09 15:00:00"
        )
        # Also add a non-duplicate to verify it's untouched.
        solo_id = _insert_feedback(connection, "PI-SOLO-1", created_at="2026-09-09 12:00:00")

        with Operations.context(MigrationContext.configure(connection)):
            _migration().upgrade()

        # The unique index was created.
        indexes = {
            index["name"]: index
            for index in sa.inspect(connection).get_indexes("customer_feedbacks")
        }
        assert indexes["uq_customer_feedbacks_order_reference"]["unique"] == 1

        # Only the newest duplicate survives.
        remaining = connection.execute(
            sa.text(
                "SELECT id FROM customer_feedbacks WHERE order_folio='PI-DUPLICATE-1'"
            )
        ).fetchall()
        assert len(remaining) == 1
        assert remaining[0][0] == newest_id

        # Non-duplicate is untouched.
        solo = connection.execute(
            sa.text("SELECT id FROM customer_feedbacks WHERE order_folio='PI-SOLO-1'")
        ).fetchall()
        assert len(solo) == 1
        assert solo[0][0] == solo_id

        # Future duplicates are blocked by the UNIQUE index.
        with pytest.raises(sa.exc.IntegrityError):
            with connection.begin_nested():
                _insert_feedback(connection, "PI-DUPLICATE-1")

