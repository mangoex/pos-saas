"""Add customer_id and customer_phone to customer_feedbacks.

Revision ID: 0085_add_customer_feedbacks_customer_id_and_phone
Revises: 0084_default_whatsapp_ordering_false
Create Date: 2026-09-09 18:00:00.000000
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0085_add_customer_feedbacks_customer_id_and_phone"
down_revision: str | None = "0084_default_whatsapp_ordering_false"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("customer_feedbacks") as batch:
        batch.add_column(
            sa.Column(
                "customer_id",
                sa.String(36),
                sa.ForeignKey("customers.id", name="fk_customer_feedbacks_customer_id"),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column("customer_phone", sa.String(32), nullable=True)
        )
        batch.create_index(
            "ix_customer_feedbacks_customer_id",
            ["customer_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("customer_feedbacks") as batch:
        batch.drop_index("ix_customer_feedbacks_customer_id")
        batch.drop_column("customer_phone")
        batch.drop_column("customer_id")
