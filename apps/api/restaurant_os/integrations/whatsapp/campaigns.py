"""Campaign and Re-engagement service for Meta WhatsApp Business Platform."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from restaurant_os import models
from restaurant_os.customer_ai import (
    generate_churn_recovery_message,
    get_crm_segments_and_churn_risk,
)

from .adapter import send_whatsapp_text_message

logger = logging.getLogger(__name__)

# Registry of opted-out phone numbers for commercial marketing communications
_COMMERCIAL_OPT_OUT_PHONES: set[str] = set()


def normalize_phone(phone: str) -> str:
    """Strip spaces, hyphens, and leading plus from phone numbers."""
    cleaned = "".join(ch for ch in str(phone or "").strip() if ch.isdigit())
    return cleaned


class WhatsAppCampaignService:
    """Dispatches targeted marketing/re-engagement campaigns with opt-out safeguards."""

    def __init__(
        self,
        session: Session,
        organization_id: str | None = None,
        branch_id: str | None = None,
    ) -> None:
        self.session = session
        self.organization_id = organization_id or ""
        self.branch_id = branch_id or ""

    def record_opt_out(self, phone: str, reason: str = "user_requested") -> bool:
        """Mark phone as opted-out of marketing communications."""
        norm = normalize_phone(phone)
        if not norm:
            return False
        _COMMERCIAL_OPT_OUT_PHONES.add(norm)

        # Update customer_phones table in database if present
        try:
            now = datetime.now(timezone.utc)
            self.session.execute(
                sa.update(models.customer_phones)
                .where(
                    sa.or_(
                        models.customer_phones.c.normalized_number == norm,
                        models.customer_phones.c.captured_number == phone,
                    )
                )
                .values(whatsapp_enabled=False, updated_at=now)
            )
            self.session.commit()
        except Exception as exc:
            logger.warning("Error updating customer_phone opt-out in db: %s", exc)

        logger.info("WhatsApp marketing opt-out recorded for phone=%s reason=%s", norm, reason)
        return True

    def is_opted_out(self, phone: str) -> bool:
        """Check if phone number has opted out of marketing campaigns."""
        norm = normalize_phone(phone)
        if not norm:
            return True
        if norm in _COMMERCIAL_OPT_OUT_PHONES:
            return True

        # Check database flag
        row = (
            self.session.execute(
                sa.select(models.customer_phones.c.whatsapp_enabled).where(
                    sa.or_(
                        models.customer_phones.c.normalized_number == norm,
                        models.customer_phones.c.captured_number == phone,
                    )
                )
            )
            .first()
        )
        if row and row[0] is False:
            _COMMERCIAL_OPT_OUT_PHONES.add(norm)
            return True

        return False

    def get_eligible_campaign_targets(
        self, segment: str, include_opted_out: bool = False
    ) -> list[dict[str, Any]]:
        """Retrieve eligible customers for the targeted marketing segment."""
        normalized_segment = segment.strip().lower()

        # Resolve CRM segments
        crm_data = get_crm_segments_and_churn_risk(
            self.session,
            organization_id=self.organization_id,
            branch_id=self.branch_id or None,
        )

        raw_candidates: list[dict[str, Any]] = []
        if normalized_segment in {"churn_risk", "churn", "at_risk"}:
            raw_candidates = crm_data.get("churn_risk_customers", []) or crm_data.get(
                "churn_risk", []
            )
        elif normalized_segment in {"vip", "vips"}:
            raw_candidates = crm_data.get("vip_customers", []) or crm_data.get("vips", [])
        elif normalized_segment in {"new", "new_customers"}:
            raw_candidates = crm_data.get("new_customers", [])
        else:
            raw_candidates = (
                crm_data.get("churn_risk", [])
                + crm_data.get("vips", [])
                + crm_data.get("new_customers", [])
            )

        targets: list[dict[str, Any]] = []
        for candidate in raw_candidates:
            cid = candidate.get("id")
            phone = str(candidate.get("phone") or "").strip()

            # If candidate summary lacks phone, query customer_phones
            if not phone and cid:
                phone_row = (
                    self.session.execute(
                        sa.select(models.customer_phones.c.normalized_number).where(
                            models.customer_phones.c.customer_id == cid,
                        )
                    )
                    .scalars()
                    .first()
                )
                if phone_row:
                    phone = str(phone_row).strip()

            if not phone:
                continue

            # Exclude opted-out phones unless included for metrics
            if not include_opted_out and self.is_opted_out(phone):
                continue

            # Query favorite product from past orders
            fav_product = "Tacos al Pastor"
            if cid:
                fav_row = (
                    self.session.execute(
                        sa.select(
                            models.order_lines.c.product_name,
                            sa.func.count(models.order_lines.c.id).label("cnt"),
                        )
                        .select_from(
                            models.order_lines.join(
                                models.orders,
                                models.order_lines.c.order_id == models.orders.c.id,
                            )
                        )
                        .where(
                            models.orders.c.customer_id == cid,
                            models.orders.c.status != "cancelled",
                        )
                        .group_by(models.order_lines.c.product_name)
                        .order_by(sa.desc("cnt"))
                        .limit(1)
                    )
                    .mappings()
                    .first()
                )
                if fav_row:
                    fav_product = fav_row["product_name"]

            targets.append(
                {
                    "customer_id": cid,
                    "name": candidate.get("name", "Cliente"),
                    "phone": phone,
                    "favorite_product": fav_product,
                    "total_orders": candidate.get("total_orders", 0),
                    "days_inactive": candidate.get("days_inactive", 0),
                }
            )

        return targets

    def _resolve_branch_info(self) -> tuple[str, str]:
        """Return (branch_name, storefront_url)."""
        branch_name = "Restaurante"
        slug = self.branch_id
        if self.branch_id:
            branch = (
                self.session.execute(
                    sa.select(models.branches).where(models.branches.c.id == self.branch_id)
                )
                .mappings()
                .first()
            )
            if branch:
                branch_name = branch["name"]
                slug = branch.get("slug") or self.branch_id
        storefront_url = f"https://mimenu.com/{slug}"
        return branch_name, storefront_url

    def preview_campaign(
        self,
        segment: str,
        discount_code: str = "VUELVE10",
        custom_message: str | None = None,
    ) -> dict[str, Any]:
        """Generate a preview of the marketing campaign with sample copy and recipient metrics."""
        targets = self.get_eligible_campaign_targets(segment)
        branch_name, storefront_url = self._resolve_branch_info()

        sample_target = targets[0] if targets else None
        sample_name = sample_target["name"] if sample_target else "Carlos"
        sample_fav = sample_target["favorite_product"] if sample_target else "Tacos al Pastor"

        if custom_message:
            body = (
                custom_message.replace("{name}", sample_name)
                .replace("{favorite_product}", sample_fav)
                .replace("{discount_code}", discount_code)
                .replace("{branch_name}", branch_name)
            )
        else:
            body = generate_churn_recovery_message(
                customer_name=sample_name,
                favorite_product_name=sample_fav,
                discount_code=discount_code,
                restaurant_name=branch_name,
            )

        opt_out_footer = "\n\nPara no recibir más promociones, responde STOP o BAJA."
        store_link = f"\n\nOrdena aquí: 👉 {storefront_url}"
        full_sample_message = f"{body}{store_link}{opt_out_footer}"

        return {
            "segment": segment,
            "total_eligible": len(targets),
            "discount_code": discount_code,
            "sample_message": full_sample_message,
            "sample_recipient": sample_name,
            "storefront_url": storefront_url,
        }

    def dispatch_campaign(
        self,
        segment: str,
        discount_code: str = "VUELVE10",
        custom_message: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch marketing campaign to all eligible customers in the segment."""
        # 1. Check WhatsApp channel integration
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
            return {
                "status": "skipped",
                "reason": "whatsapp_not_connected",
                "total_targets": 0,
                "sent_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
            }

        # 2. Check branch store mapping
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
        phone_number_id = str(mapping["external_store_id"]) if mapping else None
        if not phone_number_id:
            return {
                "status": "skipped",
                "reason": "whatsapp_not_connected",
                "total_targets": 0,
                "sent_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
            }

        branch_name, storefront_url = self._resolve_branch_info()
        opt_out_footer = "\n\nPara no recibir más promociones, responde STOP o BAJA."
        store_link = f"\n\nOrdena aquí: 👉 {storefront_url}"

        # 3. Retrieve targets (including opted out to count skipped metrics accurately)
        targets = self.get_eligible_campaign_targets(segment, include_opted_out=True)
        sent_count = 0
        skipped_count = 0
        failed_count = 0

        access_token = channel_config.get("client_secret")
        env = channel_config.get("environment", "sandbox")

        for target in targets:
            phone = target["phone"]
            if self.is_opted_out(phone):
                skipped_count += 1
                continue

            if custom_message:
                body = (
                    custom_message.replace("{name}", target["name"])
                    .replace("{favorite_product}", target["favorite_product"])
                    .replace("{discount_code}", discount_code)
                    .replace("{branch_name}", branch_name)
                )
            else:
                body = generate_churn_recovery_message(
                    customer_name=target["name"],
                    favorite_product_name=target["favorite_product"],
                    discount_code=discount_code,
                    restaurant_name=branch_name,
                )

            full_msg = f"{body}{store_link}{opt_out_footer}"
            try:
                send_whatsapp_text_message(
                    phone_number_id=phone_number_id,
                    to_phone=phone,
                    message_text=full_msg,
                    access_token=access_token,
                    environment=env,
                )
                sent_count += 1
            except Exception as e:
                logger.error("Error sending marketing WhatsApp to %s: %s", phone, e)
                failed_count += 1

        return {
            "status": "completed",
            "segment": segment,
            "discount_code": discount_code,
            "total_targets": len(targets),
            "sent_count": sent_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
        }
