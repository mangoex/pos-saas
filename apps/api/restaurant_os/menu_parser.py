from __future__ import annotations

import json
import re
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from restaurant_os.assisted_order import OpenRouterOptions


def _clean_json_text(text: str) -> str:
    """Strip markdown backticks or preamble from LLM response."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def parse_menu_document(
    file_base64: str,
    mime_type: str,
    filename: str,
    options: OpenRouterOptions,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    """Parse a menu PDF or image file into structured categories and products using Vision LLM."""
    if not options.api_key:
        raise ValueError("No se ha configurado la API Key de IA (OpenRouter) en el servidor.")

    # Normalize mime type
    m_type = (mime_type or "").lower().strip()
    if not m_type:
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        if ext in ("jpg", "jpeg"):
            m_type = "image/jpeg"
        elif ext == "png":
            m_type = "image/png"
        elif ext == "webp":
            m_type = "image/webp"
        elif ext == "pdf":
            m_type = "application/pdf"
        else:
            m_type = "image/jpeg"

    # Clean base64 prefix if passed
    if "," in file_base64:
        file_base64 = file_base64.split(",", 1)[1]

    data_url = f"data:{m_type};base64,{file_base64}"

    system_prompt = (
        "Eres un digitalizador profesional de menús y cartas de restaurantes en México. "
        "Tu trabajo es leer con precisión la imagen o documento del menú proporcionado y "
        "extraer minuciosamente todas las categorías, platillos, bebidas y postres con sus precios en pesos mexicanos.\n\n"
        "Debes responder ESTRICTAMENTE con un objeto JSON sin explicaciones adicionales ni bloques de código extra. "
        "Estructura JSON requerida:\n"
        "{\n"
        '  "categories": [\n'
        "    {\n"
        '      "name": "Nombre de la categoría (ej. Tacos, Hamburguesas, Bebidas)",\n'
        '      "products": [\n'
        "        {\n"
        '          "name": "Nombre del platillo o bebida",\n'
        '          "price": 85.0,\n'
        '          "description": "Descripción o ingredientes indicados",\n'
        '          "station": "cocina" // o "barra" para bebidas/cafés, o "postres"\n'
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Reglas:\n"
        "1. Si un producto viene con opciones de tamaño (ej. Chico $40, Grande $60), crea un producto por cada variante (ej. 'Capuchino Chico', 'Capuchino Grande').\n"
        "2. El campo 'price' debe ser un número decimal en pesos MXN (ej. 55.0, 140.0).\n"
        "3. El campo 'station' debe ser 'barra' si es bebida, café, cerveza o coctel; 'cocina' para alimentos; 'postres' para repostería.\n"
        "4. No omitas ningún producto visible en el menú."
    )

    user_content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": f"Por favor digitaliza este menú ({filename}). Extrae todas las categorías y productos.",
        },
        {
            "type": "image_url",
            "image_url": {
                "url": data_url,
            },
        },
    ]

    body = {
        "model": options.model or "google/gemini-2.5-flash",
        "temperature": 0.1,
        "max_tokens": 3500,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }

    headers = {
        "Authorization": f"Bearer {options.api_key}",
        "Content-Type": "application/json",
        "X-OpenRouter-Title": options.app_title or "RestaurantOS Menu Scanner",
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
        with opener(request, timeout=max(options.timeout_seconds, 25.0)) as response:
            envelope = json.loads(response.read().decode("utf-8"))
        raw_content = envelope["choices"][0]["message"]["content"]
        cleaned_content = _clean_json_text(raw_content)
        parsed = json.loads(cleaned_content)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Error de conexión con el proveedor de IA: {exc}") from exc
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"No fue posible interpretar el menú de la imagen o documento: {exc}") from exc

    categories = parsed.get("categories") or []
    normalized_categories: list[dict[str, Any]] = []

    for cat in categories:
        cat_name = str(cat.get("name") or "General").strip()
        products_raw = cat.get("products") or []
        normalized_products: list[dict[str, Any]] = []

        for p in products_raw:
            p_name = str(p.get("name") or "").strip()
            if not p_name:
                continue

            try:
                price = float(p.get("price") or 0)
            except (ValueError, TypeError):
                price = 0.0

            desc = str(p.get("description") or "").strip()
            station = str(p.get("station") or "cocina").lower().strip()
            if station not in ("cocina", "barra", "postres", "packing"):
                station = "cocina"

            clean_sku_prefix = re.sub(r"[^A-Z0-9]+", "", p_name.upper())[:4] or "PRD"

            normalized_products.append(
                {
                    "name": p_name,
                    "price": price,
                    "price_cents": int(round(price * 100)),
                    "description": desc,
                    "station": station,
                    "sku": f"{clean_sku_prefix}",
                }
            )

        if normalized_products:
            normalized_categories.append(
                {
                    "name": cat_name,
                    "products": normalized_products,
                }
            )

    return {"categories": normalized_categories}
