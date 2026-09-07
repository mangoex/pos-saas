"""Shared test isolation and cross-database fixtures."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from restaurant_os.config import get_settings

pytest_plugins = ("test_saas_cash_scope",)


@pytest.fixture(autouse=True)
def _isolate_cached_settings() -> Generator[None, None, None]:
    """Prevent environment-dependent settings from leaking between tests."""
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()
