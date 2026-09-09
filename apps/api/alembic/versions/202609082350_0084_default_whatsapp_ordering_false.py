"""Default branches.whatsapp_ordering_enabled to false.

Revision ID: 0084_default_whatsapp_ordering_false
Revises: 0083_add_branches_whatsapp_ordering
Create Date: 2026-09-08 23:50:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0084_default_whatsapp_ordering_false"
down_revision: str | None = "0083_add_branches_whatsapp_ordering"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "branches",
        "whatsapp_ordering_enabled",
        server_default=sa.false(),
    )
    # Set existing branches to false by default so WhatsApp ordering is strictly opt-in
    op.execute("UPDATE branches SET whatsapp_ordering_enabled = false WHERE whatsapp_ordering_enabled IS TRUE")


def downgrade() -> None:
    op.alter_column(
        "branches",
        "whatsapp_ordering_enabled",
        server_default=sa.true(),
    )
