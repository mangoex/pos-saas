"""Actual PostgreSQL column boundary and persistence in a disposable migrated schema."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import BusinessError, update_product
from sqlalchemy.orm import Session
from test_platform_api import ADMIN_USER_ID, _seed


def test_description_postgres_roundtrip():
    url = os.environ.get("SAAS_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Requires disposable PostgreSQL")
    base = sa.create_engine(url)
    schema = "product_description_" + uuid4().hex
    with base.begin() as conn:
        conn.execute(sa.schema.CreateSchema(schema))
    engine = sa.create_engine(
        sa.engine.make_url(url).update_query_dict({"options": f"-csearch_path={schema}"})
    )
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=120,
            env={
                **os.environ,
                "RESTAURANTOS_DATABASE_URL": engine.url.render_as_string(hide_password=False),
            },
        )
        assert result.returncode == 0, result.stderr
        with engine.begin() as conn:
            quote = conn.dialect.identifier_preparer.quote
            tables = [
                t for t in sa.inspect(conn).get_table_names(schema=schema) if t != "alembic_version"
            ]
            targets = ", ".join(f"{quote(schema)}.{quote(t)}" for t in tables)
            conn.execute(sa.text(f"TRUNCATE TABLE {targets} CASCADE"))
        pid = "018f6f73-2d0a-74f0-8f1c-000000000111"
        with Session(engine) as session:
            _seed(session)
            update_product(session, pid, actor_user_id=ADMIN_USER_ID, description="é" * 360)
        with Session(engine) as session:
            assert (
                session.scalar(
                    sa.select(models.products.c.description).where(models.products.c.id == pid)
                )
                == "é" * 360
            )
            with pytest.raises(BusinessError):
                update_product(session, pid, actor_user_id=ADMIN_USER_ID, description="x" * 361)
            session.rollback()
            update_product(session, pid, actor_user_id=ADMIN_USER_ID, description="")
        with Session(engine) as session:
            assert (
                session.scalar(
                    sa.select(models.products.c.description).where(models.products.c.id == pid)
                )
                == ""
            )
    finally:
        engine.dispose()
        with base.begin() as conn:
            conn.execute(sa.schema.DropSchema(schema, cascade=True))
        base.dispose()
