from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from .base import IOrderChannelAdapter, NormalizedOrder, NormalizedOrderItem


class UberAvailabilityRetryableError(RuntimeError):
    """A provider outcome which can be retried without declaring success."""


class UberAvailabilityPermanentError(ValueError):
    """A provider or configuration error which must not be retried blindly."""


class UberEatsAdapter(IOrderChannelAdapter):
    PROVIDER_NAME = "UBER_EATS"
    TOKEN_URL = "https://auth.uber.com/oauth/v2/token"
    API_BASE_URL = "https://api.uber.com"

    def update_item_availability(
        self,
        *,
        client_id: str,
        client_secret: str,
        store_id: str,
        item_id: str,
        is_available: bool,
        client: httpx.Client | None = None,
    ) -> None:
        """Issue the documented availability command; only HTTP 204 confirms it."""
        if not client_id or not client_secret:
            raise UberAvailabilityPermanentError("uber_credentials_required")
        own_client = client is None
        http_client = client or httpx.Client(timeout=10.0)
        try:
            token_response = http_client.post(
                self.TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "client_credentials",
                    "scope": "eats.store",
                },
            )
            if token_response.status_code >= 500:
                raise UberAvailabilityRetryableError(
                    f"uber_token_unavailable:{token_response.status_code}"
                )
            if token_response.status_code >= 400:
                raise UberAvailabilityPermanentError(
                    f"uber_token_rejected:{token_response.status_code}"
                )
            token = str(token_response.json().get("access_token") or "")
            if not token:
                raise UberAvailabilityPermanentError("uber_access_token_missing")
            response = http_client.post(
                f"{self.API_BASE_URL}/v2/eats/stores/{quote(store_id, safe='')}/menus/items/"
                f"{quote(item_id, safe='')}",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "suspension_info": {
                        "suspension": None if is_available else {"reason": "sold_out"}
                    }
                },
            )
            if response.status_code != 204:
                if response.status_code >= 500 or response.status_code in {408, 429}:
                    raise UberAvailabilityRetryableError(
                        f"uber_update_item_retryable:{response.status_code}"
                    )
                raise UberAvailabilityPermanentError(
                    f"uber_update_item_rejected:{response.status_code}"
                )
        except httpx.TimeoutException as exc:
            raise UberAvailabilityRetryableError("uber_update_item_timeout") from exc
        except httpx.TransportError as exc:
            raise UberAvailabilityRetryableError("uber_update_item_transport_error") from exc
        finally:
            if own_client:
                http_client.close()

    def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        signature_header: str | None,
        secret: str | None,
    ) -> bool:
        """
        Valida la firma criptográfica HMAC-SHA256 enviada por Uber en X-Uber-Signature.
        """
        if not secret or not signature_header:
            return False

        # Si el header viene en formato "sha256=...", extraemos el hash
        signature = signature_header.strip()
        if signature.startswith("sha256="):
            signature = signature[7:]

        expected_hmac = hmac.new(
            secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected_hmac.lower(), signature.lower())

    def parse_webhook_event(self, payload: dict[str, Any]) -> tuple[str, str | None]:
        """
        Extrae el tipo de evento y el identificador de orden/recurso del webhook de Uber.
        """
        event_type = str(payload.get("event_type") or payload.get("type") or "orders.notification")
        resource_id = None

        meta = payload.get("meta")
        if isinstance(meta, dict):
            resource_id = meta.get("resource_id")

        if not resource_id:
            resource_id = payload.get("order_id") or payload.get("id")

        return event_type, str(resource_id) if resource_id else None

    def normalize_order(
        self,
        payload: dict[str, Any],
        product_mappings: dict[str, str],
        default_products: list[dict[str, Any]] | None = None,
    ) -> NormalizedOrder:
        """
        Convierte la estructura oficial de Uber Eats Order v2 en NormalizedOrder canónica.
        """
        order_id = str(payload.get("id") or payload.get("order_id") or "UBER-ORD-UNKNOWN")
        display_code = str(
            payload.get("display_id") or payload.get("order_display_id") or order_id[:6].upper()
        )
        if not display_code.startswith("#"):
            display_code = f"#{display_code}"

        store = payload.get("store") or {}
        external_store_id = str(store.get("id") or payload.get("store_id") or "")

        eater = payload.get("eater") or payload.get("customer") or {}
        first_name = str(eater.get("first_name") or eater.get("name") or "Cliente")
        last_name = str(eater.get("last_name") or "")
        customer_name = f"{first_name} {last_name}".strip()
        customer_phone = eater.get("phone") or eater.get("phone_number")

        delivery = payload.get("delivery") or {}
        delivery_notes = (
            delivery.get("notes") or payload.get("delivery_notes") or payload.get("order_notes")
        )

        # Parsing items
        cart = payload.get("cart") or {}
        raw_items = cart.get("items") or payload.get("items") or []

        normalized_items: list[NormalizedOrderItem] = []
        calculated_total_cents = 0

        fallback_product_id = ""
        fallback_product_name = "Producto Uber Eats"
        if default_products and len(default_products) > 0:
            fallback_product_id = default_products[0].get("id", "")
            fallback_product_name = default_products[0].get("name", "Producto Uber Eats")

        for item in raw_items:
            item_id = str(item.get("id") or item.get("item_id") or "")
            title = str(item.get("title") or item.get("name") or fallback_product_name)
            external_data = str(item.get("external_data") or item.get("sku") or item_id)
            quantity = int(item.get("quantity") or 1)

            # Resolve internal product_id
            product_id = (
                product_mappings.get(external_data)
                or product_mappings.get(item_id)
                or fallback_product_id
            )

            # Resolve price in cents
            price_info = item.get("price") or {}
            unit_price_info = price_info.get("unit_price") if isinstance(price_info, dict) else None
            unit_price_cents = 0
            if isinstance(unit_price_info, dict) and "amount" in unit_price_info:
                unit_price_cents = int(unit_price_info["amount"])
            elif isinstance(item.get("unit_price_cents"), (int, float)):
                unit_price_cents = int(item["unit_price_cents"])
            elif isinstance(item.get("price"), (int, float)):
                unit_price_cents = int(item["price"] * 100)

            line_total_cents = unit_price_cents * quantity
            calculated_total_cents += line_total_cents

            instructions = item.get("special_instructions") or item.get("notes")
            modifiers = item.get("selected_modifier_groups") or item.get("modifiers") or []

            normalized_items.append(
                NormalizedOrderItem(
                    product_id=product_id,
                    product_name=title,
                    quantity=quantity,
                    unit_price_cents=unit_price_cents,
                    line_total_cents=line_total_cents,
                    special_instructions=str(instructions) if instructions else None,
                    selected_modifiers=list(modifiers) if isinstance(modifiers, list) else [],
                )
            )

        # Resolve total
        payment = payload.get("payment") or {}
        charges = payment.get("charges") or {}
        total_info = charges.get("total") if isinstance(charges, dict) else None
        total_cents = calculated_total_cents
        if isinstance(total_info, dict) and "amount" in total_info:
            total_cents = int(total_info["amount"])
        elif isinstance(payload.get("total_cents"), int):
            total_cents = payload["total_cents"]

        placed_at = datetime.now(timezone.utc)
        raw_placed = payload.get("placed_at") or payload.get("created_at")
        if raw_placed:
            try:
                placed_at = datetime.fromisoformat(str(raw_placed).replace("Z", "+00:00"))
            except Exception:
                pass

        return NormalizedOrder(
            external_order_id=order_id,
            provider=self.PROVIDER_NAME,
            display_code=display_code,
            external_store_id=external_store_id,
            customer_name=customer_name,
            customer_phone=str(customer_phone) if customer_phone else None,
            delivery_notes=str(delivery_notes) if delivery_notes else None,
            items=normalized_items,
            total_cents=total_cents,
            currency=str(payload.get("currency") or "MXN"),
            placed_at=placed_at,
            raw_payload=payload,
        )
