from __future__ import annotations

import pytest
from fastapi import HTTPException
from restaurant_os.api import _database_response
from restaurant_os.config import get_settings
from restaurant_os.main import create_app
from sqlalchemy.exc import SQLAlchemyError


@pytest.mark.parametrize("signal", ["STATIC_DIR", "DATABASE_URL", "ENVIRONMENT"])
def test_public_intake_requires_explicit_flag(monkeypatch, signal):
    monkeypatch.delenv("RESTAURANTOS_PUBLIC_ORDER_INTENTS_ENABLED", raising=False)
    monkeypatch.delenv("PUBLIC_ORDER_INTENTS_ENABLED", raising=False)
    monkeypatch.setenv(signal, "production" if signal == "ENVIRONMENT" else "configured")
    get_settings.cache_clear()
    assert create_app().state.public_order_intents_enabled is False


def test_database_error_does_not_disclose_sql_or_customer_data():
    def fail():
        raise SQLAlchemyError(
            "SELECT secret_column FROM customers WHERE email=private@example.test"
        )

    with pytest.raises(HTTPException) as error:
        _database_response(fail)
    assert error.value.status_code == 503
    assert "private@example.test" not in str(error.value.detail)
    assert "SELECT" not in str(error.value.detail)
    assert error.value.detail["code"] == "database_unavailable"
    assert error.value.detail["correlation_id"]
