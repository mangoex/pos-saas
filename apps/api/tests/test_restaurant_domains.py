"""Restaurant domain boundaries, tested through actual API requests."""

import secrets

import pytest
from restaurant_os import models
from restaurant_os.config import get_settings
from test_saas_onboarding import _client_with_db


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv("RESTAURANTOS_PUBLIC_BASE_URL", "https://platform.example.com")
    monkeypatch.setenv("RESTAURANTOS_PLATFORM_HOSTS", "testserver,platform.example.com")
    get_settings.cache_clear()
    client = _client_with_db()
    accounts = []
    for name in ("Tacos", "Sushi", "Platform"):
        password = secrets.token_urlsafe(24)
        response = client.post(
            "/api/v1/auth/signup",
            json={
                "business_name": name,
                "owner_name": name,
                "email": f"{name}@example.com",
                "password": password,
                "plan": "trial",
                "defer_catalog": True,
            },
        )
        assert response.status_code == 201, response.text
        data = response.json()
        accounts.append(({"Authorization": "Bearer " + data["token"]}, data, password))
    with client.app.state.test_session_factory() as session:
        session.execute(
            models.users.update()
            .where(models.users.c.id == accounts[2][1]["user"]["id"])
            .values(is_superadmin=True)
        )
        session.commit()
    yield client, accounts
    get_settings.cache_clear()


def test_links_aliases_preserve_history_and_prevent_takeover(setup):
    client, accounts = setup
    headers = accounts[0][0]
    initial = client.get("/api/v1/saas/links", headers=headers)
    assert initial.status_code == 200
    canonical = initial.json()["canonical_slug"]
    for alias in ("tacos-el-guero", "tacos-guero"):
        response = client.put("/api/v1/saas/links/alias", headers=headers, json={"alias": alias})
        assert response.status_code == 200, response.text
    for alias in (canonical, "tacos-el-guero", "tacos-guero"):
        result = client.get(f"/api/v1/public/storefronts/{alias}")
        assert result.status_code == 200
        assert result.json()["organization"]["slug"] == canonical
    assert (
        client.put(
            "/api/v1/saas/links/alias", headers=accounts[1][0], json={"alias": "tacos-el-guero"}
        ).status_code
        == 409
    )
    assert client.get("/api/v1/saas/links").status_code == 401


def test_domain_lifecycle_and_host_boundaries(setup, monkeypatch):
    from restaurant_os import restaurant_domains as domains

    client, accounts = setup
    owner, other, superadmin = [account[0] for account in accounts]
    created = client.post(
        "/api/v1/saas/domains", headers=owner, json={"hostname": "Pedidos.Tacos.Example.com"}
    )
    assert created.status_code == 200, created.text
    domain = created.json()
    domain_id = domain["id"]
    path = f"/api/v1/saas/domains/{domain_id}"
    host = {"Host": "pedidos.tacos.example.com"}
    assert client.get("/", headers=host).status_code == 404
    assert client.post(path + "/verify", headers=other).status_code == 404
    monkeypatch.setattr(domains, "lookup_txt", lambda name: [])
    assert client.post(path + "/verify", headers=owner).json()["status"] == "pending_dns"
    monkeypatch.setattr(domains, "lookup_txt", lambda name: [domain["txt_value"]])
    assert client.post(path + "/verify", headers=owner).json()["status"] == "pending_tls"
    activation = {"action": "activate", "tls_confirmed": True}
    assert client.post(path + "/supervise", headers=owner, json=activation).status_code == 403
    assert (
        client.post(
            path + "/supervise", headers=superadmin, json={"action": "activate"}
        ).status_code
        == 409
    )
    assert (
        client.post(path + "/supervise", headers=superadmin, json=activation).json()["status"]
        == "active"
    )
    links = client.get("/api/v1/saas/links", headers=owner).json()
    slug = links["canonical_slug"]
    root = client.get("/", headers=host, follow_redirects=False)
    assert root.status_code == 307
    assert root.headers["location"] == f"/menu/{slug}/"
    assert client.get("/api/v1/saas/links", headers={**host, **other}).status_code == 403
    other_slug = client.get("/api/v1/saas/links", headers=other).json()["canonical_slug"]
    assert client.get(f"/api/v1/public/storefronts/{other_slug}", headers=host).status_code == 404
    other_key = client.get(f"/api/v1/public/storefronts/{other_slug}").json()["branches"][0][
        "public_key"
    ]
    assert (
        client.get(f"/api/v1/public/branches/{other_key}/catalog", headers=host).status_code == 404
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            headers=host,
            json={
                "email": "Sushi@example.com",
                "password": accounts[1][2],
            },
        ).status_code
        == 403
    )
    assert client.get("/", headers={"Host": "unknown.example.com"}).status_code == 404
    assert (
        client.get(
            "/api/v1/saas/links",
            headers={
                **owner,
                "X-Forwarded-Host": "unknown.example.com",
            },
        ).status_code
        == 200
    )
    assert (
        client.post(path + "/supervise", headers=superadmin, json={"action": "disable"}).json()[
            "status"
        ]
        == "disabled"
    )
    assert client.get("/", headers=host).status_code == 404
    assert (
        client.post(
            "/api/v1/saas/domains", headers=other, json={"hostname": "pedidos.tacos.example.com"}
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "hostname",
    [
        "localhost",
        "127.0.0.1",
        "*.example.com",
        "https://example.com/menu",
        "example.com:8000",
        "platform.example.com",
        "x.local",
    ],
)
def test_invalid_or_reserved_domain_rejected(setup, hostname):
    client, accounts = setup
    assert (
        client.post(
            "/api/v1/saas/domains", headers=accounts[0][0], json={"hostname": hostname}
        ).status_code
        == 422
    )


def test_dns_failure_and_host_post_isolation(setup, monkeypatch):
    from restaurant_os import restaurant_domains as domains
    from restaurant_os.domain_dns import DnsUnavailable

    client, accounts = setup
    owner, other, superadmin = [account[0] for account in accounts]
    row = client.post(
        "/api/v1/saas/domains", headers=owner, json={"hostname": "orders.tacos.example.com"}
    ).json()
    path = f"/api/v1/saas/domains/{row['id']}"

    def fail(name):
        raise DnsUnavailable()

    monkeypatch.setattr(domains, "lookup_txt", fail)
    result = client.post(path + "/verify", headers=owner).json()
    assert result["status"] == "pending_dns"
    assert result["last_result"] == "dns_unavailable"
    assert (
        client.post(
            path + "/supervise",
            headers=superadmin,
            json={"action": "activate", "tls_confirmed": True},
        ).status_code
        == 409
    )
    monkeypatch.setattr(domains, "lookup_txt", lambda name: [row["txt_value"]])
    assert (
        client.post(
            path + "/supervise",
            headers=superadmin,
            json={"action": "activate", "tls_confirmed": True},
        ).status_code
        == 200
    )
    slug = client.get("/api/v1/saas/links", headers=owner).json()["canonical_slug"]
    for hostname in [
        "ORDERS.TACOS.EXAMPLE.COM",
        "orders.tacos.example.com.",
        "orders.tacos.example.com:443",
    ]:
        assert (
            client.get(f"/api/v1/public/storefronts/{slug}", headers={"Host": hostname}).status_code
            == 200
        )
    host = {"Host": "orders.tacos.example.com"}
    other_slug = client.get("/api/v1/saas/links", headers=other).json()["canonical_slug"]
    storefront = client.get(f"/api/v1/public/storefronts/{other_slug}").json()
    key = storefront["branches"][0]["public_key"]
    assert (
        client.post(
            f"/api/v1/public/branches/{key}/order-intents", headers=host, json={}
        ).status_code
        == 404
    )
    assert client.get(f"/menu/{other_slug}/", headers=host).status_code == 404
    assert client.post("/api/v1/auth/signup", headers=host, json={}).status_code == 403
    assert client.get("/health/live", headers={"Host": "internal-check"}).status_code == 200
    branch = client.get(f"/api/v1/public/storefronts/{slug}").json()["branches"][0]
    with client.app.state.test_session_factory() as session:
        session.execute(
            models.branches.update()
            .where(models.branches.c.id == branch["id"])
            .values(status="suspended")
        )
        session.commit()
    assert (
        client.get(
            f"/api/v1/public/branches/{branch['public_key']}/catalog", headers=host
        ).status_code
        == 404
    )
    monkeypatch.setenv("RESTAURANTOS_PLATFORM_HOSTS", "")
    get_settings.cache_clear()
    from fastapi.testclient import TestClient
    from restaurant_os.main import create_app

    second = create_app()
    second.dependency_overrides.update(client.app.dependency_overrides)
    with TestClient(second) as shared:
        assert (
            shared.post(
                path + "/supervise",
                headers=superadmin,
                json={"action": "activate", "tls_confirmed": True},
            ).status_code
            == 409
        )
        links = shared.get("/api/v1/saas/links", headers=owner).json()
        assert links["links"]["admin"].startswith("https://platform.example.com/")


def test_dns_adapter_exact_record_and_bounded_failure(monkeypatch):
    import httpx
    from restaurant_os import domain_dns

    original = httpx.Client
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "Status": 0,
                "Answer": [
                    {
                        "type": 16,
                        "name": "_humanio-verification.orders.example.com.",
                        "data": '"humanio-""domain=proof"',
                    },
                    {"type": 16, "name": "other.example.com.", "data": '"wrong"'},
                ],
            },
        )

    monkeypatch.setattr(
        domain_dns.httpx,
        "Client",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)),
    )
    assert domain_dns.lookup_txt("_humanio-verification.orders.example.com") == [
        "humanio-domain=proof"
    ]
    assert requested[0].startswith("https://dns.google/resolve?")

    def oversized(request):
        return httpx.Response(200, content=b"x" * 65537)

    monkeypatch.setattr(
        domain_dns.httpx,
        "Client",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(oversized)),
    )
    with pytest.raises(domain_dns.DnsUnavailable):
        domain_dns.lookup_txt("_humanio-verification.orders.example.com")


def test_alias_reservation_blocks_later_branch_and_slug_writes(setup, monkeypatch):
    from restaurant_os import saas_onboarding

    client, accounts = setup
    owner, other = accounts[0][0], accounts[1][0]
    assert (
        client.put(
            "/api/v1/saas/links/alias", headers=owner, json={"alias": "tacos-reserved"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/branches", headers=other, json={"name": "Conflict", "code": "TACOS-RESERVED"}
        ).status_code
        == 409
    )
    other_slug = client.get("/api/v1/saas/links", headers=other).json()["canonical_slug"]
    branch = client.get(f"/api/v1/public/storefronts/{other_slug}").json()["branches"][0]
    assert (
        client.put(
            f"/api/v1/branches/{branch['id']}", headers=other, json={"code": "TACOS-RESERVED"}
        ).status_code
        == 409
    )
    monkeypatch.setattr(saas_onboarding, "_generate_slug", lambda name: "tacos-reserved")
    assert (
        client.post(
            "/api/v1/auth/signup",
            json={
                "business_name": "Conflict",
                "owner_name": "Other",
                "email": "new@example.com",
                "password": secrets.token_urlsafe(24),
                "plan": "trial",
                "defer_catalog": True,
            },
        ).status_code
        == 409
    )
    assert client.get("/api/v1/public/storefronts/tacos-reserved").status_code == 200


def test_platform_configuration_drift_cannot_unbind_customer(setup, monkeypatch):
    from restaurant_os import restaurant_domains as domains

    client, accounts = setup
    owner, other, superadmin = [account[0] for account in accounts]
    row = client.post(
        "/api/v1/saas/domains", headers=owner, json={"hostname": "orders.drift.example.com"}
    ).json()
    monkeypatch.setattr(domains, "lookup_txt", lambda name: [row["txt_value"]])
    assert (
        client.post(
            f"/api/v1/saas/domains/{row['id']}/supervise",
            headers=superadmin,
            json={"action": "activate", "tls_confirmed": True},
        ).status_code
        == 200
    )
    monkeypatch.setenv(
        "RESTAURANTOS_PLATFORM_HOSTS", "testserver,platform.example.com,orders.drift.example.com"
    )
    get_settings.cache_clear()
    assert (
        client.get(
            "/api/v1/saas/links", headers={**other, "Host": "orders.drift.example.com"}
        ).status_code
        == 404
    )
    assert client.get("/api/v1/saas/links", headers=owner).status_code == 200


@pytest.fixture
def wildcard_setup(monkeypatch, tmp_path):
    monkeypatch.setenv("RESTAURANTOS_PUBLIC_BASE_URL", "https://platform.example.com")
    monkeypatch.setenv(
        "RESTAURANTOS_PLATFORM_HOSTS",
        "testserver,mimenu.onl,app.mimenu.onl,platform.example.com",
    )
    monkeypatch.setenv("RESTAURANTOS_STOREFRONT_WILDCARD_DOMAIN", "mimenu.onl")
    static_root = tmp_path / "static"
    for app_name, marker in {
        "landing-web": "KIWI_LANDING_ROOT",
        "mobile-web": "MOBILE_MENU_ROOT",
        "admin-web": "ADMIN_ROOT",
        "pos-web": "POS_ROOT",
        "kds-web": "KDS_ROOT",
    }.items():
        app_root = static_root / app_name
        app_root.mkdir(parents=True)
        (app_root / "index.html").write_text(marker, encoding="utf-8")
    monkeypatch.setenv("STATIC_DIR", str(static_root))
    get_settings.cache_clear()
    client = _client_with_db()
    accounts = []
    for name in ("Tacos", "Sushi"):
        password = secrets.token_urlsafe(24)
        response = client.post(
            "/api/v1/auth/signup",
            json={
                "business_name": name,
                "owner_name": name,
                "email": f"{name}@example.com",
                "password": password,
                "plan": "trial",
                "defer_catalog": True,
            },
        )
        assert response.status_code == 201, response.text
        accounts.append(
            ({"Authorization": "Bearer " + response.json()["token"]}, response.json(), password)
        )
    yield client, accounts
    get_settings.cache_clear()


def test_wildcard_storefront_binds_only_direct_tenant_and_serves_root_apps(wildcard_setup):
    client, accounts = wildcard_setup
    tacos, sushi = accounts
    tacos_headers, tacos_data, _ = tacos
    sushi_headers, sushi_data, sushi_password = sushi
    canonical_slug = tacos_data["organization"]["slug"]
    with client.app.state.test_session_factory() as session:
        session.execute(
            models.organizations.update()
            .where(models.organizations.c.id == tacos_data["organization"]["id"])
            .values(preferred_public_slug="a" * 64)
        )
        session.commit()
    historical_links = client.get("/api/v1/saas/links", headers=tacos_headers).json()
    assert historical_links["links"]["menu"] == f"https://{canonical_slug}.mimenu.onl/"
    too_long = client.put(
        "/api/v1/saas/links/alias", headers=tacos_headers, json={"alias": "a" * 64}
    )
    assert too_long.status_code == 409
    assert too_long.json()["detail"]["code"] == "alias_invalid"
    assert (
        client.put(
            "/api/v1/saas/links/alias", headers=tacos_headers, json={"alias": "tacos-guero"}
        ).status_code
        == 200
    )
    links = client.get("/api/v1/saas/links", headers=tacos_headers).json()
    assert links["links"]["menu"] == "https://tacos-guero.mimenu.onl/"
    assert links["links"]["admin"] == "https://tacos-guero.mimenu.onl/admin/"
    assert links["canonical_menu_url"] == f"https://{canonical_slug}.mimenu.onl/"

    host = {"Host": "tacos-guero.mimenu.onl"}
    root = client.get("/", headers=host)
    assert root.status_code == 200
    assert root.text == "MOBILE_MENU_ROOT"
    for path, marker in (("/admin/", "ADMIN_ROOT"), ("/pos/", "POS_ROOT"), ("/kds/", "KDS_ROOT")):
        assert client.get(path, headers=host).text == marker
    context = client.get("/api/v1/public/storefront-context", headers=host)
    assert context.status_code == 200, context.text
    assert context.json()["organization"]["slug"] == tacos_data["organization"]["slug"]
    assert context.json()["host_class"] == "wildcard"
    manifest = client.get("/api/v1/public/storefront-context/manifest.webmanifest", headers=host)
    assert manifest.status_code == 200
    assert manifest.json()["id"] == "/"
    assert manifest.json()["start_url"] == "/"
    assert manifest.json()["scope"] == "/"

    sushi_slug = sushi_data["organization"]["slug"]
    sushi_storefront = client.get(f"/api/v1/public/storefronts/{sushi_slug}").json()
    sushi_key = sushi_storefront["branches"][0]["public_key"]
    assert client.get(f"/api/v1/public/storefronts/{sushi_slug}", headers=host).status_code == 404
    assert (
        client.get(f"/api/v1/public/branches/{sushi_key}/catalog", headers=host).status_code == 404
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            headers=host,
            json={"email": "Sushi@example.com", "password": sushi_password},
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/public/storefront-context",
            headers={**host, "X-Forwarded-Host": "sushi.mimenu.onl"},
        ).json()["organization"]["slug"]
        == tacos_data["organization"]["slug"]
    )
    assert client.get("/", headers={"Host": "unknown.mimenu.onl"}).status_code == 404
    assert client.get("/", headers={"Host": "app.mimenu.onl"}).status_code == 200
    assert client.get("/", headers={"Host": "www.mimenu.onl"}).status_code == 404
    assert client.get("/", headers={"Host": "nested.tacos.mimenu.onl"}).status_code == 404
    assert (
        client.put(
            "/api/v1/saas/links/alias", headers=tacos_headers, json={"alias": "www"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/public/feedback",
            headers=host,
            json={
                "branch_id": sushi_storefront["branches"][0]["id"],
                "rating": 5,
                "customer_phone": "6671234567",
                "order_folio": "PI-CROSS-TENANT",
            },
        ).status_code
        == 404
    )

    with client.app.state.test_session_factory() as session:
        session.execute(
            models.organizations.update()
            .where(models.organizations.c.id == tacos_data["organization"]["id"])
            .values(status="suspended")
        )
        session.commit()
    assert client.get("/", headers=host).status_code == 404
    assert client.get("/api/v1/public/storefront-context", headers=host).status_code == 404


@pytest.mark.parametrize(
    "wildcard",
    [
        "https://mimenu.onl",
        "mimenu.onl:443",
        "mimenu.onl/menu",
        "*.mimenu.onl",
        "127.0.0.1",
        "mimenu.local",
    ],
)
def test_wildcard_configuration_rejects_non_hostname_values(monkeypatch, wildcard):
    from pydantic import ValidationError
    from restaurant_os.config import Settings

    monkeypatch.setenv("RESTAURANTOS_STOREFRONT_WILDCARD_DOMAIN", wildcard)
    with pytest.raises(ValidationError, match="STOREFRONT_WILDCARD_DOMAIN"):
        Settings()


def test_wildcard_configuration_normalizes_dns_case(monkeypatch):
    from restaurant_os.config import Settings

    monkeypatch.setenv("RESTAURANTOS_STOREFRONT_WILDCARD_DOMAIN", "MIMENU.ONL.")
    assert Settings().storefront_wildcard_domain == "mimenu.onl"


def test_wildcard_preserves_active_custom_domain_precedence(wildcard_setup, monkeypatch):
    from restaurant_os import restaurant_domains as domains

    client, accounts = wildcard_setup
    owner, owner_data, _ = accounts[0]
    with client.app.state.test_session_factory() as session:
        session.execute(
            models.users.update()
            .where(models.users.c.id == owner_data["user"]["id"])
            .values(is_superadmin=True)
        )
        session.commit()
    created = client.post(
        "/api/v1/saas/domains", headers=owner, json={"hostname": "orders.tacos.example.com"}
    )
    assert created.status_code == 200, created.text
    row = created.json()
    monkeypatch.setattr(domains, "lookup_txt", lambda name: [row["txt_value"]])
    assert (
        client.post(
            f"/api/v1/saas/domains/{row['id']}/supervise",
            headers=owner,
            json={"action": "activate", "tls_confirmed": True},
        ).status_code
        == 200
    )
    links = client.get("/api/v1/saas/links", headers=owner).json()
    slug = owner_data["organization"]["slug"]
    assert links["links"]["menu"] == f"https://orders.tacos.example.com/menu/{slug}/"
    assert links["canonical_menu_url"] == f"https://{slug}.mimenu.onl/"
    root = client.get("/", headers={"Host": "orders.tacos.example.com"}, follow_redirects=False)
    assert root.status_code == 307
    assert root.headers["location"] == f"/menu/{slug}/"
    assert (
        client.post(
            "/api/v1/saas/domains", headers=owner, json={"hostname": "pizza.mimenu.onl"}
        ).status_code
        == 422
    )


def test_empty_wildcard_preserves_landing_and_legacy_links(monkeypatch, tmp_path):
    monkeypatch.setenv("RESTAURANTOS_PUBLIC_BASE_URL", "https://platform.example.com")
    monkeypatch.setenv("RESTAURANTOS_PLATFORM_HOSTS", "")
    monkeypatch.setenv("RESTAURANTOS_STOREFRONT_WILDCARD_DOMAIN", "")
    static_root = tmp_path / "static"
    for app_name, marker in {
        "landing-web": "LANDING_ROOT",
        "mobile-web": "MOBILE_MENU_ROOT",
    }.items():
        app_root = static_root / app_name
        app_root.mkdir(parents=True)
        (app_root / "index.html").write_text(marker, encoding="utf-8")
    monkeypatch.setenv("STATIC_DIR", str(static_root))
    get_settings.cache_clear()
    client = _client_with_db()
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Tacos",
            "owner_name": "Tacos",
            "email": "tacos@example.com",
            "password": secrets.token_urlsafe(24),
            "plan": "trial",
            "defer_catalog": True,
        },
    )
    assert response.status_code == 201
    links = client.get(
        "/api/v1/saas/links", headers={"Authorization": "Bearer " + response.json()["token"]}
    ).json()
    assert client.get("/").text == "LANDING_ROOT"
    assert links["links"]["menu"] == (
        f"https://platform.example.com/menu/{response.json()['organization']['slug']}/"
    )
    get_settings.cache_clear()


def test_supervision_tenants_and_assign_domain(wildcard_setup):
    client, accounts = wildcard_setup
    owner, owner_data, _ = accounts[0]
    with client.app.state.test_session_factory() as session:
        session.execute(
            models.users.update()
            .where(models.users.c.id == owner_data["user"]["id"])
            .values(is_superadmin=True)
        )
        session.commit()

    # 1. List supervision tenants
    res = client.get("/api/v1/saas/domains/supervision/tenants", headers=owner)
    assert res.status_code == 200
    tenants = res.json()
    assert len(tenants) >= 2
    target_org_id = owner_data["organization"]["id"]
    matching = next((t for t in tenants if t["organization_id"] == target_org_id), None)
    assert matching is not None
    assert matching["organization_name"] == owner_data["organization"]["name"]
    assert "mimenu.onl" in matching["menu_url"]

    # 2. Superadmin assigns domain to client
    assign_res = client.post(
        "/api/v1/saas/domains/supervision/assign",
        headers=owner,
        json={
            "organization_id": owner_data["organization"]["id"],
            "hostname": "assigned.tacos.com",
        },
    )
    assert assign_res.status_code == 200, assign_res.text
    assigned = assign_res.json()
    assert assigned["hostname"] == "assigned.tacos.com"
    assert assigned["status"] == "pending_dns"

    # 3. Supervision list includes organization_name
    sup_list = client.get("/api/v1/saas/domains/supervision", headers=owner).json()
    found = next((d for d in sup_list if d["id"] == assigned["id"]), None)
    assert found is not None
    assert found["organization_name"] == owner_data["organization"]["name"]

    # 4. Superadmin deletes domain
    del_res = client.post(
        f"/api/v1/saas/domains/{assigned['id']}/supervise",
        headers=owner,
        json={"action": "delete"},
    )
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # Verify deleted
    sup_list_after = client.get("/api/v1/saas/domains/supervision", headers=owner).json()
    assert not any(d["id"] == assigned["id"] for d in sup_list_after)


def test_superadmin_route_redirects_to_admin_superadmin():
    client = _client_with_db()
    res = client.get("/superadmin", follow_redirects=False)
    assert res.status_code == 307
    assert res.headers["location"] == "/admin/superadmin"

    res_sub = client.get("/superadmin/domains", follow_redirects=False)
    assert res_sub.status_code == 307
    assert res_sub.headers["location"] == "/admin/superadmin/domains"
