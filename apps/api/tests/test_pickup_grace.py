# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-pickup-grace-v1
from typing import Any

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import (
    ORGANIZATION_ID,
    BusinessError,
    list_public_branches,
    update_branch,
)
from restaurant_os.platform_data import list_branches
from test_dine_in_configuration import session as session  # shared isolated SQLite fixture
from test_platform_api import ADMIN_USER_ID, BRANCH_ID


def test_roundtrip_omit_clear_and_audit(session: Any) -> None:
    updated = update_branch(
        session, BRANCH_ID, actor_user_id=ADMIN_USER_ID, extra_payload={"pickup_grace_minutes": 30}
    )
    assert updated["pickup_grace_minutes"] == 30
    update_branch(session, BRANCH_ID, actor_user_id=ADMIN_USER_ID, extra_payload={"phone": ""})
    for rows in (
        list_branches(session, ORGANIZATION_ID),
        list_public_branches(session, organization_id=ORGANIZATION_ID),
    ):
        assert next(b for b in rows if b["id"] == BRANCH_ID)["pickup_grace_minutes"] == 30
    update_branch(
        session,
        BRANCH_ID,
        actor_user_id=ADMIN_USER_ID,
        extra_payload={"pickup_grace_minutes": None},
    )
    assert (
        session.scalar(
            sa.select(models.branches.c.pickup_grace_minutes).where(
                models.branches.c.id == BRANCH_ID
            )
        )
        is None
    )
    audits = (
        session.execute(
            sa.select(models.audit_events.c.payload).where(
                models.audit_events.c.action == "branch.updated"
            )
        )
        .scalars()
        .all()
    )
    assert any(a.get("pickup_grace_minutes") == 30 for a in audits)
    assert any("pickup_grace_minutes" in a and a["pickup_grace_minutes"] is None for a in audits)


@pytest.mark.parametrize("value", [0, -1, 1.5, True, "30", "", 2147483648, [], {}])
def test_invalid_value_is_atomic(session: Any, value: Any) -> None:
    original = session.scalar(
        sa.select(models.branches.c.name).where(models.branches.c.id == BRANCH_ID)
    )
    with pytest.raises(BusinessError) as error:
        update_branch(
            session,
            BRANCH_ID,
            actor_user_id=ADMIN_USER_ID,
            name="Must not save",
            extra_payload={"pickup_grace_minutes": value},
        )
    assert error.value.code == "pickup_grace_minutes_invalid"
    assert (
        session.scalar(sa.select(models.branches.c.name).where(models.branches.c.id == BRANCH_ID))
        == original
    )
    assert (
        session.scalar(
            sa.select(sa.func.count())
            .select_from(models.audit_events)
            .where(models.audit_events.c.action == "branch.updated")
        )
        == 0
    )


def test_authorization_and_tenant_scope(session: Any) -> None:
    from restaurant_os.operations import AuthorizationError

    row = dict(
        session.execute(
            sa.select(models.organizations).where(models.organizations.c.id == ORGANIZATION_ID)
        )
        .mappings()
        .one()
    )
    row.update(id="pickup-other-org", slug="pickup-other-org")
    session.execute(models.organizations.insert().values(**row))
    session.execute(
        models.branches.update()
        .where(models.branches.c.id == BRANCH_ID)
        .values(organization_id="pickup-other-org")
    )
    session.commit()
    with pytest.raises(BusinessError) as error:
        update_branch(
            session,
            BRANCH_ID,
            actor_user_id=ADMIN_USER_ID,
            extra_payload={"pickup_grace_minutes": 30},
        )
    assert error.value.code == "branch_not_found"
    session.execute(models.user_roles.delete().where(models.user_roles.c.user_id == ADMIN_USER_ID))
    session.commit()
    with pytest.raises(AuthorizationError):
        update_branch(
            session,
            BRANCH_ID,
            actor_user_id=ADMIN_USER_ID,
            extra_payload={"pickup_grace_minutes": 30},
        )
    assert (
        session.scalar(
            sa.select(models.branches.c.pickup_grace_minutes).where(
                models.branches.c.id == BRANCH_ID
            )
        )
        is None
    )


def test_api_and_storefront_contract() -> None:
    from test_platform_api import (
        _admin_headers,
        _client_with_seeded_database,
        _test_session_factory,
    )

    client = _client_with_seeded_database()
    with _test_session_factory(client)() as setup:
        from test_dine_in_configuration import _enable_public_key

        _enable_public_key(setup)
        setup.execute(
            models.organizations.update()
            .where(models.organizations.c.id == ORGANIZATION_ID)
            .values(slug="pickup-qa")
        )
        setup.commit()
    headers = _admin_headers()
    for value in (1, 2147483647, None):
        response = client.put(
            f"/api/v1/branches/{BRANCH_ID}", headers=headers, json={"pickup_grace_minutes": value}
        )
        assert response.status_code == 200, response.text
        assert response.json()["pickup_grace_minutes"] == value
        branches = client.get("/api/v1/branches", headers=headers).json()
        branch = next(b for b in branches if b["id"] == BRANCH_ID)
        assert branch["pickup_grace_minutes"] == value
        public = client.get(f"/api/v1/public/storefronts/{branch['code'].lower()}")
        assert public.status_code == 200, public.text
        assert (
            next(b for b in public.json()["branches"] if b["id"] == BRANCH_ID)[
                "pickup_grace_minutes"
            ]
            == value
        )
    invalid = client.put(
        f"/api/v1/branches/{BRANCH_ID}", headers=headers, json={"pickup_grace_minutes": True}
    )
    assert invalid.status_code == 409
    assert invalid.json()["detail"]["code"] == "pickup_grace_minutes_invalid"
