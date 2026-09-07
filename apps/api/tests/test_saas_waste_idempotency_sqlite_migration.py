# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-test-waste-sqlite-migration-synthetic-v1
"""SQLite reversibility gate for tenant-scoped waste idempotency."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

API_DIR = Path(__file__).resolve().parents[1]


def test_0077_sqlite_upgrade_downgrade_and_reupgrade_to_current_head(tmp_path: Path) -> None:
    database_path = tmp_path / "waste-0077.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = {**os.environ, "RESTAURANTOS_DATABASE_URL": database_url}

    def migrate(action: str, target: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "alembic.ini", action, target],
            cwd=API_DIR,
            env=environment,
            text=True,
            capture_output=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    migrate("upgrade", "0077_fiscal_resource_claims")
    migrate("upgrade", "0078_waste_tenant_idempotency")
    migrate("downgrade", "0077_fiscal_resource_claims")
    migrate("upgrade", "head")

    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as connection:
            assert (
                connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
                == "0082_category_presentation"
            )
    finally:
        engine.dispose()
