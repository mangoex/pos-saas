"""Add dine_in_enabled to branches table.

Revision ID: 0093_add_dine_in_enabled
Revises: 0092_add_product_promotions
"""

from __future__ import annotations

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "0093_add_dine_in_enabled"
down_revision: str | None = "0092_add_product_promotions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("branches") as batch_op:
        batch_op.add_column(
            sa.Column("dine_in_enabled", sa.Boolean(), nullable=False, server_default=sa.true())
        )


def downgrade() -> None:
    with op.batch_alter_table("branches") as batch_op:
        batch_op.drop_column("dine_in_enabled")
