"""Create subscriptions table

Revision ID: 0091_create_subscriptions_table
Revises: 0090_branch_coupons_and_order_discounts
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0091_create_subscriptions_table"
down_revision: str | None = "0090_branch_coupons_and_order_discounts"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("restaurant_id", sa.String(36), nullable=False),
        sa.Column("customer_id", sa.String(255), nullable=False),
        sa.Column("preapproval_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("next_billing_date", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["restaurant_id"], ["organizations.id"], ondelete="CASCADE"
        ),
    )

def downgrade() -> None:
    op.drop_table("subscriptions")
