"""Add product promotions (is_promo, promo_price_cents, promo_badge_text) to products table.

Revision ID: 0092_add_product_promotions
Revises: 0091_create_subscriptions_table
"""

from __future__ import annotations

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "0092_add_product_promotions"
down_revision: str | None = "0091_create_subscriptions_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("is_promo", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("products", sa.Column("promo_price_cents", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("promo_badge_text", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "promo_badge_text")
    op.drop_column("products", "promo_price_cents")
    op.drop_column("products", "is_promo")
