"""TDD Test Suite for POS-SaaS Sprint 3: Unified Delivery Hub & Global Kill-Switch."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from restaurant_os.main import app
from restaurant_os.database import get_session
from restaurant_os import models


def _client_with_db() -> TestClient:
    engine = sa.create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_session():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session
    return TestClient(app)


def test_kill_switch_pauses_product_globally_and_locally() -> None:
    client = _client_with_db()

    # 1. Sign up a tenant
    signup_resp = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Taquería Los Parados",
            "owner_name": "Don Beto",
            "email": "beto@losparados.com",
            "password": "Password123!",
            "business_type": "taqueria",
        },
    )
    assert signup_resp.status_code == 201
    token = signup_resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Get starter products
    prod_resp = client.get("/api/v1/catalog/products", headers=headers)
    assert prod_resp.status_code == 200
    products = prod_resp.json()
    assert len(products) >= 1
    target_product = products[0]
    product_id = target_product["id"]

    # 3. Activate Kill-Switch (sold out)
    kill_resp = client.post(
        "/api/v1/integrations/kill-switch",
        headers=headers,
        json={
            "product_id": product_id,
            "is_available": False,
            "reason": "se_termino_pastor",
        },
    )
    assert kill_resp.status_code == 200
    kill_data = kill_resp.json()
    assert kill_data["product_id"] == product_id
    assert kill_data["is_available"] is False
    assert "channel_statuses" in kill_data
    assert "pos" in kill_data["channel_statuses"]
    assert "uber_eats" in kill_data["channel_statuses"]

    # 4. Check that product in POS catalog reflects unavailable
    prod_resp_after = client.get("/api/v1/catalog/products", headers=headers)
    assert prod_resp_after.status_code == 200
    updated_product = next((p for p in prod_resp_after.json() if p["id"] == product_id), None)
    # Fail-closed / unavailable: either excluded or is_available is False
    assert updated_product is None or updated_product["is_available"] is False


def test_kill_switch_restores_product_availability() -> None:
    client = _client_with_db()

    signup_resp = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Tacos al Pastor El Güero",
            "owner_name": "Pedro Güero",
            "email": "guero@pastor.com",
            "password": "Password123!",
            "business_type": "taqueria",
        },
    )
    assert signup_resp.status_code == 201
    token = signup_resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    prod_resp = client.get("/api/v1/catalog/products", headers=headers)
    target_product = prod_resp.json()[0]
    product_id = target_product["id"]

    # Pause
    client.post(
        "/api/v1/integrations/kill-switch",
        headers=headers,
        json={"product_id": product_id, "is_available": False},
    )

    # Restore (pastor is ready again)
    restore_resp = client.post(
        "/api/v1/integrations/kill-switch",
        headers=headers,
        json={"product_id": product_id, "is_available": True},
    )
    assert restore_resp.status_code == 200
    restore_data = restore_resp.json()
    assert restore_data["is_available"] is True

    # Check that product is once again available in POS
    prod_resp_restored = client.get("/api/v1/catalog/products", headers=headers)
    restored_product = next((p for p in prod_resp_restored.json() if p["id"] == product_id), None)
    assert restored_product is not None
    assert restored_product["is_available"] is True


def test_delivery_channels_status_overview() -> None:
    client = _client_with_db()

    signup_resp = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Dark Kitchen Roma",
            "owner_name": "Carlos Roma",
            "email": "carlos@darkkitchen.com",
            "password": "Password123!",
            "business_type": "general",
        },
    )
    assert signup_resp.status_code == 201
    token = signup_resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    status_resp = client.get("/api/v1/integrations/channels/status", headers=headers)
    assert status_resp.status_code == 200
    channels = status_resp.json()
    assert isinstance(channels, list)
    providers = [c["provider"].lower() for c in channels]
    assert "uber_eats" in providers
    assert "didi_food" in providers
    assert "rappi" in providers
