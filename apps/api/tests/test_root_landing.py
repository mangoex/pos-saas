"""Focused contract tests for the public SaaS acquisition landing."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from restaurant_os.main import create_app

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    static_root = tmp_path / "static"
    app_markers = {
        "landing-web": "KIWI_LANDING_ROOT",
        "mobile-web": "MOBILE_MENU_ROOT",
        "admin-web": "ADMIN_ROOT",
        "pos-web": "POS_ROOT",
        "kds-web": "KDS_ROOT",
    }
    for app_name, marker in app_markers.items():
        app_root = static_root / app_name
        app_root.mkdir(parents=True)
        (app_root / "index.html").write_text(marker, encoding="utf-8")
    (static_root / "landing-web" / "styles.css").write_text("LANDING_STYLES", encoding="utf-8")
    monkeypatch.setenv("STATIC_DIR", str(static_root))
    return TestClient(create_app())


def test_desktop_root_serves_landing_and_exact_assets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.get(
        "/",
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
    )

    assert response.status_code == 200
    assert response.text == "KIWI_LANDING_ROOT"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["vary"] == "Sec-CH-UA-Mobile, User-Agent"
    assert client.get("/landing-assets/styles.css").text == "LANDING_STYLES"
    assert client.get("/landing-assets/missing.css").status_code == 404
    assert client.get("/landing-assets/%2e%2e/admin-web/index.html").status_code == 404


@pytest.mark.parametrize(
    "headers",
    [
        {"Sec-CH-UA-Mobile": "?1"},
        {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)"},
        {"User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit Mobile"},
        {"Sec-CH-UA-Mobile": "?0", "User-Agent": "Mozilla/5.0 (iPhone)"},
    ],
)
def test_root_serves_the_acquisition_landing_for_every_device(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    headers: dict[str, str],
) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.get("/", headers=headers, follow_redirects=False)

    assert response.status_code == 200
    assert response.text == "KIWI_LANDING_ROOT"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["vary"] == "Sec-CH-UA-Mobile, User-Agent"
    assert response.headers["accept-ch"] == "Sec-CH-UA-Mobile"


def test_root_selection_does_not_change_operational_routes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = _client(monkeypatch, tmp_path)

    assert client.get("/menu/").text == "MOBILE_MENU_ROOT"
    assert client.get("/admin/").text == "ADMIN_ROOT"
    assert client.get("/pos/").text == "POS_ROOT"
    assert client.get("/kds/").text == "KDS_ROOT"
    assert client.get("/health/live").json()["status"] == "ok"


def test_landing_is_packaged_with_acquisition_and_operational_links() -> None:
    landing_html = (REPOSITORY_ROOT / "apps/landing-web/src/index.html").read_text(encoding="utf-8")

    for route in (
        "/admin/register?plan=trial",
        "/admin/register?plan=starter",
        "/admin/login",
        "/pos/",
        "/kds/",
    ):
        assert f'href="{route}"' in landing_html
    assert "Prueba 14 Días Gratis" in landing_html
    assert 'src="/landing-assets/app.js"' in landing_html

    for dockerfile in ("Dockerfile", "infra/docker/api.Dockerfile"):
        contents = (REPOSITORY_ROOT / dockerfile).read_text(encoding="utf-8")
        assert '--filter "@restaurantos/landing-web" build' in contents
        assert "/app/apps/landing-web/dist" in contents

    workflow = (REPOSITORY_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "pnpm --filter @restaurantos/landing-web build" in workflow
