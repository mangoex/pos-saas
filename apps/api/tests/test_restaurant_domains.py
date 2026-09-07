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
