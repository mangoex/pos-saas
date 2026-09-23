# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-category-delete-v1
from typing import Any

import pytest
import sqlalchemy as sa
from restaurant_os import models
from test_platform_api import (
    ADMIN_USER_ID,
    _admin_headers,
    _client_with_seeded_database,
    _test_session_factory,
)


@pytest.fixture()
def catalog() -> Any:
    client = _client_with_seeded_database()
    factory = _test_session_factory(client)
    with factory() as session:
        product = (
            session.execute(
                sa.select(models.products).where(
                    models.products.c.id == "018f6f73-2d0a-74f0-8f1c-000000000111"
                )
            )
            .mappings()
            .one()
        )
        category_id = product["category_id"]
    return client, factory, category_id


def test_delete_category_scoped_and_idempotent(catalog: Any) -> None:
    client, factory, category_id = catalog
    with factory() as session:
        before = {p["id"]: dict(p) for p in session.execute(sa.select(models.products)).mappings()}
        category_rows = session.execute(sa.select(models.product_categories)).mappings().all()
        target_ids = [p["id"] for p in before.values() if p["category_id"] == category_id]
        prices = session.execute(sa.select(models.price_versions)).mappings().all()
    url = f"/api/v1/categories/{category_id}?delete_products=true"
    for _ in range(2):
        response = client.delete(url, headers=_admin_headers())
        assert response.status_code == 200, response.text
    with factory() as session:
        after = {p["id"]: dict(p) for p in session.execute(sa.select(models.products)).mappings()}
        assert before.keys() == after.keys()
        for pid in before:
            if pid in target_ids:
                assert after[pid]["status"] == "archived"
            else:
                assert after[pid] == before[pid]
        for cat in category_rows:
            current = (
                session.execute(
                    sa.select(models.product_categories).where(
                        models.product_categories.c.id == cat["id"]
                    )
                )
                .mappings()
                .one()
            )
            assert current["status"] == ("archived" if cat["id"] == category_id else cat["status"])
        assert session.execute(sa.select(models.price_versions)).mappings().all() == prices
        audit = (
            session.execute(
                sa.select(models.audit_events).where(
                    models.audit_events.c.action == "category.deleted"
                )
            )
            .mappings()
            .one()
        )
        assert sorted(p["id"] for p in audit["payload"]["products"]) == sorted(target_ids)
        assert audit["actor_user_id"] == ADMIN_USER_ID
    assert category_id not in {
        c["id"] for c in client.get("/api/v1/categories", headers=_admin_headers()).json()
    }
    assert not set(target_ids) & {
        p["id"] for p in client.get("/api/v1/catalog/products", headers=_admin_headers()).json()
    }


def test_confirmation_and_permission_required(catalog: Any) -> None:
    client, factory, category_id = catalog
    assert (
        client.delete(f"/api/v1/categories/{category_id}", headers=_admin_headers()).status_code
        == 409
    )
    assert client.delete(f"/api/v1/categories/{category_id}?delete_products=true").status_code in (
        401,
        403,
    )
    with factory() as session:
        assert (
            session.scalar(
                sa.select(models.product_categories.c.status).where(
                    models.product_categories.c.id == category_id
                )
            )
            != "archived"
        )


def test_stale_editors_cannot_restore(catalog: Any) -> None:
    client, factory, category_id = catalog
    with factory() as session:
        product_id = session.scalar(
            sa.select(models.products.c.id).where(models.products.c.category_id == category_id)
        )
        category_name = session.scalar(
            sa.select(models.product_categories.c.name).where(
                models.product_categories.c.id == category_id
            )
        )
    assert (
        client.delete(
            f"/api/v1/categories/{category_id}?delete_products=true", headers=_admin_headers()
        ).status_code
        == 200
    )
    for path, payload in [
        (f"/api/v1/catalog/products/{product_id}", {"status": "active"}),
        (f"/api/v1/categories/{category_id}", {"status": "active"}),
    ]:
        assert client.put(path, json=payload, headers=_admin_headers()).status_code == 409
    assert (
        client.delete(
            f"/api/v1/catalog/products/{product_id}", headers=_admin_headers()
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/categories", headers=_admin_headers(), json={"name": category_name}
        ).status_code
        == 409
    )


def test_atomic_audit_failure(catalog: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from restaurant_os import operations
    from restaurant_os.category_deletion import delete_category

    _, factory, category_id = catalog

    def fail(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("synthetic audit failure")

    monkeypatch.setattr(operations, "_audit", fail)
    with factory() as session:
        with pytest.raises(RuntimeError, match="synthetic audit failure"):
            delete_category(session, category_id, ADMIN_USER_ID, True)
        assert (
            session.scalar(
                sa.select(models.product_categories.c.status).where(
                    models.product_categories.c.id == category_id
                )
            )
            == "active"
        )
        assert (
            session.scalar(
                sa.select(sa.func.count())
                .select_from(models.products)
                .where(
                    models.products.c.category_id == category_id,
                    models.products.c.status == "archived",
                )
            )
            == 0
        )


def test_foreign_category_and_missing_permission(catalog: Any) -> None:
    client, factory, category_id = catalog
    with factory() as session:
        cat = dict(
            session.execute(
                sa.select(models.product_categories).where(
                    models.product_categories.c.id == category_id
                )
            )
            .mappings()
            .one()
        )
        org = dict(
            session.execute(
                sa.select(models.organizations).where(
                    models.organizations.c.id == cat["organization_id"]
                )
            )
            .mappings()
            .one()
        )
        org.update(id="foreign-delete-org", slug="foreign-delete-org")
        session.execute(models.organizations.insert().values(**org))
        cat.update(id="foreign-delete-category", organization_id=org["id"])
        session.execute(models.product_categories.insert().values(**cat))
        session.commit()
    assert (
        client.delete(
            "/api/v1/categories/foreign-delete-category?delete_products=true",
            headers=_admin_headers(),
        ).status_code
        == 409
    )
    with factory() as session:
        session.execute(
            models.user_roles.delete().where(models.user_roles.c.user_id == ADMIN_USER_ID)
        )
        session.commit()
    assert (
        client.delete(
            f"/api/v1/categories/{category_id}?delete_products=true", headers=_admin_headers()
        ).status_code
        == 403
    )


def test_existing_order_survives_and_empty_category(catalog: Any) -> None:
    from test_platform_api import BRANCH_ID

    client, factory, category_id = catalog
    with factory() as session:
        pid = session.scalar(
            sa.select(models.products.c.id).where(models.products.c.category_id == category_id)
        )
    shift = client.post(
        "/api/v1/cash-shifts/open",
        headers=_admin_headers(),
        json={"branch_id": BRANCH_ID, "register_id": "CAJA-01", "opening_cash_cents": 0},
    )
    assert shift.status_code == 200, shift.text
    order = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={"branch_id": BRANCH_ID, "lines": [{"product_id": pid, "quantity": 1}]},
    )
    assert order.status_code == 200, order.text
    detail_path = f"/api/v1/orders/{order.json()['id']}"
    before = client.get(detail_path, headers=_admin_headers()).json()
    assert (
        client.delete(
            f"/api/v1/categories/{category_id}?delete_products=true", headers=_admin_headers()
        ).status_code
        == 200
    )
    after = client.get(detail_path, headers=_admin_headers()).json()
    assert after["lines"] == before["lines"]
    assert after["total_cents"] == before["total_cents"]
    assert after["status"] == before["status"]
    empty = client.post(
        "/api/v1/categories", json={"name": "EMPTY QA"}, headers=_admin_headers()
    ).json()
    response = client.delete(
        f"/api/v1/categories/{empty['id']}?delete_products=true", headers=_admin_headers()
    )
    assert response.status_code == 200
    assert response.json()["archived_products"] == 0


def test_archived_names_reject_case_variants_and_rename(catalog: Any) -> None:
    from restaurant_os import operations
    from restaurant_os.legacy_import import _ensure_category

    client, factory, category_id = catalog
    with factory() as session:
        cat = (
            session.execute(
                sa.select(models.product_categories).where(
                    models.product_categories.c.id == category_id
                )
            )
            .mappings()
            .one()
        )
        name, org = cat["name"], cat["organization_id"]
    assert (
        client.delete(
            f"/api/v1/categories/{category_id}?delete_products=true", headers=_admin_headers()
        ).status_code
        == 200
    )
    for helper in (
        lambda s: operations._get_or_create_category(s, name.lower(), operations._now(), org),
        lambda s: _ensure_category(s, org, name.lower()),
    ):
        with factory() as session, pytest.raises(operations.BusinessError) as err:
            helper(session)
        assert err.value.code == "category_archived"
    other = client.post(
        "/api/v1/categories", headers=_admin_headers(), json={"name": "OTHER QA"}
    ).json()
    response = client.put(
        f"/api/v1/categories/{other['id']}", headers=_admin_headers(), json={"name": name}
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "category_exists"


@pytest.mark.parametrize("archived_target", ["category", "product"])
def test_excel_loader_cannot_reactivate(
    catalog: Any, monkeypatch: pytest.MonkeyPatch, archived_target: str
) -> None:
    import pandas as pd
    import restaurant_os.real_catalog_loader as loader
    from restaurant_os.operations import BusinessError
    from restaurant_os.real_catalog_loader import load_real_catalog_from_excels

    _, factory, cid = catalog
    with factory() as session:
        cat = (
            session.execute(
                sa.select(models.product_categories).where(models.product_categories.c.id == cid)
            )
            .mappings()
            .one()
        )
        org, name = cat["organization_id"], cat["name"]
        product = (
            session.execute(sa.select(models.products).where(models.products.c.category_id == cid))
            .mappings()
            .first()
        )
        session.execute(
            models.products.update()
            .where(models.products.c.id == product["id"])
            .values(sku="PROD-ARCHIVE-QA", status="archived")
        )
        if archived_target == "category":
            session.execute(
                models.product_categories.update()
                .where(models.product_categories.c.id == cid)
                .values(status="archived")
            )
        session.commit()
    monkeypatch.setattr(loader.os.path, "exists", lambda p: str(p).endswith("PRODUCTOS.XLS"))
    monkeypatch.setattr(
        loader.pd,
        "read_excel",
        lambda *a, **kw: pd.DataFrame(
            [{"CLAVE": "ARCHIVE-QA", "DESCRIPCION": "QA", "GRUPODEPRODUCTOS": name, "PRECIO": 10}]
        ),
    )
    with factory() as session, pytest.raises(BusinessError) as err:
        load_real_catalog_from_excels(session, organization_id=org, import_customers=False)
    assert err.value.code == archived_target + "_archived"
    with factory() as session:
        assert (
            session.scalar(
                sa.select(models.products.c.status).where(models.products.c.id == product["id"])
            )
            == "archived"
        )
