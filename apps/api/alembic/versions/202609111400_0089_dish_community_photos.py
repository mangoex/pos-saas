"""Add dish_community_photos table for UGC and social proof.

Revision ID: 0089_dish_community_photos
Revises: 0088_delivery_fees_configuration
Create Date: 2026-09-11 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0089_dish_community_photos"
down_revision: str | None = "0088_delivery_fees_configuration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dish_community_photos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("order_folio", sa.String(64), nullable=True),
        sa.Column("customer_name", sa.String(160), nullable=False),
        sa.Column("customer_phone", sa.String(32), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("discount_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_dish_community_photos_status",
        ),
    )
    op.create_index(
        "ix_dish_community_photos_product_status",
        "dish_community_photos",
        ["product_id", "status"],
    )
    op.create_index(
        "ix_dish_community_photos_branch_status",
        "dish_community_photos",
        ["branch_id", "status"],
    )
    op.create_index(
        "ix_dish_community_photos_org_created",
        "dish_community_photos",
        ["organization_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_dish_community_photos_org_created", table_name="dish_community_photos")
    op.drop_index("ix_dish_community_photos_branch_status", table_name="dish_community_photos")
    op.drop_index("ix_dish_community_photos_product_status", table_name="dish_community_photos")
    op.drop_table("dish_community_photos")
