from __future__ import annotations

import os
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.database import get_session
from restaurant_os.main import create_app
from sqlalchemy.orm import Session, sessionmaker
from test_platform_api import _admin_headers, _seed

PRODUCT_ID = "018f6f73-2d0a-74f0-8f1c-000000000111"
OPTIONS_A = [{"name": "Avena", "price_delta_cents": 900}]
OPTIONS_B = [{"name": "Almendra", "price_delta_cents": 1100}]


def _client(engine: sa.Engine) -> TestClient:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        _seed(session)
    app = create_app()

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.state.test_session_factory = factory
    return TestClient(app)


def _snapshot(client: TestClient) -> dict[str, list[dict[str, Any]]]:
    factory = client.app.state.test_session_factory
    with factory() as session:
        return {
            table.name: [dict(row) for row in session.execute(sa.select(table)).mappings()]
            for table in (
                models.products,
                models.price_versions,
                models.modifier_groups,
                models.modifier_options,
                models.audit_events,
            )
        }


def _revision(client: TestClient) -> str:
    response = client.get(
        f"/api/v1/products/{PRODUCT_ID}/simple-modifiers", headers=_admin_headers()
    )
    assert response.status_code == 200, response.text
    return response.json()["revision"]


def _update(
    client: TestClient,
    options: list[dict[str, Any]],
    revision: str,
    *,
    name: str,
    price_cents: int,
    headers: dict[str, str] | None = None,
) -> Any:
    return client.put(
        f"/api/v1/catalog/products/{PRODUCT_ID}",
        headers=headers or _admin_headers(),
        json={
            "name": name,
            "price_cents": price_cents,
            "simple_modifiers": {"options": options, "expected_revision": revision},
        },
    )


def _race_same_revision(client: TestClient) -> tuple[Any, Any]:
    revision = _revision(client)
    barrier = Barrier(2)

    def save(options: list[dict[str, Any]], name: str, price: int, key: str) -> Any:
        headers = _admin_headers()
        headers["Idempotency-Key"] = key
        barrier.wait(timeout=10)
        return _update(
            client,
            options,
            revision,
            name=name,
            price_cents=price,
            headers=headers,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(save, OPTIONS_A, "RACE-A", 4200, "simple-modifier-race-a")
        second = pool.submit(save, OPTIONS_B, "RACE-B", 4300, "simple-modifier-race-b")
        return first.result(timeout=20), second.result(timeout=20)


def _assert_one_winner_one_conflict(client: TestClient) -> None:
    responses = _race_same_revision(client)
    assert sorted(response.status_code for response in responses) == [200, 409], [
        response.text for response in responses
    ]
    loser = next(response for response in responses if response.status_code == 409)
    assert loser.json()["detail"]["code"] == "simple_modifiers_conflict"

    state = _snapshot(client)
    product = next(row for row in state["products"] if row["id"] == PRODUCT_ID)
    extras = next(
        row
        for row in state["modifier_groups"]
        if row["product_id"] == PRODUCT_ID and row["name"] == "Extras"
    )
    active_options = [
        row
        for row in state["modifier_options"]
        if row["group_id"] == extras["id"] and row["status"] == "active"
    ]
    current_price = next(
        row
        for row in state["price_versions"]
        if row["product_id"] == PRODUCT_ID and row["valid_to"] is None
    )
    assert product["name"] in {"RACE-A", "RACE-B"}
    if product["name"] == "RACE-A":
        assert current_price["price_cents"] == 4200
        assert [(row["name"], row["price_delta_cents"]) for row in active_options] == [
            ("Avena", 900)
        ]
    else:
        assert current_price["price_cents"] == 4300
        assert [(row["name"], row["price_delta_cents"]) for row in active_options] == [
            ("Almendra", 1100)
        ]
    modifier_audits = [
        row
        for row in state["audit_events"]
        if row["action"] == "product.simple_modifiers_saved" and row["entity_id"] == PRODUCT_ID
    ]
    assert len(modifier_audits) == 1


def _local_postgres_url() -> sa.engine.URL | None:
    raw_url = os.environ.get("SAAS_TEST_POSTGRES_URL")
    if not raw_url:
        return None
    url = sa.engine.make_url(raw_url)
    if url.get_backend_name() not in {"postgres", "postgresql"}:
        return None
    if url.host not in {"127.0.0.1", "localhost", "::1"}:
        return None
    return url


def test_postgres_same_revision_writes_have_one_atomic_winner() -> None:
    database_url = _local_postgres_url()
    if database_url is None:
        pytest.skip("Set SAAS_TEST_POSTGRES_URL to an opt-in local PostgreSQL URL")

    schema = "mobile_modifiers_" + uuid4().hex
    base_engine = sa.create_engine(database_url)
    with base_engine.begin() as connection:
        connection.execute(sa.schema.CreateSchema(schema))
    scoped_url = database_url.update_query_dict({"options": f"-csearch_path={schema}"})
    engine = sa.create_engine(scoped_url)
    try:
        models.metadata.create_all(engine)
        client = _client(engine)
        _assert_one_winner_one_conflict(client)
    finally:
        engine.dispose()
        with base_engine.begin() as connection:
            connection.execute(sa.schema.DropSchema(schema, cascade=True))
        base_engine.dispose()


def test_sqlite_file_same_revision_writes_have_one_atomic_winner(tmp_path: Path) -> None:
    engine = sa.create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'mobile-modifiers.db'}",
        connect_args={"check_same_thread": False, "timeout": 20},
    )
    try:
        models.metadata.create_all(engine)
        client = _client(engine)
        _assert_one_winner_one_conflict(client)
    finally:
        engine.dispose()


def test_postgres_option_write_failure_rolls_back_product_and_modifier_state() -> None:
    database_url = _local_postgres_url()
    if database_url is None:
        pytest.skip("Set SAAS_TEST_POSTGRES_URL to an opt-in local PostgreSQL URL")

    schema = "mobile_modifiers_" + uuid4().hex
    base_engine = sa.create_engine(database_url)
    with base_engine.begin() as connection:
        connection.execute(sa.schema.CreateSchema(schema))
    scoped_url = database_url.update_query_dict({"options": f"-csearch_path={schema}"})
    engine = sa.create_engine(scoped_url)
    try:
        models.metadata.create_all(engine)
        client = _client(engine)
        revision = _revision(client)
        before = _snapshot(client)

        def fail_option_insert(
            connection: Any,
            cursor: Any,
            statement: str,
            parameters: Any,
            context: Any,
            executemany: bool,
        ) -> None:
            if statement.lstrip().lower().startswith("insert into modifier_options"):
                raise RuntimeError("injected option write failure")

        sa.event.listen(engine, "before_cursor_execute", fail_option_insert)
        try:
            with pytest.raises(RuntimeError, match="injected option write failure"):
                _update(client, OPTIONS_A, revision, name="SHOULD-ROLLBACK", price_cents=4200)
        finally:
            sa.event.remove(engine, "before_cursor_execute", fail_option_insert)
        assert _snapshot(client) == before
    finally:
        engine.dispose()
        with base_engine.begin() as connection:
            connection.execute(sa.schema.DropSchema(schema, cascade=True))
        base_engine.dispose()
