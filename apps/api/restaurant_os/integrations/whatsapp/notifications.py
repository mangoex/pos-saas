"""Proactive order status notification service for Meta WhatsApp Business."""

from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from restaurant_os import models

from .adapter import send_whatsapp_text_message

logger = logging.getLogger(__name__)


class WhatsAppNotificationService:
    """Dispatches real-time WhatsApp status notifications for customer orders."""

    def __init__(
        self,
        session: Session,
        organization_id: str | None = None,
        branch_id: str | None = None,
    ) -> None:
        self.session = session
        self.organization_id = organization_id
        self.branch_id = branch_id

    def notify_order_status_update(
        self,
        order_id: str,
        new_status: str,
        notes: str | None = None,
        tracking_url: str | None = None,
        smart_rating_url: str | None = None,
    ) -> dict[str, Any]:
        """Send an outbound transactional notification according to order lifecycle."""
        # If organization_id or branch_id was omitted, resolve from order
        if not self.organization_id or not self.branch_id:
            ord_row = (
                self.session.execute(
                    sa.select(models.orders.c.organization_id, models.orders.c.branch_id).where(
                        models.orders.c.id == order_id
                    )
                )
                .mappings()
                .first()
            )
            if not ord_row:
                return {"status": "skipped", "reason": "order_not_found"}
            self.organization_id = self.organization_id or str(ord_row["organization_id"])
            self.branch_id = self.branch_id or str(ord_row["branch_id"])

        # 1. Verify WhatsApp integration is configured and enabled for organization
        channel_config = (
            self.session.execute(
                sa.select(models.channel_integrations).where(
                    models.channel_integrations.c.organization_id == self.organization_id,
                    models.channel_integrations.c.provider == "WHATSAPP_BUSINESS",
                )
            )
            .mappings()
            .first()
        )
        if not channel_config or not channel_config.get("is_enabled"):
            return {"status": "skipped", "reason": "whatsapp_not_connected"}

        # 2. Verify branch has a mapped and active WhatsApp phone number
        mapping = (
            self.session.execute(
                sa.select(models.channel_store_mappings).where(
                    models.channel_store_mappings.c.organization_id == self.organization_id,
                    models.channel_store_mappings.c.branch_id == self.branch_id,
                    models.channel_store_mappings.c.provider == "WHATSAPP_BUSINESS",
                    models.channel_store_mappings.c.is_active.is_(True),
                )
            )
            .mappings()
            .first()
        )
        if not mapping or not mapping.get("external_store_id"):
            return {"status": "skipped", "reason": "whatsapp_not_connected"}

        phone_number_id = str(mapping["external_store_id"])

        # 3. Fetch order details
        order = (
            self.session.execute(
                sa.select(models.orders).where(
                    models.orders.c.id == order_id,
                    models.orders.c.organization_id == self.organization_id,
                )
            )
            .mappings()
            .first()
        )
        if not order:
            return {"status": "skipped", "reason": "order_not_found"}

        # 4. Resolve customer contact phone
        customer_snapshot = order.get("customer_snapshot") or {}
        raw_phone = str(customer_snapshot.get("phone") or "").strip()
        name = str(customer_snapshot.get("name") or "Cliente").strip()
        if not raw_phone:
            return {"status": "skipped", "reason": "no_customer_phone"}

        # 5. Resolve branch branding and tracking URL
        branch = (
            self.session.execute(
                sa.select(models.branches).where(models.branches.c.id == self.branch_id)
            )
            .mappings()
            .first()
        )
        branch_name = branch["name"] if branch else "Restaurante"
        slug = (branch.get("slug") or self.branch_id) if branch else self.branch_id
        storefront_url = f"https://mimenu.com/{slug}"
        resolved_tracking_url = tracking_url or f"{storefront_url}/orders/{order_id}"
        resolved_rating_url = smart_rating_url or f"{storefront_url}/orders/{order_id}/review"
        folio = order.get("folio") or order_id[:8].upper()
        order_type = str(order.get("order_type") or "delivery").lower()

        # 6. Compose message based on status
        normalized_status = str(new_status).upper()
        if normalized_status in {"ACCEPTED", "IN_PRODUCTION"}:
            message = (
                f"¡Hola {name}! 👋 Tu pedido #{folio} en *{branch_name}* ha sido aceptado "
                "y la cocina comenzó a prepararlo. 👨‍🍳🔥\n\n"
                "Puedes consultar el progreso en vivo aquí:\n"
                f"👉 {resolved_tracking_url}"
            )
        elif normalized_status == "READY":
            if order_type in {"takeout", "pickup", "recoger", "comedor", "dine_in"}:
                message = (
                    f"¡Tu pedido #{folio} está LISTO! 🌮🍽️ Ya puedes pasar a recogerlo "
                    f"al mostrador de *{branch_name}*. ¡Te esperamos!\n\n"
                    f"Detalles de tu orden:\n👉 {resolved_tracking_url}"
                )
            else:
                message = (
                    f"¡Tu pedido #{folio} está LISTO en cocina! 📦 "
                    "Esperando asignación de repartidor.\n\n"
                    f"Sigue tu pedido en vivo aquí:\n👉 {resolved_tracking_url}"
                )
        elif normalized_status == "IN_DELIVERY":
            message = (
                f"¡Tu pedido #{folio} va en camino! 🛵💨 Nuestro repartidor ya salió "
                "con tu comida hacia tu dirección.\n\n"
                f"Sigue la entrega en tiempo real aquí:\n👉 {resolved_tracking_url}"
            )
        elif normalized_status == "DELIVERED":
            message = (
                f"¡Tu pedido #{folio} ha sido entregado con éxito! 🎉 "
                "Esperamos que disfrutes cada bocado.\n\n"
                "⭐ Tu opinión es muy importante para nosotros. "
                "¿Cómo calificarías tu experiencia de hoy?\n"
                f"👉 {resolved_rating_url}\n\n"
                "¡Muchas gracias por tu preferencia!"
            )
        elif normalized_status in {"CANCELLED", "REJECTED"}:
            reason_str = f" Motivo: {notes}" if notes else ""
            message = (
                f"Aviso: Tu pedido #{folio} en *{branch_name}* ha sido cancelado.{reason_str}\n\n"
                "Si tienes alguna duda o deseas ordenar de nuevo, visita:\n"
                f"👉 {storefront_url}"
            )
        else:
            message = (
                f"Actualización de tu pedido #{folio} en *{branch_name}*: "
                f"el estado actual es *{normalized_status}*.\n\n"
                f"👉 {resolved_tracking_url}"
            )

        # 7. Dispatch message via WhatsApp adapter
        meta_res = send_whatsapp_text_message(
            phone_number_id=phone_number_id,
            to_phone=raw_phone,
            message_text=message,
            access_token=channel_config.get("client_secret"),
            environment=channel_config.get("environment", "sandbox"),
        )

        return {
            "status": "sent",
            "order_id": order_id,
            "folio": folio,
            "to_phone": raw_phone,
            "new_status": normalized_status,
            "message": message,
            "meta_response": meta_res,
        }

    notify_order_status_change = notify_order_status_update

