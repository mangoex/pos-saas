# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-test-saas-postgres-release-synthetic-v1
"""Real PostgreSQL release path in a disposable, uniquely named schema."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.database import get_session
from restaurant_os.main import create_app
from restaurant_os.superadmin.service import provision_platform_superadmin
from sqlalchemy.orm import sessionmaker


def test_full_migrations_signup_onboarding_and_identity_rollback():
    database_url = os.environ.get("SAAS_TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("SAAS_TEST_POSTGRES_URL is required for PostgreSQL release verification")
    schema = "saas_release_" + uuid4().hex
    base = sa.create_engine(database_url)
    with base.begin() as connection:
        connection.execute(sa.schema.CreateSchema(schema))
    scoped_url = sa.engine.make_url(database_url).update_query_dict(
        {"options": f"-csearch_path={schema}"}
    )
    engine = sa.create_engine(scoped_url)
    session_factory = sessionmaker(bind=engine)
    api_dir = Path(__file__).resolve().parents[1]
    migration_env = dict(
        os.environ, RESTAURANTOS_DATABASE_URL=scoped_url.render_as_string(hide_password=False)
    )

    def migrate(*args):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
            cwd=api_dir,
            env=migration_env,
            text=True,
            capture_output=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr

    try:
        migrate("upgrade", "head")
        app = create_app()

        def dependency():
            with session_factory() as session:
                yield session

        app.dependency_overrides[get_session] = dependency
        client = TestClient(app)
        signup = client.post(
            "/api/v1/auth/signup",
            json={
                "business_name": "Postgres QA",
                "owner_name": "QA Owner",
                "email": "postgres-owner@example.test",
                "password": "synthetic-postgres-password",
                "business_type": "blank",
            },
        )
        assert signup.status_code == 201, signup.text
        data = signup.json()
        headers = {"Authorization": f"Bearer {data['token']}"}
        with session_factory() as session:
            provision_platform_superadmin(
                session,
                email="postgres-support@example.test",
                password="synthetic-postgres-support-password",
                display_name="QA Support",
            )
        login = client.post(
            "/api/v1/auth/login",
            json={
                "email": "postgres-support@example.test",
                "password": "synthetic-postgres-support-password",
            },
        )
        assert login.status_code == 200, login.text
        support = client.post(
            f"/api/v1/superadmin/tenants/{data['organization']['id']}/impersonate",
            headers={"Authorization": f"Bearer {login.json()['token']}"},
        )
        assert support.status_code == 200, support.text
        support_headers = {"Authorization": f"Bearer {support.json()['token']}"}
        steps = [
            {
                "step": "business",
                "business_name": "Postgres QA",
                "branch_name": "QA",
                "timezone": "America/Mexico_City",
            },
            {"step": "menu", "business_type": "taqueria"},
            {"step": "register", "register_name": "CAJA-QA"},
        ]
        for step in steps:
            response = client.put(
                "/api/v1/saas/onboarding",
                headers=support_headers if step["step"] == "business" else headers,
                json=step,
            )
            assert response.status_code == 200, response.text
        org_id = data["organization"]["id"]
        with session_factory() as session:
            before = (
                session.execute(
                    sa.select(models.organizations).where(models.organizations.c.id == org_id)
                )
                .mappings()
                .one()
            )
            key = session.scalar(
                sa.select(models.public_order_keys.c.public_key).where(
                    models.public_order_keys.c.organization_id == org_id
                )
            )
            assert before["onboarding_step"] == "complete"
        url = f"/api/v1/public/storefronts/{before['slug']}"
        assert client.get(url).status_code == 200
        from datetime import datetime, timezone

        pending_id = str(uuid4())
        pending_handoff_id = str(uuid4())
        pending_handoff_correlation = str(uuid4())
        with session_factory() as session:
            product_id = session.scalar(
                sa.select(models.products.c.id).where(models.products.c.organization_id == org_id)
            )
            now = datetime.now(timezone.utc)
            session.execute(
                models.channel_availability_sync_jobs.insert().values(
                    id=pending_id,
                    organization_id=org_id,
                    branch_id=data["branch"]["id"],
                    provider="UBER_EATS",
                    external_store_id="qa-store",
                    external_item_id="qa-item",
                    product_id=product_id,
                    is_available=False,
                    desired_version=1,
                    status="PENDING",
                    attempts=0,
                    next_attempt_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
            support_actor_id = session.scalar(
                sa.select(models.users.c.id).where(models.users.c.is_superadmin.is_(True))
            )
            assert support_actor_id
            session.execute(
                models.pos_session_handoffs.insert().values(
                    id=pending_handoff_id,
                    organization_id=org_id,
                    user_id=data["user"]["id"],
                    support_real_actor_user_id=support_actor_id,
                    support_correlation_id=pending_handoff_correlation,
                    target_app="pos",
                    code_hash=hashlib.sha256(b"pending-pg-handoff").hexdigest(),
                    created_at=now,
                    expires_at=now,
                    consumed_at=None,
                )
            )
            session.commit()
        migrate("downgrade", "0069_add_slug_to_organizations_and_branches")
        migrate("upgrade", "head")
        storefront = client.get(url)
        assert storefront.status_code == 200, storefront.text
        assert storefront.json()["branches"][0]["public_key"] == key
        with session_factory() as session:
            after = (
                session.execute(
                    sa.select(models.organizations).where(models.organizations.c.id == org_id)
                )
                .mappings()
                .one()
            )
            assert after["onboarding_step"] == "complete"
            assert after["onboarding_register_name"] == "CAJA-QA"
            pending_handoff = session.execute(
                sa.select(models.pos_session_handoffs).where(
                    models.pos_session_handoffs.c.id == pending_handoff_id
                )
            ).mappings().one()
            assert pending_handoff["consumed_at"] is None
            assert pending_handoff["organization_id"] == org_id
            assert pending_handoff["support_real_actor_user_id"] == support_actor_id
            assert pending_handoff["support_correlation_id"] == pending_handoff_correlation
            assert (
                session.scalar(
                    sa.select(models.channel_availability_sync_jobs.c.status).where(
                        models.channel_availability_sync_jobs.c.id == pending_id
                    )
                )
                == "PENDING"
            )
    finally:
        engine.dispose()
        with base.begin() as connection:
            connection.execute(sa.schema.DropSchema(schema, cascade=True))
        base.dispose()
