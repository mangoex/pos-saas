"""Add delivery_price_cents to products table for SaaS differentiated channel pricing.

Revision ID: 0065_add_products_delivery_price
Revises: 0064_add_branches_google_review_url
"""

from __future__ import annotations

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "0065_add_products_delivery_price"
down_revision: str | None = "0064_add_branches_google_review_url"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("delivery_price_cents", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "delivery_price_cents")
