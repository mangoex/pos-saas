"""Exclusive resource claims for durable fiscal receipt and cancellation commands."""

import sqlalchemy as sa
from alembic import op

revision = "0077_fiscal_resource_claims"
down_revision = "0076_fiscal_issue_reconciliation_draft"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("fiscal_command_resource_claims"):
        return
    op.create_table(
        "fiscal_command_resource_claims",
        sa.Column(
            "organization_id", sa.String(36), sa.ForeignKey("organizations.id"), primary_key=True
        ),
        sa.Column("operation", sa.String(32), primary_key=True),
        sa.Column("target_id", sa.String(36), primary_key=True),
        sa.Column("command_id", sa.String(36), sa.ForeignKey("fiscal_commands.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    pass
