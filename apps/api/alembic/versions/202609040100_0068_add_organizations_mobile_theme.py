"""Add mobile_theme column to organizations table.

Revision ID: 0068_add_organizations_mobile_theme
Revises: 0067_cleanup_kiwi_branding_and_legacy_data
"""

from __future__ import annotations

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "0068_add_organizations_mobile_theme"
down_revision: str | None = "0067_cleanup_kiwi_branding_and_legacy_data"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("mobile_theme", sa.String(16), nullable=False, server_default="light"),
    )


def downgrade() -> None:
    op.drop_column("organizations", "mobile_theme")
