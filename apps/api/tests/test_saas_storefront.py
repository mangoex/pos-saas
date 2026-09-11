"""Public restaurant identity must never fall back to a different tenant."""

from datetime import datetime, timezone

import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.database import get_session
from restaurant_os.main import create_app
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def client_for_restaurants() -> tuple[TestClient, sa.Engine]:
    engine = sa.create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    models.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        for name, code in [("tacos", "ADMELG"), ("sushi", "PILOTO")]:
            session.execute(
                models.organizations.insert().values(
                    id=name, name=name, slug=name, created_at=now, updated_at=now
                )
            )
            session.execute(
                models.legal_entities.insert().values(
                    id=name, organization_id=name, name=name, created_at=now, updated_at=now
                )
            )
            session.execute(
                models.business_units.insert().values(
                    id=name,
                    organization_id=name,
                    legal_entity_id=name,
                    name=name,
                    code=name,
                    unit_type="restaurant",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.execute(
                models.branches.insert().values(
                    id=f"branch-{name}",
                    organization_id=name,
                    legal_entity_id=name,
                    business_unit_id=name,
                    name=name,
                    code=code,
                    timezone="UTC",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.execute(
                models.public_order_keys.insert().values(
                    public_key=f"key-{name}",
                    organization_id=name,
                    branch_id=f"branch-{name}",
                    status="active",
                    created_at=now,
                )
            )
        session.commit()
    app = create_app()

    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    return TestClient(app), engine


def test_exact_alias_resolves_only_tacos_and_never_piloto():
    client, _ = client_for_restaurants()
    response = client.get("/api/v1/public/storefronts/admelg")
    assert response.status_code == 200
    assert response.json()["organization"]["id"] == "tacos"
    assert [b["id"] for b in response.json()["branches"]] == ["branch-tacos"]
    assert response.json()["selected_branch_id"] == "branch-tacos"


def test_unknown_partial_and_ambiguous_aliases_never_fallback():
    client, engine = client_for_restaurants()
    for identifier in ["unknown", "admel", "pi"]:
        assert client.get(f"/api/v1/public/storefronts/{identifier}").status_code == 404
    with Session(engine) as session:
        session.execute(models.branches.update().values(code="SHARED"))
        session.commit()
    assert client.get("/api/v1/public/storefronts/shared").status_code == 409


def test_suspended_restaurant_is_not_public():
    client, engine = client_for_restaurants()
    with Session(engine) as session:
        session.execute(
            models.organizations.update()
            .where(models.organizations.c.id == "tacos")
            .values(subscription_status="suspended")
        )
        session.commit()
    assert client.get("/api/v1/public/storefronts/tacos").status_code == 403


def test_manifest_has_tenant_identity_and_narrow_scope():
    client, _ = client_for_restaurants()
    response = client.get("/api/v1/public/storefronts/admelg/manifest.webmanifest")
    assert response.status_code == 200
    manifest = response.json()
    assert manifest["name"] == "tacos"
    assert manifest["id"] == "/menu/tacos/"
    assert manifest["start_url"] == "/menu/tacos/"
    assert manifest["scope"] == "/menu/tacos/"
    assert manifest["icons"][0]["src"].endswith("/tacos/icon.svg")
    icon_response = client.get(manifest["icons"][0]["src"])
    assert icon_response.status_code == 200
    assert "image/svg+xml" in icon_response.headers["content-type"]


def test_canonical_slug_resolves_without_alias_or_selected_branch():
    client, _ = client_for_restaurants()
    response = client.get("/api/v1/public/storefronts/tacos")
    assert response.status_code == 200
    assert response.json()["selected_branch_id"] is None
    assert len(response.json()["branches"]) == 1


def test_legacy_public_catalog_and_branch_list_require_explicit_restaurant():
    client, _ = client_for_restaurants()
    assert client.get("/api/v1/public/catalog").status_code == 422
    assert client.get("/api/v1/public/branches").status_code == 422
    branches = client.get("/api/v1/public/branches", params={"identifier": "admelg"})
    assert branches.status_code == 200
    assert [branch["id"] for branch in branches.json()] == ["branch-tacos"]
    catalog = client.get("/api/v1/public/catalog", params={"public_key": "key-tacos"})
    assert catalog.status_code == 200
    assert catalog.json()["branch_id"] == "branch-tacos"


def test_public_read_does_not_provision_missing_keys():
    client, engine = client_for_restaurants()
    with Session(engine) as session:
        session.execute(
            models.public_order_keys.delete().where(
                models.public_order_keys.c.branch_id == "branch-tacos"
            )
        )
        session.commit()
    assert client.get("/api/v1/public/storefronts/tacos").status_code == 409
    with Session(engine) as session:
        assert (
            session.scalar(
                sa.select(sa.func.count())
                .select_from(models.public_order_keys)
                .where(models.public_order_keys.c.branch_id == "branch-tacos")
            )
            == 0
        )


def test_order_key_resolver_never_accepts_branch_alias_or_suspended_tenant():
    from restaurant_os.api import _resolve_active_public_order_key

    _, engine = client_for_restaurants()
    with Session(engine) as session:
        assert _resolve_active_public_order_key(session, "ADMELG") is None
        assert _resolve_active_public_order_key(session, "key-tacos") is not None
        session.execute(
            models.organizations.update()
            .where(models.organizations.c.id == "tacos")
            .values(subscription_status="suspended")
        )
        assert _resolve_active_public_order_key(session, "key-tacos") is None
