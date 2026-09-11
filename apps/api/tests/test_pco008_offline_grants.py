"""PCO-008R Ed25519 capability and issuance regressions."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

import pytest
from restaurant_os import models, operations
from test_cash_concepts import BRANCH_A, CASHIER_ID, ORG_ID
from test_cash_ledger import _new_session

pytest.importorskip("cryptography")

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from restaurant_os.offline_grants import (  # noqa: E402
    create_offline_grant_v2,
    verify_offline_grant_v2,
)

UTC = timezone.utc
DEVICE_ID = "018f6f73-2d0a-74f0-8f1c-000000000401"
PAYLOAD = {
    "actor_user_id": CASHIER_ID,
    "organization_id": ORG_ID,
    "branch_id": BRANCH_A,
    "source_device_id": DEVICE_ID,
    "capabilities": ["cash.movement.create.v1"],
}


def test_ed25519_grant_is_portable_tamper_evident_and_expiring() -> None:
    private_key = Ed25519PrivateKey.generate()
    token = create_offline_grant_v2(PAYLOAD, private_key, kid="active", now=100)

    assert verify_offline_grant_v2(token, {"active": private_key.public_key()}, now=101) == {
        **PAYLOAD,
        "kind": "offline_grant.v2",
        "version": 2,
        "iat": 100,
        "exp": 7_300,
    }
    assert verify_offline_grant_v2(token, {"active": private_key.public_key()}, now=7_301) is None
    header, body, signature = token.split(".")
    raw = bytearray(base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4)))
    raw[0] ^= 1
    changed = base64.urlsafe_b64encode(bytes(raw)).decode().rstrip("=")
    assert (
        verify_offline_grant_v2(
            f"{header}.{body}.{changed}", {"active": private_key.public_key()}, now=101
        )
        is None
    )


def test_grant_issuance_rechecks_human_permission_and_active_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, session = _new_session()
    private_key = Ed25519PrivateKey.generate()
    monkeypatch.setattr(
        operations, "_offline_grant_signing_material", lambda: (private_key, "active")
    )
    now = datetime.now(UTC)
    try:
        session.execute(
            models.device_credentials.insert().values(
                id=DEVICE_ID,
                organization_id=ORG_ID,
                branch_id=BRANCH_A,
                capability="gateway.sync",
                token_hash="0" * 64,
                key_version="test",
                expires_at=now + timedelta(hours=1),
                revoked_at=None,
                created_at=now,
            )
        )
        session.commit()

        issued = operations.issue_offline_cash_grant(
            session,
            actor_user_id=CASHIER_ID,
            organization_id=ORG_ID,
            branch_id=BRANCH_A,
            source_device_id=DEVICE_ID,
        )
        verified = verify_offline_grant_v2(
            issued["offline_grant"], {"active": private_key.public_key()}
        )
        assert verified is not None
        assert {field: verified[field] for field in PAYLOAD} == PAYLOAD

        session.execute(
            models.device_credentials.update()
            .where(models.device_credentials.c.id == DEVICE_ID)
            .values(revoked_at=now)
        )
        session.commit()
        with pytest.raises(operations.BusinessError) as inactive:
            operations.issue_offline_cash_grant(
                session,
                actor_user_id=CASHIER_ID,
                organization_id=ORG_ID,
                branch_id=BRANCH_A,
                source_device_id=DEVICE_ID,
            )
        assert inactive.value.code == "gateway_device_inactive"
    finally:
        session.close()
        engine.dispose()
