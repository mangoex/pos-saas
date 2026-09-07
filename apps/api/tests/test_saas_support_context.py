# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-test-saas-support-context-synthetic-v1
"""Synthetic support sessions retain authority and audit attribution per request."""

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.superadmin.service import grant_tenant_administrative_activation
from test_saas_superadmin import _client_with_db, _login_superadmin


def _support_session():
    client = _client_with_db()
    admin_headers = _login_superadmin(client)
    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Support QA",
            "owner_name": "Owner QA",
            "email": "support-owner@example.test",
            "password": "synthetic-support-password",
            "business_type": "general",
        },
    )
    assert signup.status_code == 201, signup.text
    data = signup.json()
    impersonation = client.post(
        f"/api/v1/superadmin/tenants/{data['organization']['id']}/impersonate",
        headers=admin_headers,
    )
    assert impersonation.status_code == 200, impersonation.text
    return client, data, {"Authorization": f"Bearer {impersonation.json()['token']}"}


def test_support_action_records_real_effective_actor_and_tenant():
    client, data, headers = _support_session()
    response = client.put(
        "/api/v1/saas/onboarding",
        headers=headers,
        json={
            "step": "business",
            "business_name": "Support QA Updated",
            "branch_name": "QA Branch",
            "timezone": "America/Mexico_City",
        },
    )
    assert response.status_code == 200, response.text
    with client._test_session_factory() as session:
        events = (
            session.execute(
                sa.select(models.audit_events).where(
                    models.audit_events.c.action != "support.impersonation_issued",
                    models.audit_events.c.organization_id == data["organization"]["id"],
                )
            )
            .mappings()
            .all()
        )
        support_events = [
            event for event in events if event["payload"].get("effective_actor_user_id")
        ]
        assert len(support_events) >= 2
        assert {event["payload"]["effective_actor_user_id"] for event in support_events} == {
            data["user"]["id"]
        }
        assert len({event["correlation_id"] for event in support_events}) == 1
        assert support_events[0]["correlation_id"]
        assert all(event["actor_user_id"] != data["user"]["id"] for event in support_events)


def test_revoked_support_issuer_cannot_keep_using_issued_token():
    client, data, headers = _support_session()
    with client._test_session_factory() as session:
        session.execute(
            models.users.update()
            .where(models.users.c.is_superadmin.is_(True))
            .values(is_superadmin=False)
        )
        session.commit()
    response = client.get("/api/v1/catalog/products", headers=headers)
    assert response.status_code == 403, response.text
    own = client.get(
        "/api/v1/catalog/products", headers={"Authorization": f"Bearer {data['token']}"}
    )
    assert own.status_code == 200, own.text


def test_owner_permission_cannot_authorize_another_tenants_branch():
    import pytest
    from restaurant_os.operations import AuthorizationError, require_permission

    client, data, _headers = _support_session()
    other = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Other QA",
            "owner_name": "Other Owner",
            "email": "other-owner@example.test",
            "password": "synthetic-other-password",
            "business_type": "general",
        },
    )
    assert other.status_code == 201, other.text
    with client._test_session_factory() as session:
        with pytest.raises(AuthorizationError):
            require_permission(
                session, data["user"]["id"], "cash.shift.open", other.json()["branch"]["id"]
            )
        require_permission(session, data["user"]["id"], "cash.shift.open", data["branch"]["id"])
        require_permission(session, data["user"]["id"], "admin.manage")


def test_administrative_activation_audit_uses_real_support_actor():
    client, data, _headers = _support_session()
    correlation_id = "support-subscription-correlation"
    with client._test_session_factory() as session:
        real_actor_id = session.scalar(
            sa.select(models.users.c.id).where(models.users.c.is_superadmin.is_(True))
        )
        assert real_actor_id
        session.info["support_audit_context"] = {
            "real_actor_user_id": real_actor_id,
            "effective_actor_user_id": data["user"]["id"],
            "target_organization_id": data["organization"]["id"],
            "correlation_id": correlation_id,
        }
        grant_tenant_administrative_activation(
            session,
            data["organization"]["id"],
            "starter_349",
            "Concesión de soporte sintética",
            real_actor_id,
        )
        audit = session.execute(
            sa.select(models.audit_events).where(
                models.audit_events.c.action
                == "tenant.subscription.administratively_activated"
            )
        ).mappings().one()
        assert audit["actor_user_id"] == real_actor_id
        assert audit["correlation_id"] == correlation_id
        assert audit["payload"]["effective_actor_user_id"] == data["user"]["id"]
        assert audit["payload"]["target_organization_id"] == data["organization"]["id"]


@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "bEaReR"])
def test_support_revocation_applies_to_every_valid_bearer_scheme(scheme):
    client, data, headers = _support_session()
    headers["Authorization"] = scheme + " " + headers["Authorization"].split(" ", 1)[1]
    with client._test_session_factory() as session:
        session.execute(models.users.update().where(
            models.users.c.is_superadmin.is_(True)
        ).values(is_superadmin=False))
        session.commit()
    response = client.put("/api/v1/saas/onboarding", headers=headers, json={
        "step": "business", "business_name": "Unauthorized rename",
        "branch_name": "Changed", "timezone": "America/Mexico_City",
    })
    assert response.status_code == 403, response.text
    with client._test_session_factory() as session:
        name = session.scalar(sa.select(models.organizations.c.name).where(
            models.organizations.c.id == data["organization"]["id"]
        ))
        assert name == "Support QA"
