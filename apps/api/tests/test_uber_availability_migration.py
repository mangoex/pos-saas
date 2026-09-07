from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_uber_availability_upgrade_creates_versioned_leased_outbox() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/202609041200_0072_uber_availability_sync.py"
    )
    spec = spec_from_file_location("uber_availability_migration", path)
    assert spec and spec.loader
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        for table in ("organizations", "branches", "products"):
            connection.execute(sa.text(f"CREATE TABLE {table}(id TEXT PRIMARY KEY)"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        columns = {
            column["name"]
            for column in sa.inspect(connection).get_columns("channel_availability_sync_jobs")
        }
    assert {"desired_version", "lease_token", "lease_expires_at"} <= columns
