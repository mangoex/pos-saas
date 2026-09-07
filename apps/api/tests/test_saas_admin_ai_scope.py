# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-recovery-test-saas-admin-ai-scope-synthetic-v1
from __future__ import annotations

from uuid import uuid4

import pytest
from restaurant_os.admin_ai import (
    AdminAiError,
    AdminAiProviderOptions,
    create_admin_ai_response,
    get_proposal,
    review_proposal,
)
from restaurant_os.operations import BusinessError
from test_saas_onboarding import _client_with_db


def _signup(client, suffix: str) -> dict:
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": f"Admin AI {suffix}",
            "owner_name": suffix,
            "email": f"admin-ai-{suffix}@example.test",
            "password": "synthetic-admin-ai-password",
            "business_type": "blank",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _product(client, tenant: dict, suffix: str) -> None:
    response = client.post(
        "/api/v1/catalog/products",
        headers={"Authorization": f"Bearer {tenant['token']}"},
        json={
            "name": f"Producto privado {suffix}",
            "sku": f"ADMIN-AI-{suffix}",
            "category_name": "Bebidas",
            "station": "bar",
            "price_cents": 1000,
        },
    )
    assert response.status_code == 200, response.text


def test_admin_ai_conversation_context_and_review_are_tenant_scoped() -> None:
    client = _client_with_db()
    tenant_a = _signup(client, "a")
    tenant_b = _signup(client, "b")
    _product(client, tenant_a, "A")
    _product(client, tenant_b, "B")
    captured_a: dict = {}
    captured_b: dict = {}
    options = AdminAiProviderOptions("synthetic", "test", "https://invalid.test", 1)

    def provider(captured: dict):
        def request(prompt, context, _options):
            captured["context"] = context
            return {
                "answer": "Necesito una aclaración.",
                "sources": ["SDD §43"],
                "questions": ["¿Cuál?"],
                "warnings": [],
                "change_set": [],
            }

        return request

    with client.app.state.test_session_factory() as session:
        proposal_a = create_admin_ai_response(
            session,
            tenant_a["user"]["id"],
            "Revisa el catálogo",
            tenant_a["branch"]["id"],
            options,
            provider(captured_a),
        )
        proposal_b = create_admin_ai_response(
            session,
            tenant_b["user"]["id"],
            "Revisa el catálogo",
            tenant_b["branch"]["id"],
            options,
            provider(captured_b),
        )
        assert [row["sku"] for row in captured_a["context"]["products"]] == ["ADMIN-AI-A"]
        assert [row["sku"] for row in captured_b["context"]["products"]] == ["ADMIN-AI-B"]
        with pytest.raises(BusinessError, match="Proposal was not found"):
            get_proposal(session, proposal_a["id"], tenant_b["user"]["id"])
        with pytest.raises(BusinessError, match="Proposal was not found"):
            review_proposal(session, proposal_a["id"], tenant_b["user"]["id"], False)
        with pytest.raises(AdminAiError, match="conversación anterior"):
            create_admin_ai_response(
                session,
                tenant_b["user"]["id"],
                "continúa",
                tenant_b["branch"]["id"],
                options,
                provider(captured_b),
                parent_proposal_id=proposal_a["id"],
                conversation_idempotency_key=str(uuid4()),
                conversation_context=["Revisa el catálogo"],
            )
        assert (
            get_proposal(session, proposal_b["id"], tenant_b["user"]["id"])["id"]
            == proposal_b["id"]
        )
