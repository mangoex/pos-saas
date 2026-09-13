"""
Feature: Voice Order Parsing in Storefront
As a customer using the storefront PWA
I want to be able to dictate my order using my voice
So that I can quickly add items to my cart without manual navigation
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from restaurant_os.database import get_session
from restaurant_os.main import create_app


BRANCH_ID = str(uuid.uuid4())
PRODUCT_1 = str(uuid.uuid4())
PRODUCT_2 = str(uuid.uuid4())

FAKE_CATALOG: dict[str, Any] = {
    "items": [
        {"id": PRODUCT_1, "name": "Tacos al Pastor"},
        {"id": PRODUCT_2, "name": "Coca Cola"},
    ]
}


def _mock_urlopen_response(items: list[dict[str, Any]]) -> MagicMock:
    """Build a context-manager mock mimicking urlopen returning an OpenRouter response."""
    body = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({"items": items}),
                    }
                }
            ]
        }
    ).encode()
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


@pytest.fixture()
def app_with_mock_session():
    """Create a FastAPI app with the DB session overridden by a mock."""
    app = create_app()
    mock_session = MagicMock()

    def override_get_session() -> Generator[MagicMock, None, None]:
        yield mock_session

    app.dependency_overrides[get_session] = override_get_session
    yield app, mock_session
    app.dependency_overrides.clear()


def test_post_storefront_voice_order_parses_transcript_to_catalog_items(
    app_with_mock_session: tuple[Any, MagicMock],
) -> None:
    """
    Given a valid branch with a catalog containing Tacos and Coca Cola
    When a transcript 'quiero 3 tacos al pastor sin cebolla y una coca' is sent
    Then it returns 200 with structured items mapped to catalog UUIDs
    """
    app, mock_session = app_with_mock_session
    client = TestClient(app)

    # Branch exists
    mock_session.execute.return_value.scalar.return_value = BRANCH_ID

    ai_items = [
        {"product_id": PRODUCT_1, "quantity": 3, "modifiers": []},
        {"product_id": PRODUCT_2, "quantity": 1, "modifiers": []},
    ]

    with patch(
        "restaurant_os.public_storefront.get_public_catalog",
        return_value=FAKE_CATALOG,
    ), patch(
        "restaurant_os.public_storefront.get_settings",
    ) as mock_settings, patch(
        "urllib.request.urlopen",
        return_value=_mock_urlopen_response(ai_items),
    ):
        mock_settings.return_value = MagicMock(
            openrouter_api_key="test-key",
            openrouter_model="google/gemini-3.1-flash-lite",
            openrouter_base_url="https://openrouter.ai/api/v1",
            openrouter_timeout_seconds=15,
            openrouter_http_referer=None,
            openrouter_app_title="RestaurantOS",
        )
        response = client.post(
            "/api/v1/storefront/orders/voice",
            json={
                "transcript": "quiero 3 tacos al pastor sin cebolla y una coca",
                "branch_id": BRANCH_ID,
            },
        )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )
    data = response.json()
    assert "items" in data
    assert len(data["items"]) == 2
    assert data["items"][0]["product_id"] == PRODUCT_1
    assert data["items"][0]["quantity"] == 3
    assert data["items"][1]["product_id"] == PRODUCT_2
    assert data["items"][1]["quantity"] == 1


def test_post_storefront_voice_order_invalid_branch(
    app_with_mock_session: tuple[Any, MagicMock],
) -> None:
    """
    Given a branch_id that does not exist in the database
    When POST /api/v1/storefront/orders/voice is called
    Then it should return 404
    """
    app, mock_session = app_with_mock_session
    client = TestClient(app)

    # Branch does NOT exist
    mock_session.execute.return_value.scalar.return_value = None

    response = client.post(
        "/api/v1/storefront/orders/voice",
        json={
            "transcript": "quiero una hamburguesa",
            "branch_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 404
