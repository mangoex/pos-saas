"""TDD-TS-310: governed public assisted-order draft."""

from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from restaurant_os.assisted_order import (
    AssistedOrderError,
    OpenRouterOptions,
    build_assisted_draft,
    extract_and_redact_customer,
    request_openrouter_draft,
)
from restaurant_os.database import get_session
from restaurant_os.main import create_app

BRANCH_ID = str(uuid.uuid4())
PUBLIC_KEY = "synthetic-public-key"
PRODUCT_1 = str(uuid.uuid4())

FAKE_CATALOG: dict[str, Any] = {
    "items": [
        {"id": PRODUCT_1, "name": "Tacos al Pastor"},
        {"id": str(uuid.uuid4()), "name": "Coca Cola"},
    ]
}


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


def test_public_voice_order_uses_public_key_and_returns_canonical_draft(
    app_with_mock_session: tuple[Any, MagicMock],
) -> None:
    """
    Given a valid branch with a catalog containing Tacos and Coca Cola
    When a transcript 'quiero 3 tacos al pastor sin cebolla y una coca' is sent
    Then it returns 200 with structured items mapped to catalog UUIDs
    """
    app, _mock_session = app_with_mock_session
    client = TestClient(app)

    with patch(
        "restaurant_os.api._resolve_active_public_order_key",
        return_value={"branch_id": BRANCH_ID},
    ), patch(
        "restaurant_os.api.get_public_catalog",
        return_value=FAKE_CATALOG,
    ), patch(
        "restaurant_os.api.get_settings",
    ) as mock_settings, patch(
        "restaurant_os.api.build_assisted_draft",
        return_value={
            "customer_name": "",
            "phone": "",
            "order_type": None,
            "lines": [
                {
                    "product_id": PRODUCT_1,
                    "product_name": "Tacos al Pastor",
                    "quantity": 3,
                    "selected_options": [],
                }
            ],
            "questions": [],
            "status": "ready",
            "model": "synthetic-model",
        },
    ) as build_draft:
        mock_settings.return_value = MagicMock(
            public_voice_order_enabled=True,
            openrouter_api_key="test-key",
            openrouter_model="google/gemini-3.1-flash-lite",
            openrouter_base_url="https://openrouter.ai/api/v1",
            openrouter_timeout_seconds=15,
            openrouter_http_referer=None,
            openrouter_app_title="RestaurantOS",
        )
        app.state.public_order_intents_enabled = True
        app.state.public_order_rate_limiter = MagicMock(allow=MagicMock(return_value=True))
        response = client.post(
            f"/api/v1/public/branches/{PUBLIC_KEY}/voice-order-draft",
            json={"text": "quiero 3 tacos al pastor"},
        )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )
    data = response.json()
    assert data["status"] == "ready"
    assert data["lines"][0]["product_id"] == PRODUCT_1
    assert build_draft.call_args.args[0] == "quiero 3 tacos al pastor"
    assert not _mock_session.method_calls


def test_public_voice_order_is_default_off(
    app_with_mock_session: tuple[Any, MagicMock],
) -> None:
    """
    Given a branch_id that does not exist in the database
    When POST /api/v1/storefront/orders/voice is called
    Then it should return 404
    """
    app, _mock_session = app_with_mock_session
    client = TestClient(app)

    with patch("restaurant_os.api.get_settings") as settings:
        settings.return_value = MagicMock(public_voice_order_enabled=False, openrouter_api_key=None)
        response = client.post(
            f"/api/v1/public/branches/{PUBLIC_KEY}/voice-order-draft",
            json={"text": "quiero una hamburguesa"},
        )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "public_voice_order_unavailable"


def test_public_voice_order_rejects_extra_fields_and_rate_limit(
    app_with_mock_session: tuple[Any, MagicMock],
) -> None:
    app, _mock_session = app_with_mock_session
    client = TestClient(app)
    response = client.post(
        f"/api/v1/public/branches/{PUBLIC_KEY}/voice-order-draft",
        json={"text": "quiero una hamburguesa", "branch_id": BRANCH_ID},
    )
    assert response.status_code == 422
    too_short = client.post(
        f"/api/v1/public/branches/{PUBLIC_KEY}/voice-order-draft", json={"text": "a"}
    )
    assert too_short.status_code == 422
    too_long = client.post(
        f"/api/v1/public/branches/{PUBLIC_KEY}/voice-order-draft",
        json={"text": "a" * 1_001},
    )
    assert too_long.status_code == 422

    with patch("restaurant_os.api.get_settings") as settings, patch(
        "restaurant_os.api._resolve_active_public_order_key",
        return_value={"branch_id": BRANCH_ID},
    ):
        settings.return_value = MagicMock(
            public_voice_order_enabled=True, openrouter_api_key="test-key"
        )
        app.state.public_order_intents_enabled = True
        app.state.public_order_rate_limiter = MagicMock(allow=MagicMock(return_value=False))
        response = client.post(
            f"/api/v1/public/branches/{PUBLIC_KEY}/voice-order-draft",
            json={"text": "quiero una hamburguesa"},
        )
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "public_voice_order_rate_limited"


def test_legacy_unauthenticated_voice_route_is_removed(
    app_with_mock_session: tuple[Any, MagicMock],
) -> None:
    app, _mock_session = app_with_mock_session
    client = TestClient(app)
    response = client.post(
        "/api/v1/storefront/orders/voice",
        json={"transcript": "quiero una hamburguesa", "branch_id": BRANCH_ID},
    )
    assert response.status_code == 404


def test_public_voice_order_provider_failure_is_safe_and_does_not_log_transcript(
    app_with_mock_session: tuple[Any, MagicMock], caplog: pytest.LogCaptureFixture
) -> None:
    app, _mock_session = app_with_mock_session
    client = TestClient(app)
    caplog.set_level("INFO", logger="restaurant_os.api")
    transcript = "quiero una hamburguesa para Persona Sintetica 5555555555"
    with patch("restaurant_os.api.get_settings") as settings, patch(
        "restaurant_os.api._resolve_active_public_order_key",
        return_value={"branch_id": BRANCH_ID},
    ), patch("restaurant_os.api.get_public_catalog", return_value=FAKE_CATALOG), patch(
        "restaurant_os.api.build_assisted_draft",
        side_effect=AssistedOrderError(
            "assisted_order_provider_unavailable", "Proveedor no disponible."
        ),
    ):
        settings.return_value = MagicMock(
            public_voice_order_enabled=True,
            openrouter_api_key="test-key",
            openrouter_model="synthetic-model",
            openrouter_base_url="https://openrouter.invalid/api/v1",
            openrouter_timeout_seconds=3,
            openrouter_http_referer=None,
            openrouter_app_title="RestaurantOS",
        )
        app.state.public_order_intents_enabled = True
        app.state.public_order_rate_limiter = MagicMock(allow=MagicMock(return_value=True))
        response = client.post(
            f"/api/v1/public/branches/{PUBLIC_KEY}/voice-order-draft",
            json={"text": transcript},
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "assisted_order_provider_unavailable"
    assert transcript not in caplog.text


def test_common_customer_introduction_is_redacted_before_provider() -> None:
    name, phone, redacted = extract_and_redact_customer(
        "soy Juan Perez y quiero dos tacos, mi telefono es 5555555555 "
        "y el alterno 6666666666"
    )

    assert name == "Juan Perez"
    assert phone == "5555555555"
    assert name not in redacted
    assert phone not in redacted
    assert "6666666666" not in redacted
    assert redacted.count("[TELEFONO]") == 2

    _name, parenthesized_phone, parenthesized = extract_and_redact_customer(
        "mi telefono es +52 (667) 201-3019 y alterno 667.201.3020"
    )
    assert parenthesized_phone == "526672013019"
    assert "667" not in parenthesized
    assert parenthesized.count("[TELEFONO]") == 2

    _name, _phone, spoken = extract_and_redact_customer(
        "mi teléfono es seis seis siete dos cero uno tres cero uno nueve y quiero tacos"
    )
    assert "seis seis siete" not in spoken
    assert "[TELEFONO]" in spoken


def test_provider_json_object_contract_accepts_fenced_json() -> None:
    captured: dict[str, Any] = {}
    response = MagicMock()
    response.read.return_value = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            '```json\n{"order_type": null, "lines": '
                            '[{"product_id": "product-1", "quantity": 1}]}\n```'
                        )
                    }
                }
            ]
        }
    ).encode()
    response.__enter__.return_value = response
    response.__exit__.return_value = False

    def opener(request: Any, timeout: float) -> MagicMock:
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return response

    options = OpenRouterOptions(
        "synthetic-provider-value",
        "synthetic-model",
        "https://openrouter.invalid/api/v1",
        3,
    )
    parsed = request_openrouter_draft(
        "un taco", [{"id": "product-1", "name": "Taco"}], options, opener
    )

    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert parsed["lines"][0]["product_id"] == "product-1"


def test_public_catalog_validation_rejects_boolean_quantity_and_requires_human_options() -> None:
    options = OpenRouterOptions(
        "synthetic-provider-value",
        "synthetic-model",
        "https://openrouter.invalid/api/v1",
        3,
    )
    catalog = [{"id": "product-1", "name": "Taco", "is_available": True}]
    with patch(
        "restaurant_os.assisted_order.request_openrouter_draft",
        return_value={
            "order_type": None,
            "lines": [{"product_id": "product-1", "quantity": True}],
        },
    ), pytest.raises(AssistedOrderError) as error:
        build_assisted_draft("un taco", catalog, lambda _id: [], options)
    assert error.value.code == "assisted_order_catalog_mismatch"

    with patch(
        "restaurant_os.assisted_order.request_openrouter_draft",
        return_value={
            "order_type": None,
            "lines": [{"product_id": "product-1", "quantity": 1}],
        },
    ):
        draft = build_assisted_draft(
            "un taco sin cebolla",
            catalog,
            lambda _id: [
                {
                    "id": "comments",
                    "minimum_selections": 0,
                    "maximum_selections": 1,
                    "options": [
                        {
                            "id": "no-onion",
                            "name": "Sin cebolla",
                            "price_delta_cents": 0,
                            "selection_kind": "order_comment",
                        }
                    ],
                }
            ],
            options,
        )

    assert draft["lines"][0]["selected_options"][0]["kind"] == "comment"
    assert draft["option_groups"][0]["options"][0]["kind"] == "comment"
    assert draft["status"] == "ready"


def test_modifier_text_is_not_applied_globally_across_multiple_lines() -> None:
    options = OpenRouterOptions(
        "synthetic-provider-value",
        "synthetic-model",
        "https://openrouter.invalid/api/v1",
        3,
    )
    catalog = [
        {"id": "burger", "name": "Hamburguesa", "is_available": True},
        {"id": "hot-dog", "name": "Hot dog", "is_available": True},
    ]
    with patch(
        "restaurant_os.assisted_order.request_openrouter_draft",
        return_value={
            "order_type": None,
            "lines": [
                {"product_id": "burger", "quantity": 1},
                {"product_id": "hot-dog", "quantity": 1},
            ],
        },
    ):
        draft = build_assisted_draft(
            "hamburguesa con queso y hot dog sin queso",
            catalog,
            lambda product_id: [
                {
                    "id": f"extras-{product_id}",
                    "name": "Extras",
                    "minimum_selections": 0,
                    "maximum_selections": 1,
                    "options": [
                        {
                            "id": f"cheese-{product_id}",
                            "name": "Queso",
                            "price_delta_cents": 100,
                            "selection_kind": "modifier",
                        }
                    ],
                }
            ],
            options,
        )

    assert [
        [selection["option_id"] for selection in line["selected_options"]]
        for line in draft["lines"]
    ] == [["cheese-burger"], []]
    assert [group["line_index"] for group in draft["option_groups"]] == [0, 1]

    with patch(
        "restaurant_os.assisted_order.request_openrouter_draft",
        return_value={
            "order_type": None,
            "lines": [
                {"product_id": "burger", "quantity": 1},
                {"product_id": "hot-dog", "quantity": 1},
            ],
        },
    ):
        ambiguous = build_assisted_draft(
            "hamburguesa con queso y un perro caliente",
            catalog,
            lambda product_id: [
                {
                    "id": f"extras-{product_id}",
                    "name": "Extras",
                    "minimum_selections": 0,
                    "maximum_selections": 1,
                    "options": [
                        {
                            "id": f"cheese-{product_id}",
                            "name": "Queso",
                            "price_delta_cents": 100,
                            "selection_kind": "modifier",
                        }
                    ],
                }
            ],
            options,
        )
    assert [line["selected_options"] for line in ambiguous["lines"]] == [[], []]


def test_voice_order_when_items_not_in_menu_returns_unresolved_with_informative_message(
    app_with_mock_session: tuple[Any, MagicMock],
) -> None:
    app, _mock_session = app_with_mock_session
    client = TestClient(app)

    with patch("restaurant_os.api.get_settings") as settings, patch(
        "restaurant_os.api._resolve_active_public_order_key",
        return_value={"branch_id": BRANCH_ID},
    ), patch("restaurant_os.api.get_public_catalog", return_value=FAKE_CATALOG), patch(
        "restaurant_os.assisted_order.request_openrouter_draft",
        return_value={
            "order_type": None,
            "lines": [],
            "unmatched_items": ["2 tacos de carne asada", "una gringa al pastor"],
        },
    ):
        settings.return_value = MagicMock(
            public_voice_order_enabled=True,
            openrouter_api_key="test-key",
            openrouter_model="test-model",
            openrouter_base_url="https://openrouter.ai/api/v1",
            openrouter_timeout_seconds=5,
            openrouter_http_referer=None,
            openrouter_app_title="RestaurantOS",
        )
        app.state.public_order_intents_enabled = True
        app.state.public_order_rate_limiter = MagicMock(allow=MagicMock(return_value=True))
        response = client.post(
            f"/api/v1/public/branches/{PUBLIC_KEY}/voice-order-draft",
            json={"text": "quiero dos tacos de asada y una gringa"},
        )

    assert response.status_code == 422
    data = response.json()
    assert data["detail"]["code"] == "assisted_order_unresolved"
    assert "2 tacos de carne asada" in data["detail"]["message"]
    assert "una gringa al pastor" in data["detail"]["message"]


def test_voice_order_partial_match_includes_unmatched_items_in_draft(
    app_with_mock_session: tuple[Any, MagicMock],
) -> None:
    app, _mock_session = app_with_mock_session
    client = TestClient(app)

    with patch("restaurant_os.api.get_settings") as settings, patch(
        "restaurant_os.api._resolve_active_public_order_key",
        return_value={"branch_id": BRANCH_ID},
    ), patch("restaurant_os.api.get_public_catalog", return_value=FAKE_CATALOG), patch(
        "restaurant_os.assisted_order.request_openrouter_draft",
        return_value={
            "order_type": None,
            "lines": [{"product_id": PRODUCT_1, "quantity": 1}],
            "unmatched_items": ["2 tacos de carne asada"],
        },
    ):
        settings.return_value = MagicMock(
            public_voice_order_enabled=True,
            openrouter_api_key="test-key",
            openrouter_model="test-model",
            openrouter_base_url="https://openrouter.ai/api/v1",
            openrouter_timeout_seconds=5,
            openrouter_http_referer=None,
            openrouter_app_title="RestaurantOS",
        )
        app.state.public_order_intents_enabled = True
        app.state.public_order_rate_limiter = MagicMock(allow=MagicMock(return_value=True))
        response = client.post(
            f"/api/v1/public/branches/{PUBLIC_KEY}/voice-order-draft",
            json={"text": "quiero una hamburguesa y 2 tacos de asada"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["lines"][0]["product_id"] == PRODUCT_1
    assert data["unmatched_items"] == ["2 tacos de carne asada"]
