"""Stable public restaurant identities; preserve all existing public keys/history."""

from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0070_storefront_identity"
down_revision = "0069_add_slug_to_organizations_and_branches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # Additive rollback preserves issued URLs. A re-upgrade must preserve the same identities.
    columns = {column["name"] for column in sa.inspect(bind).get_columns("organizations")}
    if "slug" not in columns:
        op.add_column("organizations", sa.Column("slug", sa.String(80), nullable=True))
        op.create_index(
            "uq_organizations_slug", "organizations", ["slug"], unique=True
        )
    for org_id in (
        bind.execute(sa.text("SELECT id FROM organizations WHERE slug IS NULL"))
        .scalars()
        .all()
    ):
        bind.execute(
            sa.text("UPDATE organizations SET slug=:slug WHERE id=:id"),
            {"id": org_id, "slug": f"restaurant-{uuid4().hex}"},
        )
    # Normalize already-issued trial accounts so expiry guards apply to existing sessions.
    bind.execute(sa.text("UPDATE organizations SET subscription_status='trialing' WHERE plan='trial' AND subscription_status='active' AND trial_ends_at IS NOT NULL"))
    branches = bind.execute(
        sa.text(
            "SELECT b.id, b.organization_id FROM branches b WHERE b.status='active' AND NOT EXISTS "
            "(SELECT 1 FROM public_order_keys k WHERE k.branch_id=b.id)"
        )
    ).all()
    for branch_id, org_id in branches:
        bind.execute(
            sa.text(
                "INSERT INTO public_order_keys(public_key, organization_id, branch_id, status, created_at) "
                "VALUES (:key, :org, :branch, 'active', :now)"
            ),
            {
                "key": f"pk_{uuid4().hex}",
                "org": org_id,
                "branch": branch_id,
                "now": datetime.now(timezone.utc),
            },
        )


def downgrade() -> None:
    # Compatibility rollback: previous code ignores this nullable additive column.
    # Never destroy issued restaurant URLs or keys referenced by captured orders.
    # Re-upgrade above tolerates the retained column and preserves its values.
    pass
