from __future__ import annotations

import pytest
from pytest import MonkeyPatch
from restaurant_os.config import get_settings


def setup_function() -> None:
    get_settings.cache_clear()


def test_settings_accept_standard_database_and_redis_urls(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@postgres:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")

    settings = get_settings()

    assert settings.database_url == "postgresql+psycopg://user:pass@postgres:5432/db"
    assert settings.redis_url == "redis://redis:6379/0"


def test_settings_accept_prefixed_database_and_redis_urls(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RESTAURANTOS_DATABASE_URL",
        "postgresql+psycopg://user:pass@kiwi-postgres:5432/restaurantos",
    )
    monkeypatch.setenv("RESTAURANTOS_REDIS_URL", "redis://kiwi-redis:6379/0")

    settings = get_settings()

    assert settings.database_url == "postgresql+psycopg://user:pass@kiwi-postgres:5432/restaurantos"
    assert settings.redis_url == "redis://kiwi-redis:6379/0"


def test_assisted_order_openrouter_defaults_to_disabled(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("RESTAURANTOS_ASSISTED_ORDER_ENABLED", raising=False)
    monkeypatch.delenv("RESTAURANTOS_OPENROUTER_API_KEY", raising=False)

    settings = get_settings()

    assert settings.assisted_order_enabled is False
    assert settings.public_voice_order_enabled is False
    assert settings.openrouter_api_key is None
    assert settings.openrouter_model == "google/gemini-3.1-flash-lite"


def test_assisted_order_reads_server_side_openrouter_configuration(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTAURANTOS_ASSISTED_ORDER_ENABLED", "true")
    monkeypatch.setenv("RESTAURANTOS_OPENROUTER_API_KEY", "synthetic-key-with-safe-length")
    monkeypatch.setenv("RESTAURANTOS_OPENROUTER_MODEL", "provider/model")

    settings = get_settings()

    assert settings.assisted_order_enabled is True
    assert settings.openrouter_api_key == "synthetic-key-with-safe-length"
    assert settings.openrouter_model == "provider/model"


def test_admin_ai_defaults_to_disabled_with_separate_model_and_timeout(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("RESTAURANTOS_ADMIN_AI_ASSISTANT_ENABLED", raising=False)
    monkeypatch.delenv("RESTAURANTOS_ADMIN_AI_OPENROUTER_MODEL", raising=False)
    monkeypatch.delenv("RESTAURANTOS_ADMIN_AI_OPENROUTER_TIMEOUT_SECONDS", raising=False)

    settings = get_settings()

    assert settings.admin_ai_assistant_enabled is False
    assert settings.admin_ai_openrouter_model == "google/gemini-3.1-flash-lite"
    assert settings.admin_ai_openrouter_timeout_seconds == 10.0


def test_admin_ai_reads_its_own_feature_flag_model_and_timeout(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTAURANTOS_ADMIN_AI_ASSISTANT_ENABLED", "true")
    monkeypatch.setenv("RESTAURANTOS_ADMIN_AI_OPENROUTER_MODEL", "provider/admin-model")
    monkeypatch.setenv("RESTAURANTOS_ADMIN_AI_OPENROUTER_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("RESTAURANTOS_OPENROUTER_API_KEY", "synthetic-key-with-safe-length")

    settings = get_settings()

    assert settings.admin_ai_assistant_enabled is True
    assert settings.admin_ai_openrouter_model == "provider/admin-model"
    assert settings.admin_ai_openrouter_timeout_seconds == 7.0


def test_admin_ai_requires_server_side_key_when_enabled_in_production(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTAURANTOS_ENVIRONMENT", "production")
    monkeypatch.setenv("RESTAURANTOS_SECRET_KEY", "s" * 32)
    monkeypatch.setenv("RESTAURANTOS_ADMIN_AI_ASSISTANT_ENABLED", "true")
    monkeypatch.delenv("RESTAURANTOS_OPENROUTER_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        get_settings()


def test_public_order_hmac_secret_falls_back_to_secret_key_in_production(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTAURANTOS_ENVIRONMENT", "production")
    monkeypatch.setenv("RESTAURANTOS_SECRET_KEY", "k" * 32)
    monkeypatch.setenv("RESTAURANTOS_PUBLIC_ORDER_INTENTS_ENABLED", "true")
    monkeypatch.delenv("RESTAURANTOS_PUBLIC_ORDER_RATE_LIMIT_HMAC_SECRET", raising=False)

    settings = get_settings()
    assert settings.public_order_rate_limit_hmac_secret == "k" * 32


def test_public_voice_order_requires_public_ordering_and_provider_in_production(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTAURANTOS_ENVIRONMENT", "production")
    monkeypatch.setenv("RESTAURANTOS_SECRET_KEY", "v" * 32)
    monkeypatch.setenv("RESTAURANTOS_PUBLIC_VOICE_ORDER_ENABLED", "true")
    monkeypatch.delenv("RESTAURANTOS_PUBLIC_ORDER_INTENTS_ENABLED", raising=False)
    monkeypatch.delenv("RESTAURANTOS_OPENROUTER_API_KEY", raising=False)

    with pytest.raises(ValueError, match="PUBLIC_ORDER_INTENTS_ENABLED"):
        get_settings()

    get_settings.cache_clear()
    monkeypatch.setenv("RESTAURANTOS_PUBLIC_ORDER_INTENTS_ENABLED", "true")
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        get_settings()
