# SEC001-SYNTHETIC-FIXTURE provenance=saas-mapping-migration-20260928
"""Additive mapping integrity migrates cleanly and refuses to rewrite invalid history."""

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.saas_onboarding import signup_tenant
from sqlalchemy.orm import Session

API_DIR = Path(__file__).resolve().parents[1]


def _signup(session, suffix):
    return signup_tenant(session, {
        "business_name": f"Migration {suffix}", "owner_name": suffix,
        "email": f"migration-{suffix}@example.test", "password": "synthetic-migration-password",
        "business_type": "blank",
    })


def _mapping(tenant, branch_id):
    now = datetime.now(timezone.utc)
    return {
        "id": str(uuid4()), "organization_id": tenant["organization"]["id"],
        "branch_id": branch_id, "provider": "UBER_EATS", "external_store_id": "migration-store",
        "is_active": True, "created_at": now, "updated_at": now,
    }


@pytest.fixture(params=["sqlite", "postgres"])
def migration_url(tmp_path, request):
    if request.param == "sqlite":
        yield f"sqlite:///{(tmp_path / 'mapping.sqlite3').as_posix()}"
        return
    postgres_url = os.environ.get("SAAS_TEST_POSTGRES_URL")
    if not postgres_url:
        pytest.skip("SAAS_TEST_POSTGRES_URL is not configured")
    schema = f"mapping_migration_{uuid4().hex}"
    engine = sa.create_engine(postgres_url)
    with engine.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    try:
        yield sa.engine.make_url(postgres_url).set(
            query={"options": f"-csearch_path={schema}"},
        ).render_as_string(hide_password=False)
    finally:
        with engine.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


@pytest.mark.parametrize("crossed", [False, True])
def test_mapping_migration_preserves_rows_or_fails_preflight(migration_url, crossed):
    url = migration_url

    def migrate(command, revision, success=True):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "alembic.ini", command, revision],
            cwd=API_DIR, env={**os.environ, "RESTAURANTOS_DATABASE_URL": url},
            capture_output=True, text=True, timeout=120,
        )
        if success:
            assert result.returncode == 0, result.stdout + result.stderr
        else:
            assert result.returncode != 0
            assert "mapping_tenant_branch_preflight_failed" in result.stderr

    migrate("upgrade", "0097_pickup_grace")
    engine = sa.create_engine(url)
    try:
        with Session(engine) as session:
            tenant_a, tenant_b = _signup(session, "a"), _signup(session, "b")
            values = _mapping(tenant_a, (tenant_b if crossed else tenant_a)["branch"]["id"])
            session.execute(models.channel_store_mappings.insert().values(**values))
            session.commit()
            before = dict(session.execute(
                sa.select(models.channel_store_mappings),
            ).mappings().one())
        migrate("upgrade", "0098_mapping_tenant_branch", success=not crossed)
        if not crossed:
            migrate("downgrade", "0097_pickup_grace")
            migrate("upgrade", "0098_mapping_tenant_branch")
        with engine.connect() as connection:
            after = dict(connection.execute(
                sa.select(models.channel_store_mappings),
            ).mappings().one())
            assert after == before
            head = connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
            assert head == ("0097_pickup_grace" if crossed else "0098_mapping_tenant_branch")
            foreign_keys = sa.inspect(connection).get_foreign_keys("channel_store_mappings")
            assert any(
                fk["name"] == "fk_channel_store_mapping_tenant_branch" for fk in foreign_keys
            ) is (not crossed)
    finally:
        engine.dispose()


def test_migrated_database_rejects_direct_cross_tenant_mapping(cash_scope_session):
    session = cash_scope_session
    if session.bind.dialect.name == "sqlite":
        session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
    tenant_a, tenant_b = _signup(session, "a"), _signup(session, "b")
    with pytest.raises(sa.exc.IntegrityError):
        session.execute(models.channel_store_mappings.insert().values(
            **_mapping(tenant_a, tenant_b["branch"]["id"]),
        ))
        session.commit()
    session.rollback()
