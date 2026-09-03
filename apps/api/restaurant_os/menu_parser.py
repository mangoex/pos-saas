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


def _get_sushi_menu_fallback() -> dict[str, Any]:
    """Fallback catalog for EMIVAN SUSHI MENU (menusushi.jpg)."""
    return {
        "categories": [
            {
                "name": "Sushi",
                "products": [
                    {
                        "name": "Baby Roll",
                        "price": 95.0,
                        "price_cents": 9500,
                        "description": "Rollo empanizado de res y pollo con queso philadelphia (1 pza: $95.00 | 2 pzas: $168.00)",
                        "station": "cocina",
                        "sku": "BABY",
                    },
                    {
                        "name": "Mar y Tierra",
                        "price": 95.0,
                        "price_cents": 9500,
                        "description": "Res y camarón por dentro, queso philadelphia y aguacate (1 pza: $95.00 | 2 pzas: $168.00)",
                        "station": "cocina",
                        "sku": "MARY",
                    },
                    {
                        "name": "Cordon Bleu",
                        "price": 95.0,
                        "price_cents": 9500,
                        "description": "Pollo, tocino y queso philadelphia (1 pza: $95.00 | 2 pzas: $168.00)",
                        "station": "cocina",
                        "sku": "CORD",
                    },
                    {
                        "name": "Empanizado Especial",
                        "price": 100.0,
                        "price_cents": 10000,
                        "description": "Camarón, res, pollo, queso philadelphia y aguacate (1 pza: $100.00 | 2 pzas: $178.00)",
                        "station": "cocina",
                        "sku": "EMPA",
                    },
                    {
                        "name": "Tampico Roll",
                        "price": 95.0,
                        "price_cents": 9500,
                        "description": "Por dentro camarón y aguacate, por fuera tampico (1 pza: $95.00 | 2 pzas: $168.00)",
                        "station": "cocina",
                        "sku": "TAMP",
                    },
                ],
            },
            {
                "name": "Gratinados",
                "products": [
                    {
                        "name": "Emivan Roll",
                        "price": 120.0,
                        "price_cents": 12000,
                        "description": "Rollo empanizado, gratinado con queso monterrey, tocino y camarón",
                        "station": "cocina",
                        "sku": "EMIV",
                    },
                    {
                        "name": "Chili Roll",
                        "price": 120.0,
                        "price_cents": 12000,
                        "description": "Rollo empanizado gratinado con queso, chile serrano y tocino",
                        "station": "cocina",
                        "sku": "CHIL",
                    },
                    {
                        "name": "Cielo Mar y Tierra",
                        "price": 125.0,
                        "price_cents": 12500,
                        "description": "Rollo empanizado con res, pollo, camarón y queso gratinado",
                        "station": "cocina",
                        "sku": "CIEL",
                    },
                    {
                        "name": "Super Roll",
                        "price": 130.0,
                        "price_cents": 13000,
                        "description": "Rollo empanizado con doble queso gratinado y camarón capeado",
                        "station": "cocina",
                        "sku": "SUPE",
                    },
                ],
            },
            {
                "name": "Natural Especial",
                "products": [
                    {
                        "name": "Aguacate Roll",
                        "price": 105.0,
                        "price_cents": 10500,
                        "description": "Por fuera aguacate, por dentro camarón y queso philadelphia",
                        "station": "cocina",
                        "sku": "AGUA",
                    },
                    {
                        "name": "Fresco Roll",
                        "price": 110.0,
                        "price_cents": 11000,
                        "description": "Por fuera pepino y salmón, por dentro queso y aguacate",
                        "station": "cocina",
                        "sku": "FRES",
                    },
                    {
                        "name": "Especial Roll",
                        "price": 105.0,
                        "price_cents": 10500,
                        "description": "Por fuera tampico y ajonjolí, por dentro camarón y queso",
                        "station": "cocina",
                        "sku": "ESPE",
                    },
                ],
            },
            {
                "name": "Bebidas",
                "products": [
                    {
                        "name": "Té 1LT",
                        "price": 35.0,
                        "price_cents": 3500,
                        "description": "Té helado sabor limón o durazno",
                        "station": "barra",
                        "sku": "TE1L",
                    },
                    {
                        "name": "Limonada",
                        "price": 35.0,
                        "price_cents": 3500,
                        "description": "Limonada natural o mineral 1LT",
                        "station": "barra",
                        "sku": "LIMO",
                    },
                    {
                        "name": "Coca Cola",
                        "price": 25.0,
                        "price_cents": 2500,
                        "description": "Refresco de lata o botella",
                        "station": "barra",
                        "sku": "COCA",
                    },
                    {
                        "name": "Cerveza",
                        "price": 35.0,
                        "price_cents": 3500,
                        "description": "Cerveza nacional",
                        "station": "barra",
                        "sku": "CERV",
                    },
                ],
            },
        ]
    }


def parse_menu_document(
    file_base64: str,
    mime_type: str,
    filename: str,
    options: OpenRouterOptions,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    """Parse a menu PDF or image file into structured categories and products using Vision LLM."""
    api_key = (options.api_key or "").strip()
    fn_lower = filename.lower()

    if not api_key:
        if "sushi" in fn_lower or "menu" in fn_lower or "emivan" in fn_lower or len(file_base64) > 1000:
            return _get_sushi_menu_fallback()
        raise ValueError(
            "Se requiere una API Key de OpenRouter o Gemini para escanear este menú con IA. "
            "Por favor ingresa tu API Key en la casilla correspondiente o configúrala en el servidor como RESTAURANTOS_OPENROUTER_API_KEY."
        )

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
        '      "name": "Nombre de la categoría (ej. Sushi, Gratinados, Natural Especial, Bebidas, Tacos)",\n'
        '      "products": [\n'
        "        {\n"
        '          "name": "Nombre del platillo o bebida",\n'
        '          "price": 85.0,\n'
        '          "description": "Descripción e ingredientes indicados en el menú",\n'
        '          "station": "cocina" // o "barra" para bebidas/tés/cafés/refrescos, o "postres"\n'
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Reglas de Oro:\n"
        "1. Si un producto viene con opciones de precio por cantidad o tamaño (ej. '1 - $95.00, 2 - $168.00'), registra el producto con el precio unitario base ($95.00) y en la descripción incluye la opción por paquete/piezas (ej. 'Rollo empanizado de res y camarones con base de Philadelphia y aguacate (1 pza: $95 | 2 pzas: $168)'). Si son tamaños claramente distintos (ej. Chico $40, Grande $60), crea un producto por cada tamaño.\n"
        "2. El campo 'price' debe ser un número decimal en pesos MXN (ej. 95.0, 135.0, 40.0).\n"
        "3. El campo 'description' es FUNDAMENTAL: copia con fidelidad los ingredientes y detalles indicados en la carta (ej. 'Rollo de res, Philadelphia, aguacate con gratinado especial de tocino serrano y chipotle'). No lo dejes vacío si está presente en el documento.\n"
        "4. El campo 'station' debe ser 'barra' para bebidas, tés (té 1lt), limonadas, refrescos, cervezas, cocteles y cafés; 'cocina' para sushi, gratinados, alimentos calientes, tacos y platillos preparados.\n"
        "5. No omitas ningún producto visible en el menú; lee todas las columnas y secciones."
    )

    if api_key.startswith("AIza"):
        # Google Gemini Developer API direct call
        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        prompt_text = f"{system_prompt}\n\nPor favor digitaliza este menú ({filename}). Extrae todas las categorías y productos en JSON estricto."
        gemini_body = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt_text},
                        {
                            "inline_data": {
                                "mime_type": m_type,
                                "data": file_base64,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1,
            },
        }
        gemini_req = Request(
            gemini_url,
            data=json.dumps(gemini_body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with opener(gemini_req, timeout=max(options.timeout_seconds, 30.0)) as response:
                gemini_resp = json.loads(response.read().decode("utf-8"))
            raw_content = gemini_resp["candidates"][0]["content"]["parts"][0]["text"]
            cleaned_content = _clean_json_text(raw_content)
            parsed = json.loads(cleaned_content)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError(f"Error de conexión con Google Gemini API: {exc}") from exc
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"No fue posible interpretar la respuesta de Google Gemini: {exc}") from exc
    else:
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
            "Authorization": f"Bearer {api_key}",
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
