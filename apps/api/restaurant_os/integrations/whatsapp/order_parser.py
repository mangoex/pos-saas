"""Order parser service for WhatsApp Conversational Commerce."""

from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .knowledge import WhatsAppKnowledgeService


WORD_TO_NUMBER: dict[str, int] = {
    "un": 1,
    "una": 1,
    "uno": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
}

ORDER_INTENT_WORDS = [
    "pedir",
    "ordenar",
    "quiero",
    "mandame",
    "mándame",
    "manda",
    "traeme",
    "tráeme",
    "pido",
    "llevar",
    "domicilio",
    "ordenes",
    "órdenes",
    "orden",
    "comprar",
    "encargar",
]


def _normalize(value: str) -> str:
    """Normalize string: remove accents, lowercase, strip special characters."""
    decomposed = unicodedata.normalize("NFD", value)
    without_marks = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", without_marks.lower()).strip()


def _clean_product_name(name: str) -> str:
    """Remove presentation noise from product name for matching (e.g. '(Orden)', '12oz')."""
    clean = re.sub(r"\(.*?\)", "", name)
    clean = re.sub(r"\b\d+\s*(?:oz|ml|l|gr|g|pz)?\b", "", clean, flags=re.IGNORECASE)
    return _normalize(clean)


class WhatsAppOrderParser:
    """Parses customer messages to extract items, quantities, 86'd items, and cart links."""

    def __init__(self, knowledge_service: WhatsAppKnowledgeService) -> None:
        self.knowledge_service = knowledge_service

    def parse_order_intent(self, text: str) -> dict[str, Any]:
        """Analyze message for ordering intent and map against live branch catalog."""
        raw_text = (text or "").strip()
        normalized_text = _normalize(raw_text)

        # 1. Detect order intent
        has_intent_keyword = any(w in normalized_text.split() for w in ORDER_INTENT_WORDS) or any(
            "quiero" in normalized_text
            or "me gustaria" in normalized_text
            or "me gustaría" in raw_text.lower()
            or "mandame" in normalized_text
            or "traeme" in normalized_text
            for _ in [1]
        )

        catalog_items = self.knowledge_service.get_branch_catalog_items()
        summary = self.knowledge_service.get_branch_knowledge_summary()
        storefront_url = summary.get("storefront_url") or "https://mimenu.com"

        matched_items: list[dict[str, Any]] = []
        unavailable_items: list[dict[str, Any]] = []
        matched_spans: list[tuple[int, int]] = []

        # 2. Match products against normalized text
        for item in catalog_items:
            full_norm = _normalize(item["name"])
            clean_norm = _clean_product_name(item["name"])

            # Candidate names to search
            candidates = [full_norm]
            if clean_norm and clean_norm != full_norm:
                candidates.append(clean_norm)

            for cand in candidates:
                if not cand or len(cand) < 3:
                    continue

                idx = normalized_text.find(cand)
                if idx >= 0:
                    matched_spans.append((idx, idx + len(cand)))

                    # Extract quantity immediately before the product name
                    prefix = normalized_text[:idx].strip()
                    qty = 1
                    # Pattern matching quantity before product: e.g. "2 ordenes de", "dos", "2"
                    qty_match = re.search(
                        r"(?:^|\s)(un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|\d+)\s*(?:ordenes|orden|piezas|pzs|pz|de|\s)*$",
                        prefix,
                        flags=re.IGNORECASE,
                    )
                    if qty_match:
                        raw_qty_chunk = qty_match.group(1).lower()
                        if raw_qty_chunk.isdigit():
                            qty = max(1, int(raw_qty_chunk))
                        elif raw_qty_chunk in WORD_TO_NUMBER:
                            qty = WORD_TO_NUMBER[raw_qty_chunk]
                    else:
                        suffix = normalized_text[idx + len(cand) :].strip()
                        post_match = re.search(
                            r"^(?:x|\*|de)?\s*(un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|\d+)\b",
                            suffix,
                            flags=re.IGNORECASE,
                        )
                        if post_match:
                            raw_post = post_match.group(1).lower()
                            if raw_post.isdigit():
                                qty = max(1, int(raw_post))
                            elif raw_post in WORD_TO_NUMBER:
                                qty = WORD_TO_NUMBER[raw_post]

                    # Check availability (86'd)
                    if item["is_available"]:
                        matched_items.append(
                            {
                                "product_id": item["id"],
                                "product_name": item["name"],
                                "quantity": qty,
                                "unit_price_cents": item["price_cents"],
                                "subtotal_cents": qty * item["price_cents"],
                                "sku": item.get("sku", ""),
                            }
                        )
                    else:
                        unavailable_items.append(
                            {
                                "product_id": item["id"],
                                "product_name": item["name"],
                                "quantity": qty,
                                "unit_price_cents": item["price_cents"],
                                "is_available": False,
                            }
                        )
                    break

        is_order_intent = has_intent_keyword or bool(matched_items) or bool(unavailable_items)

        # 3. Detect unmatched food items if order intent was present
        unmatched_items: list[str] = []
        if is_order_intent:
            # Look for segments joined by 'y', ',', 'con', 'mas' that were not matched
            segments = re.split(r",|\by\b|\bmas\b|\bcon\b", normalized_text)
            for seg in segments:
                seg_clean = seg.strip()
                # Remove intent prefixes
                prefix_words = ORDER_INTENT_WORDS + [
                    "un", "una", "uno", "de", "por", "favor", "hola", "buenas", "tardes"
                ]
                for prefix_word in prefix_words:
                    seg_clean = re.sub(rf"\b{prefix_word}\b", "", seg_clean).strip()

                if not seg_clean or len(seg_clean) < 3:
                    continue

                # Check if this segment matched any known product
                already_matched = False
                for item in matched_items + unavailable_items:
                    clean_item = _clean_product_name(item["product_name"])
                    if clean_item in seg_clean or seg_clean in clean_item:
                        already_matched = True
                        break

                if not already_matched:
                    # Ignore common greeting/pleasantry noise
                    ignored_words = {
                        "buenas", "tardes", "noches", "dias", "saludos",
                        "gracias", "llevar", "domicilio"
                    }
                    if seg_clean not in ignored_words:
                        unmatched_items.append(seg_clean)

        total_cents = sum(item["subtotal_cents"] for item in matched_items)

        # 4. Construct prefilled digital storefront cart URL
        cart_url = ""
        if matched_items:
            items_payload = [
                {"product_id": item["product_id"], "quantity": item["quantity"]}
                for item in matched_items
            ]
            encoded_payload = urllib.parse.quote(json.dumps(items_payload))
            cart_url = f"{storefront_url}/cart?items={encoded_payload}&from=wa"

        return {
            "is_order_intent": is_order_intent,
            "matched_items": matched_items,
            "unavailable_items": unavailable_items,
            "unmatched_items": unmatched_items,
            "total_cents": total_cents,
            "cart_url": cart_url,
            "storefront_url": storefront_url,
            "branch_name": summary.get("branch_name", "Restaurante"),
        }
