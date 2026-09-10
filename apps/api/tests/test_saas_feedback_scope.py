# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-recovery-test-saas-feedback-scope-synthetic-v1
"""Restaurant feedback is listed only inside the authenticated tenant."""

import uuid
from datetime import datetime, timezone

from restaurant_os import models
from restaurant_os.main import app
from restaurant_os.saas_onboarding import signup_tenant
from test_saas_cash_scope import _cash_scope_api_client


def _seed_feedback_order(session, tenant, key):
    now = datetime.now(timezone.utc)
    branch_id = tenant["branch"]["id"]
    organization_id = tenant["organization"]["id"]
    public_key = session.scalar(
        models.public_order_keys.select()
        .with_only_columns(models.public_order_keys.c.public_key)
        .where(models.public_order_keys.c.branch_id == branch_id)
    )
    reference = f"PI-FEEDBACK-{key}"
    phone = f"667123450{1 if key == 'A' else 2}"
    if not public_key:
        public_key = f"pk_feedback_{key.lower()}"
        session.execute(
            models.public_order_keys.insert().values(
                public_key=public_key,
                organization_id=organization_id,
                branch_id=branch_id,
                status="active",
                created_at=now,
            )
        )
    session.execute(
        models.public_order_intents.insert().values(
            id=str(uuid.uuid4()),
            organization_id=organization_id,
            branch_id=branch_id,
            public_key=public_key,
            public_reference=reference,
            correlation_id=str(uuid.uuid4()),
            status="PENDING_REVIEW",
            customer_snapshot={"name": key, "phone": phone},
            order_type="takeout",
            total_cents=0,
            currency="MXN",
            version=1,
            created_at=now,
        )
    )
    session.commit()
    return reference, phone


def test_feedback_admin_list_stays_in_own_organization_and_branch():
    client, factory = _cash_scope_api_client()
    try:
        with factory() as session:
            tenants = [
                signup_tenant(
                    session,
                    {
                        "business_name": f"Feedback {key}",
                        "owner_name": key,
                        "email": f"feedback-{key}@example.test",
                        "password": "synthetic-feedback-password",
                        "business_type": "blank",
                    },
                )
                for key in ("a", "b")
            ]
            feedback_identities = [
                _seed_feedback_order(session, tenant, key)
                for key, tenant in zip(("A", "B"), tenants, strict=True)
            ]
        for key, tenant, (reference, phone) in zip(
            ("A", "B"), tenants, feedback_identities, strict=True
        ):
            saved = client.post(
                "/api/v1/public/feedback",
                json={
                    "branch_id": tenant["branch"]["id"],
                    "rating": 5,
                    "customer_phone": phone,
                    "order_folio": reference,
                    "comment": f"comment-{key}",
                },
            )
            assert saved.status_code == 201, saved.text
        for key, tenant in zip(("A", "B"), tenants, strict=True):
            auth = {"Authorization": f"Bearer {tenant['token']}"}
            own = client.get("/api/v1/admin/feedbacks", headers=auth)
            assert own.status_code == 200, own.text
            assert [row["customer_name"] for row in own.json()] == [key]
            foreign = client.get(
                "/api/v1/admin/feedbacks",
                headers=auth,
                params={"branch_id": tenants[1 if key == "A" else 0]["branch"]["id"]},
            )
            assert foreign.status_code == 403, foreign.text
    finally:
        app.dependency_overrides.clear()
