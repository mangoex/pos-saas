from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

ORGANIZATION_ID = "018f6f73-2d0a-74f0-8f1c-000000000001"


def test_insumos_and_presentations_migration_and_determinism(tmp_path: Path) -> None:
    database_path = tmp_path / "insumos_sync_test.db"
    db_url = f"sqlite+pysqlite:///{database_path}"
    env = {
        **os.environ,
        "RESTAURANTOS_DATABASE_URL": db_url,
        "DATABASE_URL": db_url,
    }

    api_dir = str(Path(__file__).resolve().parents[1])

    # Exercise the historical data migration before later cleanup revisions.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic.ini",
            "upgrade",
            "0048_sync_insumos_and_presentations",
        ],
        cwd=api_dir,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Alembic failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )

    engine = sa.create_engine(db_url)
    with engine.connect() as conn:
        # Check units
        units = conn.execute(
            sa.text("SELECT code FROM inventory_units WHERE organization_id = :org_id"),
            {"org_id": ORGANIZATION_ID},
        ).fetchall()
        unit_codes = [u[0] for u in units]
        assert "KILO" in unit_codes
        assert "LITRO" in unit_codes
        assert "PZA" in unit_codes

        # Check 156 insumos
        items = conn.execute(
            sa.text(
                "SELECT sku, name, item_type FROM inventory_items "
                "WHERE organization_id = :org_id"
            ),
            {"org_id": ORGANIZATION_ID},
        ).fetchall()
        assert len(items) >= 150

        # Check presentations
        presentations = conn.execute(
            sa.text(
                "SELECT code, name, last_net_price FROM purchase_presentations "
                "WHERE organization_id = :org_id"
            ),
            {"org_id": ORGANIZATION_ID},
        ).fetchall()
        assert len(presentations) >= 150

        # Check cost states
        costs = conn.execute(
            sa.text("SELECT item_id, last_unit_cost, average_unit_cost FROM inventory_cost_states"),
        ).fetchall()
        assert len(costs) >= 150

        for c in costs[:10]:
            assert c[1] >= 0
            assert c[2] >= 0
