"""PostgreSQL reversibility gate for tenant-scoped waste idempotency."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa

API_DIR = Path(__file__).resolve().parents[1]


def test_0077_downgrade_blocks_cross_tenant_keys_without_ddl_or_data_loss() -> None:
    database_url = os.environ.get("SAAS_TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("SAAS_TEST_POSTGRES_URL is required")
    schema = f"saas_waste_0077_{uuid4().hex}"
    base = sa.create_engine(database_url)
    with base.begin() as connection:
        connection.execute(sa.schema.CreateSchema(schema))
    scoped_url = sa.engine.make_url(database_url).update_query_dict(
        {"options": f"-csearch_path={schema}"}
    )
    environment = {
        **os.environ,
        "RESTAURANTOS_DATABASE_URL": scoped_url.render_as_string(hide_password=False),
    }

    def migrate(
        action: str, target: str, *, succeeds: bool = True
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "alembic.ini", action, target],
            cwd=API_DIR,
            env=environment,
            text=True,
            capture_output=True,
            timeout=120,
        )
        assert (result.returncode == 0) is succeeds, result.stdout + result.stderr
        return result

    engine = sa.create_engine(scoped_url)
    try:
        migrate("upgrade", "0077_fiscal_resource_claims")
        migrate("upgrade", "0078_waste_tenant_idempotency")
        rows = [
            {"id": str(uuid4()), "organization_id": str(uuid4()), "key": "cross-tenant-key"},
            {"id": str(uuid4()), "organization_id": str(uuid4()), "key": "cross-tenant-key"},
        ]
        with engine.begin() as connection:
            connection.execute(sa.text("SET session_replication_role = replica"))
            for row in rows:
                connection.execute(
                    sa.text("""
                    INSERT INTO inventory_movements (
                        id, organization_id, branch_id, warehouse_id, item_id, movement_type,
                        quantity_delta, unit_id, unit_cost, total_cost, effective_at, reason,
                        idempotency_key, status, created_at
                    ) VALUES (
                        :id, :organization_id, :id, :id, :id, 'WASTE_REAL', -1, :id, 1, -1,
                        CURRENT_TIMESTAMP, 'synthetic migration fixture', :key, 'confirmed',
                        CURRENT_TIMESTAMP
                    )
                """),
                    row,
                )
            connection.execute(sa.text("SET session_replication_role = origin"))
        blocked = migrate("downgrade", "0077_fiscal_resource_claims", succeeds=False)
        assert "0077 downgrade blocked" in blocked.stderr
        with engine.begin() as connection:
            assert (
                connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
                == "0078_waste_tenant_idempotency"
            )
            assert (
                connection.scalar(
                    sa.text("""
                SELECT COUNT(*) FROM pg_constraint
                WHERE conname = 'uq_inventory_movements_org_idempotency'
                  AND conrelid = 'inventory_movements'::regclass
            """)
                )
                == 1
            )
            assert (
                connection.scalar(
                    sa.text(
                        "SELECT COUNT(*) FROM inventory_movements "
                        "WHERE idempotency_key = 'cross-tenant-key'"
                    )
                )
                == 2
            )
            connection.execute(
                sa.text("DELETE FROM inventory_movements WHERE id = ANY(:ids)"),
                {"ids": [row["id"] for row in rows]},
            )
            connection.execute(sa.text("SET session_replication_role = replica"))
            connection.execute(
                sa.text("""
                INSERT INTO inventory_movements (
                    id, organization_id, branch_id, warehouse_id, item_id, movement_type,
                    quantity_delta, unit_id, unit_cost, total_cost, effective_at, reason,
                    idempotency_key, status, created_at
                ) VALUES (
                    :id, :organization_id, :id, :id, :id, 'WASTE_REAL', -1, :id, 1, -1,
                    CURRENT_TIMESTAMP, 'synthetic migration fixture', 'preserved-key', 'confirmed',
                    CURRENT_TIMESTAMP
                )
            """),
                {"id": str(uuid4()), "organization_id": str(uuid4())},
            )
            connection.execute(sa.text("SET session_replication_role = origin"))
        migrate("downgrade", "0077_fiscal_resource_claims")
        migrate("upgrade", "head")
        with engine.begin() as connection:
            assert (
                connection.scalar(
                    sa.text(
                        "SELECT COUNT(*) FROM inventory_movements "
                        "WHERE idempotency_key = 'preserved-key'"
                    )
                )
                == 1
            )
    finally:
        engine.dispose()
        with base.begin() as connection:
            connection.execute(sa.schema.DropSchema(schema, cascade=True))
        base.dispose()
