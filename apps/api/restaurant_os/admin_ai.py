"""Governed knowledge and one-action configuration proposals for Admin.

Provider output is untrusted and never receives a write tool.  Python validates a
single proposed action, persists it for review, and applies it through an existing
domain service only after a second authorization and freshness check.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Session

from restaurant_os import models
from restaurant_os.operations import (
    ORGANIZATION_ID,
    AuthorizationError,
    BusinessError,
    authorize_branch_scope,
    create_inventory_item,
    create_modifier_group,
    create_modifier_option,
    create_product,
    require_permission,
    update_product,
    update_product_recipe_versioned,
)

UTC = timezone.utc
ADMIN_AI_CONVERSATION_TURN_LIMIT = 5
INVENTORY_PRICE_CLARIFICATION_OPTIONS = (
    {"id": "missing_purchase_price", "label": "Precio de compra"},
    {"id": "missing_average_cost", "label": "Costo promedio"},
)


class AdminAiError(RuntimeError):
    def __init__(self, code: str, message: str, http_status: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status


@dataclass(frozen=True)
class AdminAiProviderOptions:
    api_key: str
    model: str
    base_url: str
    timeout_seconds: float
    app_title: str = "RestaurantOS Admin"


CANONICAL_RULES: tuple[dict[str, str], ...] = (
    {
        "source": "PRD-FR-001",
        "topics": "organizacion razones sociales sucursales estructura",
        "text": (
            "La organización puede contener varias razones sociales; cada sucursal "
            "mantiene su pertenencia y configuración dentro de esa estructura."
        ),
    },
    {
        "source": "PRD-FR-005",
        "topics": "usuarios permisos sucursal",
        "text": (
            "Identidad, rol, permiso y alcance se resuelven en backend; "
            "ocultar una opción no autoriza la acción."
        ),
    },
    {
        "source": "PRD-FR-007",
        "topics": "auditoria cambios",
        "text": (
            "Las acciones administrativas y operativas sensibles producen "
            "auditoría con actor y alcance."
        ),
    },
    {
        "source": "PRD-FR-010",
        "topics": "productos categorias modificadores extras combos",
        "text": (
            "El catálogo administra categorías, productos, variantes, "
            "modificadores, extras y combos."
        ),
    },
    {
        "source": "PRD-FR-015",
        "topics": "precios precio versiones historico pedidos",
        "text": (
            "Los precios se versionan y cada pedido conserva el precio que se le aplicó; "
            "una edición de catálogo no reescribe el histórico."
        ),
    },
    {
        "source": "PRD-FR-089",
        "topics": "insumos inventario costo promedio ponderado",
        "text": (
            "El costo promedio ponderado pertenece al inventario y no equivale al precio "
            "de venta de un producto ni al precio de compra de una presentación."
        ),
    },
    {
        "source": "PRD-FR-093",
        "topics": "insumos presentaciones compra proveedor precio",
        "text": (
            "Cada presentación de compra relaciona un insumo con un proveedor, unidad comercial, "
            "contenido y rendimiento en unidad base."
        ),
    },
    {
        "source": "PRD-FR-094",
        "topics": "insumos presentaciones precio compra historial proveedor",
        "text": (
            "El precio de una presentación conserva historial y equivalencia por unidad base; "
            "editarlo no modifica por sí solo el costo promedio contable."
        ),
    },
    {
        "source": "PRD-FR-109",
        "topics": "insumos inventario costo promedio sucursal almacen recepcion",
        "text": (
            "El costo promedio se actualiza al confirmar una recepción y tiene alcance por "
            "sucursal, almacén e insumo."
        ),
    },
    {
        "source": "PRD-FR-018",
        "topics": "admin corporativo supervisor sucursal",
        "text": (
            "El catálogo corporativo y las excepciones de sucursal tienen "
            "autoridades separadas y permisos granulares."
        ),
    },
    {
        "source": "SDD-ADR-015",
        "topics": "rbac permisos autoridad",
        "text": (
            "RBAC y el scope persistido son autoridad; is_superadmin del "
            "cliente no sustituye require_permission."
        ),
    },
    {
        "source": "PRD-FR-095",
        "topics": "modificadores grupos opciones minimo maximo obligatorio",
        "text": (
            "Los modificadores pertenecen a grupos por producto con obligatoriedad, mínimo "
            "y máximo; sus opciones deben respetar cardinalidad y efecto configurado."
        ),
    },
    {
        "source": "PRD-FR-027",
        "topics": "pedidos estados produccion pago",
        "text": (
            "Los pedidos usan transiciones explícitas; pago, producción y "
            "fulfillment conservan autoridades separadas."
        ),
    },
    {
        "source": "PRD-FR-043",
        "topics": "produccion kds tareas estaciones listo",
        "text": (
            "Un pedido sólo puede marcarse listo cuando concluyen todas sus tareas "
            "obligatorias de producción por estación."
        ),
    },
    {
        "source": "PRD-FR-054",
        "topics": "caja pagos efectivo tarjeta transferencia correccion",
        "text": (
            "Los pagos confirmados son inmutables; cualquier corrección conserva "
            "trazabilidad y no edita el cobro histórico."
        ),
    },
    {
        "source": "PRD-FR-060",
        "topics": "inventario movimientos recetas merma",
        "text": (
            "Inventario deriva de movimientos y las cantidades usan Decimal; "
            "no se editan existencias históricas."
        ),
    },
    {
        "source": "PRD-FR-082",
        "topics": "recetas subrecetas versiones activacion retiro",
        "text": (
            "Las recetas de venta y producción se versionan; activar una versión nueva "
            "retira la anterior sin destruirla."
        ),
    },
    {
        "source": "PRD-FR-108",
        "topics": "compras proveedores recepcion confirmacion cancelacion",
        "text": (
            "Una compra directa pasa por borrador, confirmación y cancelación controlada; "
            "confirmar es la frontera que afecta inventario y costo."
        ),
    },
    {
        "source": "PRD-FR-128",
        "topics": "reparto entrega repartidor despacho estados",
        "text": (
            "El reparto conserva estados explícitos desde despacho y permite operación manual "
            "cuando una recomendación externa no está disponible."
        ),
    },
    {
        "source": "PRD-FR-141",
        "topics": "integraciones webhooks idempotencia adaptadores canales externos",
        "text": (
            "Los webhooks externos son idempotentes y cada proveedor se aísla detrás de un "
            "adaptador; su payload original se conserva."
        ),
    },
    {
        "source": "PRD-FR-164",
        "topics": "exportaciones facturacion contpaqi doble exportacion",
        "text": (
            "Las exportaciones previenen duplicados y separan autoridad por razón social; "
            "una reexportación requiere autorización."
        ),
    },
    {
        "source": "PRD-FR-184",
        "topics": "offline desconexion sincronizacion outbox inbox replay",
        "text": (
            "La continuidad offline usa outbox, inbox e idempotencia; reconciliar no debe "
            "perder ni duplicar pedidos."
        ),
    },
    {
        "source": "SDD §5.4 Orders",
        "topics": "maquina pedido transiciones dominio",
        "text": "El módulo Orders gobierna comandos, eventos y transiciones del pedido.",
    },
    {
        "source": "SDD §5.7 Inventory",
        "topics": "ledger inventario reservas consumo",
        "text": "El módulo Inventory gobierna ledger, reservas, consumos y compensaciones.",
    },
    {
        "source": "SDD §43",
        "topics": "asistente ia propuestas revision",
        "text": (
            "El asistente sólo propone una acción; Python valida y un humano "
            "autorizado acepta o rechaza."
        ),
    },
)
KNOWN_SOURCES = frozenset(rule["source"] for rule in CANONICAL_RULES)

ACTION_FIELDS: dict[str, tuple[set[str], set[str]]] = {
    "product.create": (
        {"name", "sku", "category_name", "station", "price_cents", "image_url"},
        {"name", "sku", "category_name", "station", "price_cents"},
    ),
    "product.update": (
        {"name", "sku", "category_name", "station", "price_cents", "image_url", "status"},
        set(),
    ),
    "inventory_item.create": (
        {"name", "sku", "base_unit_id", "item_type"},
        {"name", "sku", "base_unit_id"},
    ),
    "modifier_group.create": (
        {
            "name",
            "is_required",
            "minimum_selections",
            "maximum_selections",
            "station",
            "display_order",
        },
        {"name", "is_required", "minimum_selections", "maximum_selections"},
    ),
    "modifier_option.create": (
        {
            "name",
            "effect_type",
            "price_delta_cents",
            "affected_item_id",
            "replacement_item_id",
            "remove_quantity",
            "add_quantity",
            "inventory_effect",
            "kitchen_text",
            "station",
            "display_order",
        },
        {"name", "effect_type"},
    ),
    "recipe.version": (
        {"yield_quantity", "yield_unit_id", "components"},
        {"yield_quantity", "yield_unit_id", "components"},
    ),
}
CREATE_ACTIONS = {"product.create", "inventory_item.create"}
MATERIAL_FIELDS: dict[str, set[str]] = {
    "product.create": {
        "name",
        "sku",
        "category_name",
        "station",
        "price_cents",
        "image_url",
    },
    "product.update": {
        "name",
        "sku",
        "category_name",
        "station",
        "price_cents",
        "image_url",
        "status",
    },
    "inventory_item.create": {"name", "sku", "item_type"},
    "modifier_group.create": {
        "name",
        "is_required",
        "minimum_selections",
        "maximum_selections",
        "station",
        "display_order",
    },
    "modifier_option.create": {
        "name",
        "effect_type",
        "price_delta_cents",
        "remove_quantity",
        "add_quantity",
        "inventory_effect",
        "kitchen_text",
        "station",
        "display_order",
    },
    "recipe.version": {"yield_quantity"},
}

NUMERIC_EVIDENCE_FIELDS = {
    "price_cents",
    "minimum_selections",
    "maximum_selections",
    "price_delta_cents",
    "remove_quantity",
    "add_quantity",
    "display_order",
    "yield_quantity",
}
BOOLEAN_EVIDENCE_FIELDS = {"is_required", "inventory_effect"}
VALUE_ALIASES: dict[str, tuple[str, ...]] = {
    "kitchen": ("kitchen", "cocina"),
    "drinks": ("drinks", "bebidas", "barra"),
    "packing": ("packing", "empaque"),
    "ingredient": ("ingredient", "ingrediente", "insumo"),
    "instruction": ("instruction", "instrucción", "instruccion"),
    "remove": ("remove", "quitar", "remover"),
    "add": ("add", "agregar", "añadir", "anadir"),
    "substitute": ("substitute", "sustituir", "sustitución", "sustitucion"),
    "quantity": ("quantity", "cantidad"),
    "variant": ("variant", "variante", "variación", "variacion"),
    "active": ("active", "activo", "activa"),
    "inactive": ("inactive", "inactivo", "inactiva"),
    "needs_review": ("needs_review", "requiere revisión", "requiere revision"),
}
TECHNICAL_ID_PATTERN = re.compile(
    r"(?<![0-9a-f])"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"(?![0-9a-f])",
    re.IGNORECASE,
)
DIAGNOSTIC_ITEM_LIMIT = 100
DIAGNOSTIC_VISIBLE_ITEM_LIMIT = 10


def _now() -> datetime:
    return datetime.now(UTC)


def _json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _redact_prompt(prompt: str) -> str:
    redacted = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[CORREO]", prompt)
    return re.sub(r"(?:\+?52[\s-]?)?\b\d[\d\s-]{8,}\d\b", "[TELEFONO]", redacted)


def _fold_text(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )


def _fold_words(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _fold_text(value)))


def _is_price_diagnostic(prompt: str, words: set[str]) -> bool:
    diagnostic_terms = {
        "dime",
        "identifica",
        "identificar",
        "indica",
        "indicar",
        "lista",
        "listar",
        "muestra",
        "mostrar",
        "reporta",
        "reportar",
    }
    folded = _fold_text(prompt)
    interrogative_request = re.match(
        r"^(?:que|cual|cuales|cuanto|cuantos)\b",
        folded.lstrip(" ¿¡"),
    )
    if interrogative_request or words.intersection(diagnostic_terms):
        return True

    explicit_configuration = re.search(
        r"\b(?:agrega|agregar|anade|anadir|actualiza|actualizar|cambia|cambiar|"
        r"configura|configurar|crea|crear|edita|editar|quita|quitar|versiona|versionar)\b"
        r".{0,32}\b(?:insumos?|ingredientes?|productos?|grupos?|opciones?|recetas?)\b",
        folded,
    )
    if explicit_configuration:
        return False

    missing_price = re.search(
        r"\b(?:no\s+tienen|sin|falta|faltan|faltante|faltantes)\b.{0,40}"
        r"\b(?:precio|precios|costo|costos|coste|costes|valor)\b",
        folded,
    )
    return bool(missing_price)


def _safe_diagnostic_text(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or TECHNICAL_ID_PATTERN.search(text):
        return None
    return text


def _diagnostic_item(row: Any) -> dict[str, Any]:
    name = _safe_diagnostic_text(row["name"])
    sku = _safe_diagnostic_text(row["sku"])
    unit = _safe_diagnostic_text(row["base_unit_code"])
    if name and sku:
        label = f"{name} ({sku})"
    elif name:
        label = name
    elif sku:
        label = f"SKU {sku}"
    else:
        label = "Insumo sin etiqueta legible"
    return {
        "id": str(row["id"]),
        "name": name,
        "sku": sku,
        "base_unit_code": unit,
        "label": label,
    }


def _diagnostic_payload(
    *,
    kind: str,
    description: str,
    sources: list[str],
    scope: dict[str, Any],
    total: int,
    rows: list[Any],
) -> dict[str, Any]:
    items = [_diagnostic_item(row) for row in rows]
    visible = items[:DIAGNOSTIC_VISIBLE_ITEM_LIMIT]
    answer = f"Se encontraron {total} {description}."
    if visible:
        answer += " " + "; ".join(item["label"] for item in visible) + "."
        if total > len(visible):
            answer += f" Hay {total - len(visible)} registros adicionales."
        if total > len(items):
            answer += f" El detalle está limitado a {len(items)} registros."
    warnings = []
    unlabeled = sum(item["name"] is None and item["sku"] is None for item in items)
    if unlabeled:
        warnings.append(
            f"{unlabeled} registros no tienen nombre ni SKU legibles y requieren saneamiento."
        )
    return {
        "answer": answer,
        "sources": sources,
        "questions": [],
        "warnings": warnings,
        "change_set": [],
        "diagnostic": {
            "kind": kind,
            "scope": scope,
            "total": total,
            "items": items,
            "truncated": total > len(items),
        },
    }


def _inventory_price_clarification_payload(
    *,
    turn: int = 1,
    answer: str | None = None,
) -> dict[str, Any]:
    return {
        "answer": answer
        or (
            "“Precio” no identifica una única autoridad para insumos en RestaurantOS. "
            "Elige si buscas el precio de compra por presentación o el costo promedio "
            "contable por sucursal y almacén."
        ),
        "sources": [
            "PRD-FR-015",
            "PRD-FR-093",
            "PRD-FR-094",
            "PRD-FR-089",
            "PRD-FR-109",
        ],
        "questions": [
            "¿Quieres consultar insumos sin precio de compra o insumos sin costo promedio?"
        ],
        "warnings": [
            "La consulta necesita una aclaración; no se invocó al proveedor "
            "ni se creó una propuesta."
        ],
        "change_set": [],
        "clarification": {
            "kind": "inventory_price_authority",
            "turn": turn,
            "options": [dict(option) for option in INVENTORY_PRICE_CLARIFICATION_OPTIONS],
        },
    }


def _load_conversation_parent(
    session: Session,
    actor_id: str,
    parent_proposal_id: str,
    branch_id: str | None,
) -> dict[str, Any]:
    row = (
        session.execute(
            sa.select(models.admin_ai_proposals)
            .where(
                models.admin_ai_proposals.c.id == parent_proposal_id,
                models.admin_ai_proposals.c.organization_id == ORGANIZATION_ID,
                models.admin_ai_proposals.c.actor_user_id == actor_id,
            )
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if not row:
        raise AdminAiError(
            "admin_ai_conversation_invalid",
            "La conversación anterior no está disponible para este usuario.",
        )
    parent = dict(row)
    if parent.get("branch_id") != branch_id:
        raise AdminAiError(
            "admin_ai_conversation_scope_mismatch",
            "La conversación anterior pertenece a otra sucursal.",
        )
    expires_at = parent.get("expires_at")
    if isinstance(expires_at, datetime):
        aware_expiry = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
    else:
        aware_expiry = _now()
    payload = parent.get("payload")
    if (
        parent.get("status") != "DRAFT"
        or aware_expiry <= _now()
        or not isinstance(payload, dict)
        or payload.get("change_set")
        or not payload.get("questions")
        or not isinstance(payload.get("clarification"), dict)
    ):
        raise AdminAiError(
            "admin_ai_conversation_invalid",
            "La conversación anterior ya no admite aclaraciones.",
        )
    turn = payload["clarification"].get("turn")
    if not isinstance(turn, int) or turn < 1 or turn >= ADMIN_AI_CONVERSATION_TURN_LIMIT:
        raise AdminAiError(
            "admin_ai_conversation_invalid",
            "La conversación alcanzó su límite de aclaraciones; inicia una consulta nueva.",
        )
    return parent


def _find_conversation_replay(
    session: Session,
    actor_id: str,
    parent_proposal_id: str,
    branch_id: str | None,
    idempotency_key: str,
) -> dict[str, Any] | None:
    statement = sa.select(models.admin_ai_proposals).where(
        models.admin_ai_proposals.c.organization_id == ORGANIZATION_ID,
        models.admin_ai_proposals.c.actor_user_id == actor_id,
        models.admin_ai_proposals.c.payload["conversation"]["parent_proposal_id"].as_string()
        == parent_proposal_id,
        models.admin_ai_proposals.c.payload["conversation"]["idempotency_key"].as_string()
        == idempotency_key,
    )
    statement = statement.where(
        models.admin_ai_proposals.c.branch_id.is_(None)
        if branch_id is None
        else models.admin_ai_proposals.c.branch_id == branch_id
    )
    row = session.execute(statement.limit(1)).mappings().first()
    return dict(row) if row else None


def _resolve_inventory_price_clarification(
    session: Session,
    actor_id: str,
    branch_id: str | None,
    prompt: str,
    clarification: dict[str, Any],
    clarification_choice: str | None,
) -> dict[str, Any]:
    allowed = {
        str(option.get("id"))
        for option in clarification.get("options", [])
        if isinstance(option, dict) and option.get("id")
    }
    selected = clarification_choice
    if selected is not None and selected not in allowed:
        raise AdminAiError(
            "admin_ai_conversation_invalid",
            "La opción de aclaración no pertenece a esta conversación.",
        )
    if selected is None:
        words = _fold_words(prompt)
        purchase = bool(
            words.intersection(
                {
                    "compra",
                    "compras",
                    "proveedor",
                    "proveedores",
                    "presentacion",
                    "presentaciones",
                    "cotizacion",
                    "cotizaciones",
                }
            )
        )
        average = "promedio" in words or "contable" in words
        if purchase != average:
            selected = "missing_purchase_price" if purchase else "missing_average_cost"

    if selected == "missing_purchase_price":
        return _missing_purchase_price_payload(session, actor_id, branch_id)
    if selected == "missing_average_cost":
        return _missing_average_cost_payload(session, actor_id, branch_id)
    return _inventory_price_clarification_payload(
        turn=int(clarification["turn"]) + 1,
        answer=(
            "Todavía necesito elegir una sola opción para continuar. Puedes responder "
            "“de compra” o “costo promedio”, o usar uno de los botones."
        ),
    )


def _normalize_conversation_context(values: list[str] | None) -> list[str]:
    if not values or len(values) > ADMIN_AI_CONVERSATION_TURN_LIMIT - 1:
        raise AdminAiError(
            "admin_ai_conversation_context_required",
            "La conversación necesita su contexto efímero para continuar.",
        )
    normalized = [value.strip() for value in values]
    if any(not value or len(value) > 1600 for value in normalized):
        raise AdminAiError(
            "admin_ai_conversation_invalid",
            "El contexto efímero de la conversación es inválido.",
        )
    return normalized


def _limited_missing_items(session: Session, statement: Any) -> tuple[int, list[Any]]:
    total_column = "_admin_ai_diagnostic_total"
    limited_statement = statement.add_columns(sa.func.count().over().label(total_column)).limit(
        DIAGNOSTIC_ITEM_LIMIT
    )
    rows = session.execute(limited_statement).mappings().all()
    total = int(rows[0][total_column]) if rows else 0
    return total, list(rows)


def _missing_purchase_price_payload(
    session: Session,
    actor_id: str,
    branch_id: str | None,
) -> dict[str, Any]:
    if not branch_id:
        return {
            "answer": (
                "El precio de compra depende de proveedores habilitados para una sucursal; "
                "selecciona una sucursal antes de ejecutar el diagnóstico."
            ),
            "sources": ["PRD-FR-093", "PRD-FR-094"],
            "questions": ["¿En qué sucursal quieres consultar el precio de compra?"],
            "warnings": [],
            "change_set": [],
            "diagnostic": None,
        }
    require_permission(session, actor_id, "purchases.read", branch_id)
    presentation = models.purchase_presentations.alias("admin_ai_purchase_presentation")
    supplier = models.suppliers.alias("admin_ai_purchase_supplier")
    presentation_from = presentation.join(
        supplier,
        presentation.c.supplier_id == supplier.c.id,
    )
    valid_filters: list[Any] = [
        presentation.c.item_id == models.inventory_items.c.id,
        presentation.c.organization_id == ORGANIZATION_ID,
        presentation.c.status == "active",
        presentation.c.last_net_price > Decimal("0"),
        supplier.c.organization_id == ORGANIZATION_ID,
        supplier.c.status == "active",
    ]
    if branch_id:
        terms = models.supplier_branch_terms.alias("admin_ai_supplier_branch_terms")
        presentation_from = presentation_from.outerjoin(
            terms,
            sa.and_(
                terms.c.supplier_id == supplier.c.id,
                terms.c.branch_id == branch_id,
            ),
        )
        valid_filters.append(sa.or_(terms.c.supplier_id.is_(None), terms.c.is_enabled.is_(True)))
    has_usable_price = sa.exists(
        sa.select(presentation.c.id).select_from(presentation_from).where(*valid_filters)
    )
    statement = (
        sa.select(
            models.inventory_items.c.id,
            models.inventory_items.c.name,
            models.inventory_items.c.sku,
            models.inventory_units.c.code.label("base_unit_code"),
        )
        .select_from(
            models.inventory_items.join(
                models.inventory_units,
                models.inventory_items.c.base_unit_id == models.inventory_units.c.id,
            )
        )
        .where(
            models.inventory_items.c.organization_id == ORGANIZATION_ID,
            models.inventory_units.c.organization_id == ORGANIZATION_ID,
            models.inventory_items.c.status == "active",
            sa.or_(
                models.inventory_items.c.catalog_scope == "organization",
                models.inventory_items.c.source_branch_id == branch_id,
            ),
            ~has_usable_price,
        )
        .order_by(
            sa.func.lower(models.inventory_items.c.name),
            models.inventory_items.c.sku,
            models.inventory_items.c.id,
        )
    )
    total, rows = _limited_missing_items(session, statement)
    return _diagnostic_payload(
        kind="missing_purchase_price",
        description="insumos sin precio de compra utilizable",
        sources=["PRD-FR-093", "PRD-FR-094"],
        scope={"organization_id": ORGANIZATION_ID, "branch_id": branch_id},
        total=total,
        rows=rows,
    )


def _missing_average_cost_payload(
    session: Session,
    actor_id: str,
    branch_id: str | None,
) -> dict[str, Any]:
    if not branch_id:
        return {
            "answer": (
                "El costo promedio tiene alcance por sucursal y almacén; selecciona una sucursal "
                "antes de ejecutar el diagnóstico."
            ),
            "sources": ["PRD-FR-089", "PRD-FR-109"],
            "questions": ["¿En qué sucursal quieres consultar el costo promedio?"],
            "warnings": [],
            "change_set": [],
            "diagnostic": None,
        }
    require_permission(session, actor_id, "inventory.read", branch_id)
    warehouse = (
        session.execute(
            sa.select(
                models.warehouses.c.id,
                models.warehouses.c.name,
            ).where(
                models.warehouses.c.organization_id == ORGANIZATION_ID,
                models.warehouses.c.branch_id == branch_id,
                models.warehouses.c.status == "active",
            )
        )
        .mappings()
        .first()
    )
    if not warehouse:
        return {
            "answer": "La sucursal seleccionada no tiene un almacén activo para calcular costos.",
            "sources": ["PRD-FR-089", "PRD-FR-109"],
            "questions": [],
            "warnings": ["Diagnóstico bloqueado hasta configurar un almacén activo."],
            "change_set": [],
            "diagnostic": None,
        }
    has_confirmed_cost = sa.exists(
        sa.select(models.inventory_cost_states.c.item_id).where(
            models.inventory_cost_states.c.branch_id == branch_id,
            models.inventory_cost_states.c.warehouse_id == warehouse["id"],
            models.inventory_cost_states.c.item_id == models.inventory_items.c.id,
            models.inventory_cost_states.c.last_cost_at.is_not(None),
        )
    )
    statement = (
        sa.select(
            models.inventory_items.c.id,
            models.inventory_items.c.name,
            models.inventory_items.c.sku,
            models.inventory_units.c.code.label("base_unit_code"),
        )
        .select_from(
            models.inventory_items.join(
                models.inventory_units,
                models.inventory_items.c.base_unit_id == models.inventory_units.c.id,
            )
        )
        .where(
            models.inventory_items.c.organization_id == ORGANIZATION_ID,
            models.inventory_units.c.organization_id == ORGANIZATION_ID,
            models.inventory_items.c.status == "active",
            sa.or_(
                models.inventory_items.c.catalog_scope == "organization",
                models.inventory_items.c.source_branch_id == branch_id,
            ),
            ~has_confirmed_cost,
        )
        .order_by(
            sa.func.lower(models.inventory_items.c.name),
            models.inventory_items.c.sku,
            models.inventory_items.c.id,
        )
    )
    total, rows = _limited_missing_items(session, statement)
    return _diagnostic_payload(
        kind="missing_average_cost",
        description="insumos sin costo promedio confirmado",
        sources=["PRD-FR-089", "PRD-FR-109"],
        scope={
            "organization_id": ORGANIZATION_ID,
            "branch_id": branch_id,
            "warehouse_id": str(warehouse["id"]),
            "warehouse_name": _safe_diagnostic_text(warehouse["name"]),
        },
        total=total,
        rows=rows,
    )


def _price_diagnostic_preflight(
    session: Session,
    actor_id: str,
    prompt: str,
    branch_id: str | None,
) -> dict[str, Any] | None:
    words = _fold_words(prompt)
    inventory_terms = {"insumo", "insumos", "ingrediente", "ingredientes"}
    price_terms = {
        "precio",
        "precios",
        "costo",
        "costos",
        "coste",
        "costes",
        "costar",
        "cuesta",
        "cuestan",
        "cotizacion",
        "cotizaciones",
        "presentacion",
        "presentaciones",
        "valor",
    }
    if (
        not words.intersection(inventory_terms)
        or not words.intersection(price_terms)
        or not _is_price_diagnostic(prompt, words)
    ):
        return None

    purchase_intent = bool(
        words.intersection(
            {
                "compra",
                "compras",
                "proveedor",
                "proveedores",
                "presentacion",
                "presentaciones",
                "cotizacion",
                "cotizaciones",
                "neto",
            }
        )
    )
    average_cost_intent = "promedio" in words or "contable" in words
    sale_intent = "venta" in words or "ventas" in words
    selected_intents = sum((purchase_intent, average_cost_intent, sale_intent))

    if selected_intents != 1:
        return _inventory_price_clarification_payload()

    if sale_intent:
        return _inventory_price_clarification_payload(
            answer=(
                "El precio de venta pertenece a productos, no a insumos. Para continuar con "
                "insumos elige precio de compra o costo promedio."
            )
        )

    if purchase_intent:
        return _missing_purchase_price_payload(session, actor_id, branch_id)

    return _missing_average_cost_payload(session, actor_id, branch_id)


def curated_answer(prompt: str) -> dict[str, Any]:
    words = set(re.findall(r"[a-záéíóúñ0-9]+", prompt.lower()))
    ranked = sorted(
        CANONICAL_RULES,
        key=lambda rule: len(words & set(rule["topics"].split())),
        reverse=True,
    )
    selected = [rule for rule in ranked if len(words & set(rule["topics"].split()))][:3]
    if not selected:
        selected = [CANONICAL_RULES[-1], CANONICAL_RULES[4]]
    return {
        "answer": " ".join(rule["text"] for rule in selected),
        "sources": [rule["source"] for rule in selected],
        "questions": [],
        "warnings": [
            "El proveedor de IA está deshabilitado; esta orientación local "
            "no creó una propuesta aplicable."
        ],
        "change_set": [],
    }


def build_context(session: Session, branch_id: str | None) -> dict[str, Any]:
    if branch_id:
        valid_branch = session.execute(
            sa.select(models.branches.c.id).where(
                models.branches.c.id == branch_id,
                models.branches.c.organization_id == ORGANIZATION_ID,
                models.branches.c.status == "active",
            )
        ).scalar_one_or_none()
        if not valid_branch:
            raise AdminAiError(
                "admin_ai_reference_invalid", "La sucursal no pertenece al contexto autorizado."
            )
    current_prices = models.price_versions.alias("admin_ai_current_prices")
    products = (
        session.execute(
            sa.select(
                models.products.c.id,
                models.products.c.name,
                models.products.c.sku,
                models.products.c.station,
                models.products.c.status,
                models.products.c.updated_at,
                current_prices.c.price_cents,
            )
            .select_from(
                models.products.outerjoin(
                    current_prices,
                    sa.and_(
                        current_prices.c.product_id == models.products.c.id,
                        current_prices.c.valid_to.is_(None),
                    ),
                )
            )
            .where(models.products.c.organization_id == ORGANIZATION_ID)
            .order_by(models.products.c.id)
        )
        .mappings()
        .all()
    )
    items = (
        session.execute(
            sa.select(
                models.inventory_items.c.id,
                models.inventory_items.c.name,
                models.inventory_items.c.sku,
                models.inventory_items.c.base_unit_id,
                models.inventory_items.c.status,
                models.inventory_items.c.updated_at,
            )
            .where(models.inventory_items.c.organization_id == ORGANIZATION_ID)
            .order_by(models.inventory_items.c.id)
        )
        .mappings()
        .all()
    )
    units = (
        session.execute(
            sa.select(
                models.inventory_units.c.id,
                models.inventory_units.c.code,
                models.inventory_units.c.name,
            )
            .where(models.inventory_units.c.organization_id == ORGANIZATION_ID)
            .order_by(models.inventory_units.c.id)
        )
        .mappings()
        .all()
    )
    groups = (
        session.execute(
            sa.select(
                models.modifier_groups.c.id,
                models.modifier_groups.c.product_id,
                models.modifier_groups.c.name,
                models.modifier_groups.c.minimum_selections,
                models.modifier_groups.c.maximum_selections,
                models.modifier_groups.c.status,
                models.modifier_groups.c.updated_at,
            )
            .where(models.modifier_groups.c.organization_id == ORGANIZATION_ID)
            .order_by(models.modifier_groups.c.id)
        )
        .mappings()
        .all()
    )
    recipes = (
        session.execute(
            sa.select(
                models.recipes.c.id,
                models.recipes.c.product_id,
                models.recipes.c.branch_id,
                models.recipes.c.version,
                models.recipes.c.updated_at,
            )
            .where(
                models.recipes.c.organization_id == ORGANIZATION_ID,
                models.recipes.c.status == "active",
            )
            .order_by(models.recipes.c.id)
        )
        .mappings()
        .all()
    )
    return _json(
        {
            "branch_id": branch_id,
            "rules": list(CANONICAL_RULES),
            "products": [dict(row) for row in products],
            "inventory_items": [dict(row) for row in items],
            "units": [dict(row) for row in units],
            "modifier_groups": [dict(row) for row in groups],
            "active_recipes": [dict(row) for row in recipes],
        }
    )


def context_fingerprint(context: dict[str, Any]) -> str:
    canonical = json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "string", "maxLength": 3000},
            "sources": {
                "type": "array",
                "maxItems": 8,
                "items": {"type": "string", "enum": sorted(KNOWN_SOURCES)},
            },
            "questions": {
                "type": "array",
                "maxItems": 8,
                "items": {"type": "string", "maxLength": 300},
            },
            "warnings": {
                "type": "array",
                "maxItems": 8,
                "items": {"type": "string", "maxLength": 300},
            },
            "change_set": {
                "type": "array",
                "maxItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "kind": {"type": "string", "enum": sorted(ACTION_FIELDS)},
                        "target_id": {"type": ["string", "null"]},
                        "payload_json": {"type": "string", "maxLength": 12000},
                        "evidence": {
                            "type": "array",
                            "maxItems": 40,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "field": {"type": "string"},
                                    "quote": {"type": "string"},
                                },
                                "required": ["field", "quote"],
                            },
                        },
                    },
                    "required": ["kind", "target_id", "payload_json", "evidence"],
                },
            },
        },
        "required": ["answer", "sources", "questions", "warnings", "change_set"],
    }


def request_openrouter_proposal(
    prompt: str,
    context: dict[str, Any],
    options: AdminAiProviderOptions,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    body = {
        "model": options.model,
        "temperature": 0,
        "max_tokens": 1800,
        "provider": {"require_parameters": True},
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "admin_configuration_proposal",
                "strict": True,
                "schema": _response_schema(),
            },
        },
        "messages": [
            {
                "role": "system",
                "content": (
                    "Eres un asistente administrativo de RestaurantOS. Responde "
                    "usando sólo las reglas y IDs del contexto. No inventes nombres, "
                    "SKU, precios, cantidades ni cardinalidades: cada valor material "
                    "debe citar una frase exacta de request en evidence. Si falta algo, "
                    "pregunta y deja change_set vacío. Propón máximo una acción. "
                    "payload_json debe ser un objeto JSON serializado. Nunca propongas "
                    "órdenes, pagos, caja, compras, "
                    "existencias, producción operativa, usuarios, roles, borrados o archivos."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"request": _redact_prompt(prompt), "context": context}, ensure_ascii=False
                ),
            },
        ],
    }
    request = Request(
        f"{options.base_url.rstrip('/')}/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {options.api_key}",
            "Content-Type": "application/json",
            "X-OpenRouter-Title": options.app_title,
        },
        method="POST",
    )
    try:
        with opener(request, timeout=options.timeout_seconds) as response:
            envelope = json.loads(response.read().decode("utf-8"))
        content = envelope["choices"][0]["message"]["content"]
        parsed = json.loads(content) if isinstance(content, str) else content
    except (HTTPError, URLError, TimeoutError) as exc:
        raise AdminAiError(
            "admin_ai_provider_unavailable", "El proveedor de IA no respondió a tiempo.", 503
        ) from exc
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AdminAiError(
            "admin_ai_provider_invalid_response",
            "El proveedor devolvió una respuesta inválida.",
            502,
        ) from exc
    if not isinstance(parsed, dict):
        raise AdminAiError(
            "admin_ai_provider_invalid_response",
            "El proveedor devolvió una respuesta inválida.",
            502,
        )
    return parsed


def _evidence_map(prompt: str, evidence: Any) -> dict[str, list[str]]:
    if not isinstance(evidence, list):
        raise AdminAiError(
            "admin_ai_evidence_missing", "La propuesta no contiene evidencia humana válida."
        )
    prompt_folded = prompt.casefold()
    fields: dict[str, list[str]] = {}
    for item in evidence:
        if not isinstance(item, dict) or set(item) != {"field", "quote"}:
            raise AdminAiError(
                "admin_ai_evidence_missing", "La evidencia de la propuesta es inválida."
            )
        field = str(item["field"]).strip()
        quote = str(item["quote"]).strip()
        if not field or not quote or quote.casefold() not in prompt_folded:
            raise AdminAiError(
                "admin_ai_evidence_missing",
                f"El campo {field or 'desconocido'} no procede de la solicitud humana.",
            )
        fields.setdefault(field, []).append(quote)
    return fields


def _numeric_value_is_quoted(value: Any, quote: str) -> bool:
    try:
        expected = Decimal(str(value))
    except Exception:
        return False
    for token in re.findall(r"(?<![\w])[-+]?\d+(?:[.,]\d+)?(?![\w])", quote):
        try:
            if Decimal(token.replace(",", ".")) == expected:
                return True
        except Exception:
            continue
    return False


def _quote_contains_term(quote: str, term: str) -> bool:
    normalized_quote = quote.casefold()
    normalized_term = term.strip().casefold()
    if not normalized_term:
        return False
    if len(normalized_term) <= 2:
        return (
            re.search(rf"(?<!\w){re.escape(normalized_term)}(?!\w)", normalized_quote) is not None
        )
    return normalized_term in normalized_quote


def _value_is_quoted(field: str, value: Any, quote: str) -> bool:
    if field in NUMERIC_EVIDENCE_FIELDS or field.endswith((".net_quantity", ".waste_rate")):
        return _numeric_value_is_quoted(value, quote)
    if field in BOOLEAN_EVIDENCE_FIELDS:
        truthy = ("true", "verdadero", "sí", "si", "requerido", "obligatorio")
        falsy = ("false", "falso", "no", "opcional", "sin efecto")
        return any(_quote_contains_term(quote, term) for term in (truthy if value else falsy))
    normalized = str(value).strip().casefold()
    aliases = VALUE_ALIASES.get(normalized, (normalized,))
    return any(_quote_contains_term(quote, alias) for alias in aliases)


def _require_value_evidence(field: str, value: Any, evidence: dict[str, list[str]]) -> None:
    quotes = evidence.get(field, [])
    if not quotes or not any(_value_is_quoted(field, value, quote) for quote in quotes):
        raise AdminAiError(
            "admin_ai_evidence_missing",
            f"La evidencia humana no respalda el valor propuesto para {field}.",
        )


def _strict_int(field: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AdminAiError("admin_ai_change_set_invalid", f"{field} debe ser un entero JSON.")
    return value


def _strict_bool(field: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise AdminAiError("admin_ai_change_set_invalid", f"{field} debe ser un booleano JSON.")
    return value


def _require_reference_evidence(
    field: str, labels: list[Any], evidence: dict[str, list[str]]
) -> None:
    quotes = evidence.get(field, [])
    normalized_labels = [str(label) for label in labels if label]
    if not quotes or not any(
        _quote_contains_term(quote, label) for quote in quotes for label in normalized_labels
    ):
        raise AdminAiError(
            "admin_ai_evidence_missing",
            f"La solicitud no identifica de forma verificable la referencia {field}.",
        )


def _unit_labels(session: Session, unit_id: str) -> list[Any]:
    row = (
        session.execute(
            sa.select(models.inventory_units.c.code, models.inventory_units.c.name).where(
                models.inventory_units.c.id == unit_id,
                models.inventory_units.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .one()
    )
    return [row["code"], row["name"]]


def _item_labels(session: Session, item_id: str) -> list[Any]:
    row = (
        session.execute(
            sa.select(models.inventory_items.c.sku, models.inventory_items.c.name).where(
                models.inventory_items.c.id == item_id,
                models.inventory_items.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .one()
    )
    return [row["sku"], row["name"]]


def _require_reference(
    session: Session, table: sa.Table, value: Any, organization_column: Any | None = None
) -> str:
    reference = str(value or "").strip()
    if not reference:
        raise AdminAiError(
            "admin_ai_reference_invalid", "La propuesta contiene una referencia vacía."
        )
    query = sa.select(table.c.id).where(table.c.id == reference)
    if organization_column is not None:
        query = query.where(organization_column == ORGANIZATION_ID)
    if session.execute(query).scalar_one_or_none() is None:
        raise AdminAiError(
            "admin_ai_reference_invalid", "La propuesta contiene un ID inexistente o ajeno."
        )
    return reference


def _product_snapshot(session: Session, product_id: str) -> dict[str, Any]:
    price = models.price_versions.alias("admin_ai_snapshot_price")
    row = (
        session.execute(
            sa.select(
                models.products.c.id,
                models.products.c.name,
                models.products.c.sku,
                models.product_categories.c.name.label("category_name"),
                models.products.c.station,
                models.products.c.status,
                models.products.c.image_url,
                models.products.c.updated_at,
                price.c.price_cents,
            )
            .select_from(
                models.products.join(models.product_categories).outerjoin(
                    price,
                    sa.and_(price.c.product_id == models.products.c.id, price.c.valid_to.is_(None)),
                )
            )
            .where(
                models.products.c.id == product_id,
                models.products.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise AdminAiError(
            "admin_ai_reference_invalid", "El producto no existe en la organización."
        )
    return _json(dict(row))


def _normalize_change(
    session: Session,
    prompt: str,
    raw: dict[str, Any],
    branch_id: str | None,
) -> dict[str, Any]:
    if set(raw) != {"kind", "target_id", "payload_json", "evidence"}:
        raise AdminAiError(
            "admin_ai_change_set_invalid", "La acción propuesta contiene campos no soportados."
        )
    kind = str(raw.get("kind", ""))
    if kind not in ACTION_FIELDS:
        raise AdminAiError("admin_ai_change_set_invalid", "La acción propuesta no está permitida.")
    try:
        payload = json.loads(str(raw.get("payload_json", "")))
    except json.JSONDecodeError as exc:
        raise AdminAiError(
            "admin_ai_change_set_invalid", "El payload de la propuesta no es JSON válido."
        ) from exc
    if not isinstance(payload, dict):
        raise AdminAiError(
            "admin_ai_change_set_invalid", "El payload de la propuesta debe ser un objeto."
        )
    allowed, required = ACTION_FIELDS[kind]
    if set(payload) - allowed or not required.issubset(payload):
        raise AdminAiError(
            "admin_ai_change_set_invalid", "La propuesta tiene campos faltantes o no permitidos."
        )
    if kind == "product.update" and not payload:
        raise AdminAiError(
            "admin_ai_change_set_invalid", "La actualización de producto está vacía."
        )
    evidence = _evidence_map(prompt, raw.get("evidence"))
    for field in MATERIAL_FIELDS[kind].intersection(payload):
        _require_value_evidence(field, payload[field], evidence)

    target_id = str(raw.get("target_id") or "").strip() or None
    current: dict[str, Any] | None = None
    review_path = "/products"
    if kind in CREATE_ACTIONS:
        if target_id:
            raise AdminAiError("admin_ai_change_set_invalid", "Una creación no acepta target_id.")
    elif not target_id:
        raise AdminAiError(
            "admin_ai_reference_invalid", "La acción requiere un target_id existente."
        )

    if kind == "product.create":
        payload["price_cents"] = _strict_int("price_cents", payload["price_cents"])
        if payload["price_cents"] <= 0:
            raise AdminAiError("admin_ai_change_set_invalid", "price_cents debe ser positivo.")
        review_path = f"/products?search={payload['sku']}"
    elif kind == "product.update":
        current = _product_snapshot(session, target_id or "")
        _require_reference_evidence("target_id", [current["sku"], current["name"]], evidence)
        if "price_cents" in payload:
            payload["price_cents"] = _strict_int("price_cents", payload["price_cents"])
            if payload["price_cents"] <= 0:
                raise AdminAiError("admin_ai_change_set_invalid", "price_cents debe ser positivo.")
        review_path = f"/products?search={current['sku']}"
    elif kind == "inventory_item.create":
        payload["base_unit_id"] = _require_reference(
            session,
            models.inventory_units,
            payload["base_unit_id"],
            models.inventory_units.c.organization_id,
        )
        _require_reference_evidence(
            "base_unit_id", _unit_labels(session, payload["base_unit_id"]), evidence
        )
        payload.setdefault("item_type", "ingredient")
        if payload["item_type"] != "ingredient":
            raise AdminAiError(
                "admin_ai_change_set_invalid",
                "El MVP sólo permite crear insumos de tipo ingredient.",
            )
        review_path = "/inventory/items"
    elif kind == "modifier_group.create":
        _require_reference(session, models.products, target_id, models.products.c.organization_id)
        payload["minimum_selections"] = _strict_int(
            "minimum_selections", payload["minimum_selections"]
        )
        payload["maximum_selections"] = _strict_int(
            "maximum_selections", payload["maximum_selections"]
        )
        payload["is_required"] = _strict_bool("is_required", payload["is_required"])
        if "display_order" in payload:
            payload["display_order"] = _strict_int("display_order", payload["display_order"])
        current = {"product": _product_snapshot(session, target_id or ""), "group": None}
        _require_reference_evidence(
            "target_id",
            [current["product"]["sku"], current["product"]["name"]],
            evidence,
        )
        review_path = f"/products?search={current['product']['sku']}"
    elif kind == "modifier_option.create":
        group = (
            session.execute(
                sa.select(models.modifier_groups).where(
                    models.modifier_groups.c.id == target_id,
                    models.modifier_groups.c.organization_id == ORGANIZATION_ID,
                    models.modifier_groups.c.status == "active",
                )
            )
            .mappings()
            .first()
        )
        if not group:
            raise AdminAiError("admin_ai_reference_invalid", "El grupo de modificadores no existe.")
        _require_reference_evidence("target_id", [group["name"]], evidence)
        for field in ("price_delta_cents", "display_order"):
            if field in payload:
                payload[field] = _strict_int(field, payload[field])
        if "inventory_effect" in payload:
            payload["inventory_effect"] = _strict_bool(
                "inventory_effect", payload["inventory_effect"]
            )
        for field in ("affected_item_id", "replacement_item_id"):
            if payload.get(field):
                payload[field] = _require_reference(
                    session,
                    models.inventory_items,
                    payload[field],
                    models.inventory_items.c.organization_id,
                )
                _require_reference_evidence(field, _item_labels(session, payload[field]), evidence)
        current = {
            "group": _json(dict(group)),
            "product": _product_snapshot(session, str(group["product_id"])),
        }
        review_path = f"/products?search={current['product']['sku']}"
    elif kind == "recipe.version":
        product = _product_snapshot(session, target_id or "")
        _require_reference_evidence("target_id", [product["sku"], product["name"]], evidence)
        payload["yield_unit_id"] = _require_reference(
            session,
            models.inventory_units,
            payload["yield_unit_id"],
            models.inventory_units.c.organization_id,
        )
        _require_reference_evidence(
            "yield_unit_id", _unit_labels(session, payload["yield_unit_id"]), evidence
        )
        components = payload.get("components")
        if not isinstance(components, list) or not components:
            raise AdminAiError(
                "admin_ai_change_set_invalid", "La receta requiere al menos un componente."
            )
        normalized_components = []
        for index, component in enumerate(components):
            if (
                not isinstance(component, dict)
                or set(component) - {"item_id", "unit_id", "net_quantity", "waste_rate"}
                or not {"item_id", "unit_id", "net_quantity"}.issubset(component)
            ):
                raise AdminAiError(
                    "admin_ai_change_set_invalid", "Un componente de receta es inválido."
                )
            for field in ("net_quantity", "waste_rate"):
                if field in component:
                    _require_value_evidence(
                        f"components.{index}.{field}",
                        component[field],
                        evidence,
                    )
            item_id = _require_reference(
                session,
                models.inventory_items,
                component["item_id"],
                models.inventory_items.c.organization_id,
            )
            unit_id = _require_reference(
                session,
                models.inventory_units,
                component["unit_id"],
                models.inventory_units.c.organization_id,
            )
            _require_reference_evidence(
                f"components.{index}.item_id", _item_labels(session, item_id), evidence
            )
            _require_reference_evidence(
                f"components.{index}.unit_id", _unit_labels(session, unit_id), evidence
            )
            normalized_components.append(
                {
                    "item_id": item_id,
                    "unit_id": unit_id,
                    "net_quantity": str(component["net_quantity"]),
                    "waste_rate": str(component.get("waste_rate", "0")),
                }
            )
        payload["components"] = normalized_components
        active = (
            session.execute(
                sa.select(models.recipes).where(
                    models.recipes.c.organization_id == ORGANIZATION_ID,
                    models.recipes.c.product_id == target_id,
                    models.recipes.c.status == "active",
                    models.recipes.c.branch_id.is_(branch_id)
                    if branch_id is None
                    else models.recipes.c.branch_id == branch_id,
                )
            )
            .mappings()
            .first()
        )
        if active:
            current_recipe = dict(active)
            current_recipe["components"] = [
                dict(row)
                for row in session.execute(
                    sa.select(models.recipe_components)
                    .where(models.recipe_components.c.recipe_id == active["id"])
                    .order_by(models.recipe_components.c.sort_order)
                ).mappings()
            ]
            current = _json(current_recipe)
        else:
            current = None
        review_path = f"/recipes?search={product['sku']}"

    return {
        "kind": kind,
        "target_id": target_id,
        "current": current,
        "proposed": _json(payload),
        "review_path": review_path,
        "evidence_fields": sorted(evidence),
    }


def validate_provider_result(
    session: Session,
    prompt: str,
    result: dict[str, Any],
    branch_id: str | None,
) -> dict[str, Any]:
    required = {"answer", "sources", "questions", "warnings", "change_set"}
    if set(result) != required:
        raise AdminAiError(
            "admin_ai_provider_invalid_response",
            "La respuesta no cumple el contrato estricto.",
            502,
        )
    if (
        not isinstance(result["answer"], str)
        or not isinstance(result["sources"], list)
        or not isinstance(result["questions"], list)
        or not isinstance(result["warnings"], list)
        or not isinstance(result["change_set"], list)
    ):
        raise AdminAiError(
            "admin_ai_provider_invalid_response",
            "La respuesta no cumple el contrato estricto.",
            502,
        )
    visible_values = [result["answer"], *result["questions"], *result["warnings"]]
    if any(TECHNICAL_ID_PATTERN.search(str(value)) for value in visible_values):
        raise AdminAiError(
            "admin_ai_provider_invalid_response",
            "La respuesta visible del proveedor contiene identificadores técnicos.",
            502,
        )
    sources = [str(source) for source in result["sources"]]
    if not sources or any(source not in KNOWN_SOURCES for source in sources):
        raise AdminAiError("admin_ai_source_unknown", "El proveedor citó una fuente no autorizada.")
    if len(result["change_set"]) > 1:
        raise AdminAiError("admin_ai_change_set_invalid", "Cada propuesta admite una sola acción.")
    if result["questions"] and result["change_set"]:
        raise AdminAiError(
            "admin_ai_change_set_invalid", "Una propuesta con faltantes no puede quedar lista."
        )
    normalized_changes = []
    if result["change_set"]:
        change = result["change_set"][0]
        if not isinstance(change, dict):
            raise AdminAiError("admin_ai_change_set_invalid", "La acción propuesta es inválida.")
        normalized_changes.append(_normalize_change(session, prompt, change, branch_id))
    return {
        "answer": result["answer"].strip(),
        "sources": sources,
        "questions": [str(value) for value in result["questions"]],
        "warnings": [str(value) for value in result["warnings"]],
        "change_set": normalized_changes,
    }


def _audit_event(
    session: Session,
    action: str,
    proposal_id: str,
    actor_id: str,
    branch_id: str | None,
    payload: dict[str, Any],
) -> None:
    session.execute(
        models.audit_events.insert().values(
            id=str(uuid4()),
            organization_id=ORGANIZATION_ID,
            branch_id=branch_id,
            actor_user_id=actor_id,
            action=action,
            entity_type="admin_ai_proposal",
            entity_id=proposal_id,
            payload=_json(payload),
            correlation_id=None,
            created_at=_now(),
        )
    )


ProviderRequester = Callable[[str, dict[str, Any], AdminAiProviderOptions], dict[str, Any]]


def create_admin_ai_response(
    session: Session,
    actor_id: str,
    prompt: str,
    branch_id: str | None,
    provider_options: AdminAiProviderOptions | None = None,
    provider_requester: ProviderRequester = request_openrouter_proposal,
    *,
    parent_proposal_id: str | None = None,
    clarification_choice: str | None = None,
    conversation_context: list[str] | None = None,
    conversation_idempotency_key: str | None = None,
) -> dict[str, Any]:
    branch_id = authorize_branch_scope(session, actor_id, "catalog.manage", branch_id)
    normalized_prompt = prompt.strip()
    if not normalized_prompt or len(normalized_prompt) > 1600:
        raise AdminAiError(
            "admin_ai_prompt_invalid", "La consulta debe contener entre 1 y 1600 caracteres."
        )
    context = build_context(session, branch_id)
    external_provider_used = False
    parent: dict[str, Any] | None = None
    conversation_turn = 1
    if parent_proposal_id:
        if not conversation_idempotency_key:
            raise AdminAiError(
                "admin_ai_conversation_idempotency_required",
                "La continuación requiere una clave idempotente.",
            )
        try:
            conversation_idempotency_key = str(UUID(conversation_idempotency_key))
        except ValueError as exc:
            raise AdminAiError(
                "admin_ai_conversation_invalid",
                "La clave idempotente de la conversación es inválida.",
            ) from exc
        try:
            parent = _load_conversation_parent(
                session,
                actor_id,
                parent_proposal_id,
                branch_id,
            )
        except AdminAiError as exc:
            replay = (
                _find_conversation_replay(
                    session,
                    actor_id,
                    parent_proposal_id,
                    branch_id,
                    conversation_idempotency_key,
                )
                if exc.code == "admin_ai_conversation_invalid"
                else None
            )
            if replay:
                _require_diagnostic_access(session, actor_id, replay)
                return _json(replay)
            raise
        parent_payload = parent["payload"]
        clarification = parent_payload["clarification"]
        conversation_turn = int(clarification["turn"]) + 1
        if clarification.get("kind") == "inventory_price_authority":
            payload = _resolve_inventory_price_clarification(
                session,
                actor_id,
                branch_id,
                normalized_prompt,
                clarification,
                clarification_choice,
            )
        elif clarification.get("kind") == "free_text":
            if clarification_choice is not None:
                raise AdminAiError(
                    "admin_ai_conversation_invalid",
                    "Esta conversación no ofreció una opción estructurada.",
                )
            previous_user_messages = _normalize_conversation_context(conversation_context)
            pending_question = " ".join(
                str(question) for question in parent_payload.get("questions", [])[:3]
            )
            follow_up_prompt = (
                "Mensajes anteriores del usuario (contexto efímero):\n- "
                + "\n- ".join(previous_user_messages)
                + "\n"
                f"Pregunta pendiente del asistente: {pending_question}\n"
                f"Respuesta del usuario: {normalized_prompt}"
            )
            if provider_options is None:
                payload = curated_answer(follow_up_prompt)
            else:
                raw = provider_requester(follow_up_prompt, context, provider_options)
                payload = validate_provider_result(session, follow_up_prompt, raw, branch_id)
                external_provider_used = True
        else:
            raise AdminAiError(
                "admin_ai_conversation_invalid",
                "La conversación anterior no contiene una aclaración compatible.",
            )
    else:
        if (
            clarification_choice is not None
            or conversation_context
            or conversation_idempotency_key is not None
        ):
            raise AdminAiError(
                "admin_ai_conversation_invalid",
                "La aclaración y su contexto requieren una conversación anterior.",
            )
        preflight_payload = _price_diagnostic_preflight(
            session,
            actor_id,
            normalized_prompt,
            branch_id,
        )
        if preflight_payload is not None:
            payload = preflight_payload
        elif provider_options is None:
            payload = curated_answer(normalized_prompt)
        else:
            raw = provider_requester(normalized_prompt, context, provider_options)
            payload = validate_provider_result(session, normalized_prompt, raw, branch_id)
            external_provider_used = True
    payload = dict(payload)
    if payload.get("questions") and not isinstance(payload.get("clarification"), dict):
        payload["clarification"] = {
            "kind": "free_text",
            "turn": conversation_turn,
            "options": [],
        }
    if parent_proposal_id:
        payload["conversation"] = {
            "parent_proposal_id": parent_proposal_id,
            "turn": conversation_turn,
            "idempotency_key": conversation_idempotency_key,
        }
    now = _now()
    proposal = {
        "id": str(uuid4()),
        "organization_id": ORGANIZATION_ID,
        "branch_id": branch_id,
        "actor_user_id": actor_id,
        "status": "READY_FOR_REVIEW" if payload["change_set"] else "DRAFT",
        "base_fingerprint": context_fingerprint(context),
        "payload": _json(payload),
        "created_at": now,
        "updated_at": now,
        "expires_at": now + timedelta(hours=24),
        "reviewed_by_user_id": None,
        "apply_idempotency_key": None,
        "result": None,
        "applied_at": None,
        "rejected_at": None,
    }
    if parent_proposal_id:
        session.execute(
            sa.update(models.admin_ai_proposals)
            .where(
                models.admin_ai_proposals.c.id == parent_proposal_id,
                models.admin_ai_proposals.c.status == "DRAFT",
            )
            .values(expires_at=now, updated_at=now)
        )
    session.execute(models.admin_ai_proposals.insert().values(**proposal))
    if parent_proposal_id:
        _audit_event(
            session,
            "admin_ai.conversation_advanced",
            parent_proposal_id,
            actor_id,
            branch_id,
            {"child_proposal_id": proposal["id"], "conversation_turn": conversation_turn},
        )
    _audit_event(
        session,
        "admin_ai.proposal_created"
        if proposal["status"] == "READY_FOR_REVIEW"
        else "admin_ai.answer_created",
        proposal["id"],
        actor_id,
        branch_id,
        {
            "status": proposal["status"],
            "sources": payload["sources"],
            "kind": payload["change_set"][0]["kind"] if payload["change_set"] else None,
            "external_provider": external_provider_used,
            "parent_proposal_id": parent_proposal_id,
            "conversation_turn": conversation_turn if parent_proposal_id else None,
        },
    )
    session.commit()
    return _json(proposal)


def get_proposal(session: Session, proposal_id: str, actor_id: str) -> dict[str, Any]:
    require_permission(session, actor_id, "catalog.manage")
    proposal = (
        session.execute(
            sa.select(models.admin_ai_proposals).where(
                models.admin_ai_proposals.c.id == proposal_id,
                models.admin_ai_proposals.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not proposal:
        raise BusinessError("admin_ai_proposal_not_found", "Proposal was not found")
    result = dict(proposal)
    _require_diagnostic_access(session, actor_id, result)
    return _json(result)


def _require_diagnostic_access(
    session: Session,
    actor_id: str,
    proposal: dict[str, Any],
) -> None:
    payload = proposal.get("payload")
    diagnostic = payload.get("diagnostic") if isinstance(payload, dict) else None
    if not isinstance(diagnostic, dict):
        return
    scope = diagnostic.get("scope")
    branch_id = scope.get("branch_id") if isinstance(scope, dict) else None
    kind = diagnostic.get("kind")
    if not branch_id:
        raise AuthorizationError(
            "permission_denied",
            "A branch-scoped diagnostic requires an authorized branch",
        )
    if kind == "missing_purchase_price":
        require_permission(session, actor_id, "purchases.read", str(branch_id))
    elif kind == "missing_average_cost":
        require_permission(session, actor_id, "inventory.read", str(branch_id))


class _DeferredCommitSession:
    """Let canonical services flush while the proposal owns the final transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)

    def commit(self) -> None:
        self._session.flush()

    def rollback(self) -> None:
        self._session.rollback()


def _apply_action(
    session: Session,
    proposal: dict[str, Any],
    actor_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    change = proposal["payload"]["change_set"][0]
    kind = change["kind"]
    target_id = change.get("target_id")
    payload = dict(change["proposed"])
    governed_session = _DeferredCommitSession(session)
    if kind == "product.create":
        return create_product(governed_session, actor_user_id=actor_id, **payload)
    if kind == "product.update":
        return update_product(governed_session, target_id, actor_user_id=actor_id, **payload)
    if kind == "inventory_item.create":
        return create_inventory_item(governed_session, actor_user_id=actor_id, **payload)
    if kind == "modifier_group.create":
        return create_modifier_group(governed_session, target_id, payload, actor_user_id=actor_id)
    if kind == "modifier_option.create":
        return create_modifier_option(governed_session, target_id, payload, actor_user_id=actor_id)
    if kind == "recipe.version":
        current = change.get("current")
        return update_product_recipe_versioned(
            governed_session,
            target_id,
            payload,
            proposal.get("branch_id"),
            current.get("id") if isinstance(current, dict) else None,
            f"admin-ai:{proposal['id']}:{idempotency_key}",
            actor_id,
        )
    raise BusinessError("admin_ai_change_set_invalid", "Proposal action is not supported")


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def review_proposal(
    session: Session,
    proposal_id: str,
    actor_id: str,
    accept: bool,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    require_permission(session, actor_id, "catalog.manage")
    row = (
        session.execute(
            sa.select(models.admin_ai_proposals)
            .where(
                models.admin_ai_proposals.c.id == proposal_id,
                models.admin_ai_proposals.c.organization_id == ORGANIZATION_ID,
            )
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if not row:
        raise BusinessError("admin_ai_proposal_not_found", "Proposal was not found")
    proposal = dict(row)
    _require_diagnostic_access(session, actor_id, proposal)
    now = _now()
    if proposal["status"] == "APPLIED":
        if accept and idempotency_key and proposal["apply_idempotency_key"] == idempotency_key:
            return _json(proposal)
        raise BusinessError(
            "idempotency_conflict", "Proposal was already applied with another command"
        )
    if proposal["status"] in {"REJECTED", "EXPIRED"}:
        raise BusinessError(
            "admin_ai_proposal_not_ready", "Proposal is terminal and cannot be applied"
        )
    if _aware(proposal["expires_at"]) <= now:
        session.execute(
            sa.update(models.admin_ai_proposals)
            .where(models.admin_ai_proposals.c.id == proposal_id)
            .values(status="EXPIRED", updated_at=now)
        )
        _audit_event(
            session,
            "admin_ai.proposal_expired",
            proposal_id,
            actor_id,
            proposal["branch_id"],
            {"previous_status": proposal["status"]},
        )
        session.commit()
        raise BusinessError("admin_ai_proposal_expired", "Proposal expired")
    if not accept:
        session.execute(
            sa.update(models.admin_ai_proposals)
            .where(models.admin_ai_proposals.c.id == proposal_id)
            .values(
                status="REJECTED", reviewed_by_user_id=actor_id, rejected_at=now, updated_at=now
            )
        )
        _audit_event(
            session,
            "admin_ai.proposal_rejected",
            proposal_id,
            actor_id,
            proposal["branch_id"],
            {"previous_status": proposal["status"]},
        )
        session.commit()
        return get_proposal(session, proposal_id, actor_id)
    if proposal["status"] != "READY_FOR_REVIEW" or not proposal["payload"].get("change_set"):
        raise BusinessError(
            "admin_ai_proposal_not_ready", "No verified change set is available for review"
        )
    key = (idempotency_key or "").strip()
    if not key:
        raise BusinessError("idempotency_key_required", "Idempotency-Key is required")
    current_context = build_context(session, proposal["branch_id"])
    if context_fingerprint(current_context) != proposal["base_fingerprint"]:
        raise BusinessError(
            "admin_ai_proposal_stale", "Catalog configuration changed; regenerate the proposal"
        )
    try:
        result = _apply_action(session, proposal, actor_id, key)
        session.execute(
            sa.update(models.admin_ai_proposals)
            .where(models.admin_ai_proposals.c.id == proposal_id)
            .values(
                status="APPLIED",
                reviewed_by_user_id=actor_id,
                apply_idempotency_key=key,
                result=_json(result),
                applied_at=now,
                updated_at=now,
            )
        )
        change = proposal["payload"]["change_set"][0]
        _audit_event(
            session,
            "admin_ai.proposal_applied",
            proposal_id,
            actor_id,
            proposal["branch_id"],
            {
                "kind": change["kind"],
                "sources": proposal["payload"]["sources"],
                "result_entity_id": result.get("id"),
            },
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return get_proposal(session, proposal_id, actor_id)
