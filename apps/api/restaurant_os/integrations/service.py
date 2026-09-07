from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, cast

import sqlalchemy as sa
from sqlalchemy.orm import Session

from .. import models
from .base import NormalizedOrder
from .didi_food import DiDiFoodAdapter
from .rappi import RappiAdapter
from .uber_eats import UberAvailabilityPermanentError, UberEatsAdapter


@dataclass(frozen=True)
class WebhookTarget:
    """The one configured tenant target allowed for an inbound event."""

    organization_id: str
    branch_id: str
    provider: str
    external_store_id: str
    webhook_secret: str


class ChannelIntegrationService:
    def __init__(self) -> None:
        self.uber_adapter = UberEatsAdapter()
        self.didi_adapter = DiDiFoodAdapter()
        self.rappi_adapter = RappiAdapter()

    def get_adapter(self, provider: str) -> UberEatsAdapter | DiDiFoodAdapter | RappiAdapter:
        if provider == "UBER_EATS":
            return self.uber_adapter
        if provider == "DIDI_FOOD":
            return self.didi_adapter
        if provider == "RAPPI":
            return self.rappi_adapter
        raise ValueError(f"Proveedor no soportado: {provider}")

    def resolve_webhook_target(
        self, session: Session, provider: str, payload: dict[str, Any]
    ) -> WebhookTarget:
        """Resolve exactly one enabled mapping before verifying a webhook.

        A provider store id is untrusted input.  It never selects a default
        organization or branch, and ambiguous mappings fail closed.
        """
        adapter = self.get_adapter(provider)
        external_store_id = adapter.normalize_order(payload, {}, None).external_store_id.strip()
        if not external_store_id:
            raise ValueError("webhook_store_required")
        rows = (
            session.execute(
                sa.select(
                    models.channel_store_mappings.c.organization_id,
                    models.channel_store_mappings.c.branch_id,
                    models.channel_integrations.c.webhook_secret,
                )
                .join(
                    models.channel_integrations,
                    sa.and_(
                        models.channel_integrations.c.organization_id
                        == models.channel_store_mappings.c.organization_id,
                        models.channel_integrations.c.provider
                        == models.channel_store_mappings.c.provider,
                    ),
                )
                .where(
                    models.channel_store_mappings.c.provider == provider,
                    models.channel_store_mappings.c.external_store_id == external_store_id,
                    models.channel_store_mappings.c.is_active.is_(True),
                    models.channel_integrations.c.is_enabled.is_(True),
                )
            )
            .mappings()
            .all()
        )
        if len(rows) != 1:
            raise ValueError("webhook_store_not_configured")
        row = rows[0]
        secret = str(row["webhook_secret"] or "").strip()
        if not secret:
            raise ValueError("webhook_secret_required")
        return WebhookTarget(
            organization_id=str(row["organization_id"]),
            branch_id=str(row["branch_id"]),
            provider=provider,
            external_store_id=external_store_id,
            webhook_secret=secret,
        )

    def get_config(
        self, session: Session, organization_id: str, provider: str
    ) -> dict[str, Any] | None:
        query = sa.select(models.channel_integrations).where(
            models.channel_integrations.c.organization_id == organization_id,
            models.channel_integrations.c.provider == provider,
        )
        row = session.execute(query).mappings().first()
        if not row:
            return None
        return dict(row)

    def save_config(
        self,
        session: Session,
        organization_id: str,
        provider: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        existing = self.get_config(session, organization_id, provider)
        now = datetime.now(timezone.utc)

        payload = {
            "is_enabled": bool(data.get("is_enabled", False)),
            "environment": str(data.get("environment", "sandbox")),
            "client_id": str(data.get("client_id", "")).strip() or None,
            "client_secret": str(data.get("client_secret", "")).strip() or None,
            "webhook_secret": str(data.get("webhook_secret", "")).strip() or None,
            "auto_accept": bool(data.get("auto_accept", True)),
            "default_prep_time_minutes": int(data.get("default_prep_time_minutes", 20)),
            "updated_at": now,
        }

        if existing:
            session.execute(
                sa.update(models.channel_integrations)
                .where(
                    models.channel_integrations.c.organization_id == organization_id,
                    models.channel_integrations.c.provider == provider,
                )
                .values(**payload)
            )
            config_id = existing["id"]
        else:
            config_id = str(uuid.uuid4())
            session.execute(
                models.channel_integrations.insert().values(
                    id=config_id,
                    organization_id=organization_id,
                    provider=provider,
                    created_at=now,
                    **payload,
                )
            )

        session.commit()
        return self.get_config(session, organization_id, provider) or {}

    def list_store_mappings(
        self, session: Session, organization_id: str, provider: str
    ) -> list[dict[str, Any]]:
        query = (
            sa.select(
                models.channel_store_mappings.c.id,
                models.channel_store_mappings.c.branch_id,
                models.channel_store_mappings.c.provider,
                models.channel_store_mappings.c.external_store_id,
                models.channel_store_mappings.c.is_active,
                models.channel_store_mappings.c.created_at,
                models.branches.c.name.label("branch_name"),
                models.branches.c.code.label("branch_code"),
            )
            .join(
                models.branches, models.channel_store_mappings.c.branch_id == models.branches.c.id
            )
            .where(
                models.channel_store_mappings.c.organization_id == organization_id,
                models.channel_store_mappings.c.provider == provider,
            )
            .order_by(models.branches.c.name.asc())
        )
        return [dict(r) for r in session.execute(query).mappings().all()]

    def save_store_mapping(
        self,
        session: Session,
        organization_id: str,
        provider: str,
        branch_id: str,
        external_store_id: str,
        is_active: bool = True,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        existing = (
            session.execute(
                sa.select(models.channel_store_mappings).where(
                    models.channel_store_mappings.c.organization_id == organization_id,
                    models.channel_store_mappings.c.provider == provider,
                    models.channel_store_mappings.c.branch_id == branch_id,
                )
            )
            .mappings()
            .first()
        )

        if existing:
            session.execute(
                sa.update(models.channel_store_mappings)
                .where(models.channel_store_mappings.c.id == existing["id"])
                .values(
                    external_store_id=external_store_id.strip(),
                    is_active=is_active,
                    updated_at=now,
                )
            )
            mapping_id = existing["id"]
        else:
            mapping_id = str(uuid.uuid4())
            session.execute(
                models.channel_store_mappings.insert().values(
                    id=mapping_id,
                    organization_id=organization_id,
                    branch_id=branch_id,
                    provider=provider,
                    external_store_id=external_store_id.strip(),
                    is_active=is_active,
                    created_at=now,
                    updated_at=now,
                )
            )

        session.commit()
        return {
            "id": mapping_id,
            "branch_id": branch_id,
            "external_store_id": external_store_id,
            "is_active": is_active,
        }

    def delete_store_mapping(self, session: Session, organization_id: str, mapping_id: str) -> bool:
        session.execute(
            sa.delete(models.channel_store_mappings).where(
                models.channel_store_mappings.c.id == mapping_id,
                models.channel_store_mappings.c.organization_id == organization_id,
            )
        )
        session.commit()
        return True

    def enqueue_uber_availability_sync(
        self,
        session: Session,
        organization_id: str,
        product_id: str,
        is_available: bool,
        branch_id: str | None = None,
    ) -> int:
        """Store the latest desired Uber state; delivery remains unconfirmed."""
        now = datetime.now(timezone.utc)
        rows = session.execute(
            sa.select(
                models.channel_store_mappings.c.branch_id,
                models.channel_store_mappings.c.external_store_id,
                models.channel_product_mappings.c.external_item_id,
            )
            .join(
                models.channel_product_mappings,
                sa.and_(
                    models.channel_product_mappings.c.organization_id
                    == models.channel_store_mappings.c.organization_id,
                    models.channel_product_mappings.c.provider == "UBER_EATS",
                    models.channel_product_mappings.c.product_id == product_id,
                    models.channel_product_mappings.c.is_active.is_(True),
                ),
            )
            .where(
                models.channel_store_mappings.c.organization_id == organization_id,
                models.channel_store_mappings.c.provider == "UBER_EATS",
                models.channel_store_mappings.c.is_active.is_(True),
                *([models.channel_store_mappings.c.branch_id == branch_id] if branch_id else []),
            )
        ).all()
        jobs = models.channel_availability_sync_jobs
        for mapped_branch_id, store_id, item_id in rows:
            target = sa.and_(
                jobs.c.organization_id == organization_id,
                jobs.c.provider == "UBER_EATS",
                jobs.c.external_store_id == store_id,
                jobs.c.external_item_id == item_id,
            )
            existing = session.scalar(sa.select(jobs.c.id).where(target))
            values: dict[str, Any] = dict(
                is_available=is_available,
                status="PENDING",
                attempts=0,
                next_attempt_at=now,
                last_error=None,
                confirmed_at=None,
                lease_token=None,
                lease_expires_at=None,
                updated_at=now,
            )
            if existing:
                session.execute(
                    jobs.update()
                    .where(jobs.c.id == existing)
                    .values(desired_version=jobs.c.desired_version + 1, **values)
                )
            else:
                session.execute(
                    jobs.insert().values(
                        id=str(uuid.uuid4()),
                        organization_id=organization_id,
                        branch_id=mapped_branch_id,
                        provider="UBER_EATS",
                        external_store_id=store_id,
                        external_item_id=item_id,
                        product_id=product_id,
                        desired_version=1,
                        created_at=now,
                        **values,
                    )
                )
        return len(rows)

    def claim_due_uber_availability_sync(self, session: Session) -> dict[str, Any] | None:
        """CAS-claim one job and commit before network I/O."""
        now = datetime.now(timezone.utc)
        jobs = models.channel_availability_sync_jobs
        due = sa.or_(
            sa.and_(jobs.c.status.in_(("PENDING", "RETRY")), jobs.c.next_attempt_at <= now),
            sa.and_(jobs.c.status == "CLAIMED", jobs.c.lease_expires_at <= now),
        )
        candidate = (
            session.execute(
                sa.select(jobs)
                .where(jobs.c.provider == "UBER_EATS", due)
                .order_by(jobs.c.next_attempt_at, jobs.c.created_at)
                .limit(1)
            )
            .mappings()
            .first()
        )
        if not candidate:
            return None
        token = str(uuid.uuid4())
        claimed = session.execute(
            jobs.update()
            .where(
                jobs.c.id == candidate["id"],
                jobs.c.desired_version == candidate["desired_version"],
                due,
            )
            .values(
                status="CLAIMED",
                lease_token=token,
                lease_expires_at=now + timedelta(minutes=2),
                updated_at=now,
            )
        )
        if cast(sa.engine.CursorResult[Any], claimed).rowcount != 1:
            session.rollback()
            return None
        config = self.get_config(session, str(candidate["organization_id"]), "UBER_EATS")
        organization = (
            session.execute(
                sa.select(
                    models.organizations.c.status,
                    models.organizations.c.subscription_status,
                    models.organizations.c.trial_ends_at,
                ).where(models.organizations.c.id == candidate["organization_id"])
            )
            .mappings()
            .first()
        )
        session.commit()
        job = dict(candidate)
        job.update(
            lease_token=token,
            config=config,
            organization=dict(organization) if organization else None,
        )
        return job

    @staticmethod
    def _outbound_permitted(organization: dict[str, Any] | None, now: datetime) -> bool:
        if not organization or organization.get("status") != "active":
            return False
        if organization.get("subscription_status") == "active":
            return True
        trial_end = organization.get("trial_ends_at")
        return bool(
            organization.get("subscription_status") == "trialing"
            and isinstance(trial_end, datetime)
            and now
            < (trial_end.replace(tzinfo=timezone.utc) if trial_end.tzinfo is None else trial_end)
        )

    def finish_uber_availability_sync(
        self, session: Session, job: dict[str, Any], error: Exception | None
    ) -> str:
        """Only the current lease/version can report provider confirmation."""
        now = datetime.now(timezone.utc)
        attempts = int(job["attempts"]) + 1
        if not bool((job.get("config") or {}).get("is_enabled")) or not self._outbound_permitted(
            job.get("organization"), now
        ):
            status, message, due = "FAILED", "uber_outbound_disabled", now
        elif error is None:
            status, message, due = "CONFIRMED", None, now
        elif isinstance(error, UberAvailabilityPermanentError):
            status, message, due = "FAILED", str(error)[:500], now
        else:
            status, message, due = (
                "RETRY",
                str(error)[:500],
                now + timedelta(seconds=min(300, 2 ** min(attempts, 8))),
            )
        jobs = models.channel_availability_sync_jobs
        values: dict[str, Any] = dict(
            status=status,
            attempts=attempts,
            last_error=message,
            next_attempt_at=due,
            lease_token=None,
            lease_expires_at=None,
            updated_at=now,
        )
        if status == "CONFIRMED":
            values["confirmed_at"] = now
        result = session.execute(
            jobs.update()
            .where(
                jobs.c.id == job["id"],
                jobs.c.status == "CLAIMED",
                jobs.c.lease_token == job["lease_token"],
                jobs.c.desired_version == job["desired_version"],
            )
            .values(**values)
        )
        if cast(sa.engine.CursorResult[Any], result).rowcount == 1:
            session.commit()
            return status
        # A stale HTTP request may reach Uber after a newer command.  Force a
        # later dispatch of the current desired state even if it was already
        # confirmed by another lease.
        reconciled = session.execute(
            jobs.update()
            .where(jobs.c.id == job["id"], jobs.c.desired_version > job["desired_version"])
            .values(
                desired_version=jobs.c.desired_version + 1,
                status="PENDING",
                attempts=0,
                next_attempt_at=now,
                last_error="uber_availability_superseded_reconcile",
                confirmed_at=None,
                lease_token=None,
                lease_expires_at=None,
                updated_at=now,
            )
        )
        session.commit()
        return (
            "RECONCILE"
            if cast(sa.engine.CursorResult[Any], reconciled).rowcount == 1
            else "SUPERSEDED"
        )

    def dispatch_due_uber_availability_syncs(
        self, session_factory: Callable[[], Session], limit: int = 100
    ) -> list[dict[str, Any]]:
        """Perform bounded network dispatch outside the database claim transaction."""
        results: list[dict[str, Any]] = []
        for _ in range(limit):
            with session_factory() as claim_session:
                job = self.claim_due_uber_availability_sync(claim_session)
            if not job:
                break
            config = job.get("config") or {}
            organization = job.get("organization")
            error: Exception | None = None
            if bool(config.get("is_enabled")) and self._outbound_permitted(
                organization, datetime.now(timezone.utc)
            ):
                try:
                    self.uber_adapter.update_item_availability(
                        client_id=str(config.get("client_id") or ""),
                        client_secret=str(config.get("client_secret") or ""),
                        store_id=str(job["external_store_id"]),
                        item_id=str(job["external_item_id"]),
                        is_available=bool(job["is_available"]),
                    )
                except Exception as exc:
                    error = exc
            with session_factory() as finish_session:
                status = self.finish_uber_availability_sync(finish_session, job, error)
            results.append({"id": job["id"], "status": status})
        return results

    def list_webhook_logs(
        self, session: Session, organization_id: str, provider: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        query = (
            sa.select(models.integration_webhook_logs)
            .where(
                models.integration_webhook_logs.c.organization_id == organization_id,
                models.integration_webhook_logs.c.provider == provider,
            )
            .order_by(models.integration_webhook_logs.c.created_at.desc())
            .limit(limit)
        )
        return [dict(r) for r in session.execute(query).mappings().all()]

    def log_webhook(
        self,
        session: Session,
        organization_id: str,
        provider: str,
        event_type: str,
        event_id: str | None,
        signature: str | None,
        payload_raw: dict[str, Any],
        status: str,
        error_message: str | None = None,
    ) -> str:
        now = datetime.now(timezone.utc)
        log_id = str(uuid.uuid4())
        session.execute(
            models.integration_webhook_logs.insert().values(
                id=log_id,
                organization_id=organization_id,
                provider=provider,
                event_type=event_type,
                event_id=event_id,
                signature=signature,
                payload_raw=payload_raw,
                status=status,
                error_message=error_message,
                processed_at=now if status == "processed" else None,
                created_at=now,
            )
        )
        session.commit()
        return log_id

    @staticmethod
    def _webhook_payload_hash(payload_raw: dict[str, Any]) -> str:
        import hashlib
        import json

        canonical = json.dumps(
            payload_raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def claim_webhook(
        self,
        session: Session,
        organization_id: str,
        provider: str,
        event_id: str | None,
        payload_raw: dict[str, Any],
    ) -> dict[str, Any]:
        """Atomically lease a webhook delivery without treating a duplicate as success.

        The API must only process a result with ``claimed`` true. A processed
        duplicate is safe to acknowledge, while a live processing lease asks
        the provider to retry after its expiry.
        """
        payload_hash = self._webhook_payload_hash(payload_raw)
        durable_event_id = str(event_id or f"sha256:{payload_hash}")
        now = datetime.now(timezone.utc)
        lease_token = str(uuid.uuid4())
        lease_until = now + timedelta(minutes=2)
        inbox = models.integration_webhook_inbox
        inbox_id = str(uuid.uuid4())
        try:
            session.execute(
                inbox.insert().values(
                    id=inbox_id,
                    organization_id=organization_id,
                    provider=provider,
                    event_id=durable_event_id,
                    payload_hash=payload_hash,
                    status="processing",
                    attempts=1,
                    lease_token=lease_token,
                    lease_expires_at=lease_until,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()
            return {
                "claimed": True,
                "id": inbox_id,
                "event_id": durable_event_id,
                "lease_token": lease_token,
            }
        except sa.exc.IntegrityError:
            session.rollback()
        existing = (
            session.execute(
                sa.select(inbox).where(
                    inbox.c.organization_id == organization_id,
                    inbox.c.provider == provider,
                    inbox.c.event_id == durable_event_id,
                )
            )
            .mappings()
            .one()
        )
        if existing["payload_hash"] != payload_hash:
            raise ValueError("webhook_event_payload_conflict")
        if existing["status"] == "processed":
            return {"claimed": False, "replay": True, "id": existing["id"]}
        reclaimable = sa.or_(
            inbox.c.status == "error",
            sa.and_(inbox.c.status == "processing", inbox.c.lease_expires_at <= now),
        )
        claimed = session.execute(
            inbox.update()
            .where(
                inbox.c.id == existing["id"],
                reclaimable,
            )
            .values(
                status="processing",
                attempts=inbox.c.attempts + 1,
                last_error=None,
                lease_token=lease_token,
                lease_expires_at=lease_until,
                updated_at=now,
            )
        )
        if cast(sa.engine.CursorResult[Any], claimed).rowcount != 1:
            session.rollback()
            return {"claimed": False, "in_progress": True, "id": existing["id"]}
        session.commit()
        return {
            "claimed": True,
            "id": existing["id"],
            "event_id": durable_event_id,
            "lease_token": lease_token,
        }

    def finish_webhook(
        self,
        session: Session,
        inbox_id: str,
        lease_token: str,
        status: str,
        error_message: str | None = None,
    ) -> bool:
        if status not in {"processed", "error"}:
            raise ValueError("webhook_inbox_status_invalid")
        now = datetime.now(timezone.utc)
        result = session.execute(
            models.integration_webhook_inbox.update()
            .where(
                models.integration_webhook_inbox.c.id == inbox_id,
                models.integration_webhook_inbox.c.status == "processing",
                models.integration_webhook_inbox.c.lease_token == lease_token,
            )
            .values(
                status=status,
                last_error=error_message,
                processed_at=now if status == "processed" else None,
                lease_token=None,
                lease_expires_at=None,
                updated_at=now,
            )
        )
        session.commit()
        return cast(sa.engine.CursorResult[Any], result).rowcount == 1

    def process_webhook_order(
        self,
        session: Session,
        organization_id: str,
        provider: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        target = self.resolve_webhook_target(session, provider, payload)
        if target.organization_id != organization_id:
            raise ValueError("webhook_tenant_mismatch")
        adapter = self.get_adapter(provider)
        config = self.get_config(session, organization_id, provider)

        # Get product mappings
        product_mappings_rows = session.execute(
            sa.select(
                models.channel_product_mappings.c.external_item_id,
                models.channel_product_mappings.c.product_id,
            ).where(
                models.channel_product_mappings.c.organization_id == organization_id,
                models.channel_product_mappings.c.provider == provider,
                models.channel_product_mappings.c.is_active.is_(True),
            )
        ).all()
        product_mappings = {r[0]: r[1] for r in product_mappings_rows}

        # Only products in the resolved tenant's catalog may be used.  A
        # missing mapping is a recoverable webhook error, never a cross-tenant
        # fallback to an arbitrary product.
        products_query = (
            sa.select(
                models.products.c.id,
                models.products.c.name,
                models.products.c.category_id,
                models.products.c.station,
            )
            .where(
                models.products.c.organization_id == organization_id,
                models.products.c.status == "active",
            )
            .limit(10)
        )
        default_products = [dict(r) for r in session.execute(products_query).mappings().all()]
        if not default_products:
            raise ValueError("webhook_catalog_not_configured")

        # Normalize order
        normalized: NormalizedOrder = adapter.normalize_order(
            payload, product_mappings, default_products
        )

        # Idempotency check: if order with this external_order_id already exists
        existing_meta = (
            session.execute(
                sa.select(models.channel_orders_meta).where(
                    models.channel_orders_meta.c.organization_id == organization_id,
                    models.channel_orders_meta.c.provider == provider,
                    models.channel_orders_meta.c.external_order_id == normalized.external_order_id,
                )
            )
            .mappings()
            .first()
        )

        if existing_meta:
            return {
                "status": "already_processed",
                "order_id": existing_meta["order_id"],
                "external_order_id": normalized.external_order_id,
            }

        target_branch_id = target.branch_id

        # Create order record in orders table
        now = datetime.now(timezone.utc)
        order_id = str(uuid.uuid4())
        short_suffix = uuid.uuid4().hex[:4].upper()
        daily_folio = f"UBER-{normalized.display_code.replace('#', '')}-{short_suffix}"

        # Category for line items
        cat_id = default_products[0]["category_id"] if default_products else None
        cat_name = "Marketplace"
        if cat_id:
            cat_row = session.execute(
                sa.select(models.product_categories.c.name).where(
                    models.product_categories.c.id == cat_id
                )
            ).scalar_one_or_none()
            if cat_row:
                cat_name = str(cat_row)
        if not cat_id:
            any_cat = session.execute(
                sa.select(models.product_categories.c.id, models.product_categories.c.name)
                .where(models.product_categories.c.organization_id == organization_id)
                .limit(1)
            ).first()
            if any_cat:
                cat_id = str(any_cat[0])
                cat_name = str(any_cat[1])
            else:
                cat_id = "00000000-0000-0000-0000-000000000001"
                cat_name = "General"

        order_status = "ACCEPTED" if (config and config.get("auto_accept")) else "PENDING"

        session.execute(
            models.orders.insert().values(
                id=order_id,
                organization_id=organization_id,
                branch_id=target_branch_id,
                cash_shift_id=None,
                public_order_intent_id=None,
                public_order_intent_status=None,
                customer_id=None,
                customer_snapshot={
                    "name": normalized.customer_name,
                    "phone": normalized.customer_phone or "",
                },
                delivery_address_snapshot={
                    "notes": normalized.delivery_notes or "",
                    "channel": provider,
                },
                folio=daily_folio,
                channel=provider,
                status=order_status,
                total_cents=normalized.total_cents,
                currency=normalized.currency,
                owner_name=normalized.customer_name,
                order_type="delivery",
                payment_method_intent="marketplace_uber",
                version=1,
                created_at=now,
                accepted_at=now if order_status == "ACCEPTED" else None,
            )
        )

        # Insert lines
        for line in normalized.items:
            line_id = str(uuid.uuid4())
            if not line.product_id:
                raise ValueError("webhook_product_not_mapped")
            prod_id = line.product_id
            session.execute(
                models.order_lines.insert().values(
                    id=line_id,
                    order_id=order_id,
                    product_id=prod_id,
                    product_name=line.product_name,
                    quantity=line.quantity,
                    unit_price_cents=line.unit_price_cents,
                    line_total_cents=line.line_total_cents,
                    station="kitchen",
                    selected_modifiers=line.selected_modifiers,
                    modifier_total_cents=0,
                    line_notes=line.special_instructions,
                    status="active",
                    revision=1,
                    family_id_snapshot=cat_id,
                    family_name_snapshot=cat_name,
                    family_snapshot_source="captured",
                    created_at=now,
                )
            )

        # Insert channel_orders_meta
        session.execute(
            models.channel_orders_meta.insert().values(
                id=str(uuid.uuid4()),
                organization_id=organization_id,
                order_id=order_id,
                provider=provider,
                external_order_id=normalized.external_order_id,
                display_code=normalized.display_code,
                customer_name=normalized.customer_name,
                driver_name=None,
                driver_phone=None,
                external_status="ACCEPTED" if order_status == "ACCEPTED" else "CREATED",
                estimated_ready_at=None,
                raw_payload=payload,
                created_at=now,
                updated_at=now,
            )
        )

        session.commit()
        return {
            "status": "created",
            "order_id": order_id,
            "folio": daily_folio,
            "display_code": normalized.display_code,
            "branch_id": target_branch_id,
            "order_status": order_status,
        }

    def list_pos_orders(
        self,
        session: Session,
        branch_id: str,
        provider: str = "UBER_EATS",
        status_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        query = (
            sa.select(
                models.orders.c.id,
                models.orders.c.folio,
                models.orders.c.channel,
                models.orders.c.status,
                models.orders.c.total_cents,
                models.orders.c.currency,
                models.orders.c.created_at,
                models.orders.c.accepted_at,
                models.orders.c.customer_snapshot,
                models.orders.c.delivery_address_snapshot,
                models.channel_orders_meta.c.external_order_id,
                models.channel_orders_meta.c.display_code,
                models.channel_orders_meta.c.customer_name,
                models.channel_orders_meta.c.driver_name,
                models.channel_orders_meta.c.driver_phone,
                models.channel_orders_meta.c.external_status,
                models.channel_orders_meta.c.estimated_ready_at,
            )
            .join(
                models.channel_orders_meta,
                models.orders.c.id == models.channel_orders_meta.c.order_id,
            )
            .where(
                models.orders.c.branch_id == branch_id,
                models.orders.c.channel == provider,
            )
            .order_by(models.orders.c.created_at.desc())
            .limit(100)
        )

        rows = session.execute(query).mappings().all()
        results: list[dict[str, Any]] = []

        for row in rows:
            # Fetch lines for each order
            lines_rows = (
                session.execute(
                    sa.select(
                        models.order_lines.c.id,
                        models.order_lines.c.product_name,
                        models.order_lines.c.quantity,
                        models.order_lines.c.unit_price_cents,
                        models.order_lines.c.line_total_cents,
                        models.order_lines.c.line_notes,
                        models.order_lines.c.selected_modifiers,
                    )
                    .where(models.order_lines.c.order_id == row["id"])
                    .order_by(models.order_lines.c.created_at.asc())
                )
                .mappings()
                .all()
            )

            order_data = dict(row)
            order_data["lines"] = [dict(item_line) for item_line in lines_rows]
            results.append(order_data)

        return results

    def update_order_status(
        self,
        session: Session,
        order_id: str,
        new_status: str,
        actor_id: str | None = None,
        *,
        organization_id: str,
        branch_id: str,
        provider: str,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        order = (
            session.execute(
                sa.select(models.orders).where(
                    models.orders.c.id == order_id,
                    models.orders.c.organization_id == organization_id,
                    models.orders.c.branch_id == branch_id,
                    models.orders.c.channel == provider,
                )
            )
            .mappings()
            .first()
        )

        if not order:
            raise ValueError(f"Orden no encontrada: {order_id}")

        session.execute(
            sa.update(models.orders)
            .where(
                models.orders.c.id == order_id,
                models.orders.c.organization_id == organization_id,
                models.orders.c.branch_id == branch_id,
                models.orders.c.channel == provider,
            )
            .values(
                status=new_status,
                accepted_at=now if new_status == "ACCEPTED" else order["accepted_at"],
            )
        )

        session.execute(
            sa.update(models.channel_orders_meta)
            .where(
                models.channel_orders_meta.c.order_id == order_id,
                models.channel_orders_meta.c.organization_id == organization_id,
                models.channel_orders_meta.c.provider == provider,
            )
            .values(external_status=new_status, updated_at=now)
        )

        session.commit()
        return {"order_id": order_id, "status": new_status, "updated_at": now.isoformat()}


channel_service = ChannelIntegrationService()
