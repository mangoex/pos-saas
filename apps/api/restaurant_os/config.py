from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RESTAURANTOS_", env_file=".env", populate_by_name=True
    )

    environment: str = Field(default="local")
    service_name: str = Field(default="restaurant-os-api")
    app_version: str = Field(default="0.0.0")
    git_commit: str = Field(default="unknown")
    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RESTAURANTOS_DATABASE_URL", "DATABASE_URL"),
    )
    redis_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RESTAURANTOS_REDIS_URL", "REDIS_URL"),
    )
    public_order_intents_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "RESTAURANTOS_PUBLIC_ORDER_INTENTS_ENABLED", "PUBLIC_ORDER_INTENTS_ENABLED"
        ),
    )
    public_order_global_rate_limit_per_minute: int = Field(default=20, ge=1, le=1000)
    public_order_client_rate_limit_per_minute: int = Field(default=5, ge=1, le=1000)
    public_order_rate_limit_hmac_secret: str | None = Field(default=None, min_length=32)
    assisted_order_enabled: bool = Field(default=False)
    admin_ai_assistant_enabled: bool = Field(default=False)
    admin_ai_openrouter_model: str = Field(default="google/gemini-3.1-flash-lite")
    admin_ai_openrouter_timeout_seconds: float = Field(default=10.0, ge=1.0, le=30.0)
    openrouter_api_key: str | None = Field(
        default=None,
        min_length=16,
        validation_alias=AliasChoices(
            "RESTAURANTOS_OPENROUTER_API_KEY",
            "OPENROUTER_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
        ),
    )
    openrouter_model: str = Field(default="google/gemini-3.1-flash-lite")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1")
    openrouter_timeout_seconds: float = Field(default=10.0, ge=1.0, le=30.0)
    openrouter_http_referer: str | None = Field(default=None)
    openrouter_app_title: str = Field(default="RestaurantOS POS")
    secret_key: str = Field(
        default="dev-secret-change-me",
        validation_alias=AliasChoices("RESTAURANTOS_SECRET_KEY", "SECRET_KEY"),
    )
    offline_grant_private_key: str | None = Field(
        default=None,
        validation_alias="RESTAURANTOS_OFFLINE_GRANT_PRIVATE_KEY",
    )
    offline_grant_key_id: str | None = Field(
        default=None,
        validation_alias="RESTAURANTOS_OFFLINE_GRANT_KEY_ID",
    )
    offline_grant_public_keyring: str | None = Field(
        default=None,
        validation_alias="RESTAURANTOS_OFFLINE_GRANT_PUBLIC_KEYRING",
    )

    @field_validator("environment", mode="before")
    @classmethod
    def normalize_environment(cls, value: object) -> str:
        normalized = str(value).strip().lower()
        if normalized not in {"local", "test", "production"}:
            raise ValueError("RESTAURANTOS_ENVIRONMENT must be local, test or production")
        return normalized

    @model_validator(mode="after")
    def production_settings_are_safe(self) -> Settings:
        """Production must never silently fall back to development credentials."""
        if self.environment == "production" and (
            self.secret_key == "dev-secret-change-me" or len(self.secret_key.strip()) < 32
        ):
            raise ValueError(
                "RESTAURANTOS_SECRET_KEY must contain at least 32 characters in production"
            )
        if (
            self.public_order_client_rate_limit_per_minute
            > self.public_order_global_rate_limit_per_minute
        ):
            raise ValueError(
                "RESTAURANTOS_PUBLIC_ORDER_CLIENT_RATE_LIMIT_PER_MINUTE must not exceed "
                "RESTAURANTOS_PUBLIC_ORDER_GLOBAL_RATE_LIMIT_PER_MINUTE"
            )
        if (
            self.environment == "production"
            and self.public_order_intents_enabled
            and not self.public_order_rate_limit_hmac_secret
        ):
            if (
                self.secret_key
                and len(self.secret_key.strip()) >= 32
                and self.secret_key != "dev-secret-change-me"
            ):
                self.public_order_rate_limit_hmac_secret = self.secret_key
            else:
                raise ValueError(
                    "RESTAURANTOS_PUBLIC_ORDER_RATE_LIMIT_HMAC_SECRET is required when "
                    "public ordering is enabled in production"
                )
        if (
            self.environment == "production"
            and self.assisted_order_enabled
            and not self.openrouter_api_key
        ):
            raise ValueError(
                "RESTAURANTOS_OPENROUTER_API_KEY is required when assisted ordering is enabled"
            )
        if (
            self.environment == "production"
            and self.admin_ai_assistant_enabled
            and not self.openrouter_api_key
        ):
            raise ValueError("RESTAURANTOS_OPENROUTER_API_KEY is required when admin AI is enabled")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
