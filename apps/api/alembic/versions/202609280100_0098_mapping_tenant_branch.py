"""Enforce tenant/branch identity in external store mappings without rewriting history."""

from alembic import op
import sqlalchemy as sa

revision = "0098_mapping_tenant_branch"
down_revision = "0097_pickup_grace"
branch_labels = None
depends_on = None

CONSTRAINT = "fk_channel_store_mapping_tenant_branch"


def upgrade() -> None:
    bind = op.get_bind()
    invalid = bind.scalar(sa.text("""
        SELECT COUNT(*) FROM channel_store_mappings AS mapping
        LEFT JOIN branches AS branch
          ON branch.id = mapping.branch_id
         AND branch.organization_id = mapping.organization_id
        WHERE branch.id IS NULL
    """))
    if invalid:
        raise RuntimeError(
            "mapping_tenant_branch_preflight_failed: inconsistent mappings require "
            "explicit reconciliation; no rows have been deleted or reassigned"
        )
    with op.batch_alter_table("channel_store_mappings") as batch:
        batch.create_foreign_key(
            CONSTRAINT, "branches", ["organization_id", "branch_id"], ["organization_id", "id"]
        )


def downgrade() -> None:
    # Preserve every mapping and provider identifier; only remove this additional guard.
    with op.batch_alter_table("channel_store_mappings") as batch:
        batch.drop_constraint(CONSTRAINT, type_="foreignkey")
