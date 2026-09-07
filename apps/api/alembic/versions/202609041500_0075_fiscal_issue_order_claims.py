"""Atomically claim every order covered by a durable fiscal issue command."""

import sqlalchemy as sa
from alembic import op

revision = "0075_fiscal_issue_order_claims"
down_revision = "0074_fiscal_issue_commands"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("fiscal_command_order_claims"):
        return
    op.create_table(
        "fiscal_command_order_claims",
        sa.Column(
            "organization_id", sa.String(36), sa.ForeignKey("organizations.id"), primary_key=True
        ),
        sa.Column("operation", sa.String(32), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), primary_key=True),
        sa.Column("command_id", sa.String(36), sa.ForeignKey("fiscal_commands.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_fiscal_command_claims_command", "fiscal_command_order_claims", ["command_id"]
    )


def downgrade() -> None:
    # Claims preserve the no-reissue barrier when rolling the application image back.
    pass
