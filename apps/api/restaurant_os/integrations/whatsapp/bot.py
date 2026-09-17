"""Conversational AI Assistant (PBD) for WhatsApp Customer Service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .order_parser import WhatsAppOrderParser

if TYPE_CHECKING:
    from .knowledge import WhatsAppKnowledgeService


class WhatsAppBot:
    """Prompt Behavior Design (PBD) conversational bot for WhatsApp."""

    def __init__(
        self,
        knowledge_service: WhatsAppKnowledgeService,
        campaign_service: Any = None,
    ) -> None:
        self.knowledge_service = knowledge_service
        self.campaign_service = campaign_service
        self.order_parser = WhatsAppOrderParser(knowledge_service)

    def parse_order(self, incoming_text: str) -> dict[str, Any]:
        """Parse ordering intent and return structured cart data."""
        return self.order_parser.parse_order_intent(incoming_text)

    def generate_reply(self, incoming_text: str, sender_phone: str | None = None) -> str:
        """Generate a contextual response based on the restaurant's live knowledge base."""
        summary = self.knowledge_service.get_branch_knowledge_summary()
        text = (incoming_text or "").strip().lower()

        branch_name = summary["branch_name"]
        store_url = summary["storefront_url"]
        menu = summary["available_products_text"]
        hours = summary["hours_text"]
        promos = summary["promotions_text"]

        # Check for opt-out / unsubscribe keywords
        words = set(text.replace(".", " ").replace(",", " ").split())
        opt_out_words = {"stop", "baja", "cancelar", "cancel", "desuscribir"}
        if words.intersection(opt_out_words) or "baja" in text or "stop" in text:
            if self.campaign_service and sender_phone:
                self.campaign_service.record_opt_out(sender_phone, reason="user_stop")
            return (
                f"Has sido dado de baja de nuestras promociones por WhatsApp de *{branch_name}*. "
                "No recibirás más mensajes publicitarios. Seguirás recibiendo las notificaciones "
                "del estado de tus pedidos en curso. Si deseas volver a suscribirte, responde ALTA."
            )

        # 0. Conversational Commerce: Order intent & cart proposals
        parsed_order = self.parse_order(incoming_text)
        if parsed_order["is_order_intent"]:
            matched = parsed_order["matched_items"]
            unavail = parsed_order["unavailable_items"]
            unmatched = parsed_order["unmatched_items"]

            if matched or unavail:
                lines = ["¡Excelente elección! 🌮 He preparado tu pedido:\n"]
                if matched:
                    for item in matched:
                        unit_fmt = f"${item['unit_price_cents'] / 100:.2f}"
                        sub_fmt = f"${item['subtotal_cents'] / 100:.2f}"
                        lines.append(
                            f"• {item['quantity']}x {item['product_name']} — "
                            f"{sub_fmt} MXN ({unit_fmt} c/u)"
                        )

                if unavail:
                    lines.append("\n⚠️ *Aviso de disponibilidad:*")
                    for u in unavail:
                        lines.append(
                            f"• *{u['product_name']}* no está disponible en este momento (agotado)."
                        )

                if unmatched:
                    items_str = ", ".join(f"*{u}*" for u in unmatched)
                    lines.append(f"\nℹ️ No encontramos en nuestro menú: {items_str}.")

                if matched:
                    total_fmt = f"${parsed_order['total_cents'] / 100:.2f}"
                    lines.append(f"\n💰 *Total estimado: {total_fmt} MXN*")
                    lines.append(
                        "\nPara confirmar tu dirección o entrega y elegir método de pago, "
                        "finaliza tu pedido aquí:"
                    )
                    lines.append(f"👉 {parsed_order['cart_url']}")
                    lines.append(
                        "\n¡En cuanto lo confirmes, cocina comenzará a prepararlo! 👨‍🍳🔥"
                    )
                else:
                    lines.append(
                        "\nPor el momento no fue posible agregar productos disponibles al carrito. "
                        f"Consulta nuestro menú digital actualizado aquí:\n👉 {store_url}"
                    )

                return "\n".join(lines)

            # Order intent detected without specific items
            order_keywords = ["pedir", "ordenar", "domicilio", "llevar", "quiero ordenar"]
            if any(w in text for w in order_keywords):
                return (
                    f"¡Con gusto te tomamos tu orden en *{branch_name}*! 🛵💨\n\n"
                    "¿Qué se te antoja hoy? Puedes escribirnos lo que deseas "
                    "(ej. *'Quiero 2 tacos al pastor'*), o consultar nuestro menú digital "
                    "completo y ordenar directamente aquí:\n"
                    f"👉 {store_url}\n\n"
                    "¡Estamos listos para atenderte!"
                )

        # 1. Hours / Schedule inquiry
        hour_words = ["hora", "horario", "abren", "cierran", "abierto", "cerrado", "que dias"]
        if any(w in text for w in hour_words):
            return (
                f"¡Hola! 👋 En *{branch_name}*, nuestro horario de atención es:\n\n"
                f"🕒 {hours}\n\n"
                f"Puedes consultar nuestro menú completo y realizar pedidos aquí:\n"
                f"👉 {store_url}\n\n"
                f"¿Hay algo más en lo que te pueda ayudar?"
            )

        # 2. Promotions / Discounts inquiry
        if any(w in text for w in ["promo", "promocion", "descuento", "cupon", "oferta", "2x1"]):
            return (
                f"¡Claro! 🎉 En *{branch_name}* tenemos estas promociones activas:\n\n"
                f"{promos}\n\n"
                f"Aprovecha y ordena directo desde nuestro menú digital:\n"
                f"👉 {store_url}\n\n"
                f"¡Estamos listos para preparar tu pedido!"
            )

        # 3. Menu / Food inquiry
        menu_words = [
            "menu", "carta", "comida", "platillo", "venden", "antojo", "comer", "recomiend"
        ]
        if any(w in text for w in menu_words):
            return (
                f"¡Bienvenido a *{branch_name}*! 🌮🍽️\n\n"
                f"Aquí tienes nuestros platillos disponibles preparados al momento:\n"
                f"{menu}\n\n"
                f"Puedes personalizar tus ingredientes y ordenar en línea aquí:\n"
                f"👉 {store_url}\n\n"
                f"¿Deseas saber más sobre algún platillo o realizar tu pedido?"
            )

        # 4. Location / Address inquiry
        loc_words = ["donde estan", "ubicacion", "direccion", "sucursal", "donde quedan"]
        if any(w in text for w in loc_words):
            phone = summary.get("phone") or "nuestro teléfono"
            return (
                f"📍 *{branch_name}*\n"
                f"Para mayor detalle de cómo llegar o zonas de reparto, visita:\n"
                f"👉 {store_url}\n\n"
                f"O si prefieres, puedes llamarnos directamente al: {phone}."
            )

        # 5. General greeting or Fallback
        return (
            f"¡Hola! 👋 Bienvenido a *{branch_name}*. ¿En qué podemos ayudarte hoy?\n\n"
            f"Puedes consultar nuestro menú de hoy, promociones y hacer pedidos aquí:\n"
            f"👉 {store_url}\n\n"
            f"O dime si deseas saber sobre nuestros *horarios*, *menú* o *promociones* del día."
        )

