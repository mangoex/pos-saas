"""Add accepts_cash_payments, accepts_card_payments and bank_transfer_info to branches.

Revision ID: 0095_branch_payment_methods_and_bank_info
Revises: 0094_branch_service_schedule_and_auto_cash
Create Date: 2026-09-21 22:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0095_branch_payment_methods_and_bank_info"
down_revision: str | None = "0094_branch_service_schedule_and_auto_cash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("branches") as batch_op:
        batch_op.add_column(
            sa.Column(
                "accepts_cash_payments",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "accepts_card_payments",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "bank_transfer_info",
                sa.JSON(),
                nullable=False,
                server_default="{}",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("branches") as batch_op:
        batch_op.drop_column("bank_transfer_info")
        batch_op.drop_column("accepts_card_payments")
        batch_op.drop_column("accepts_cash_payments")
