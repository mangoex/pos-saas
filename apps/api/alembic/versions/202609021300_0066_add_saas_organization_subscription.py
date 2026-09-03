"""Add subscription fields to organizations and is_superadmin to users.

Revision ID: 0066_add_saas_organization_subscription
Revises: 0065_add_products_delivery_price
"""

from __future__ import annotations

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "0066_add_saas_organization_subscription"
down_revision: str | None = "0065_add_products_delivery_price"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Organizations subscription & contact columns
    op.add_column("organizations", sa.Column("plan", sa.String(32), nullable=False, server_default="trial"))
    op.add_column("organizations", sa.Column("subscription_status", sa.String(32), nullable=False, server_default="active"))
    op.add_column("organizations", sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("organizations", sa.Column("monthly_fee_cents", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("organizations", sa.Column("suspended_reason", sa.String(255), nullable=True))
    op.add_column("organizations", sa.Column("owner_name", sa.String(160), nullable=True))
    op.add_column("organizations", sa.Column("owner_email", sa.String(160), nullable=True))
    op.add_column("organizations", sa.Column("owner_phone", sa.String(32), nullable=True))
    op.add_column("organizations", sa.Column("business_type", sa.String(32), nullable=True))

    # Users is_superadmin column
    op.add_column("users", sa.Column("is_superadmin", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("users", "is_superadmin")
    op.drop_column("organizations", "business_type")
    op.drop_column("organizations", "owner_phone")
    op.drop_column("organizations", "owner_email")
    op.drop_column("organizations", "owner_name")
    op.drop_column("organizations", "suspended_reason")
    op.drop_column("organizations", "monthly_fee_cents")
    op.drop_column("organizations", "trial_ends_at")
    op.drop_column("organizations", "subscription_status")
    op.drop_column("organizations", "plan")
