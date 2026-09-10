"""Widen image_url and menu_home_image_url columns to Text.

Revision ID: 0087_widen_image_url_columns
Revises: 0086_secure_customer_feedback_reference
Create Date: 2026-09-10 20:00:00.000000

Allows mobile camera captures and photo gallery uploads (Base64 Data URLs)
without triggering VARCHAR(512) StringDataRightTruncation errors.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0087_widen_image_url_columns"
down_revision: str | None = "0086_secure_customer_feedback_reference"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("products") as batch_op:
        batch_op.alter_column(
            "image_url",
            type_=sa.Text(),
            existing_type=sa.String(512),
            nullable=True,
        )
    with op.batch_alter_table("product_categories") as batch_op:
        batch_op.alter_column(
            "image_url",
            type_=sa.Text(),
            existing_type=sa.String(512),
            nullable=True,
        )
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.alter_column(
            "menu_home_image_url",
            type_=sa.Text(),
            existing_type=sa.String(512),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.alter_column(
            "menu_home_image_url",
            type_=sa.String(512),
            existing_type=sa.Text(),
            nullable=True,
        )
    with op.batch_alter_table("product_categories") as batch_op:
        batch_op.alter_column(
            "image_url",
            type_=sa.String(512),
            existing_type=sa.Text(),
            nullable=True,
        )
    with op.batch_alter_table("products") as batch_op:
        batch_op.alter_column(
            "image_url",
            type_=sa.String(512),
            existing_type=sa.Text(),
            nullable=True,
        )
