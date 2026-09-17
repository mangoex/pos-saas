"""Service and catalog for official Meta WhatsApp Message Templates (HSM)."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# Official standard templates required for RestaurantOS
STANDARD_TEMPLATES: dict[str, dict[str, Any]] = {
    "restaurantos_order_update": {
        "name": "restaurantos_order_update",
        "category": "UTILITY",
        "allow_category_change": True,
        "language": "es_MX",
        "components": [
            {
                "type": "BODY",
                "text": (
                    "¡Hola {{1}}! Tu pedido #{{2}} en {{3}} ahora está: {{4}}. "
                    "Sigue el estado en vivo aquí: {{5}}"
                ),
                "example": {
                    "body_text": [
                        [
                            "Carlos",
                            "ORD-101",
                            "Tacos El Güero",
                            "En Preparación",
                            "https://elguero.mimenu.onl/orders/101",
                        ]
                    ]
                },
            }
        ],
    },
    "restaurantos_reengagement_offer": {
        "name": "restaurantos_reengagement_offer",
        "category": "MARKETING",
        "allow_category_change": True,
        "language": "es_MX",
        "components": [
            {
                "type": "BODY",
                "text": (
                    "¡Hola {{1}}! En {{2}} te extrañamos. {{3}} Usa el cupón {{4}} "
                    "en tu próxima compra: {{5}}. Para no recibir más promociones, "
                    "responde STOP o BAJA."
                ),
                "example": {
                    "body_text": [
                        [
                            "Carlos",
                            "Tacos El Güero",
                            "¡Hace tiempo que no ordenas tus Tacos al Pastor!",
                            "VUELVE10",
                            "https://elguero.mimenu.onl",
                        ]
                    ]
                },
            },
            {
                "type": "BUTTONS",
                "buttons": [
                    {
                        "type": "QUICK_REPLY",
                        "text": "STOP",
                    }
                ],
            },
        ],
    },
}


class WhatsAppTemplateService:
    """Manages creation, verification, and retrieval of Meta HSM Message Templates."""

    @staticmethod
    def list_waba_templates(
        waba_id: str,
        access_token: str | None = None,
        environment: str = "sandbox",
    ) -> list[dict[str, Any]]:
        """List registered message templates from Meta Graph API or simulate in sandbox."""
        if not waba_id:
            return []

        if environment == "sandbox" or not access_token or access_token.startswith("EAAB_mock"):
            return [
                {
                    "id": f"tpl_mock_{name}",
                    "name": tpl["name"],
                    "status": "APPROVED",
                    "category": tpl["category"],
                    "language": tpl["language"],
                    "components": tpl["components"],
                }
                for name, tpl in STANDARD_TEMPLATES.items()
            ]

        url = f"https://graph.facebook.com/v20.0/{waba_id}/message_templates?limit=100"
        req = Request(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "User-Agent": "RestaurantOS-WhatsApp-Adapter/1.0",
            },
        )
        try:
            with urlopen(req, timeout=10) as resp:
                data: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
                return data.get("data", [])
        except (HTTPError, URLError, TimeoutError) as e:
            logger.error("Failed to list Meta message templates for WABA %s: %s", waba_id, e)
            return []

    @classmethod
    def register_standard_templates(
        cls,
        waba_id: str,
        access_token: str | None = None,
        environment: str = "sandbox",
    ) -> dict[str, Any]:
        """Ensure all required standard templates exist in the WABA, registering missing ones."""
        if not waba_id:
            return {"status": "error", "message": "missing_waba_id"}

        existing_templates = cls.list_waba_templates(waba_id, access_token, environment)
        existing_names = {t.get("name") for t in existing_templates if isinstance(t, dict)}

        results: list[dict[str, Any]] = []

        for name, tpl in STANDARD_TEMPLATES.items():
            if name in existing_names:
                existing_item = next(
                    (t for t in existing_templates if t.get("name") == name), None
                )
                status = existing_item.get("status", "APPROVED") if existing_item else "APPROVED"
                results.append(
                    {
                        "name": name,
                        "action": "already_exists",
                        "status": status,
                        "category": tpl["category"],
                    }
                )
                continue

            if environment == "sandbox" or not access_token or access_token.startswith("EAAB_mock"):
                results.append(
                    {
                        "name": name,
                        "action": "created",
                        "status": "APPROVED",
                        "category": tpl["category"],
                    }
                )
                continue

            url = f"https://graph.facebook.com/v20.0/{waba_id}/message_templates"
            body_bytes = json.dumps(tpl).encode("utf-8")
            req = Request(
                url,
                data=body_bytes,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}",
                    "User-Agent": "RestaurantOS-WhatsApp-Adapter/1.0",
                },
            )
            try:
                with urlopen(req, timeout=10) as resp:
                    resp_data: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
                    results.append(
                        {
                            "name": name,
                            "action": "created",
                            "status": "PENDING",
                            "meta_id": resp_data.get("id"),
                            "category": tpl["category"],
                        }
                    )
            except HTTPError as e:
                err_body = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
                logger.error("Failed to create template %s on WABA %s: %s", name, waba_id, err_body)
                results.append({"name": name, "action": "failed", "error": err_body})
            except Exception as e:
                logger.error("Unexpected error creating template %s: %s", name, e)
                results.append({"name": name, "action": "failed", "error": str(e)})

        return {
            "status": "success",
            "waba_id": waba_id,
            "environment": environment,
            "templates": results,
        }

    @classmethod
    def get_template_status_summary(
        cls,
        waba_id: str,
        access_token: str | None = None,
        environment: str = "sandbox",
    ) -> dict[str, Any]:
        """Return a formatted status report of standard templates for admin UI display."""
        existing = cls.list_waba_templates(waba_id, access_token, environment)
        indexed = {t.get("name"): t for t in existing if isinstance(t, dict)}

        desc_utility = "Notificación transaccional de cambio de estado de pedido (Utilidad)"
        desc_marketing = "Campaña de reactivación y cupones con cláusula de Opt-Out (Marketing)"

        summary: list[dict[str, Any]] = []
        for name, definition in STANDARD_TEMPLATES.items():
            found = indexed.get(name)
            cat = definition["category"]
            description = desc_utility if cat == "UTILITY" else desc_marketing
            if found:
                summary.append(
                    {
                        "name": name,
                        "category": cat,
                        "language": definition["language"],
                        "status": found.get("status", "APPROVED"),
                        "registered": True,
                        "description": description,
                    }
                )
            else:
                summary.append(
                    {
                        "name": name,
                        "category": cat,
                        "language": definition["language"],
                        "status": "NOT_REGISTERED",
                        "registered": False,
                        "description": description,
                    }
                )

        return {
            "waba_id": waba_id,
            "total_standard": len(STANDARD_TEMPLATES),
            "templates": summary,
        }
