"""Real PostgreSQL constraint races and reversible additive schema."""

import os
import secrets
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.database import get_session
from restaurant_os.main import create_app
from sqlalchemy.orm import Session


def test_domain_claim_race_and_migration_history():
    url = os.environ.get("SAAS_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("SAAS_TEST_POSTGRES_URL required")
    base = sa.create_engine(url)
    schema = "domain_qa_" + uuid4().hex
    with base.begin() as conn:
        conn.execute(sa.schema.CreateSchema(schema))
    scoped = sa.engine.make_url(url).update_query_dict({"options": f"-csearch_path={schema}"})
    engine = sa.create_engine(scoped)

    def migrate(*args):
        return subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=120,
            env={
                **os.environ,
                "RESTAURANTOS_DATABASE_URL": scoped.render_as_string(hide_password=False),
            },
        )

    try:
        assert migrate("upgrade", "head").returncode == 0
        assert migrate("downgrade", "0080_delivery_inbox_idempotency").returncode == 0
        assert migrate("upgrade", "head").returncode == 0
        app = create_app()

        def sessions():
            with Session(engine) as session:
                yield session

        app.dependency_overrides[get_session] = sessions
        client = TestClient(app)
        headers = []
        for name in ("tacos", "sushi"):
            result = client.post(
                "/api/v1/auth/signup",
                json={
                    "business_name": name,
                    "owner_name": name,
                    "email": name + "@example.com",
                    "password": secrets.token_urlsafe(24),
                    "plan": "trial",
                    "defer_catalog": True,
                },
            )
            assert result.status_code == 201, result.text
            headers.append({"Authorization": "Bearer " + result.json()["token"]})
        for route, payload in [
            ("/domains", {"hostname": "orders.race.example.com"}),
            ("/links/alias", {"alias": "concurrent-tacos"}),
        ]:
            barrier = Barrier(2)

            def claim(header, barrier=barrier, route=route, payload=payload):
                barrier.wait(timeout=10)
                method = client.post if route == "/domains" else client.put
                return method("/api/v1/saas" + route, headers=header, json=payload).status_code

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(claim, headers))
            assert sorted(results) == [200, 409]
        mixed_barrier = Barrier(2)

        def alias_or_branch(index):
            mixed_barrier.wait(timeout=10)
            if index == 0:
                return client.put(
                    "/api/v1/saas/links/alias",
                    headers=headers[0],
                    json={"alias": "mixed-race-name"},
                ).status_code
            return client.post(
                "/api/v1/branches",
                headers=headers[1],
                json={"name": "Race", "code": "MIXED-RACE-NAME"},
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(alias_or_branch, (0, 1))) == [200, 409]
        assert client.get("/api/v1/public/storefronts/mixed-race-name").status_code == 200
        with Session(engine) as session:
            alias_count = session.scalar(
                sa.select(sa.func.count()).select_from(models.storefront_aliases)
            )
        rollback = migrate("downgrade", "0080_delivery_inbox_idempotency")
        assert rollback.returncode != 0
        assert "preserve domain/alias history" in rollback.stderr
        with Session(engine) as session:
            assert (
                session.scalar(sa.select(sa.func.count()).select_from(models.restaurant_domains))
                == 1
            )
            assert (
                session.scalar(sa.select(sa.func.count()).select_from(models.storefront_aliases))
                == alias_count
            )
            assert (
                session.scalar(sa.text("select version_num from alembic_version"))
                == "0081_restaurant_domains"
            )
    finally:
        engine.dispose()
        with base.begin() as conn:
            conn.execute(sa.schema.DropSchema(schema, cascade=True))
        base.dispose()
