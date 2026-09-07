"""Fiscal issue command migration preserves the durable retry barrier."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_fiscal_issue_command_upgrade_creates_durable_unknown_state() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/202609041400_0074_fiscal_issue_commands.py"
    )
    spec = spec_from_file_location("fiscal_issue_commands_migration", path)
    assert spec and spec.loader
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        for table in ("organizations", "branches", "cfdi_invoices", "users"):
            connection.execute(sa.text(f"CREATE TABLE {table}(id TEXT PRIMARY KEY)"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        columns = {
            column["name"] for column in sa.inspect(connection).get_columns("fiscal_commands")
        }
    assert {"operation_fingerprint", "payload_hash", "provider_resource_id", "status"} <= columns
