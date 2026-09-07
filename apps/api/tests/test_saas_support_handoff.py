# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-test-saas-support-handoff-synthetic-v1
"""A POS handoff issued by support remains bound to the live issuer."""

from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.auth import verify_session_token
from restaurant_os.config import get_settings
from test_saas_superadmin import _client_with_db, _login_superadmin


def _grant_pos_operation(client, user_id: str) -> None:
    with client._test_session_factory() as session:
        role_id = session.scalar(
            sa.select(models.user_roles.c.role_id).where(
                models.user_roles.c.user_id == user_id
            )
        )
        permission_id = session.scalar(
            sa.select(models.permissions.c.id).where(
                models.permissions.c.code == "pos.operate"
            )
        )
        assert role_id
        if not permission_id:
            permission_id = str(uuid4())
            session.execute(
                models.permissions.insert().values(
                    id=permission_id,
                    code="pos.operate",
                    description="Operación POS para handoff de soporte sintético",
                    created_at=datetime.now(timezone.utc),
                )
            )
        session.execute(
            models.role_permissions.insert().values(
                role_id=role_id, permission_id=permission_id
            )
        )
        session.commit()


def test_revoked_support_issuer_cannot_exchange_pos_handoff() -> None:
    client = _client_with_db()
    superadmin_headers = _login_superadmin(client)
    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Handoff Support QA",
            "owner_name": "Handoff Owner",
            "email": "handoff-owner@example.test",
            "password": "synthetic-handoff-password",
            "business_type": "general",
        },
    )
    assert signup.status_code == 201, signup.text
    tenant = signup.json()
    _grant_pos_operation(client, tenant["user"]["id"])
    impersonation = client.post(
        f"/api/v1/superadmin/tenants/{tenant['organization']['id']}/impersonate",
        headers=superadmin_headers,
    )
    assert impersonation.status_code == 200, impersonation.text
    support_headers = {"Authorization": f"Bearer {impersonation.json()['token']}"}

    issued = client.post("/api/v1/auth/pos-handoffs", headers=support_headers)
    assert issued.status_code == 200, issued.text

    with client._test_session_factory() as session:
        issuer_id = session.scalar(
            sa.select(models.users.c.id).where(models.users.c.is_superadmin.is_(True))
        )
        assert issuer_id
        issued_audit = session.execute(
            sa.select(models.audit_events).where(
                models.audit_events.c.action == "auth.pos_handoff_issued"
            )
        ).mappings().one()
        session.execute(
            models.users.update()
            .where(models.users.c.id == issuer_id)
            .values(is_superadmin=False)
        )
        session.commit()

    rejected = client.post(
        "/api/v1/auth/pos-handoffs/exchange",
        json={"handoff_code": issued.json()["handoff_code"]},
    )
    assert rejected.status_code == 403, rejected.text
    assert rejected.json()["detail"]["code"] == "superadmin_forbidden"
    with client._test_session_factory() as session:
        rejection_audit = session.execute(
            sa.select(models.audit_events).where(
                models.audit_events.c.action == "auth.pos_handoff_rejected"
            )
        ).mappings().one()
        assert issued_audit["actor_user_id"] == issuer_id
        assert rejection_audit["actor_user_id"] == issuer_id
        assert issued_audit["correlation_id"]
        assert rejection_audit["correlation_id"] == issued_audit["correlation_id"]


def test_support_handoff_exchange_preserves_support_claims() -> None:
    client = _client_with_db()
    superadmin_headers = _login_superadmin(client)
    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Handoff Claims QA",
            "owner_name": "Claims Owner",
            "email": "handoff-claims@example.test",
            "password": "synthetic-handoff-claims-password",
            "business_type": "general",
        },
    )
    assert signup.status_code == 201, signup.text
    tenant = signup.json()
    _grant_pos_operation(client, tenant["user"]["id"])
    impersonation = client.post(
        f"/api/v1/superadmin/tenants/{tenant['organization']['id']}/impersonate",
        headers=superadmin_headers,
    )
    assert impersonation.status_code == 200, impersonation.text
    issued = client.post(
        "/api/v1/auth/pos-handoffs",
        headers={"Authorization": f"Bearer {impersonation.json()['token']}"},
    )
    assert issued.status_code == 200, issued.text
    with client._test_session_factory() as session:
        issued_audit = session.execute(
            sa.select(models.audit_events).where(
                models.audit_events.c.action == "auth.pos_handoff_issued"
            )
        ).mappings().one()

    exchanged = client.post(
        "/api/v1/auth/pos-handoffs/exchange",
        json={"handoff_code": issued.json()["handoff_code"]},
    )
    assert exchanged.status_code == 200, exchanged.text
    claims = verify_session_token(exchanged.json()["token"], get_settings().secret_key)
    assert claims
    assert claims["sub"] == tenant["user"]["id"]
    assert claims["impersonated_by"]
    assert claims["target_organization_id"] == tenant["organization"]["id"]
    assert claims["support_correlation_id"]
    with client._test_session_factory() as session:
        consumed_audit = session.execute(
            sa.select(models.audit_events).where(
                models.audit_events.c.action == "auth.pos_handoff_consumed"
            )
        ).mappings().one()
        assert consumed_audit["actor_user_id"] == issued_audit["actor_user_id"]
        assert consumed_audit["correlation_id"] == issued_audit["correlation_id"]
