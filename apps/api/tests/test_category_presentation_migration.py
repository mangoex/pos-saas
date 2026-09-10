"""Additive upgrade preserves legacy rows; rollback never silently erases media."""

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


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
def test_presentation_upgrade_and_protected_rollback(tmp_path, dialect):
    url = (
        os.environ.get("SAAS_TEST_POSTGRES_URL")
        if dialect == "postgresql"
        else ("sqlite:///" + (tmp_path / "presentation.db").as_posix())
    )
    if not url:
        pytest.skip("SAAS_TEST_POSTGRES_URL required")
    base = sa.create_engine(url)
    schema = "media_qa_" + uuid4().hex
    scoped = sa.engine.make_url(url)
    if dialect == "postgresql":
        with base.begin() as conn:
            conn.execute(sa.schema.CreateSchema(schema))
        scoped = scoped.update_query_dict({"options": f"-csearch_path={schema}"})
    engine = sa.create_engine(scoped)

    def migrate(action, target):
        return subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "alembic.ini", action, target],
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
        result = migrate("upgrade", "0081_restaurant_domains")
        assert result.returncode == 0, result.stderr
        org, category = str(uuid4()), str(uuid4())
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO organizations (id,name,created_at,updated_at) "
                    "VALUES (:id,'Legacy menu',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ),
                {"id": org},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO product_categories "
                    "(id,organization_id,name,created_at,updated_at) VALUES "
                    "(:id,:org,'Tacos',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ),
                {"id": category, "org": org},
            )
        result = migrate("upgrade", "head")
        assert result.returncode == 0, result.stderr
        with engine.connect() as conn:
            assert conn.execute(
                sa.text(
                    "SELECT menu_home_name,menu_home_image_url FROM organizations WHERE id=:id"
                ),
                {"id": org},
            ).one() == ("Todos", None)
            assert conn.execute(
                sa.text("SELECT name,image_url FROM product_categories WHERE id=:id"),
                {"id": category},
            ).one() == ("Tacos", None)
        assert migrate("downgrade", "0081_restaurant_domains").returncode == 0
        assert migrate("upgrade", "head").returncode == 0
        if dialect == "postgresql":
            verify_concurrent_category_audit(engine)
        with engine.begin() as conn:
            conn.execute(
                sa.text("UPDATE organizations SET menu_home_name='Nuestra carta' WHERE id=:id"),
                {"id": org},
            )
        blocked = migrate("downgrade", "0081_restaurant_domains")
        assert blocked.returncode != 0
        assert "preserve menu presentation" in blocked.stderr
        with engine.connect() as conn:
            expected_revision = (
                "0086_secure_customer_feedback_reference"
                if dialect == "postgresql"
                else "0082_category_presentation"
            )
            assert (
                conn.scalar(sa.text("SELECT version_num FROM alembic_version"))
                == expected_revision
            )
            assert (
                conn.scalar(
                    sa.text("SELECT menu_home_name FROM organizations WHERE id=:id"), {"id": org}
                )
                == "Nuestra carta"
            )
    finally:
        engine.dispose()
        if dialect == "postgresql":
            with base.begin() as conn:
                conn.execute(sa.schema.DropSchema(schema, cascade=True))
        base.dispose()


def verify_concurrent_category_audit(engine):
    app = create_app()

    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    client = TestClient(app)
    account = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Media race",
            "owner_name": "QA",
            "email": "media-race@example.test",
            "password": secrets.token_urlsafe(24),
            "plan": "trial",
            "defer_catalog": True,
        },
    )
    assert account.status_code == 201, account.text
    header = {"Authorization": "Bearer " + account.json()["token"]}
    category = client.post("/api/v1/categories", headers=header, json={"name": "Concurrent media"})
    assert category.status_code == 200, category.text
    category_id = category.json()["id"]
    barrier = Barrier(2)
    images = {"https://example.test/a.jpg", "https://example.test/b.jpg"}

    def update(url):
        barrier.wait(timeout=10)
        result = client.put(
            f"/api/v1/categories/{category_id}", headers=header, json={"image_url": url}
        )
        assert result.status_code == 200, result.text

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(update, images))
    with engine.connect() as conn:
        events = (
            conn.execute(
                sa.select(models.audit_events.c.payload)
                .where(
                    models.audit_events.c.entity_id == category_id,
                    models.audit_events.c.action == "category.updated",
                )
                .order_by(models.audit_events.c.created_at)
            )
            .scalars()
            .all()
        )
        current = conn.scalar(
            sa.select(models.product_categories.c.image_url).where(
                models.product_categories.c.id == category_id
            )
        )
    assert len(events) == 2
    assert events[0]["before"]["image_url"] is None
    assert events[0]["after"] == events[1]["before"]
    assert {e["after"]["image_url"] for e in events} == images
    assert current == events[1]["after"]["image_url"]
