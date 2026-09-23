"""Exercise the incremental migration against pre-existing branch rows."""

import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_pickup_migration_roundtrip(backend: str) -> None:
    url = os.environ.get("SAAS_TEST_POSTGRES_URL") if backend == "postgresql" else "sqlite://"
    if not url:
        pytest.skip("SAAS_TEST_POSTGRES_URL required for PostgreSQL gate")
    engine = sa.create_engine(url)
    schema = "pickup_" + uuid4().hex if backend == "postgresql" else None
    path = (
        Path(__file__).resolve().parents[1] / "alembic/versions/202609231200_0097_pickup_grace.py"
    )
    spec = importlib.util.spec_from_file_location("pickup_migration", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    try:
        with engine.begin() as conn:
            if schema:
                conn.execute(sa.schema.CreateSchema(schema))
                conn.execute(sa.text(f'SET search_path TO "{schema}"'))
            conn.execute(
                sa.text("CREATE TABLE branches (id INTEGER PRIMARY KEY, name VARCHAR(100))")
            )
            conn.execute(sa.text("INSERT INTO branches VALUES (1, 'Existing')"))
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
            assert (
                conn.execute(sa.text("SELECT pickup_grace_minutes FROM branches")).scalar() is None
            )
            conn.execute(sa.text("UPDATE branches SET pickup_grace_minutes = 30"))
            for invalid in (0, -1):
                with pytest.raises(sa.exc.IntegrityError), conn.begin_nested():
                    conn.execute(
                        sa.text("UPDATE branches SET pickup_grace_minutes = :minutes"),
                        {"minutes": invalid},
                    )
            assert conn.execute(sa.text("SELECT pickup_grace_minutes FROM branches")).scalar() == 30
            with Operations.context(MigrationContext.configure(conn)):
                migration.downgrade()
            assert conn.execute(sa.text("SELECT id, name FROM branches")).one() == (1, "Existing")
            assert "pickup_grace_minutes" not in {
                c["name"] for c in sa.inspect(conn).get_columns("branches")
            }
    finally:
        if schema:
            with engine.begin() as conn:
                conn.execute(sa.schema.DropSchema(schema, cascade=True))
        engine.dispose()
