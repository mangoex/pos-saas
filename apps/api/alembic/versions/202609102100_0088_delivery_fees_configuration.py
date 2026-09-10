"""Add delivery fees configuration to branches, orders and public_order_intents.

Revision ID: 0088_delivery_fees_configuration
Revises: 0087_widen_image_url_columns
Create Date: 2026-09-10 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0088_delivery_fees_configuration"
down_revision: str | None = "0087_widen_image_url_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("branches") as batch_op:
        batch_op.add_column(
            sa.Column("delivery_fee_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("delivery_tiers", sa.JSON(), nullable=False, server_default="[]")
        )
        batch_op.add_column(
            sa.Column("free_delivery_min_cents", sa.Integer(), nullable=True)
        )

    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(
            sa.Column("delivery_fee_cents", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.create_check_constraint(
            "ck_orders_delivery_fee_cents_non_negative",
            "delivery_fee_cents >= 0",
        )

    with op.batch_alter_table("public_order_intents") as batch_op:
        batch_op.add_column(
            sa.Column("delivery_fee_cents", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.create_check_constraint(
            "ck_public_order_intents_delivery_fee_non_negative",
            "delivery_fee_cents >= 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("public_order_intents") as batch_op:
        batch_op.drop_constraint("ck_public_order_intents_delivery_fee_non_negative", type_="check")
        batch_op.drop_column("delivery_fee_cents")

    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_constraint("ck_orders_delivery_fee_cents_non_negative", type_="check")
        batch_op.drop_column("delivery_fee_cents")

    with op.batch_alter_table("branches") as batch_op:
        batch_op.drop_column("free_delivery_min_cents")
        batch_op.drop_column("delivery_tiers")
        batch_op.drop_column("delivery_fee_enabled")
