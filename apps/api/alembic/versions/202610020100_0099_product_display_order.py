"""Add display_order column and index to products table for manual catalog ordering."""

import sqlalchemy as sa
from alembic import op

revision = "0099_product_display_order"
down_revision = "0098_mapping_tenant_branch"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("products") as batch_op:
        batch_op.add_column(
            sa.Column("display_order", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.create_index(
            "ix_products_category_display_order",
            ["category_id", "display_order"],
        )


def downgrade() -> None:
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_index("ix_products_category_display_order")
        batch_op.drop_column("display_order")
