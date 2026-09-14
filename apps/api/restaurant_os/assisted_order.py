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


def _line_segments(
    text: str,
    proposal_lines: list[dict[str, Any]],
    catalog_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    normalized = _normalize(text)
    starts: list[int] = []
    search_from = 0
    for candidate in proposal_lines:
        product = catalog_by_id.get(str(candidate.get("product_id", "")))
        product_name = _normalize(str(product.get("name", ""))) if product else ""
        start = normalized.find(product_name, search_from) if product_name else -1
        match_len = len(product_name)
        if start < 0 and product_name:
            stripped = re.sub(r"\d+\s*(?:oz|ml|l|gr|g|pz)?\b", "", product_name).strip()
            if stripped:
                start = normalized.find(stripped, search_from)
                match_len = len(stripped)
        if start < 0:
            return [""] * len(proposal_lines)
        starts.append(start)
        search_from = max(search_from, start + match_len)
    return [
        normalized[start : starts[index + 1] if index + 1 < len(starts) else len(normalized)]
        for index, start in enumerate(starts)
    ]


def _option_is_requested(option_name: str, line_segment: str) -> bool:
    normalized_option = _normalize(option_name)
    if not normalized_option:
        return False
    option_pattern = rf"(?<!\w){re.escape(normalized_option)}(?!\w)"
    if not re.search(option_pattern, line_segment):
        return False
    if normalized_option.startswith(("sin ", "no ")):
        return True
    negated_pattern = rf"(?<!\w)(?:sin|no)\s+{re.escape(normalized_option)}(?!\w)"
    return re.search(negated_pattern, line_segment) is None


def extract_and_redact_customer(text: str) -> tuple[str, str, str]:
    phone_pattern = re.compile(
        r"(?<!\d)(?:\+?52[\s().-]*)?\(?(?:\d[\s().-]*){9}\d(?!\d)"
    )
    phone_matches = list(phone_pattern.finditer(text))
    valid_phones = [
        digits
        for match in phone_matches
        if (
            len(digits := re.sub(r"\D", "", match.group(0))) in {10, 12}
            and (len(digits) == 10 or digits.startswith("52"))
        )
    ]
    phone = valid_phones[0] if valid_phones else ""
    number_word = r"(?:cero|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve)"
    spoken_phone_pattern = re.compile(
        rf"(?<!\w)(?:{number_word}[\s-]+){{6,14}}{number_word}(?!\w)",
        flags=re.IGNORECASE,
    )
    name_pattern = re.compile(
        r"\b(?:para|a\s+nombre\s+de|soy|me\s+llamo|mi\s+nombre\s+es|"
        r"pedido\s+(?:para|de))\s+(?!recoger\b|llevar\b)(.+?)"
        r"(?=\s+(?:con\s+)?tel[eé]fono\b|\s+\+?\d[\d\s-]{8,}\d|,?\s+"
        r"(?:y\s+)?(?:va\s+a\s+querer|quiero|quiere|pido|pide)\b|$)",
        flags=re.IGNORECASE,
    )
    detected_names = [match.group(1).strip(" ,") for match in name_pattern.finditer(text)]
    customer_name = detected_names[0] if detected_names else ""
    redacted = spoken_phone_pattern.sub(
        "[TELEFONO]", phone_pattern.sub("[TELEFONO]", text)
    )
    for detected_name in detected_names:
        redacted = re.sub(
            re.escape(detected_name), "[CLIENTE]", redacted, count=1, flags=re.IGNORECASE
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
                "minItems": 0,
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
            "unmatched_items": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["order_type", "lines", "unmatched_items"],
    }


def _parse_json_content(content: object) -> dict[str, Any]:
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        raise ValueError("provider content must be JSON")
    normalized = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", normalized, flags=re.IGNORECASE)
    if fenced:
        normalized = fenced.group(1).strip()
    parsed = json.loads(normalized)
    if not isinstance(parsed, dict):
        raise ValueError("provider content must be an object")
    return parsed


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
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Eres un capturista experto de pedidos para restaurantes en México.\n"
                    "Tu tarea es interpretar la solicitud del cliente y mapearla al catálogo provisto.\n\n"
                    "Debes devolver estrictamente un JSON con las siguientes 3 claves obligatorias:\n"
                    "- 'order_type': 'delivery', 'takeout', o null si no se especifica explícitamente.\n"
                    "- 'lines': lista de objetos {'product_id': <id_del_catalogo>, 'quantity': <numero>} ÚNICAMENTE para los productos pedidos que SÍ existen en el catálogo provisto. Usa el 'id' exacto del producto.\n"
                    "- 'unmatched_items': lista de strings con CADA artículo, comida o bebida que el cliente pidió pero que NO existe en el catálogo provisto (ejemplo: si piden tacos o sushi en una hamburguesería, pon ['2 tacos de carne asada', 'una gringa']). Si TODO lo solicitado está en el catálogo, debe ser obligatoriamente una lista vacía [].\n\n"
                    "Reglas obligatorias y estrictas:\n"
                    "1. LA CLAVE 'unmatched_items' ES OBLIGATORIA: Siempre debes incluirla en el JSON. Identifica cuidadosamente cualquier producto pedido que no esté en el menú y ponlo en 'unmatched_items'.\n"
                    "2. PROHIBIDO FORZAR COINCIDENCIAS: Si el cliente pide algo que NO existe en el catálogo, NUNCA lo asignes a otro producto del menú (como 'platillo especial', 'combo' o 'hamburguesa'). Agrégalo a 'unmatched_items' y NO lo agregues a 'lines'.\n"
                    "3. Si NINGUNO de los productos pedidos existe en el catálogo, 'lines' debe ser una lista vacía [] y 'unmatched_items' debe listar todo lo solicitado.\n"
                    "4. Asocia sinónimos directos o variaciones de presentación del mismo producto (por ejemplo: 'cafe americano' -> 'Café Americano12Oz', 'una bebida' -> 'Bebida del día', 'combo' -> 'Combo del día', 'coca' -> 'Refresco Coca-Cola').\n"
                    "5. 'quantity' debe ser un número entero (ej: 1, 2, 3).\n"
                    "6. Responde estrictamente con el JSON requerido, sin texto adicional."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "request": redacted_text,
                        "catalog": menu,
                        "response_schema": _response_schema(),
                    },
                    ensure_ascii=False,
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
        parsed = _parse_json_content(content)
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
    proposal_lines = proposal.get("lines")
    if not isinstance(proposal_lines, list) or not 0 <= len(proposal_lines) <= 20:
        raise AssistedOrderError(
            "assisted_order_invalid_response", "OpenRouter devolvió una respuesta inválida."
        )
    unmatched_items = [
        str(item).strip()
        for item in (proposal.get("unmatched_items") or [])
        if isinstance(item, str) and item.strip()
    ]
    raw_order_type = str(proposal.get("order_type") or "").strip().lower()
    if raw_order_type in {"delivery", "domicilio", "envio", "envío"}:
        order_type: str | None = "delivery"
    elif raw_order_type in {
        "takeout", "llevar", "para llevar", "recoger", "sucursal", "comedor",
        "dine_in", "aqui", "aquí", "pedido", "orden"
    }:
        order_type = "takeout"
    else:
        order_type = None

    typed_proposal_lines = [
        candidate for candidate in proposal_lines if isinstance(candidate, dict)
    ]
    if len(typed_proposal_lines) != len(proposal_lines):
        raise AssistedOrderError(
            "assisted_order_invalid_response", "La línea propuesta no es válida."
        )
    line_segments = _line_segments(redacted_text, typed_proposal_lines, by_id)
    lines: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    option_groups: list[dict[str, Any]] = []
    for index, candidate in enumerate(typed_proposal_lines):
        product_id = str(candidate.get("product_id", "")).strip()
        quantity = candidate.get("quantity")
        if product_id not in by_id:
            norm_pid = _normalize(product_id)
            for item in active_catalog:
                if _normalize(str(item["name"])) == norm_pid:
                    product_id = str(item["id"])
                    break
        if product_id not in by_id:
            norm_pid = _normalize(product_id)
            if len(norm_pid) >= 4:
                for item in active_catalog:
                    item_norm = _normalize(str(item["name"]))
                    if norm_pid in item_norm or item_norm in norm_pid:
                        product_id = str(item["id"])
                        break

        if type(quantity) is bool or type(quantity) is not int or not 1 <= quantity <= 99:
            raise AssistedOrderError(
                "assisted_order_catalog_mismatch",
                "La interpretación no coincide con el catálogo disponible.",
            )

        if product_id not in by_id:
            item_label = candidate.get("product_id") or "desconocido"
            raise AssistedOrderError(
                "assisted_order_catalog_mismatch",
                f"El producto «{item_label}» no se encuentra en el catálogo disponible de este restaurante.",
            )
        groups = modifier_loader(product_id)
        selected_options: list[dict[str, Any]] = []
        for group in groups:
            group_options = list(group.get("options") or [])
            maximum = int(group.get("maximum_selections") or 1)
            matched = [
                option
                for option in group_options
                if _option_is_requested(str(option.get("name", "")), line_segments[index])
            ][:maximum]
            selected_options.extend(
                {
                    "group_id": str(group["id"]),
                    "option_id": str(option["id"]),
                    "option_name": str(option["name"]),
                    "price_delta_cents": int(option.get("price_delta_cents") or 0),
                    "kind": "comment"
                    if (option.get("variation_kind") or option.get("selection_kind"))
                    == "order_comment"
                    else "modifier",
                }
                for option in matched
            )
            minimum = int(group.get("minimum_selections") or 0)
            if group_options:
                group_name = str(group.get("name") or "opción").lower()
                product_name = str(by_id[product_id]["name"])
                option_group = {
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
                            if (option.get("variation_kind") or option.get("selection_kind"))
                            == "order_comment"
                            else "modifier",
                        }
                        for option in group_options
                    ],
                }
                option_groups.append(option_group)
                if len(matched) < minimum:
                    questions.append(option_group)
        lines.append(
            {
                "product_id": product_id,
                "product_name": str(by_id[product_id]["name"]),
                "quantity": quantity,
                "selected_options": selected_options,
            }
        )
    if not lines:
        if unmatched_items:
            items_preview = ", ".join(f"«{item}»" for item in unmatched_items[:3])
            message = (
                f"No encontramos en el menú de este restaurante: {items_preview}. "
                "Por favor revisa los productos disponibles."
            )
        else:
            message = (
                "No se encontraron productos disponibles del catálogo en tu pedido. "
                "Por favor revisa los productos disponibles."
            )
        raise AssistedOrderError("assisted_order_unresolved", message)
    return {
        "customer_name": customer_name,
        "phone": phone,
        "order_type": order_type,
        "lines": lines,
        "unmatched_items": unmatched_items,
        "questions": questions,
        "option_groups": option_groups,
        "status": "needs_input" if questions else "ready",
        "model": options.model,
    }
