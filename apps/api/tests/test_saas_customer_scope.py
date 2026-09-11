# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-test-saas-customer-scope-synthetic-v1
"""Customer directory and snapshots are scoped to the restaurant owning the order."""

import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.superadmin.service import provision_platform_superadmin
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


def _login_superadmin(client) -> dict[str, str]:
    with client.app.state.test_session_factory() as session:
        provision_platform_superadmin(
            session,
            email="platform-superadmin@example.test",
            password="test-platform-superadmin-password",
            display_name="Platform Superadmin",
        )
    resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": "platform-superadmin@example.test",
            "password": "test-platform-superadmin-password",
        },
    )
    assert resp.status_code == 200, f"Superadmin login failed: {resp.text}"
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_superadmin_can_view_customers_across_all_organizations_and_filter_by_tenant():
    client = _client_with_db()
    tenants = []
    for name in ("tacos", "pizza"):
        resp = client.post(
            "/api/v1/auth/signup",
            json={
                "business_name": f"Restaurante {name.capitalize()}",
                "owner_name": f"Owner {name}",
                "email": f"owner-{name}@example.test",
                "password": "synthetic-customer-password",
                "business_type": "blank",
            },
        )
        assert resp.status_code == 201, resp.text
        tenants.append(resp.json())

    tacos, pizza = tenants
    headers_tacos = {"Authorization": f"Bearer {tacos['token']}"}
    headers_pizza = {"Authorization": f"Bearer {pizza['token']}"}

    c_tacos = client.post(
        "/api/v1/customers",
        headers=headers_tacos,
        json={
            "name": "Cliente de Tacos",
            "branch_id": tacos["branch"]["id"],
            "phones": [{"number": "6691112233", "is_primary": True}],
        },
    )
    assert c_tacos.status_code == 200, c_tacos.text
    tacos_cust_id = c_tacos.json()["id"]

    c_pizza = client.post(
        "/api/v1/customers",
        headers=headers_pizza,
        json={
            "name": "Cliente de Pizza",
            "branch_id": pizza["branch"]["id"],
            "phones": [{"number": "6694445566", "is_primary": True}],
        },
    )
    assert c_pizza.status_code == 200, c_pizza.text
    pizza_cust_id = c_pizza.json()["id"]

    headers_sa = _login_superadmin(client)

    # 1. Superadmin can query all customers across all tenants
    global_res = client.get("/api/v1/customers?all_organizations=true", headers=headers_sa)
    assert global_res.status_code == 200, global_res.text
    global_items = global_res.json()
    all_ids = {c["id"] for c in global_items}
    assert tacos_cust_id in all_ids
    assert pizza_cust_id in all_ids

    # Check enrichment with organization_name and origin_branch_name
    tacos_item = next(c for c in global_items if c["id"] == tacos_cust_id)
    assert tacos_item["organization_name"] == "Restaurante Tacos"
    assert tacos_item["organization_id"] == tacos["organization"]["id"]
    assert tacos_item["origin_branch_name"] == tacos["branch"]["name"]

    pizza_item = next(c for c in global_items if c["id"] == pizza_cust_id)
    assert pizza_item["organization_name"] == "Restaurante Pizza"
    assert pizza_item["organization_id"] == pizza["organization"]["id"]

    # 2. Superadmin can paginate across all tenants
    page_res = client.get("/api/v1/customers?all_organizations=true&limit=50&offset=0", headers=headers_sa)
    assert page_res.status_code == 200, page_res.text
    page_data = page_res.json()
    assert "items" in page_data
    assert page_data["total"] >= 2
    page_ids = {c["id"] for c in page_data["items"]}
    assert tacos_cust_id in page_ids
    assert pizza_cust_id in page_ids

    # 3. Superadmin can filter specifically by organization_id
    filter_tacos = client.get(f"/api/v1/customers?organization_id={tacos['organization']['id']}", headers=headers_sa)
    assert filter_tacos.status_code == 200, filter_tacos.text
    filter_tacos_ids = {c["id"] for c in filter_tacos.json()}
    assert tacos_cust_id in filter_tacos_ids
    assert pizza_cust_id not in filter_tacos_ids

    filter_pizza = client.get(f"/api/v1/customers?organization_id={pizza['organization']['id']}", headers=headers_sa)
    assert filter_pizza.status_code == 200, filter_pizza.text
    filter_pizza_ids = {c["id"] for c in filter_pizza.json()}
    assert pizza_cust_id in filter_pizza_ids
    assert tacos_cust_id not in filter_pizza_ids


def test_regular_tenant_cannot_access_cross_tenant_customers_via_superadmin_params():
    client = _client_with_db()
    tenants = []
    for name in ("one", "two"):
        resp = client.post(
            "/api/v1/auth/signup",
            json={
                "business_name": f"Restaurante {name}",
                "owner_name": f"Owner {name}",
                "email": f"tenant-{name}@example.test",
                "password": "synthetic-customer-password",
                "business_type": "blank",
            },
        )
        assert resp.status_code == 201, resp.text
        tenants.append(resp.json())

    tenant_1, tenant_2 = tenants
    headers_1 = {"Authorization": f"Bearer {tenant_1['token']}"}

    # Attempt to use all_organizations as a regular tenant
    denied_all = client.get("/api/v1/customers?all_organizations=true", headers=headers_1)
    assert denied_all.status_code == 403, denied_all.text

    # Attempt to query another organization's customers
    denied_org = client.get(f"/api/v1/customers?organization_id={tenant_2['organization']['id']}", headers=headers_1)
    assert denied_org.status_code == 403, denied_org.text
