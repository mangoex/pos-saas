"""Add slug columns to organizations and branches tables.

Revision ID: 0069_add_slug_to_organizations_and_branches
Revises: 0068_add_organizations_mobile_theme
"""

from __future__ import annotations

import re
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "0069_add_slug_to_organizations_and_branches"
down_revision: str | None = "0068_add_organizations_mobile_theme"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("slug", sa.String(80), nullable=True),
    )
    op.create_index(
        "ix_organizations_slug",
        "organizations",
        ["slug"],
        unique=True,
    )
    op.add_column(
        "branches",
        sa.Column("slug", sa.String(80), nullable=True),
    )

    # Backfill slugs for existing organizations if any exist
    conn = op.get_bind()
    try:
        org_rows = conn.execute(sa.text("SELECT id, name FROM organizations WHERE slug IS NULL")).fetchall()
        for r in org_rows:
            org_id, org_name = str(r[0]), str(r[1])
            cleaned = re.sub(r"[^a-z0-9]+", "-", org_name.lower()).strip("-") or "org"
            short_suffix = org_id.replace("-", "")[:6]
            slug = f"{cleaned[:30]}-{short_suffix}"
            conn.execute(
                sa.text("UPDATE organizations SET slug = :slug WHERE id = :id"),
                {"slug": slug, "id": org_id},
            )
    except Exception:
        pass


def downgrade() -> None:
    op.drop_column("branches", "slug")
    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_column("organizations", "slug")
