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


def _insert_feedback(connection: sa.Connection, order_folio: str) -> None:
    connection.execute(
        sa.text(
            """
            INSERT INTO customer_feedbacks (
                id, organization_id, branch_id, order_folio, rating, created_at
            ) VALUES (:id, 'org', 'branch', :order_folio, 4, CURRENT_TIMESTAMP)
            """
        ),
        {"id": str(uuid4()), "order_folio": order_folio},
    )


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


def test_feedback_reference_upgrade_blocks_historical_duplicates() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        _prepare(connection)
        _insert_feedback(connection, "PI-DUPLICATE-1")
        _insert_feedback(connection, "PI-DUPLICATE-1")
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError, match="duplicate customer feedback order references"):
                _migration().upgrade()
        assert not sa.inspect(connection).get_indexes("customer_feedbacks")
        assert (
            connection.scalar(
                sa.text(
                    "SELECT COUNT(*) FROM customer_feedbacks WHERE order_folio='PI-DUPLICATE-1'"
                )
            )
            == 2
        )
