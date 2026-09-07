"""Facturapi & CFDI 4.0 Invoicing Domain Service."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from restaurant_os import models
from restaurant_os.config import get_settings

from .facturapi_client import FacturapiClient

logger = logging.getLogger(__name__)


class InvoicingService:
    """Orchestrator for Mexican electronic invoicing CFDI 4.0 via Facturapi."""

    @staticmethod
    def _write_fiscal_audit(
        session: Session,
        *,
        action: str,
        organization_id: str,
        branch_id: str | None,
        actor_user_id: str | None,
        entity_type: str,
        entity_id: str,
        outcome: str,
        provider_confirmation: str,
        order_count: int | None = None,
    ) -> None:
        """Persist an operational fiscal outcome without storing fiscal command data.

        Support impersonation is attributed to the real issuer.  The effective actor
        remains in the minimal audit payload because `audit_events` has one actor
        column, while the request-local context carries both identities.
        """
        correlation_id: str | None = str(uuid.uuid4())
        payload: dict[str, Any] = {
            "outcome": outcome,
            "provider_confirmation": provider_confirmation,
        }
        if order_count is not None:
            payload["order_count"] = order_count

        context = session.info.get("support_audit_context")
        if context:
            if str(context["target_organization_id"]) != organization_id:
                raise ValueError("El contexto de soporte no corresponde a la organización fiscal.")
            actor_user_id = str(context["real_actor_user_id"])
            correlation_id = str(context["correlation_id"])
            payload["effective_actor_user_id"] = str(context["effective_actor_user_id"])
        elif actor_user_id:
            payload["effective_actor_user_id"] = actor_user_id

        session.execute(
            models.audit_events.insert().values(
                id=str(uuid.uuid4()),
                organization_id=organization_id,
                branch_id=branch_id,
                actor_user_id=actor_user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                payload=payload,
                correlation_id=correlation_id,
                created_at=datetime.now(timezone.utc),
            )
        )

    def _record_fiscal_failure(
        self,
        session: Session,
        *,
        action: str,
        organization_id: str,
        branch_id: str | None,
        actor_user_id: str | None,
        entity_type: str,
        entity_id: str,
        order_count: int | None = None,
    ) -> None:
        """Rollback command effects, then record that provider confirmation is unknown."""
        session.rollback()
        self._write_fiscal_audit(
            session,
            action=action,
            organization_id=organization_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            outcome="failed",
            provider_confirmation="unknown",
            order_count=order_count,
        )
        session.commit()

    @staticmethod
    def _issue_fingerprint(order_ids: list[str]) -> str:
        """Stable command identity: the same orders remain one fiscal attempt."""
        canonical_orders = json.dumps(sorted(order_ids), separators=(",", ":"))
        return hashlib.sha256(canonical_orders.encode("utf-8")).hexdigest()

    @staticmethod
    def _payload_hash(receptor: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(receptor, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()

    def _prepare_issue_command(
        self,
        session: Session,
        *,
        organization_id: str,
        branch_id: str,
        order_ids: list[str],
        receptor: dict[str, Any],
        invoice_draft: dict[str, Any],
        actor_user_id: str | None,
    ) -> dict[str, Any]:
        """Commit a durable intent and claim it before provider I/O.

        No retry may send the same or overlapping orders while a prior command is
        unresolved. Provider idempotency is deliberately not assumed.
        """
        fingerprint = self._issue_fingerprint(order_ids)
        payload_hash = self._payload_hash(receptor)
        existing = (
            session.execute(
                sa.select(models.fiscal_commands).where(
                    models.fiscal_commands.c.organization_id == organization_id,
                    models.fiscal_commands.c.operation == "issue",
                    models.fiscal_commands.c.operation_fingerprint == fingerprint,
                )
            )
            .mappings()
            .first()
        )
        if existing:
            command = dict(existing)
            if command["status"] == "confirmed" and command.get("invoice_id"):
                if command["payload_hash"] == payload_hash:
                    return command
                raise ValueError(
                    "El pedido ya fue facturado con datos fiscales distintos."
                )
            raise ValueError(
                "La emisión fiscal previa requiere reconciliación antes de volver a intentarla."
            )

        context = session.info.get("support_audit_context")
        command_actor = str(context["real_actor_user_id"]) if context else actor_user_id
        correlation_id = str(context["correlation_id"]) if context else str(uuid.uuid4())
        command_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        try:
            session.execute(
                models.fiscal_commands.insert().values(
                    id=command_id,
                    organization_id=organization_id,
                    branch_id=branch_id,
                    operation="issue",
                    operation_fingerprint=fingerprint,
                    payload_hash=payload_hash,
                    order_ids=sorted(order_ids),
                    invoice_draft=invoice_draft,
                    status="pending",
                    provider_resource_id=None,
                    invoice_id=None,
                    actor_user_id=command_actor,
                    correlation_id=correlation_id,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.execute(
                models.fiscal_command_order_claims.insert(),
                [
                    {
                        "organization_id": organization_id,
                        "operation": "issue",
                        "order_id": order_id,
                        "command_id": command_id,
                        "created_at": now,
                    }
                    for order_id in order_ids
                ],
            )
            session.commit()
        except IntegrityError:
            session.rollback()
            claimed_command = (
                session.execute(
                    sa.select(models.fiscal_commands)
                    .join(
                        models.fiscal_command_order_claims,
                        models.fiscal_command_order_claims.c.command_id
                        == models.fiscal_commands.c.id,
                    )
                    .where(
                        models.fiscal_command_order_claims.c.organization_id == organization_id,
                        models.fiscal_command_order_claims.c.operation == "issue",
                        models.fiscal_command_order_claims.c.order_id.in_(order_ids),
                    )
                )
                .mappings()
                .first()
            )
            if claimed_command and (
                claimed_command["operation_fingerprint"] == fingerprint
                and claimed_command["status"] == "confirmed"
                and claimed_command.get("invoice_id")
            ):
                if claimed_command["payload_hash"] == payload_hash:
                    return dict(claimed_command)
                raise ValueError(
                    "El pedido ya fue facturado con datos fiscales distintos."
                ) from None
            if claimed_command and claimed_command["status"] == "confirmed":
                raise ValueError("Uno o más pedidos ya fueron facturados.") from None
            raise ValueError(
                "Uno o más pedidos tienen una emisión fiscal pendiente de reconciliación."
            ) from None

        claimed = session.execute(
            models.fiscal_commands.update()
            .where(
                models.fiscal_commands.c.id == command_id,
                models.fiscal_commands.c.status == "pending",
            )
            .values(status="inflight", updated_at=datetime.now(timezone.utc))
        )
        if getattr(claimed, "rowcount", None) != 1:
            session.rollback()
            raise ValueError("La emisión fiscal no pudo reclamarse para envío.")
        session.commit()
        return {
            "id": command_id,
            "status": "inflight",
            "operation_fingerprint": fingerprint,
            "payload_hash": payload_hash,
        }

    def _mark_issue_unknown(
        self, session: Session, command_id: str, provider_resource_id: str | None
    ) -> None:
        """Persist ambiguity after provider I/O; it is a stop state, never a retry cue."""
        session.rollback()
        session.execute(
            models.fiscal_commands.update()
            .where(models.fiscal_commands.c.id == command_id)
            .values(
                status="unknown",
                provider_resource_id=provider_resource_id,
                updated_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

    def _prepare_resource_command(
        self,
        session: Session,
        *,
        organization_id: str,
        branch_id: str,
        operation: str,
        target_id: str,
        snapshot: dict[str, Any],
        actor_user_id: str | None,
    ) -> dict[str, Any]:
        """Atomically claim one receipt/cancel resource before provider I/O."""
        fingerprint = hashlib.sha256(f"{operation}:{target_id}".encode()).hexdigest()
        payload_hash = self._payload_hash(snapshot)
        existing = (
            session.execute(
                sa.select(models.fiscal_commands)
                .join(
                    models.fiscal_command_resource_claims,
                    models.fiscal_command_resource_claims.c.command_id
                    == models.fiscal_commands.c.id,
                )
                .where(
                    models.fiscal_command_resource_claims.c.organization_id == organization_id,
                    models.fiscal_command_resource_claims.c.operation == operation,
                    models.fiscal_command_resource_claims.c.target_id == target_id,
                )
            )
            .mappings()
            .first()
        )
        if existing:
            if existing["status"] == "confirmed" and existing["payload_hash"] == payload_hash:
                return dict(existing)
            raise ValueError(
                "El comando fiscal previo requiere reconciliación antes de reintentarse."
            )
        command_id, now = str(uuid.uuid4()), datetime.now(timezone.utc)
        try:
            session.execute(
                models.fiscal_commands.insert().values(
                    id=command_id,
                    organization_id=organization_id,
                    branch_id=branch_id,
                    operation=operation,
                    operation_fingerprint=fingerprint,
                    payload_hash=payload_hash,
                    order_ids=[],
                    invoice_draft=snapshot,
                    status="pending",
                    provider_resource_id=None,
                    invoice_id=None,
                    actor_user_id=actor_user_id,
                    correlation_id=str(uuid.uuid4()),
                    created_at=now,
                    updated_at=now,
                )
            )
            session.execute(
                models.fiscal_command_resource_claims.insert().values(
                    organization_id=organization_id,
                    operation=operation,
                    target_id=target_id,
                    command_id=command_id,
                    created_at=now,
                )
            )
            session.commit()
        except IntegrityError:
            session.rollback()
            raise ValueError(
                "El comando fiscal previo requiere reconciliación antes de reintentarse."
            ) from None
        claimed = session.execute(
            models.fiscal_commands.update()
            .where(
                models.fiscal_commands.c.id == command_id,
                models.fiscal_commands.c.status == "pending",
            )
            .values(status="inflight", updated_at=datetime.now(timezone.utc))
        )
        if getattr(claimed, "rowcount", None) != 1:
            session.rollback()
            raise ValueError("El comando fiscal no pudo reclamarse.")
        session.commit()
        return {"id": command_id, "status": "inflight"}

    def reconcile_issue_command(
        self,
        session: Session,
        organization_id: str,
        command_id: str,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        """Query a known provider resource without turning ambiguity into a reissue.

        Local invoice reconstruction is intentionally a separate operation: the provider
        response is inspected first and this method never marks an unknown command confirmed.
        """
        command = (
            session.execute(
                sa.select(models.fiscal_commands).where(
                    models.fiscal_commands.c.id == command_id,
                    models.fiscal_commands.c.organization_id == organization_id,
                    models.fiscal_commands.c.operation == "issue",
                )
            )
            .mappings()
            .first()
        )
        if not command:
            raise ValueError("Comando fiscal no encontrado.")
        if command["status"] == "confirmed":
            return {
                "status": "confirmed",
                "invoice_id": command.get("invoice_id"),
                "reconciliation_required": False,
            }
        resource_id = command.get("provider_resource_id")
        if not resource_id:
            return {
                "status": "unknown",
                "provider_resource_known": False,
                "reconciliation_required": True,
            }

        provider = self.get_client(session, organization_id)
        result = provider.get_invoice(str(resource_id))
        provider_status = str(result.get("status") or "unknown").lower()
        draft = command.get("invoice_draft")
        if provider_status not in {"valid", "issued"} or not result.get("uuid") or not draft:
            return {
                "status": "unknown",
                "provider_resource_known": True,
                "provider_status": provider_status,
                "reconciliation_required": True,
            }

        existing_invoice_id = session.scalar(
            sa.select(models.cfdi_invoices.c.id).where(
                models.cfdi_invoices.c.organization_id == organization_id,
                models.cfdi_invoices.c.facturapi_invoice_id == resource_id,
            )
        )
        invoice_id = str(existing_invoice_id) if existing_invoice_id else str(uuid.uuid4())
        if not existing_invoice_id:
            series = str(draft["series"])
            folio_part = result.get("folio_number") or str(resource_id)[-8:]
            session.execute(
                models.cfdi_invoices.insert().values(
                    id=invoice_id,
                    organization_id=organization_id,
                    branch_id=command["branch_id"],
                    order_id=command["order_ids"][0] if len(command["order_ids"]) == 1 else None,
                    facturapi_invoice_id=resource_id,
                    facturapi_receipt_id=None,
                    uuid_sat=result["uuid"],
                    folio_number=f"{series}-{folio_part}",
                    rfc_emisor=draft["rfc_emisor"],
                    rfc_receptor=draft["rfc_receptor"],
                    nombre_receptor=draft["nombre_receptor"],
                    codigo_postal_receptor=draft["codigo_postal_receptor"],
                    regimen_fiscal_receptor=draft["regimen_fiscal_receptor"],
                    uso_cfdi=draft["uso_cfdi"],
                    forma_pago_sat=draft["forma_pago_sat"],
                    metodo_pago_sat=draft["metodo_pago_sat"],
                    total_cents=draft["total_cents"],
                    currency="MXN",
                    status="issued",
                    verification_url=result.get("verification_url"),
                    self_invoice_url=None,
                    pdf_url=f"https://www.facturapi.io/v2/invoices/{resource_id}/pdf",
                    xml_url=f"https://www.facturapi.io/v2/invoices/{resource_id}/xml",
                    cancellation_reason=None,
                    raw_sat_response=result,
                    created_at=datetime.now(timezone.utc),
                    cancelled_at=None,
                )
            )
        session.execute(
            models.fiscal_commands.update()
            .where(models.fiscal_commands.c.id == command_id)
            .values(
                status="confirmed", invoice_id=invoice_id, updated_at=datetime.now(timezone.utc)
            )
        )
        self._write_fiscal_audit(
            session,
            action="cfdi.issue.reconciled",
            organization_id=organization_id,
            branch_id=str(command["branch_id"]),
            actor_user_id=actor_user_id,
            entity_type="fiscal_command",
            entity_id=command_id,
            outcome="confirmed",
            provider_confirmation="confirmed",
            order_count=len(command["order_ids"]),
        )
        session.commit()
        return {
            "status": "confirmed",
            "invoice_id": invoice_id,
            "reconciliation_required": False,
        }

    def reconcile_resource_command(
        self,
        session: Session,
        organization_id: str,
        command_id: str,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        """Confirm a known receipt/cancellation resource without re-sending it.

        An ``unknown`` command is deliberately not retried through the provider.
        The resource identifier captured after the original response is queried first;
        only the expected provider state permits the local command to become confirmed.
        """
        command = (
            session.execute(
                sa.select(models.fiscal_commands).where(
                    models.fiscal_commands.c.id == command_id,
                    models.fiscal_commands.c.organization_id == organization_id,
                    models.fiscal_commands.c.operation.in_(("receipt", "cancel")),
                )
            )
            .mappings()
            .first()
        )
        if not command:
            raise ValueError("Comando fiscal no encontrado.")
        if command["status"] == "confirmed":
            return {"status": "confirmed", "reconciliation_required": False}
        if command["status"] != "unknown":
            return {"status": str(command["status"]), "reconciliation_required": True}
        resource_id = command.get("provider_resource_id")
        if not resource_id:
            return {
                "status": "unknown",
                "provider_resource_known": False,
                "reconciliation_required": True,
            }

        provider = self.get_client(session, organization_id)
        operation = str(command["operation"])
        if operation == "receipt":
            result = provider.get_receipt(str(resource_id))
            provider_status = str(result.get("status") or "unknown").lower()
            confirmed = bool(result.get("id")) and provider_status == "open"
            action, entity_type, entity_id = "cfdi.receipt.reconciled", "order", None
        else:
            result = provider.get_invoice(str(resource_id))
            provider_status = str(result.get("status") or "unknown").lower()
            confirmed = provider_status in {"cancelled", "canceled"} or str(
                result.get("cancellation_status") or ""
            ).lower() == "accepted"
            claim = session.execute(
                sa.select(models.fiscal_command_resource_claims.c.target_id).where(
                    models.fiscal_command_resource_claims.c.command_id == command_id
                )
            ).scalar_one()
            entity_type, entity_id, action = "cfdi_invoice", str(claim), "cfdi.cancel.reconciled"

        if not confirmed:
            return {
                "status": "unknown",
                "provider_resource_known": True,
                "provider_status": provider_status,
                "reconciliation_required": True,
            }

        try:
            claimed = session.execute(
                models.fiscal_commands.update()
                .where(
                    models.fiscal_commands.c.id == command_id,
                    models.fiscal_commands.c.status == "unknown",
                )
                .values(status="confirmed", updated_at=datetime.now(timezone.utc))
            )
            if getattr(claimed, "rowcount", None) != 1:
                session.rollback()
                current_status = session.scalar(
                    sa.select(models.fiscal_commands.c.status).where(
                        models.fiscal_commands.c.id == command_id
                    )
                )
                return {
                    "status": "confirmed" if current_status == "confirmed" else "unknown",
                    "reconciliation_required": current_status != "confirmed",
                }
            if operation == "cancel":
                session.execute(
                    models.cfdi_invoices.update()
                    .where(
                        models.cfdi_invoices.c.organization_id == organization_id,
                        models.cfdi_invoices.c.id == entity_id,
                    )
                    .values(
                        status="cancelled",
                        cancellation_reason=(command.get("invoice_draft") or {}).get("motive"),
                        cancelled_at=datetime.now(timezone.utc),
                    )
                )
            self._write_fiscal_audit(
                session,
                action=action,
                organization_id=organization_id,
                branch_id=str(command["branch_id"]),
                actor_user_id=actor_user_id,
                entity_type=entity_type,
                entity_id=entity_id or command_id,
                outcome="confirmed",
                provider_confirmation="confirmed",
                order_count=1 if operation == "receipt" else None,
            )
            session.commit()
        except Exception:
            self._mark_issue_unknown(session, command_id, str(resource_id))
            raise
        return {"status": "confirmed", "reconciliation_required": False}

    @staticmethod
    def _is_explicit_sandbox_simulation(config: dict[str, Any]) -> bool:
        """Return whether this configured sandbox intentionally uses the local simulator."""
        api_key = str(config.get("api_key") or "").strip()
        return (
            get_settings().environment != "production"
            and str(config.get("environment") or "").lower() == "sandbox"
            and api_key.startswith(("sk_test_mock", "mock_test_"))
        )

    def _require_provider_config(self, session: Session, organization_id: str) -> dict[str, Any]:
        """Validate configuration before any provider client or fiscal side effect."""
        config = self.get_config(session, organization_id)
        if not config or not config.get("is_enabled"):
            raise ValueError("La facturación electrónica no está habilitada en la configuración.")

        api_key = str(config.get("api_key") or "").strip()
        if not api_key:
            raise ValueError(
                "La configuración de FacturAPI requiere una API key antes de facturar."
            )

        environment = str(config.get("environment") or "").lower()
        if environment not in {"sandbox", "production"}:
            raise ValueError("El entorno de FacturAPI debe ser sandbox o production.")
        if get_settings().environment == "production" and api_key.startswith(
            ("sk_test_mock", "mock_test_")
        ):
            raise ValueError("La simulación de FacturAPI no está permitida en producción.")
        if environment == "production" and api_key.startswith(("sk_test_mock", "mock_test_")):
            raise ValueError("La configuración de producción no admite una API key simulada.")
        return config

    def get_client(self, session: Session, organization_id: str) -> FacturapiClient:
        config = self._require_provider_config(session, organization_id)
        api_key = str(config["api_key"]).strip()
        return FacturapiClient(
            api_key=api_key,
            is_mock=self._is_explicit_sandbox_simulation(config),
        )

    def get_config(self, session: Session, organization_id: str) -> dict[str, Any] | None:
        row = (
            session.execute(
                sa.select(models.facturapi_config).where(
                    models.facturapi_config.c.organization_id == organization_id
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    def save_config(
        self, session: Session, organization_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        existing = self.get_config(session, organization_id)

        clean_data = {
            "is_enabled": bool(payload.get("is_enabled", False)),
            "environment": payload.get("environment") or "sandbox",
            "api_key": payload.get("api_key") or None,
            "organization_legal_name": payload.get("organization_legal_name")
            or "RESTAURANTE KIWI SA DE CV",
            "organization_rfc": (payload.get("organization_rfc") or "KIW210101ABC").upper().strip(),
            "organization_tax_system": payload.get("organization_tax_system") or "601",
            "organization_zip": payload.get("organization_zip") or "80000",
            "default_product_sat_key": payload.get("default_product_sat_key") or "90101501",
            "default_unit_sat_key": payload.get("default_unit_sat_key") or "E48",
            "series": (payload.get("series") or "F").upper().strip(),
            "enable_self_invoicing": bool(payload.get("enable_self_invoicing", True)),
            "self_invoicing_domain": payload.get("self_invoicing_domain") or "demo",
            "self_invoicing_days_valid": int(payload.get("self_invoicing_days_valid") or 30),
            "print_qr_on_ticket": bool(payload.get("print_qr_on_ticket", True)),
            "updated_at": now,
        }

        if existing:
            session.execute(
                models.facturapi_config.update()
                .where(models.facturapi_config.c.organization_id == organization_id)
                .values(clean_data)
            )
        else:
            config_id = str(uuid.uuid4())
            values_to_insert = dict(clean_data)
            values_to_insert["id"] = config_id
            values_to_insert["organization_id"] = organization_id
            values_to_insert["created_at"] = now
            session.execute(models.facturapi_config.insert().values(values_to_insert))

        session.commit()
        return self.get_config(session, organization_id) or {}

    def test_connection(self, session: Session, organization_id: str) -> dict[str, Any]:
        client = self.get_client(session, organization_id)
        result = client.validate_api_key()
        if client.is_mock:
            return {**result, "status": "simulated", "provider_confirmed": False}
        return {**result, "provider_confirmed": True}

    def create_receipt_for_order(
        self,
        session: Session,
        organization_id: str,
        branch_id: str,
        order_id: str,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        """Generates an E-Receipt for an order so the customer can self-invoice."""
        config = self._require_provider_config(session, organization_id)

        order_row = (
            session.execute(
                sa.select(models.orders).where(
                    models.orders.c.organization_id == organization_id,
                    models.orders.c.branch_id == branch_id,
                    models.orders.c.id == order_id,
                )
            )
            .mappings()
            .first()
        )

        if not order_row:
            raise ValueError(f"Orden con ID {order_id} no encontrada.")

        # Payment form mapping
        pm = order_row.get("payment_method_intent") or "cash"
        payment_form_map = {
            "cash": "01",
            "card_debit": "28",
            "card_credit": "04",
            "transfer": "03",
            "marketplace_uber": "31",
        }
        sat_payment_form = payment_form_map.get(pm, "01")

        # Total in currency units
        total_amount = float(order_row["total_cents"]) / 100.0

        receipt_payload = {
            "payment_form": sat_payment_form,
            "items": [
                {
                    "quantity": 1,
                    "product": {
                        "description": f"Consumo en restaurante Folio {order_row['folio']}",
                        "product_key": config.get("default_product_sat_key") or "90101501",
                        "unit_key": config.get("default_unit_sat_key") or "E48",
                        "price": total_amount,
                        "taxes": [{"type": "IVA", "rate": 0.16}],
                    },
                }
            ],
        }

        client = self.get_client(session, organization_id)
        command = (
            self._prepare_resource_command(
                session,
                organization_id=organization_id,
                branch_id=branch_id,
                operation="receipt",
                target_id=order_id,
                snapshot={},
                actor_user_id=actor_user_id,
            )
            if not client.is_mock
            else None
        )
        if command and command["status"] == "confirmed":
            return {
                "receipt_id": command.get("provider_resource_id"),
                "order_id": order_id,
                "status": "open",
                "provider_confirmed": True,
            }
        res: dict[str, Any] = {}
        try:
            res = client.create_receipt(receipt_payload)
            if (
                not client.is_mock
                and (not res.get("id") or str(res.get("status") or "").lower() != "open")
            ):
                raise RuntimeError("FacturAPI no confirmó la creación del recibo.")
        except Exception:
            if command:
                self._mark_issue_unknown(
                    session, str(command["id"]), str(res.get("id") or "") or None
                )
            self._record_fiscal_failure(
                session,
                action="cfdi.receipt.failed",
                organization_id=organization_id,
                branch_id=branch_id,
                actor_user_id=actor_user_id,
                entity_type="order",
                entity_id=order_id,
                order_count=1,
            )
            raise

        if client.is_mock:
            self._write_fiscal_audit(
                session,
                action="cfdi.receipt.simulated",
                organization_id=organization_id,
                branch_id=branch_id,
                actor_user_id=actor_user_id,
                entity_type="order",
                entity_id=order_id,
                outcome="simulated",
                provider_confirmation="not_requested",
                order_count=1,
            )
            session.commit()
            return {
                "receipt_id": res.get("id"),
                "order_id": order_id,
                "status": "simulated",
                "provider_confirmed": False,
            }

        receipt_id = res.get("id")
        subdomain = config.get("self_invoice_domain") or "demo"
        self_invoice_url = (
            res.get("self_invoice_url") or f"https://factura.space/{subdomain}/receipt/{receipt_id}"
        )
        self._write_fiscal_audit(
            session,
            action="cfdi.receipt.confirmed",
            organization_id=organization_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            entity_type="order",
            entity_id=order_id,
            outcome="confirmed",
            provider_confirmation="confirmed",
            order_count=1,
        )
        if command:
            session.execute(
                models.fiscal_commands.update()
                .where(models.fiscal_commands.c.id == command["id"])
                .values(
                    status="confirmed",
                    provider_resource_id=receipt_id,
                    updated_at=datetime.now(timezone.utc),
                )
            )
        try:
            session.commit()
        except Exception:
            if command:
                self._mark_issue_unknown(session, str(command["id"]), str(receipt_id))
            raise

        return {
            "receipt_id": receipt_id,
            "order_id": order_id,
            "self_invoice_url": self_invoice_url,
            "key": res.get("key"),
            "status": "open",
            "provider_confirmed": True,
        }

    def issue_invoice(
        self,
        session: Session,
        org_id: str,
        branch_id: str,
        order_ids: list[str],
        receptor: dict[str, Any],
        actor_user_id: str | None = None,
        audit_operation: str = "issue",
    ) -> dict[str, Any]:
        """Directly issues a CFDI 4.0 for one or multiple orders."""
        if audit_operation not in {"issue", "self_invoice"}:
            raise ValueError("Operación de auditoría fiscal inválida.")
        audit_action = f"cfdi.{audit_operation}"
        # Validate the complete command before instantiating or calling the provider.
        if not order_ids or len(set(order_ids)) != len(order_ids):
            raise ValueError("Los pedidos a facturar deben ser únicos.")
        orders_rows = (
            session.execute(
                sa.select(models.orders).where(
                    models.orders.c.organization_id == org_id,
                    models.orders.c.branch_id == branch_id,
                    models.orders.c.id.in_(order_ids),
                )
            )
            .mappings()
            .all()
        )

        if len(orders_rows) != len(order_ids):
            raise ValueError("Uno o más pedidos no pertenecen a la organización o sucursal.")

        config = self._require_provider_config(session, org_id)
        client = self.get_client(session, org_id)

        total_cents = sum(o["total_cents"] for o in orders_rows)
        total_amount = float(total_cents) / 100.0

        rfc_receptor = receptor.get("rfc", "XAXX010101000").upper().strip()
        legal_name = receptor.get("legal_name", "PUBLICO EN GENERAL").upper().strip()
        zip_code = str(receptor.get("zip", "80000")).strip()
        tax_system = str(receptor.get("tax_system", "616")).strip()
        use = str(receptor.get("use", "S01")).upper().strip()
        payment_form = str(receptor.get("payment_form", "01")).strip()
        payment_method = str(receptor.get("payment_method", "PUE")).upper().strip()

        customer_obj = {
            "legal_name": legal_name,
            "tax_id": rfc_receptor,
            "tax_system": tax_system,
            "address": {"zip": zip_code},
        }
        if receptor.get("email"):
            customer_obj["email"] = receptor["email"]

        folios_str = ", ".join(o["folio"] for o in orders_rows)
        invoice_payload = {
            "customer": customer_obj,
            "payment_form": payment_form,
            "payment_method": payment_method,
            "use": use,
            "series": config.get("series") or "F",
            "items": [
                {
                    "quantity": 1,
                    "product": {
                        "description": f"Consumo de alimentos y bebidas (Folios: {folios_str})",
                        "product_key": config.get("default_product_sat_key") or "90101501",
                        "unit_key": config.get("default_unit_sat_key") or "E48",
                        "price": total_amount,
                        "taxes": [{"type": "IVA", "rate": 0.16}],
                    },
                }
            ],
        }

        command: dict[str, Any] | None = None
        if not client.is_mock:
            invoice_draft = {
                "rfc_emisor": config.get("organization_rfc") or "KIW210101ABC",
                "rfc_receptor": rfc_receptor,
                "nombre_receptor": legal_name,
                "codigo_postal_receptor": zip_code,
                "regimen_fiscal_receptor": tax_system,
                "uso_cfdi": use,
                "forma_pago_sat": payment_form,
                "metodo_pago_sat": payment_method,
                "total_cents": total_cents,
                "series": config.get("series") or "F",
            }
            command = self._prepare_issue_command(
                session,
                organization_id=org_id,
                branch_id=branch_id,
                order_ids=order_ids,
                receptor=receptor,
                invoice_draft=invoice_draft,
                actor_user_id=actor_user_id,
            )
            if command["status"] == "confirmed":
                return self.get_invoice_detail(session, org_id, str(command["invoice_id"])) or {}

        try:
            res = client.create_invoice(invoice_payload)
        except Exception:
            if command:
                self._mark_issue_unknown(session, str(command["id"]), None)
            self._record_fiscal_failure(
                session,
                action=f"{audit_action}.failed",
                organization_id=org_id,
                branch_id=branch_id,
                actor_user_id=actor_user_id,
                entity_type="order",
                entity_id=order_ids[0],
                order_count=len(order_ids),
            )
            raise

        if client.is_mock:
            self._write_fiscal_audit(
                session,
                action=f"{audit_action}.simulated",
                organization_id=org_id,
                branch_id=branch_id,
                actor_user_id=actor_user_id,
                entity_type="order",
                entity_id=order_ids[0],
                outcome="simulated",
                provider_confirmation="not_requested",
                order_count=len(order_ids),
            )
            session.commit()
            return {
                "status": "simulated",
                "provider_confirmed": False,
                "order_ids": order_ids,
                "total_cents": total_cents,
            }

        if str(res.get("status") or "").lower() not in {"valid", "issued"} or not res.get("uuid"):
            if command:
                self._mark_issue_unknown(
                    session, str(command["id"]), str(res.get("id") or "") or None
                )
            self._record_fiscal_failure(
                session,
                action=f"{audit_action}.failed",
                organization_id=org_id,
                branch_id=branch_id,
                actor_user_id=actor_user_id,
                entity_type="order",
                entity_id=order_ids[0],
                order_count=len(order_ids),
            )
            raise RuntimeError("FacturAPI no confirmó el timbrado de la factura.")

        invoice_db_id = str(uuid.uuid4())
        facturapi_inv_id = res.get("id") or str(uuid.uuid4())
        uuid_sat = res.get("uuid") or str(uuid.uuid4()).upper()
        series = config.get("series") or "F"
        folio_part = res.get("folio_number") or uuid.uuid4().hex[:4].upper()
        folio_num = f"{series}-{folio_part}"
        now = datetime.now(timezone.utc)

        pdf_url = f"https://www.facturapi.io/v2/invoices/{facturapi_inv_id}/pdf"
        xml_url = f"https://www.facturapi.io/v2/invoices/{facturapi_inv_id}/xml"
        verification_url = (
            res.get("verification_url")
            or f"https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx?id={uuid_sat}"
        )

        primary_order_id = orders_rows[0]["id"] if len(orders_rows) == 1 else None

        session.execute(
            models.cfdi_invoices.insert().values(
                id=invoice_db_id,
                organization_id=org_id,
                branch_id=branch_id,
                order_id=primary_order_id,
                facturapi_invoice_id=facturapi_inv_id,
                facturapi_receipt_id=None,
                uuid_sat=uuid_sat,
                folio_number=folio_num,
                rfc_emisor=config.get("organization_rfc") or "KIW210101ABC",
                rfc_receptor=rfc_receptor,
                nombre_receptor=legal_name,
                codigo_postal_receptor=zip_code,
                regimen_fiscal_receptor=tax_system,
                uso_cfdi=use,
                forma_pago_sat=payment_form,
                metodo_pago_sat=payment_method,
                total_cents=total_cents,
                currency="MXN",
                status="issued",
                verification_url=verification_url,
                self_invoice_url=None,
                pdf_url=pdf_url,
                xml_url=xml_url,
                cancellation_reason=None,
                raw_sat_response=res,
                created_at=now,
                cancelled_at=None,
            )
        )
        self._write_fiscal_audit(
            session,
            action=f"{audit_action}.confirmed",
            organization_id=org_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            entity_type="cfdi_invoice",
            entity_id=invoice_db_id,
            outcome="confirmed",
            provider_confirmation="confirmed",
            order_count=len(order_ids),
        )
        if command:
            session.execute(
                models.fiscal_commands.update()
                .where(
                    models.fiscal_commands.c.id == command["id"],
                    models.fiscal_commands.c.status == "inflight",
                )
                .values(
                    status="confirmed",
                    provider_resource_id=facturapi_inv_id,
                    invoice_id=invoice_db_id,
                    updated_at=datetime.now(timezone.utc),
                )
            )
        try:
            session.commit()
        except Exception:
            if command:
                self._mark_issue_unknown(session, str(command["id"]), str(facturapi_inv_id))
            raise

        # If email provided, send it
        if receptor.get("email"):
            try:
                client.send_email(facturapi_inv_id, receptor["email"])
            except Exception as e:
                logger.warning("No se pudo enviar factura por correo: %s", e)

        return self.get_invoice_detail(session, org_id, invoice_db_id) or {}

    def list_invoices(
        self,
        session: Session,
        org_id: str,
        branch_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = sa.select(models.cfdi_invoices).where(
            models.cfdi_invoices.c.organization_id == org_id
        )
        if branch_id:
            query = query.where(models.cfdi_invoices.c.branch_id == branch_id)
        if status:
            query = query.where(models.cfdi_invoices.c.status == status)

        query = query.order_by(models.cfdi_invoices.c.created_at.desc()).limit(limit).offset(offset)
        rows = session.execute(query).mappings().all()
        return [dict(r) for r in rows]

    def get_invoice_detail(
        self, session: Session, org_id: str, invoice_id: str
    ) -> dict[str, Any] | None:
        row = (
            session.execute(
                sa.select(models.cfdi_invoices).where(
                    models.cfdi_invoices.c.organization_id == org_id,
                    models.cfdi_invoices.c.id == invoice_id,
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    def cancel_invoice(
        self,
        session: Session,
        org_id: str,
        invoice_id: str,
        motive: str = "02",
        substitution_uuid: str | None = None,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        inv = self.get_invoice_detail(session, org_id, invoice_id)
        if not inv:
            raise ValueError(f"Factura con ID {invoice_id} no encontrada.")

        client = self.get_client(session, org_id)
        cancel_snapshot = {"motive": motive, "substitution_uuid": substitution_uuid}
        command = (
            self._prepare_resource_command(
                session,
                organization_id=org_id,
                branch_id=str(inv["branch_id"]),
                operation="cancel",
                target_id=invoice_id,
                snapshot=cancel_snapshot,
                actor_user_id=actor_user_id,
            )
            if not client.is_mock
            else None
        )
        if command and command["status"] == "confirmed":
            return self.get_invoice_detail(session, org_id, invoice_id) or {}
        try:
            provider_result = (
                client.cancel_invoice(inv["facturapi_invoice_id"], motive, substitution_uuid)
                if inv.get("facturapi_invoice_id")
                else {}
            )
            if (
                not client.is_mock
                and str(provider_result.get("status") or "").lower()
                not in {
                    "cancelled",
                    "canceled",
                }
                and str(provider_result.get("cancellation_status") or "").lower() != "accepted"
            ):
                raise RuntimeError("FacturAPI no confirmó la cancelación de la factura.")
        except Exception:
            if command:
                self._mark_issue_unknown(
                    session, str(command["id"]), str(inv.get("facturapi_invoice_id") or "") or None
                )
            self._record_fiscal_failure(
                session,
                action="cfdi.cancel.failed",
                organization_id=org_id,
                branch_id=str(inv["branch_id"]),
                actor_user_id=actor_user_id,
                entity_type="cfdi_invoice",
                entity_id=invoice_id,
            )
            raise

        if client.is_mock:
            self._write_fiscal_audit(
                session,
                action="cfdi.cancel.simulated",
                organization_id=org_id,
                branch_id=str(inv["branch_id"]),
                actor_user_id=actor_user_id,
                entity_type="cfdi_invoice",
                entity_id=invoice_id,
                outcome="simulated",
                provider_confirmation="not_requested",
            )
            session.commit()
            return {
                "id": invoice_id,
                "status": "simulated",
                "provider_confirmed": False,
            }

        now = datetime.now(timezone.utc)
        session.execute(
            models.cfdi_invoices.update()
            .where(
                models.cfdi_invoices.c.organization_id == org_id,
                models.cfdi_invoices.c.id == invoice_id,
            )
            .values(
                status="cancelled",
                cancellation_reason=motive,
                cancelled_at=now,
            )
        )
        self._write_fiscal_audit(
            session,
            action="cfdi.cancel.confirmed",
            organization_id=org_id,
            branch_id=str(inv["branch_id"]),
            actor_user_id=actor_user_id,
            entity_type="cfdi_invoice",
            entity_id=invoice_id,
            outcome="confirmed",
            provider_confirmation="confirmed",
        )
        if command:
            session.execute(
                models.fiscal_commands.update()
                .where(models.fiscal_commands.c.id == command["id"])
                .values(
                    status="confirmed",
                    provider_resource_id=inv.get("facturapi_invoice_id"),
                    invoice_id=invoice_id,
                    updated_at=datetime.now(timezone.utc),
                )
            )
        try:
            session.commit()
        except Exception:
            if command:
                self._mark_issue_unknown(
                    session, str(command["id"]), str(inv.get("facturapi_invoice_id") or "") or None
                )
            raise
        return self.get_invoice_detail(session, org_id, invoice_id) or {}
