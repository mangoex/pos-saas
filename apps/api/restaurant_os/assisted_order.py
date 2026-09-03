from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class AssistedOrderError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class OpenRouterOptions:
    api_key: str
    model: str
    base_url: str
    timeout_seconds: float
    http_referer: str | None = None
    app_title: str = "RestaurantOS POS"


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    without_marks = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", without_marks.lower()).strip()


def extract_and_redact_customer(text: str) -> tuple[str, str, str]:
    phone_match = re.search(r"(?:\+?52[\s-]?)?(\d[\d\s-]{8,}\d)", text)
    raw_phone = phone_match.group(0) if phone_match else ""
    digits = re.sub(r"\D", "", raw_phone)
    phone = (
        digits if len(digits) in {10, 12} and (len(digits) == 10 or digits.startswith("52")) else ""
    )
    name_match = re.search(
        r"\b(?:para|a\s+nombre\s+de)\s+(?!recoger\b|llevar\b)(.+?)"
        r"(?=\s+(?:con\s+)?tel[eé]fono\b|\s+\+?\d[\d\s-]{8,}\d|,?\s+"
        r"(?:va\s+a\s+querer|quiere|pide)\b|$)",
        text,
        flags=re.IGNORECASE,
    )
    customer_name = name_match.group(1).strip(" ,") if name_match else ""
    redacted = text
    if phone_match:
        redacted = redacted[: phone_match.start()] + "[TELEFONO]" + redacted[phone_match.end() :]
    if customer_name:
        redacted = re.sub(
            re.escape(customer_name), "[CLIENTE]", redacted, count=1, flags=re.IGNORECASE
        )
    return customer_name, phone, redacted


def _response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "order_type": {"type": ["string", "null"], "enum": ["takeout", "delivery", None]},
            "lines": {
                "type": "array",
                "minItems": 1,
                "maxItems": 20,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "product_id": {"type": "string"},
                        "quantity": {"type": "integer", "minimum": 1, "maximum": 99},
                    },
                    "required": ["product_id", "quantity"],
                },
            },
        },
        "required": ["order_type", "lines"],
    }


def request_openrouter_draft(
    redacted_text: str,
    catalog: list[dict[str, Any]],
    options: OpenRouterOptions,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    menu = [{"id": str(item["id"]), "name": str(item["name"])} for item in catalog]
    body = {
        "model": options.model,
        "temperature": 0,
        "max_tokens": 700,
        "provider": {"require_parameters": True},
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "restaurant_order_draft",
                "strict": True,
                "schema": _response_schema(),
            },
        },
        "messages": [
            {
                "role": "system",
                "content": (
                    "Eres un capturista de pedidos en español de México. Elige exclusivamente IDs "
                    "del catálogo dado. No inventes productos. Devuelve sólo el JSON del esquema."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"request": redacted_text, "catalog": menu}, ensure_ascii=False
                ),
            },
        ],
    }
    headers = {
        "Authorization": f"Bearer {options.api_key}",
        "Content-Type": "application/json",
        "X-OpenRouter-Title": options.app_title,
    }
    if options.http_referer:
        headers["HTTP-Referer"] = options.http_referer
    request = Request(
        f"{options.base_url.rstrip('/')}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with opener(request, timeout=options.timeout_seconds) as response:
            envelope = json.loads(response.read().decode("utf-8"))
        content = envelope["choices"][0]["message"]["content"]
        parsed = json.loads(content) if isinstance(content, str) else content
    except (HTTPError, URLError, TimeoutError) as exc:
        raise AssistedOrderError(
            "assisted_order_provider_unavailable", "OpenRouter no respondió a tiempo."
        ) from exc
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AssistedOrderError(
            "assisted_order_invalid_response", "OpenRouter devolvió una respuesta inválida."
        ) from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("lines"), list):
        raise AssistedOrderError(
            "assisted_order_invalid_response", "OpenRouter devolvió una respuesta inválida."
        )
    return parsed


def build_assisted_draft(
    text: str,
    catalog: list[dict[str, Any]],
    modifier_loader: Callable[[str], list[dict[str, Any]]],
    options: OpenRouterOptions,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    customer_name, phone, redacted_text = extract_and_redact_customer(text)
    active_catalog = [
        item
        for item in catalog
        if item.get("status", "active") == "active" and item.get("is_available", True) is not False
    ]
    by_id = {str(item["id"]): item for item in active_catalog}
    proposal = request_openrouter_draft(redacted_text, active_catalog, options, opener)
    order_type = proposal.get("order_type")
    if order_type not in {None, "takeout", "delivery"}:
        raise AssistedOrderError(
            "assisted_order_invalid_response", "La modalidad propuesta no es válida."
        )

    normalized_text = _normalize(redacted_text)
    lines: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    for index, candidate in enumerate(proposal["lines"]):
        if not isinstance(candidate, dict):
            raise AssistedOrderError(
                "assisted_order_invalid_response", "La línea propuesta no es válida."
            )
        product_id = str(candidate.get("product_id", ""))
        quantity = candidate.get("quantity")
        if product_id not in by_id or not isinstance(quantity, int) or not 1 <= quantity <= 99:
            raise AssistedOrderError(
                "assisted_order_catalog_mismatch",
                "La interpretación no coincide con el catálogo disponible.",
            )
        groups = modifier_loader(product_id)
        selected_options: list[dict[str, Any]] = []
        for group in groups:
            group_options = list(group.get("options") or [])
            matched = [
                option
                for option in group_options
                if _normalize(str(option.get("name", "")))
                and _normalize(str(option.get("name", ""))) in normalized_text
            ][: int(group.get("maximum_selections") or len(group_options) or 1)]
            selected_options.extend(
                {
                    "group_id": str(group["id"]),
                    "option_id": str(option["id"]),
                    "option_name": str(option["name"]),
                    "price_delta_cents": int(option.get("price_delta_cents") or 0),
                    "kind": "comment"
                    if option.get("variation_kind") == "order_comment"
                    else "modifier",
                }
                for option in matched
            )
            minimum = int(group.get("minimum_selections") or 0)
            maximum = int(group.get("maximum_selections") or 1)
            if len(matched) < minimum:
                group_name = str(group.get("name") or "opción").lower()
                product_name = str(by_id[product_id]["name"])
                questions.append(
                    {
                        "line_index": index,
                        "group_id": str(group["id"]),
                        "prompt": f"¿Qué {group_name} quiere para {product_name}?",
                        "minimum_selections": minimum,
                        "maximum_selections": maximum,
                        "options": [
                            {
                                "id": str(option["id"]),
                                "name": str(option["name"]),
                                "price_delta_cents": int(option.get("price_delta_cents") or 0),
                                "kind": "comment"
                                if option.get("variation_kind") == "order_comment"
                                else "modifier",
                            }
                            for option in group_options
                        ],
                    }
                )
        lines.append(
            {
                "product_id": product_id,
                "product_name": str(by_id[product_id]["name"]),
                "quantity": quantity,
                "selected_options": selected_options,
            }
        )
    if not lines:
        raise AssistedOrderError(
            "assisted_order_unresolved", "No se pudo identificar un producto del catálogo."
        )
    return {
        "customer_name": customer_name,
        "phone": phone,
        "order_type": order_type,
        "lines": lines,
        "questions": questions,
        "status": "needs_input" if questions else "ready",
        "model": options.model,
    }
