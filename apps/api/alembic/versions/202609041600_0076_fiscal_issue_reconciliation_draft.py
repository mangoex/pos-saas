"""Retain the minimum local invoice draft required to reconcile known provider work."""

import sqlalchemy as sa
from alembic import op

revision = "0076_fiscal_issue_reconciliation_draft"
down_revision = "0075_fiscal_issue_order_claims"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("fiscal_commands")
    }
    if "invoice_draft" not in columns:
        op.add_column("fiscal_commands", sa.Column("invoice_draft", sa.JSON(), nullable=True))


def downgrade() -> None:
    # Preserve reconciliation data on rollback while unknown fiscal commands exist.
    pass
