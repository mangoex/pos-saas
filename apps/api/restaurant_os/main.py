import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from restaurant_os.api import router as platform_router
from restaurant_os.config import get_settings
from restaurant_os.health import readiness_payload
from restaurant_os.public_order_rate_limit import (
    InMemoryPublicOrderRateLimiter,
    RedisPublicOrderRateLimiter,
)

logger = logging.getLogger(__name__)


_PHONE_USER_AGENT = re.compile(
    r"iPhone|iPod|Windows Phone|BlackBerry|Opera Mini|Android.+Mobile",
    re.IGNORECASE,
)


def _request_prefers_mobile_menu(request: Request) -> bool:
    mobile_hint = request.headers.get("sec-ch-ua-mobile")
    if mobile_hint == "?1":
        return True
    if mobile_hint == "?0":
        return False
    return bool(_PHONE_USER_AGENT.search(request.headers.get("user-agent", "")))


def _with_device_variant_headers(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Sec-CH-UA-Mobile, User-Agent"
    response.headers["Accept-CH"] = "Sec-CH-UA-Mobile"
    return response


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="RestaurantOS API", version=settings.app_version)
    intents_enabled = settings.public_order_intents_enabled
    if not intents_enabled:
        env_val = os.environ.get(
            "RESTAURANTOS_PUBLIC_ORDER_INTENTS_ENABLED",
            os.environ.get("PUBLIC_ORDER_INTENTS_ENABLED", ""),
        ).strip().lower()
        if env_val in ("true", "1", "yes"):
            intents_enabled = True
        elif env_val == "" and (
            os.path.exists("/app/static")
            or bool(os.environ.get("STATIC_DIR"))
            or bool(os.environ.get("DATABASE_URL"))
            or str(os.environ.get("ENVIRONMENT", "")).lower() in ("production", "prod")
        ):
            intents_enabled = True

    app.state.public_order_intents_enabled = intents_enabled
    if intents_enabled:
        if settings.redis_url and settings.public_order_rate_limit_hmac_secret:
            app.state.public_order_rate_limiter = RedisPublicOrderRateLimiter(
                settings.redis_url,
                settings.public_order_global_rate_limit_per_minute,
                settings.public_order_client_rate_limit_per_minute,
                settings.public_order_rate_limit_hmac_secret,
            )
        else:
            app.state.public_order_rate_limiter = InMemoryPublicOrderRateLimiter(
                settings.public_order_global_rate_limit_per_minute,
                settings.public_order_client_rate_limit_per_minute,
                settings.public_order_rate_limit_hmac_secret
                or settings.secret_key
                or "restaurantos-dev-secret-key-32chars",
            )
    app.include_router(platform_router)

    static_dir = os.environ.get("STATIC_DIR", "/app/static")
    # For local dev fallback
    if not os.path.exists(static_dir):
        static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../static"))

    def serve_spa(app_name: str, full_path: str) -> Response:
        base_path = Path(static_dir, app_name).resolve()
        cleaned = full_path.lstrip("/")
        if cleaned:
            file_path = (base_path / cleaned).resolve()
            try:
                file_path.relative_to(base_path)
            except ValueError:
                return Response(status_code=404)
            if file_path.is_file():
                return FileResponse(file_path)
            if (file_path / "index.html").is_file():
                return FileResponse(file_path / "index.html")
        index_path = base_path / "index.html"
        if index_path.is_file():
            return FileResponse(index_path)
        return HTMLResponse(
            f"<h3>{app_name} UI not built.</h3><p>Ensure static files are in {base_path}</p>"
        )

    def serve_static_asset(app_name: str, full_path: str) -> Response:
        base_path = Path(static_dir, app_name).resolve()
        cleaned = full_path.lstrip("/")
        if not cleaned:
            return Response(status_code=404)
        file_path = (base_path / cleaned).resolve()
        try:
            file_path.relative_to(base_path)
        except ValueError:
            return Response(status_code=404)
        if file_path.is_file():
            return FileResponse(file_path)
        return Response(status_code=404)

    @app.get("/", tags=["platform"])
    def platform_home(request: Request) -> Response:
        return _with_device_variant_headers(serve_spa("landing-web", ""))

    @app.get("/landing-assets/{full_path:path}", tags=["platform"])
    def platform_landing_asset(full_path: str) -> Response:
        return serve_static_asset("landing-web", full_path)

    @app.get("/menu{full_path:path}", tags=["platform"])
    def platform_menu(full_path: str) -> Response:
        return serve_spa("mobile-web", full_path.lstrip("/"))

    @app.get("/order{full_path:path}", tags=["platform"])
    def platform_order(full_path: str) -> Response:
        return serve_spa("mobile-web", full_path.lstrip("/"))

    @app.get("/mobile{full_path:path}", tags=["platform"])
    def platform_mobile(full_path: str) -> Response:
        return serve_spa("mobile-web", full_path.lstrip("/"))

    @app.get("/images/{full_path:path}", tags=["platform"])
    def platform_images(full_path: str) -> Response:
        return serve_spa("mobile-web", f"images/{full_path.lstrip('/')}")

    @app.get("/admin{full_path:path}", tags=["platform"])
    def platform_admin(full_path: str) -> Response:
        return serve_spa("admin-web", full_path.lstrip("/"))

    @app.get("/pos{full_path:path}", tags=["platform"])
    def platform_pos(full_path: str) -> Response:
        return serve_spa("pos-web", full_path.lstrip("/"))

    @app.get("/kds{full_path:path}", tags=["platform"])
    def platform_kds(full_path: str) -> Response:
        return serve_spa("kds-web", full_path.lstrip("/"))

    @app.get("/manual{full_path:path}", tags=["platform"])
    def platform_manual(full_path: str) -> Response:
        return serve_spa("landing-web", f"manual/{full_path.lstrip('/')}")

    @app.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    @app.get("/health/ready", tags=["health"])
    def ready() -> dict[str, object]:
        return readiness_payload(settings)

    @app.get("/health/version", tags=["health"])
    def version() -> dict[str, str]:
        return {
            "service": settings.service_name,
            "version": settings.app_version,
            "commit": settings.git_commit,
        }

    return app


app = create_app()
