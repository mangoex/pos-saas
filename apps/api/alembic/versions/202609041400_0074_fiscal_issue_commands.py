"""Persist durable fiscal issue commands before external provider I/O."""

import sqlalchemy as sa
from alembic import op

revision = "0074_fiscal_issue_commands"
down_revision = "0073_pos_handoff_support_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("fiscal_commands"):
        return
    op.create_table(
        "fiscal_commands",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("operation_fingerprint", sa.String(64), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("order_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("provider_resource_id", sa.String(128), nullable=True),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("cfdi_invoices.id"), nullable=True),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("correlation_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'inflight', 'confirmed', 'unknown')",
            name="ck_fiscal_commands_status",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "operation",
            "operation_fingerprint",
            name="uq_fiscal_commands_operation",
        ),
    )
    op.create_index(
        "ix_fiscal_commands_reconcile", "fiscal_commands", ["organization_id", "status"]
    )


def downgrade() -> None:
    # Retain durable evidence of externally attempted fiscal work on rollback.
    pass
