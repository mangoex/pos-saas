"""Create subscriptions table

Revision ID: 0089_create_subscriptions_table
Revises: 0088_delivery_fees_configuration
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0089_create_subscriptions_table"
down_revision: str | None = "0088_delivery_fees_configuration"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("restaurant_id", sa.Uuid(), nullable=False),
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
