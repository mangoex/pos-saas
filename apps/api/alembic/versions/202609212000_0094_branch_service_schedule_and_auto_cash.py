"""Add service_schedule, auto_cash_shift_enabled and auto_cash_opening_cents to branches.

Revision ID: 0094_branch_service_schedule_and_auto_cash
Revises: 0093_add_dine_in_enabled
Create Date: 2026-09-21 20:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0094_branch_service_schedule_and_auto_cash"
down_revision: str | None = "0093_add_dine_in_enabled"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("branches") as batch_op:
        batch_op.add_column(
            sa.Column("service_schedule", sa.JSON(), nullable=False, server_default="[]")
        )
        batch_op.add_column(
            sa.Column(
                "auto_cash_shift_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "auto_cash_opening_cents",
                sa.Integer(),
                nullable=False,
                server_default="50000",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("branches") as batch_op:
        batch_op.drop_column("auto_cash_opening_cents")
        batch_op.drop_column("auto_cash_shift_enabled")
        batch_op.drop_column("service_schedule")
