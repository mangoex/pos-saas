"""HTTP boundary regressions for the recipe-only PCO-007 workspace."""

from __future__ import annotations

from collections.abc import Generator

from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.database import get_session
from restaurant_os.main import create_app
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from test_cash_concepts import (
    BRANCH_A,
    BRANCH_B,
    CASHIER_ID,
    OWNER_ID,
    OWNER_ROLE_ID,
)
from test_pco007_recipe_reports import ITEM_ID, PRODUCT_ID, UNIT_ID, _seed_recipe_scope


def _client() -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        # Shared seed gives actual branch/user/role FKs; recipe permission is intentionally scoped.
        from test_cash_concepts import _seed_cash_concept_scope

        _seed_cash_concept_scope(session)
        _seed_recipe_scope(session)
        recipe_permission = (
            session.execute(
                models.permissions.select().where(models.permissions.c.code == "recipes.manage")
            )
            .mappings()
            .one()
        )
        session.execute(
            models.role_permissions.insert().values(
                role_id=OWNER_ROLE_ID, permission_id=recipe_permission["id"]
            )
        )
        session.commit()
    app = create_app()

    def override() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    return TestClient(app)


def test_recipe_workspace_fails_closed_at_the_saas_boundary() -> None:
    client = _client()
    requests = (
        client.get("/api/v1/recipes/workspace", headers={"X-Actor-User-Id": CASHIER_ID}),
        client.get(
            f"/api/v1/recipes/workspace?branch_id={BRANCH_A}",
            headers={"X-Actor-User-Id": CASHIER_ID},
        ),
        client.get(
            f"/api/v1/recipes/workspace?branch_id={BRANCH_B}",
            headers={"X-Actor-User-Id": CASHIER_ID},
        ),
        client.get("/api/v1/recipes/workspace", headers={"X-Actor-User-Id": OWNER_ID}),
    )

    for response in requests:
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "feature_out_of_saas_scope"


def test_recipe_write_requires_actor_then_fails_closed_at_the_saas_boundary() -> None:
    client = _client()
    base = {
        "branch_id": BRANCH_A,
        "expected_active_recipe_id": None,
        "yield_quantity": 1,
        "yield_unit_id": UNIT_ID,
        "components": [
            {"item_id": ITEM_ID, "unit_id": UNIT_ID, "net_quantity": 1, "waste_rate": 0}
        ],
    }
    path = f"/api/v1/products/{PRODUCT_ID}/recipe"
    actor_headers = {"X-Actor-User-Id": CASHIER_ID}
    missing_actor = client.put(path, json=base, headers={"Idempotency-Key": "http-key"})
    assert missing_actor.status_code == 401
    response = client.put(
        path,
        json=base,
        headers={**actor_headers, "Idempotency-Key": "http-recipe-out-of-scope"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "feature_out_of_saas_scope"
