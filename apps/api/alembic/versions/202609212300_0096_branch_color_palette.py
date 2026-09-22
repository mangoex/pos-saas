"""Add color_palette to branches.

Revision ID: 0096_branch_color_palette
Revises: 0095_branch_payment_methods_and_bank_info
Create Date: 2026-09-21 23:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0096_branch_color_palette"
down_revision: str | None = "0095_branch_payment_methods_and_bank_info"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("branches") as batch_op:
        batch_op.add_column(
            sa.Column(
                "color_palette",
                sa.String(32),
                nullable=False,
                server_default="orange",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("branches") as batch_op:
        batch_op.drop_column("color_palette")
