"""Persist resumable onboarding without rewriting existing restaurant history."""

import sqlalchemy as sa
from alembic import op

revision = "0071_saas_setup"
down_revision = "0070_storefront_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("organizations")}
    if "onboarding_step" not in columns:
        op.add_column(
            "organizations",
            sa.Column("onboarding_step", sa.String(16), nullable=False, server_default="complete"),
        )
    if "onboarding_register_name" not in columns:
        op.add_column("organizations", sa.Column("onboarding_register_name", sa.String(80)))


def downgrade() -> None:
    # Previous runtime ignores additive columns; preserve progress across image rollback.
    pass
