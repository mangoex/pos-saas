"""Issued public URLs survive additive schema and image rollback."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_identity_upgrade_rollback_preserves_keys_and_urls():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/202609041000_0070_storefront_identity.py"
    )
    spec = spec_from_file_location("storefront_migration", path)
    assert spec and spec.loader
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE organizations(id TEXT PRIMARY KEY, slug TEXT UNIQUE, "
                "plan TEXT, subscription_status TEXT, trial_ends_at DATETIME)"
            )
        )
        connection.execute(
            sa.text("CREATE TABLE branches(id TEXT PRIMARY KEY, organization_id TEXT, status TEXT)")
        )
        connection.execute(
            sa.text(
                "CREATE TABLE public_order_keys(public_key TEXT PRIMARY KEY, organization_id TEXT, "
                "branch_id TEXT, status TEXT, created_at DATETIME)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO organizations VALUES "
                "('one','issued-restaurant','trial','active','2026-09-21'), "
                "('two',NULL,'trial','active',NULL)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO branches VALUES ('b-one','one','active'), "
                "('b-two','two','active'), ('b-revoked','two','active')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO public_order_keys VALUES ('issued-key','one','b-one','active',NULL)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO public_order_keys VALUES "
                "('revoked-key','two','b-revoked','revoked',NULL)"
            )
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            before = connection.execute(
                sa.text("SELECT id, slug FROM organizations ORDER BY id")
            ).all()
            keys_before = (
                connection.execute(
                    sa.text("SELECT public_key FROM public_order_keys ORDER BY public_key")
                )
                .scalars()
                .all()
            )
            assert len({row.slug for row in before}) == 2
            assert before[0].slug == "issued-restaurant"
            assert (
                connection.scalar(
                    sa.text("SELECT subscription_status FROM organizations WHERE id='one'")
                )
                == "trialing"
            )
            assert len(keys_before) == 3
            assert (
                connection.scalar(
                    sa.text(
                        "SELECT COUNT(*) FROM public_order_keys WHERE branch_id='b-revoked' "
                        "AND status='active'"
                    )
                )
                == 0
            )
            assert "issued-key" in keys_before
            assert (
                connection.scalar(
                    sa.text("SELECT subscription_status FROM organizations WHERE id='two'")
                )
                == "active"
            )
            migration.downgrade()
            migration.upgrade()
            assert (
                connection.execute(sa.text("SELECT id, slug FROM organizations ORDER BY id")).all()
                == before
            )
            assert (
                connection.execute(
                    sa.text("SELECT public_key FROM public_order_keys ORDER BY public_key")
                )
                .scalars()
                .all()
                == keys_before
            )
