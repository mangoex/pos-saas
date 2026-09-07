"""Tenant-scoped idempotency for real-waste commands."""

from alembic import op
import sqlalchemy as sa

revision = "0078_waste_tenant_idempotency"
down_revision = "0077_fiscal_resource_claims"
branch_labels = None
depends_on = None


def _drop_legacy_postgresql_constraints() -> None:
    op.execute(sa.text(
        "ALTER TABLE inventory_movements DROP CONSTRAINT IF EXISTS uq_inventory_movements_idempotency"
    ))
    op.execute(sa.text(
        "ALTER TABLE inventory_movements DROP CONSTRAINT IF EXISTS inventory_movements_idempotency_key_key"
    ))
    op.execute(sa.text(
        "ALTER TABLE waste_records DROP CONSTRAINT IF EXISTS waste_records_confirmation_idempotency_key_key"
    ))
    op.execute(sa.text(
        "ALTER TABLE waste_records DROP CONSTRAINT IF EXISTS waste_records_reversal_idempotency_key_key"
    ))


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _drop_legacy_postgresql_constraints()
        op.create_unique_constraint(
            "uq_inventory_movements_org_idempotency",
            "inventory_movements",
            ["organization_id", "idempotency_key"],
        )
        op.create_unique_constraint(
            "uq_waste_records_confirmation_idempotency",
            "waste_records",
            ["organization_id", "confirmation_idempotency_key"],
        )
        op.create_unique_constraint(
            "uq_waste_records_reversal_idempotency",
            "waste_records",
            ["organization_id", "reversal_idempotency_key"],
        )
        return
    convention = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
    with op.batch_alter_table("inventory_movements", recreate="always", naming_convention=convention) as batch:
        batch.drop_constraint("uq_inventory_movements_idempotency", type_="unique")
        batch.create_unique_constraint(
            "uq_inventory_movements_org_idempotency", ["organization_id", "idempotency_key"]
        )
    with op.batch_alter_table("waste_records", recreate="always", naming_convention=convention) as batch:
        batch.drop_constraint("uq_waste_records_confirmation_idempotency_key", type_="unique")
        batch.drop_constraint("uq_waste_records_reversal_idempotency_key", type_="unique")
        batch.create_unique_constraint(
            "uq_waste_records_confirmation_idempotency",
            ["organization_id", "confirmation_idempotency_key"],
        )
        batch.create_unique_constraint(
            "uq_waste_records_reversal_idempotency",
            ["organization_id", "reversal_idempotency_key"],
        )



def _assert_downgrade_safe(bind: sa.Connection) -> None:
    duplicate_key = bind.execute(
        sa.text(
            """
            SELECT idempotency_key FROM inventory_movements
            WHERE idempotency_key IS NOT NULL
            GROUP BY idempotency_key
            HAVING COUNT(DISTINCT organization_id) > 1
            UNION ALL
            SELECT confirmation_idempotency_key FROM waste_records
            WHERE confirmation_idempotency_key IS NOT NULL
            GROUP BY confirmation_idempotency_key
            HAVING COUNT(DISTINCT organization_id) > 1
            UNION ALL
            SELECT reversal_idempotency_key FROM waste_records
            WHERE reversal_idempotency_key IS NOT NULL
            GROUP BY reversal_idempotency_key
            HAVING COUNT(DISTINCT organization_id) > 1
            LIMIT 1
            """
        )
    ).scalar_one_or_none()
    if duplicate_key is not None:
        raise RuntimeError(
            "0077 downgrade blocked: tenant-scoped idempotency keys overlap; "
            "global uniqueness cannot be restored without deleting history"
        )


def downgrade() -> None:
    bind = op.get_bind()
    _assert_downgrade_safe(bind)
    if bind.dialect.name == "postgresql":
        op.drop_constraint("uq_waste_records_reversal_idempotency", "waste_records", type_="unique")
        op.drop_constraint("uq_waste_records_confirmation_idempotency", "waste_records", type_="unique")
        op.drop_constraint("uq_inventory_movements_org_idempotency", "inventory_movements", type_="unique")
        op.create_unique_constraint(
            "waste_records_confirmation_idempotency_key_key",
            "waste_records",
            ["confirmation_idempotency_key"],
        )
        op.create_unique_constraint(
            "waste_records_reversal_idempotency_key_key",
            "waste_records",
            ["reversal_idempotency_key"],
        )
        op.create_unique_constraint(
            "uq_inventory_movements_idempotency", "inventory_movements", ["idempotency_key"]
        )
        return
    convention = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
    with op.batch_alter_table("waste_records", recreate="always", naming_convention=convention) as batch:
        batch.drop_constraint("uq_waste_records_reversal_idempotency", type_="unique")
        batch.drop_constraint("uq_waste_records_confirmation_idempotency", type_="unique")
        batch.create_unique_constraint(
            "uq_waste_records_confirmation_idempotency_key", ["confirmation_idempotency_key"]
        )
        batch.create_unique_constraint(
            "uq_waste_records_reversal_idempotency_key", ["reversal_idempotency_key"]
        )
    with op.batch_alter_table("inventory_movements", recreate="always", naming_convention=convention) as batch:
        batch.drop_constraint("uq_inventory_movements_org_idempotency", type_="unique")
        batch.create_unique_constraint(
            "uq_inventory_movements_idempotency", ["idempotency_key"]
        )
