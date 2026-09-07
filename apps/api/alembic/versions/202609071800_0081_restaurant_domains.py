"""Reserve public aliases and supervised domains without changing canonical identity."""

import sqlalchemy as sa
from alembic import op

revision = "0081_restaurant_domains"
down_revision = "0080_delivery_inbox_idempotency"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("organizations", sa.Column("preferred_public_slug", sa.String(80), nullable=True))
    op.create_table(
        "storefront_aliases",
        sa.Column("alias", sa.String(80), primary_key=True),
        sa.Column(
            "organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "restaurant_domains",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("hostname", sa.String(253), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("verification_token", sa.String(100), nullable=False),
        sa.Column("last_result", sa.String(40), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending_dns','pending_tls','active','disabled')",
            name="ck_restaurant_domain_status",
        ),
    )


def downgrade():
    # Public printed aliases/domain reservations cannot be silently recycled by rollback.
    bind = op.get_bind()
    if any(
        bind.scalar(sa.text(f"SELECT COUNT(*) FROM {name}"))
        for name in ("storefront_aliases", "restaurant_domains")
    ):
        raise RuntimeError("Export and preserve domain/alias history before schema rollback")
    op.drop_table("restaurant_domains")
    op.drop_table("storefront_aliases")
    op.drop_column("organizations", "preferred_public_slug")
