"""Add coupons to branches, and coupon_code + discount_cents to orders and public_order_intents.

Revision ID: 0090_branch_coupons_and_order_discounts
Revises: 0089_dish_community_photos
Create Date: 2026-09-11 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0090_branch_coupons_and_order_discounts"
down_revision: str | None = "0089_dish_community_photos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("branches") as batch_op:
        batch_op.add_column(
            sa.Column(
                "coupons",
                sa.JSON(),
                nullable=False,
                server_default='[{"code": "MIMENU-GRACIAS10", "discount_percentage": 10, "is_active": true}]',
            )
        )

    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(
            sa.Column("coupon_code", sa.String(64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("discount_cents", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.create_check_constraint(
            "ck_orders_discount_cents_non_negative",
            "discount_cents >= 0",
        )

    with op.batch_alter_table("public_order_intents") as batch_op:
        batch_op.add_column(
            sa.Column("coupon_code", sa.String(64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("discount_cents", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.create_check_constraint(
            "ck_public_order_intents_discount_cents_non_negative",
            "discount_cents >= 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("public_order_intents") as batch_op:
        batch_op.drop_constraint(
            "ck_public_order_intents_discount_cents_non_negative", type_="check"
        )
        batch_op.drop_column("discount_cents")
        batch_op.drop_column("coupon_code")

    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_constraint(
            "ck_orders_discount_cents_non_negative", type_="check"
        )
        batch_op.drop_column("discount_cents")
        batch_op.drop_column("coupon_code")

    with op.batch_alter_table("branches") as batch_op:
        batch_op.drop_column("coupons")
