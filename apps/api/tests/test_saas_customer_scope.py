# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-test-saas-customer-scope-synthetic-v1
"""Customer directory and snapshots are scoped to the restaurant owning the order."""

import sqlalchemy as sa
from restaurant_os import models
from test_saas_onboarding import _client_with_db


def test_customer_directory_mutations_and_search_never_cross_restaurants():
    client = _client_with_db()
    tenants = []
    for name in ("a", "b"):
        response = client.post(
            "/api/v1/auth/signup",
            json={
                "business_name": f"Customer QA {name}",
                "owner_name": name,
                "email": f"customer-owner-{name}@example.test",
                "password": "synthetic-customer-password",
                "business_type": "blank",
            },
        )
        assert response.status_code == 201, response.text
        tenants.append(response.json())
    first, other = tenants
    headers_a = {"Authorization": f"Bearer {first['token']}"}
    headers_b = {"Authorization": f"Bearer {other['token']}"}
    created = client.post(
        "/api/v1/customers",
        headers=headers_a,
        json={
            "name": "Customer A",
            "branch_id": first["branch"]["id"],
            "phones": [],
        },
    )
    assert created.status_code == 200, created.text
    customer_id = created.json()["id"]
    with client.app.state.test_session_factory() as session:
        assert (
            session.scalar(
                sa.select(models.customers.c.organization_id).where(
                    models.customers.c.id == customer_id
                )
            )
            == first["organization"]["id"]
        )
    own = client.get("/api/v1/customers", headers=headers_a)
    assert own.status_code == 200, own.text
    assert [row["id"] for row in own.json()] == [customer_id]
    foreign = client.get("/api/v1/customers", headers=headers_b)
    assert foreign.status_code == 200, foreign.text
    assert foreign.json() == []
    update = client.put(
        f"/api/v1/customers/{customer_id}", headers=headers_b, json={"name": "Intrusion"}
    )
    assert update.status_code in (403, 404, 409), update.text
    with client.app.state.test_session_factory() as session:
        assert (
            session.scalar(
                sa.select(models.customers.c.name).where(models.customers.c.id == customer_id)
            )
            == "Customer A"
        )

    address_ids = []
    for index in range(2):
        address = client.post(
            f"/api/v1/customers/{customer_id}/addresses",
            headers=headers_a,
            json={
                "branch_id": first["branch"]["id"],
                "alias": f"Home {index}",
                "street": "Original",
                "exterior_number": "1",
                "neighborhood": "Centro",
                "postal_code": "80000",
                "city": "Culiacán",
                "municipality": "Culiacán",
                "state": "Sinaloa",
                "is_default": index == 0,
            },
        )
        assert address.status_code == 200, address.text
        address_ids.append(address.json()["id"])
    before = None
    with client.app.state.test_session_factory() as session:
        before = [
            dict(row)
            for row in session.execute(
                sa.select(models.customer_addresses)
                .where(models.customer_addresses.c.customer_id == customer_id)
                .order_by(models.customer_addresses.c.id)
            ).mappings()
        ]
    denied = client.put(
        f"/api/v1/customers/{customer_id}/addresses/{address_ids[1]}",
        headers=headers_b,
        json={"branch_id": other["branch"]["id"], "street": "Intrusion", "is_default": True},
    )
    assert denied.status_code in (403, 404, 409), denied.text
    with client.app.state.test_session_factory() as session:
        after = [
            dict(row)
            for row in session.execute(
                sa.select(models.customer_addresses)
                .where(models.customer_addresses.c.customer_id == customer_id)
                .order_by(models.customer_addresses.c.id)
            ).mappings()
        ]
        assert after == before
    allowed = client.put(
        f"/api/v1/customers/{customer_id}/addresses/{address_ids[1]}",
        headers=headers_a,
        json={"branch_id": first["branch"]["id"], "street": "Updated by owner", "is_default": True},
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["street"] == "Updated by owner"
