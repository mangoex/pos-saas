"""Deterministic concurrent catalog archival in a disposable PostgreSQL schema."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy as sa
from restaurant_os import models, operations
from restaurant_os.category_deletion import delete_category
from sqlalchemy.orm import sessionmaker
from test_platform_api import ADMIN_USER_ID, _seed


@pytest.mark.parametrize("winner", ["delete", "create", "move"])
def test_serialized_membership(winner: str, monkeypatch: pytest.MonkeyPatch) -> None:
    url = os.environ.get("SAAS_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("SAAS_TEST_POSTGRES_URL is required")
    base = sa.create_engine(url)
    schema = "category_delete_" + uuid4().hex
    with base.begin() as conn:
        conn.execute(sa.schema.CreateSchema(schema))
    engine = sa.create_engine(
        sa.engine.make_url(url).update_query_dict({"options": f"-csearch_path={schema}"})
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    paused, release, contender = Event(), Event(), Event()
    original_audit = operations._audit
    wanted = {"delete": "category.deleted", "create": "product.created", "move": "product.updated"}[
        winner
    ]

    def audit(*args: Any, **kwargs: Any) -> None:
        original_audit(*args, **kwargs)
        if kwargs["action"] == wanted and not paused.is_set():
            paused.set()
            assert release.wait(15), "test coordinator did not release transaction"

    def observe(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, many: Any
    ) -> None:
        if paused.is_set() and "organizations" in statement and "FOR UPDATE" in statement:
            contender.set()

    try:
        migration = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=Path(__file__).resolve().parents[1],
            env={
                **os.environ,
                "RESTAURANTOS_DATABASE_URL": engine.url.render_as_string(hide_password=False),
            },
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert migration.returncode == 0, migration.stderr
        # Migrations include legacy seed rows. Reset only this disposable schema.
        with engine.begin() as conn:
            quote = conn.dialect.identifier_preparer.quote
            tables = [
                name
                for name in sa.inspect(conn).get_table_names(schema=schema)
                if name != "alembic_version"
            ]
            targets = ", ".join(f"{quote(schema)}.{quote(name)}" for name in tables)
            conn.execute(sa.text(f"TRUNCATE TABLE {targets} CASCADE"))
        with factory() as session:
            _seed(session)
            pid = "018f6f73-2d0a-74f0-8f1c-000000000111"
            cid = session.scalar(
                sa.select(models.products.c.category_id).where(models.products.c.id == pid)
            )
            cname = session.scalar(
                sa.select(models.product_categories.c.name).where(
                    models.product_categories.c.id == cid
                )
            )
            # Public mutations require canonical category names for the demo tenant.
            cname = cname.upper()
            session.execute(
                models.product_categories.update()
                .where(models.product_categories.c.id == cid)
                .values(name=cname)
            )
            session.commit()
        monkeypatch.setattr(operations, "_audit", audit)
        sa.event.listen(engine, "before_cursor_execute", observe)

        def remove() -> Any:
            with factory() as session:
                return delete_category(session, cid, ADMIN_USER_ID, True)

        def create() -> Any:
            with factory() as session:
                try:
                    return operations.create_product(
                        session,
                        name="NEW PRODUCT",
                        sku="999991",
                        category_name=cname,
                        station="kitchen",
                        price_cents=100,
                        actor_user_id=ADMIN_USER_ID,
                    )
                except operations.BusinessError as exc:
                    return exc.code

        def move() -> Any:
            with factory() as session:
                return operations.update_product(
                    session, pid, category_name="OTHER QA", actor_user_id=ADMIN_USER_ID
                )

        first = {"delete": remove, "create": create, "move": move}[winner]
        second = create if winner == "delete" else remove
        with ThreadPoolExecutor(max_workers=2) as pool:
            primary = pool.submit(first)
            try:
                assert paused.wait(10)
                secondary = pool.submit(second)
                assert contender.wait(10)
            finally:
                release.set()
            primary.result(timeout=15)
            result = secondary.result(timeout=15)
        if winner == "delete":
            assert result == "category_archived"
        with factory() as session:
            assert (
                session.scalar(
                    sa.select(sa.func.count())
                    .select_from(models.products)
                    .where(
                        models.products.c.category_id == cid, models.products.c.status != "archived"
                    )
                )
                == 0
            )
            if winner == "move":
                assert (
                    session.scalar(
                        sa.select(models.products.c.status).where(models.products.c.id == pid)
                    )
                    == "active"
                )
    finally:
        release.set()
        engine.dispose()
        with base.begin() as conn:
            conn.execute(sa.schema.DropSchema(schema, cascade=True))
        base.dispose()
