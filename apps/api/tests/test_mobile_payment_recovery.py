# SEC001-SYNTHETIC-FIXTURE provenance=mobile-payment-recovery-20260928
"""The mobile retry contract returns the original receipt and one fulfillment effect."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import (
    AuthorizationError,
    BusinessError,
    create_local_order,
    fulfill_order,
    open_cash_shift,
    pay_order,
)
from restaurant_os.saas_onboarding import signup_tenant
from sqlalchemy.orm import Session


def test_mobile_recovery_preserves_receipt_tenant_and_single_effect(
    cash_scope_session, monkeypatch,
):
    session = cash_scope_session
    monkeypatch.setattr(
        "restaurant_os.integrations.whatsapp.notifications.WhatsAppNotificationService."
        "notify_order_status_change", lambda *args, **kwargs: None,
    )
    tenants = [signup_tenant(session, {
        "business_name": f"Recovery {suffix}", "owner_name": f"Owner {suffix}",
        "email": f"recovery-{suffix}@example.test", "password": "synthetic-recovery-password",
        "business_type": "taqueria",
    }) for suffix in ("a", "b")]
    owner = tenants[0]["user"]["id"]
    foreign_owner = tenants[1]["user"]["id"]
    branch = tenants[0]["branch"]["id"]
    org = tenants[0]["organization"]["id"]
    product = session.scalar(sa.select(models.products.c.id).where(
        models.products.c.organization_id == org,
    ))
    open_cash_shift(session, 0, branch_id=branch, actor_user_id=owner)
    order = create_local_order(session, [{"product_id": product, "quantity": 1}],
                               branch_id=branch, actor_user_id=owner)
    session.commit()
    key = "mobile-original-payment-command"

    def pay(current):
        return pay_order(current, order["id"], order["total_cents"], "cash", owner, "CAJA-01",
                         idempotency_key=key)

    if session.bind.dialect.name == "postgresql":
        barrier = Barrier(2)
        engine = session.bind

        def concurrent_payment():
            with Session(engine) as concurrent:
                barrier.wait(timeout=10)
                return pay(concurrent)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, retry = list(pool.map(lambda _: concurrent_payment(), range(2)))
    else:
        first, retry = pay(session), pay(session)
    assert first == retry
    assert first["status"] == "CONFIRMED"
    # The first response may be lost. Even after delivery, replay recovers that exact receipt.
    delivered = fulfill_order(session, order["id"], "deliver", "mobile-delivery-command", owner)
    assert fulfill_order(
        session, order["id"], "deliver", "mobile-delivery-command", owner,
    ) == delivered
    assert pay(session) == first
    with pytest.raises(BusinessError) as conflict:
        pay_order(session, order["id"], order["total_cents"], "card", owner, "CAJA-01",
                  idempotency_key=key)
    assert conflict.value.code == "payment_idempotency_conflict"
    session.rollback()
    with pytest.raises(AuthorizationError):
        pay_order(session, order["id"], order["total_cents"], "cash", foreign_owner, "CAJA-01",
                  idempotency_key=key)
    session.rollback()
    with pytest.raises(AuthorizationError):
        fulfill_order(session, order["id"], "deliver", "mobile-delivery-command", foreign_owner)
    session.rollback()
    for table in (models.payments, models.payment_commands, models.sales_operation_snapshots,
                  models.order_fulfillment_commands):
        assert session.scalar(sa.select(sa.func.count()).select_from(table).where(
            table.c.order_id == order["id"],
        )) == 1
    for event in ("PAYMENT_CONFIRMED", "DELIVERED"):
        assert session.scalar(sa.select(sa.func.count()).select_from(models.order_events).where(
            models.order_events.c.order_id == order["id"],
            models.order_events.c.event_type == event,
        )) == 1
