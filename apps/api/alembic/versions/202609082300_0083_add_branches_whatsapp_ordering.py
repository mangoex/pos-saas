"""Add whatsapp_ordering_enabled to branches.

Revision ID: 0083_add_branches_whatsapp_ordering
Revises: 0082_category_presentation
Create Date: 2026-09-08 23:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0083_add_branches_whatsapp_ordering"
down_revision: str | None = "0082_category_presentation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "branches",
        sa.Column(
            "whatsapp_ordering_enabled",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("branches", "whatsapp_ordering_enabled")
