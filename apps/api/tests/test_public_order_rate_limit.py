"""Focused security contracts for public-order Redis throttling."""

from __future__ import annotations

import pytest
from restaurant_os.config import Settings
from restaurant_os.main import create_app
from restaurant_os.public_order_rate_limit import RedisPublicOrderRateLimiter


class _FakePipeline:
    def __init__(
        self, counts: dict[str, int], keys: list[str], failure: Exception | None = None
    ) -> None:
        self._counts = counts
        self._keys = keys
        self._failure = failure
        self._commands: list[tuple[str, str]] = []

    def incr(self, key: str) -> _FakePipeline:
        self._commands.append(("incr", key))
        self._keys.append(key)
        return self

    def expire(self, key: str, _seconds: int, *, nx: bool) -> _FakePipeline:
        assert nx is True
        self._commands.append(("expire", key))
        self._keys.append(key)
        return self

    def execute(self) -> list[int | bool]:
        if self._failure:
            raise self._failure
        result: list[int | bool] = []
        for command, key in self._commands:
            if command == "incr":
                self._counts[key] = self._counts.get(key, 0) + 1
                result.append(self._counts[key])
            else:
                result.append(True)
        return result


class _FakeRedis:
    def __init__(self, failure: Exception | None = None) -> None:
        self.counts: dict[str, int] = {}
        self.keys: list[str] = []
        self.failure = failure

    def pipeline(self, *, transaction: bool) -> _FakePipeline:
        assert transaction is True
        return _FakePipeline(self.counts, self.keys, self.failure)


def _limiter(monkeypatch: pytest.MonkeyPatch, fake: _FakeRedis) -> RedisPublicOrderRateLimiter:
    def factory(*_args: object, **_kwargs: object) -> _FakeRedis:
        return fake

    monkeypatch.setattr("restaurant_os.public_order_rate_limit.Redis.from_url", factory)
    return RedisPublicOrderRateLimiter(
        "redis://example", 3, 1, "hmac-secret-which-is-long-enough-for-tests"
    )


def test_limiter_uses_only_public_key_and_hmac_for_redis_buckets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeRedis()
    limiter = _limiter(monkeypatch, fake)
    client_signal = "203.0.113.4|Mozilla/5.0 private user agent"

    assert limiter.allow("pk_branch_123", client_signal) is True

    assert fake.keys[0] == "restaurantos:public-order:pk_branch_123"
    assert fake.keys[2].startswith("restaurantos:public-order:pk_branch_123:")
    assert client_signal not in " ".join(fake.keys)
    assert "203.0.113.4" not in " ".join(fake.keys)
    assert "Mozilla" not in " ".join(fake.keys)
    assert len(fake.keys[2].rsplit(":", maxsplit=1)[1]) == 64


def test_limiter_enforces_smaller_client_budget_and_shared_global_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeRedis()
    limiter = _limiter(monkeypatch, fake)

    assert limiter.allow("pk_branch_123", "client-a") is True
    assert limiter.allow("pk_branch_123", "client-a") is False
    assert limiter.allow("pk_branch_123", "client-b") is True
    assert limiter.allow("pk_branch_123", "client-c") is False


def test_limiter_propagates_redis_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = _limiter(monkeypatch, _FakeRedis(ConnectionError("redis unavailable")))

    with pytest.raises(ConnectionError, match="redis unavailable"):
        limiter.allow("pk_branch_123", "client-a")


def test_limiter_rejects_invalid_budgets_and_missing_hmac_secret() -> None:
    with pytest.raises(ValueError, match="client limit"):
        RedisPublicOrderRateLimiter("redis://example", 1, 2, "secret")
    with pytest.raises(ValueError, match="secret"):
        RedisPublicOrderRateLimiter("redis://example", 1, 1, "")


def test_rate_limit_settings_have_safe_separate_defaults_and_validate_relationship() -> None:
    settings = Settings(_env_file=None)
    assert settings.public_order_intents_enabled is False
    assert not hasattr(settings, "auto_migrate")
    assert settings.public_order_global_rate_limit_per_minute == 20
    assert settings.public_order_client_rate_limit_per_minute == 5

    with pytest.raises(ValueError, match="must not exceed"):
        Settings(
            _env_file=None,
            public_order_global_rate_limit_per_minute=5,
            public_order_client_rate_limit_per_minute=6,
        )


def test_production_enabled_public_orders_require_dedicated_hmac_secret() -> None:
    # When secret_key >= 32 chars is provided, it falls back to secret_key
    settings = Settings(
        _env_file=None,
        environment="production",
        secret_key="x" * 32,
        public_order_intents_enabled=True,
    )
    assert settings.public_order_rate_limit_hmac_secret == "x" * 32

    # When dedicated secret is provided, it takes precedence
    settings_dedicated = Settings(
        _env_file=None,
        environment="production",
        secret_key="x" * 32,
        public_order_rate_limit_hmac_secret="dedicated-secret-with-plenty-of-bytes",
        public_order_intents_enabled=True,
    )
    assert (
        settings_dedicated.public_order_rate_limit_hmac_secret
        == "dedicated-secret-with-plenty-of-bytes"
    )


def test_app_only_installs_limiter_with_redis_and_hmac_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        public_order_intents_enabled=True,
        redis_url="redis://example",
        public_order_rate_limit_hmac_secret="hmac-secret-which-is-long-enough-for-tests",
    )
    calls: list[tuple[object, ...]] = []

    class _Limiter:
        def __init__(self, *args: object) -> None:
            calls.append(args)

    monkeypatch.setattr("restaurant_os.main.get_settings", lambda: settings)
    monkeypatch.setattr("restaurant_os.main.RedisPublicOrderRateLimiter", _Limiter)

    app = create_app()

    assert calls == [
        (
            "redis://example",
            settings.public_order_global_rate_limit_per_minute,
            settings.public_order_client_rate_limit_per_minute,
            settings.public_order_rate_limit_hmac_secret,
        ),
        (
            "redis://example",
            settings.supervisor_authorization_global_rate_limit_per_minute,
            settings.supervisor_authorization_actor_rate_limit_per_minute,
            settings.public_order_rate_limit_hmac_secret,
        ),
    ]
    assert app.state.public_order_intents_enabled is True
    assert (
        app.state.public_order_rate_limiter is not app.state.supervisor_authorization_rate_limiter
    )
