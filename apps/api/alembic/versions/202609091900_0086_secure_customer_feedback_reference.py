"""Secure customer feedback order references.

Revision ID: 0086_secure_customer_feedback_reference
Revises: 0085_add_customer_feedbacks_customer_id_and_phone
Create Date: 2026-09-09 19:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0086_secure_customer_feedback_reference"
down_revision: str | None = "0085_add_customer_feedbacks_customer_id_and_phone"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    duplicate = (
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT organization_id, branch_id, order_folio, COUNT(*) AS row_count
                FROM customer_feedbacks
                WHERE order_folio IS NOT NULL
                GROUP BY organization_id, branch_id, order_folio
                HAVING COUNT(*) > 1
                LIMIT 1
                """
            )
        )
        .mappings()
        .first()
    )
    if duplicate:
        raise RuntimeError(
            "0086 blocked: duplicate customer feedback order references require reviewed "
            "forward remediation before the uniqueness gate can be installed"
        )
    op.create_index(
        "uq_customer_feedbacks_order_reference",
        "customer_feedbacks",
        ["organization_id", "branch_id", "order_folio"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_customer_feedbacks_order_reference",
        table_name="customer_feedbacks",
    )
