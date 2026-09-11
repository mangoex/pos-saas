# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-admin-ai-tests-v1
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import admin_ai, models
from restaurant_os.admin_ai import (
    AdminAiError,
    AdminAiProviderOptions,
    build_context,
    create_admin_ai_response,
    get_proposal,
    request_openrouter_proposal,
    review_proposal,
)
from restaurant_os.database import get_session
from restaurant_os.main import create_app
from restaurant_os.operations import AuthorizationError, BusinessError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from test_platform_api import ADMIN_USER_ID, BRANCH_ID, _seed

UTC = timezone.utc

PRODUCT_ID = "018f6f73-2d0a-74f0-8f1c-000000000111"
ITEM_ID = "018f6f73-2d0a-74f0-8f1c-000000000311"
UNIT_ID = "018f6f73-2d0a-74f0-8f1c-000000000301"
WAREHOUSE_ID = "018f6f73-2d0a-74f0-8f1c-000000000004"
SUPPLIER_ID = "018f6f73-2d0a-74f0-8f1c-000000000701"
PRESENTATION_ID = "018f6f73-2d0a-74f0-8f1c-000000000711"
OTHER_BRANCH_ID = "018f6f73-2d0a-74f0-8f1c-000000000703"
OTHER_ADMIN_ID = "018f6f73-2d0a-74f0-8f1c-000000000704"
OPTIONS = AdminAiProviderOptions(
    api_key="synthetic-admin-ai-key",
    model="test-model",
    base_url="https://openrouter.invalid/api/v1",
    timeout_seconds=3,
)


def _conversation_key(sequence: int) -> str:
    return f"018f6f73-2d0a-74f0-8f1c-{sequence:012d}"


def _factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        _seed(session)
        session.commit()
    return factory


def _client(factory: sessionmaker[Session]) -> TestClient:
    app = create_app()

    def override_session():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


def _result(
    kind: str,
    target_id: str | None,
    payload: dict[str, Any],
    evidence: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "answer": "Preparé una propuesta revisable.",
        "sources": ["PRD-FR-010", "SDD §43"],
        "questions": [],
        "warnings": [],
        "change_set": [
            {
                "kind": kind,
                "target_id": target_id,
                "payload_json": json.dumps(payload),
                "evidence": evidence,
            }
        ],
    }


def _fake(result: dict[str, Any], captured: dict[str, Any] | None = None):
    def provider(
        prompt: str, context: dict[str, Any], _options: AdminAiProviderOptions
    ) -> dict[str, Any]:
        if captured is not None:
            captured["prompt"] = prompt
            captured["context"] = context
        return result

    return provider


def _seed_purchase_price(session: Session) -> None:
    now = datetime(2026, 8, 29, 18, 0, tzinfo=UTC)
    session.execute(
        models.suppliers.insert().values(
            id=SUPPLIER_ID,
            organization_id="018f6f73-2d0a-74f0-8f1c-000000000001",
            code="SUP-AIA-207",
            commercial_name="Proveedor sintético AIA",
            supplier_type="insumos",
            credit_days=0,
            currency="MXN",
            delivery_days=[],
            payment_methods=[],
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.purchase_presentations.insert().values(
            id=PRESENTATION_ID,
            organization_id="018f6f73-2d0a-74f0-8f1c-000000000001",
            supplier_id=SUPPLIER_ID,
            item_id=ITEM_ID,
            code="PRES-AIA-207",
            name="Carne caja sintética",
            package_type="box",
            commercial_quantity=1,
            commercial_unit_id=UNIT_ID,
            base_unit_id=UNIT_ID,
            base_unit_yield=1000,
            usable_content=1000,
            yield_percent=1,
            last_net_price=120,
            cost_per_base_unit="0.12",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()


def test_tdd_tc_194_provider_context_is_allowlisted_and_transport_redacts_pii() -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            content = {
                "answer": "Regla",
                "sources": ["SDD §43"],
                "questions": [],
                "warnings": [],
                "change_set": [],
            }
            return json.dumps({"choices": [{"message": {"content": json.dumps(content)}}]}).encode()

    captured: dict[str, Any] = {}

    def opener(request: Any, timeout: float) -> FakeResponse:
        captured["body"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return FakeResponse()

    context = {
        "rules": [],
        "products": [],
        "inventory_items": [],
        "units": [],
        "modifier_groups": [],
        "active_recipes": [],
        "branch_id": BRANCH_ID,
    }
    parsed = request_openrouter_proposal(
        "Ayuda a ana@example.com, 6672013019 con producto 1001", context, OPTIONS, opener
    )
    external = captured["body"]["messages"][1]["content"]
    assert "ana@example.com" not in external and "6672013019" not in external
    assert "[CORREO]" in external and "[TELEFONO]" in external
    assert captured["body"]["temperature"] == 0
    assert captured["body"]["response_format"]["json_schema"]["strict"] is True
    assert parsed["sources"] == ["SDD §43"]


def test_tdd_tc_202_http_boundary_keeps_disabled_provider_in_draft() -> None:
    client = _client(_factory())
    headers = {"X-Actor-User-Id": ADMIN_USER_ID}

    created = client.post(
        "/api/v1/admin-ai/proposals",
        headers=headers,
        json={"prompt": "¿Cómo configuro un producto?", "branch_id": BRANCH_ID},
    )

    assert created.status_code == 200, created.text
    proposal = created.json()
    assert proposal["status"] == "DRAFT"
    assert proposal["payload"]["change_set"] == []

    fetched = client.get(f"/api/v1/admin-ai/proposals/{proposal['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == proposal["id"]

    accepted = client.post(
        f"/api/v1/admin-ai/proposals/{proposal['id']}/review",
        headers={**headers, "Idempotency-Key": "draft-cannot-apply"},
        json={"accept": True},
    )
    assert accepted.status_code == 409
    assert accepted.json()["detail"]["code"] == "admin_ai_proposal_not_ready"

    rejected = client.post(
        f"/api/v1/admin-ai/proposals/{proposal['id']}/review",
        headers=headers,
        json={"accept": False},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"


def test_tdd_tc_205_observability_uses_ids_and_codes_without_prompt_or_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _client(_factory())
    headers = {"X-Actor-User-Id": ADMIN_USER_ID}
    secret_prompt_marker = "PROMPT-PRIVADO-AIA-205"
    secret_key_marker = "KEY-PRIVADA-AIA-205"

    with caplog.at_level(logging.INFO, logger="restaurant_os.api"):
        created = client.post(
            "/api/v1/admin-ai/proposals",
            headers=headers,
            json={"prompt": secret_prompt_marker, "branch_id": BRANCH_ID},
        )
        proposal = created.json()
        failed = client.post(
            f"/api/v1/admin-ai/proposals/{proposal['id']}/review",
            headers={**headers, "Idempotency-Key": secret_key_marker},
            json={"accept": True},
        )

    assert created.status_code == 200
    assert failed.status_code == 409
    assert "admin_ai_proposal result=success" in caplog.text
    assert "admin_ai_review result=error" in caplog.text
    assert "admin_ai_proposal_not_ready" in caplog.text
    assert proposal["id"] in caplog.text
    assert secret_prompt_marker not in caplog.text
    assert secret_key_marker not in caplog.text


def test_tdd_tc_205_http_permission_denial_is_redacted_and_fail_closed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _client(_factory())
    unauthorized_actor = "018f6f73-2d0a-74f0-8f1c-000000009999"
    prompt_marker = "PROMPT-NO-AUTORIZADO-AIA-205"

    with caplog.at_level(logging.INFO, logger="restaurant_os.api"):
        response = client.post(
            "/api/v1/admin-ai/proposals",
            headers={"X-Actor-User-Id": unauthorized_actor},
            json={"prompt": prompt_marker, "branch_id": BRANCH_ID},
        )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "actor_not_authorized"
    assert "admin_ai_proposal result=error" in caplog.text
    assert "actor_not_authorized" in caplog.text
    assert unauthorized_actor in caplog.text
    assert prompt_marker not in caplog.text


def test_tdd_tc_196_and_198_product_proposal_is_reviewed_applied_and_replayed() -> None:
    factory = _factory()
    prompt = "Actualiza Hamburguesa Kiwi a HAMBURGUESA PREMIUM con precio 9900"
    result = _result(
        "product.update",
        PRODUCT_ID,
        {"name": "HAMBURGUESA PREMIUM", "price_cents": 9900},
        [
            {"field": "target_id", "quote": "Hamburguesa Kiwi"},
            {"field": "name", "quote": "HAMBURGUESA PREMIUM"},
            {"field": "price_cents", "quote": "9900"},
        ],
    )
    with factory() as session:
        proposal = create_admin_ai_response(
            session, ADMIN_USER_ID, prompt, BRANCH_ID, OPTIONS, _fake(result)
        )
        assert proposal["status"] == "READY_FOR_REVIEW"
        assert proposal["payload"]["change_set"][0]["current"]["name"] == "Hamburguesa Kiwi"
        assert (
            session.execute(
                sa.select(models.products.c.name).where(models.products.c.id == PRODUCT_ID)
            ).scalar_one()
            == "Hamburguesa Kiwi"
        )
        applied = review_proposal(session, proposal["id"], ADMIN_USER_ID, True, "apply-product-1")
        assert applied["status"] == "APPLIED" and applied["result"]["id"] == PRODUCT_ID
        replay = review_proposal(session, proposal["id"], ADMIN_USER_ID, True, "apply-product-1")
        assert replay["result"] == applied["result"]
        assert (
            session.execute(
                sa.select(models.products.c.name).where(models.products.c.id == PRODUCT_ID)
            ).scalar_one()
            == "HAMBURGUESA PREMIUM"
        )
        with pytest.raises(BusinessError) as conflict:
            review_proposal(session, proposal["id"], ADMIN_USER_ID, True, "another-key")
        assert conflict.value.code == "idempotency_conflict"


def test_tdd_tc_195_unknown_source_missing_evidence_and_unknown_reference_fail_closed() -> None:
    factory = _factory()
    with factory() as session:
        unknown_source = _result(
            "product.update",
            PRODUCT_ID,
            {"name": "NUEVO NOMBRE"},
            [{"field": "name", "quote": "NUEVO NOMBRE"}],
        )
        unknown_source["sources"] = ["manual inventado"]
        with pytest.raises(AdminAiError) as source_error:
            create_admin_ai_response(
                session, ADMIN_USER_ID, "NUEVO NOMBRE", BRANCH_ID, OPTIONS, _fake(unknown_source)
            )
        assert source_error.value.code == "admin_ai_source_unknown"

        missing = _result(
            "product.update",
            PRODUCT_ID,
            {"price_cents": 1234},
            [
                {"field": "target_id", "quote": "Hamburguesa Kiwi"},
                {"field": "price_cents", "quote": "precio 4321"},
            ],
        )
        with pytest.raises(AdminAiError) as evidence_error:
            create_admin_ai_response(
                session,
                ADMIN_USER_ID,
                "Hamburguesa Kiwi precio 4321",
                BRANCH_ID,
                OPTIONS,
                _fake(missing),
            )
        assert evidence_error.value.code == "admin_ai_evidence_missing"

        bad_reference = _result(
            "modifier_group.create",
            "missing",
            {
                "name": "TAMAÑO",
                "is_required": False,
                "minimum_selections": 0,
                "maximum_selections": 1,
            },
            [
                {"field": "name", "quote": "TAMAÑO"},
                {"field": "is_required", "quote": "opcional"},
                {"field": "minimum_selections", "quote": "mínimo 0"},
                {"field": "maximum_selections", "quote": "máximo 1"},
            ],
        )
        with pytest.raises(AdminAiError) as reference_error:
            create_admin_ai_response(
                session,
                ADMIN_USER_ID,
                "TAMAÑO opcional mínimo 0 máximo 1",
                BRANCH_ID,
                OPTIONS,
                _fake(bad_reference),
            )
        assert reference_error.value.code == "admin_ai_reference_invalid"
        assert (
            session.execute(
                sa.select(sa.func.count()).select_from(models.admin_ai_proposals)
            ).scalar_one()
            == 0
        )


def test_tdd_tc_197_vertical_actions_use_canonical_services() -> None:
    factory = _factory()
    with factory() as session:
        product_prompt = (
            "Crea producto PANINI VERDE SKU 9100 categoría COMIDA estación cocina precio 8800"
        )
        product_raw = _result(
            "product.create",
            None,
            {
                "name": "PANINI VERDE",
                "sku": "9100",
                "category_name": "COMIDA",
                "station": "kitchen",
                "price_cents": 8800,
            },
            [
                {"field": "name", "quote": "PANINI VERDE"},
                {"field": "sku", "quote": "9100"},
                {"field": "category_name", "quote": "COMIDA"},
                {"field": "station", "quote": "cocina"},
                {"field": "price_cents", "quote": "8800"},
            ],
        )
        product_proposal = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            product_prompt,
            BRANCH_ID,
            OPTIONS,
            _fake(product_raw),
        )
        product_applied = review_proposal(
            session, product_proposal["id"], ADMIN_USER_ID, True, "apply-product-create"
        )
        assert product_applied["result"]["sku"] == "9100"

        item_prompt = "Crea insumo QUESO NUEVO SKU 9001 tipo ingredient unidad Gramo"
        item_raw = _result(
            "inventory_item.create",
            None,
            {
                "name": "QUESO NUEVO",
                "sku": "9001",
                "base_unit_id": UNIT_ID,
                "item_type": "ingredient",
            },
            [
                {"field": "name", "quote": "QUESO NUEVO"},
                {"field": "sku", "quote": "9001"},
                {"field": "item_type", "quote": "ingredient"},
                {"field": "base_unit_id", "quote": "unidad Gramo"},
            ],
        )
        item_proposal = create_admin_ai_response(
            session, ADMIN_USER_ID, item_prompt, BRANCH_ID, OPTIONS, _fake(item_raw)
        )
        item_applied = review_proposal(
            session, item_proposal["id"], ADMIN_USER_ID, True, "apply-item"
        )
        assert item_applied["result"]["sku"] == "9001"

        group_prompt = "Para Hamburguesa Kiwi crea grupo TAMAÑO opcional mínimo 0 máximo 1"
        group_raw = _result(
            "modifier_group.create",
            PRODUCT_ID,
            {
                "name": "TAMAÑO",
                "is_required": False,
                "minimum_selections": 0,
                "maximum_selections": 1,
            },
            [
                {"field": "target_id", "quote": "Hamburguesa Kiwi"},
                {"field": "name", "quote": "TAMAÑO"},
                {"field": "is_required", "quote": "opcional"},
                {"field": "minimum_selections", "quote": "mínimo 0"},
                {"field": "maximum_selections", "quote": "máximo 1"},
            ],
        )
        group_proposal = create_admin_ai_response(
            session, ADMIN_USER_ID, group_prompt, BRANCH_ID, OPTIONS, _fake(group_raw)
        )
        group_applied = review_proposal(
            session, group_proposal["id"], ADMIN_USER_ID, True, "apply-group"
        )

        option_prompt = "En grupo TAMAÑO crea opción SIN CORTAR efecto instruction precio 0"
        option_raw = _result(
            "modifier_option.create",
            group_applied["result"]["id"],
            {"name": "SIN CORTAR", "effect_type": "instruction", "price_delta_cents": 0},
            [
                {"field": "target_id", "quote": "grupo TAMAÑO"},
                {"field": "name", "quote": "SIN CORTAR"},
                {"field": "effect_type", "quote": "instruction"},
                {"field": "price_delta_cents", "quote": "precio 0"},
            ],
        )
        option_proposal = create_admin_ai_response(
            session, ADMIN_USER_ID, option_prompt, BRANCH_ID, OPTIONS, _fake(option_raw)
        )
        option_applied = review_proposal(
            session, option_proposal["id"], ADMIN_USER_ID, True, "apply-option"
        )
        assert option_applied["result"]["group_id"] == group_applied["result"]["id"]

        recipe_prompt = (
            "Versiona receta de Hamburguesa Kiwi con rendimiento 1 Gramo, "
            "Carne molida 100 Gramo y merma 0"
        )
        recipe_raw = _result(
            "recipe.version",
            PRODUCT_ID,
            {
                "yield_quantity": "1",
                "yield_unit_id": UNIT_ID,
                "components": [
                    {
                        "item_id": ITEM_ID,
                        "unit_id": UNIT_ID,
                        "net_quantity": "100",
                        "waste_rate": "0",
                    }
                ],
            },
            [
                {"field": "target_id", "quote": "Hamburguesa Kiwi"},
                {"field": "yield_quantity", "quote": "rendimiento 1"},
                {"field": "yield_unit_id", "quote": "1 Gramo"},
                {"field": "components.0.item_id", "quote": "Carne molida"},
                {"field": "components.0.unit_id", "quote": "100 Gramo"},
                {"field": "components.0.net_quantity", "quote": "100"},
                {"field": "components.0.waste_rate", "quote": "merma 0"},
            ],
        )
        recipe_proposal = create_admin_ai_response(
            session, ADMIN_USER_ID, recipe_prompt, BRANCH_ID, OPTIONS, _fake(recipe_raw)
        )
        recipe_applied = review_proposal(
            session, recipe_proposal["id"], ADMIN_USER_ID, True, "apply-recipe"
        )
        assert recipe_applied["result"]["product_id"] == PRODUCT_ID
        assert recipe_applied["result"]["components"][0]["item_id"] == ITEM_ID


def test_tdd_tc_198_stale_and_tdd_tc_199_reject_are_fail_closed() -> None:
    factory = _factory()
    prompt = "Actualiza Hamburguesa Kiwi a HAMBURGUESA STALE"
    raw = _result(
        "product.update",
        PRODUCT_ID,
        {"name": "HAMBURGUESA STALE"},
        [
            {"field": "target_id", "quote": "Hamburguesa Kiwi"},
            {"field": "name", "quote": "HAMBURGUESA STALE"},
        ],
    )
    with factory() as session:
        stale = create_admin_ai_response(
            session, ADMIN_USER_ID, prompt, BRANCH_ID, OPTIONS, _fake(raw)
        )
        session.execute(
            sa.update(models.products)
            .where(models.products.c.id == PRODUCT_ID)
            .values(updated_at=datetime(2030, 1, 1, tzinfo=UTC))
        )
        session.commit()
        with pytest.raises(BusinessError) as stale_error:
            review_proposal(session, stale["id"], ADMIN_USER_ID, True, "stale-key")
        assert stale_error.value.code == "admin_ai_proposal_stale"
        assert (
            session.execute(
                sa.select(models.products.c.name).where(models.products.c.id == PRODUCT_ID)
            ).scalar_one()
            == "Hamburguesa Kiwi"
        )

    factory = _factory()
    with factory() as session:
        unauthorized = create_admin_ai_response(
            session, ADMIN_USER_ID, prompt, BRANCH_ID, OPTIONS, _fake(raw)
        )
        with pytest.raises(AuthorizationError):
            review_proposal(
                session, unauthorized["id"], "actor-without-role", True, "unauthorized-key"
            )
        assert (
            session.execute(
                sa.select(models.products.c.name).where(models.products.c.id == PRODUCT_ID)
            ).scalar_one()
            == "Hamburguesa Kiwi"
        )

    factory = _factory()
    with factory() as session:
        expired = create_admin_ai_response(
            session, ADMIN_USER_ID, prompt, BRANCH_ID, OPTIONS, _fake(raw)
        )
        session.execute(
            sa.update(models.admin_ai_proposals)
            .where(models.admin_ai_proposals.c.id == expired["id"])
            .values(expires_at=datetime(2000, 1, 1, tzinfo=UTC))
        )
        session.commit()
        with pytest.raises(BusinessError) as expired_error:
            review_proposal(session, expired["id"], ADMIN_USER_ID, True, "expired-key")
        assert expired_error.value.code == "admin_ai_proposal_expired"
        assert (
            session.execute(
                sa.select(models.admin_ai_proposals.c.status).where(
                    models.admin_ai_proposals.c.id == expired["id"]
                )
            ).scalar_one()
            == "EXPIRED"
        )

    factory = _factory()
    with factory() as session:
        rejected = create_admin_ai_response(
            session, ADMIN_USER_ID, prompt, BRANCH_ID, OPTIONS, _fake(raw)
        )
        decision = review_proposal(session, rejected["id"], ADMIN_USER_ID, False)
        assert decision["status"] == "REJECTED"
        assert (
            session.execute(
                sa.select(models.products.c.name).where(models.products.c.id == PRODUCT_ID)
            ).scalar_one()
            == "Hamburguesa Kiwi"
        )


def test_tdd_tc_207_purchase_and_cost_changes_do_not_stale_catalog_proposal() -> None:
    factory = _factory()
    prompt = "Actualiza Hamburguesa Kiwi a HAMBURGUESA SIN STALE AJENO"
    raw = _result(
        "product.update",
        PRODUCT_ID,
        {"name": "HAMBURGUESA SIN STALE AJENO"},
        [
            {"field": "target_id", "quote": "Hamburguesa Kiwi"},
            {"field": "name", "quote": "HAMBURGUESA SIN STALE AJENO"},
        ],
    )

    with factory() as session:
        _seed_purchase_price(session)
        proposal = create_admin_ai_response(
            session, ADMIN_USER_ID, prompt, BRANCH_ID, OPTIONS, _fake(raw)
        )
        assert proposal["status"] == "READY_FOR_REVIEW"

        now = datetime(2026, 8, 29, 18, 20, tzinfo=UTC)
        session.execute(
            models.purchase_presentations.update()
            .where(models.purchase_presentations.c.id == PRESENTATION_ID)
            .values(last_net_price=135, updated_at=now)
        )
        session.execute(
            models.inventory_cost_states.insert().values(
                branch_id=BRANCH_ID,
                warehouse_id=WAREHOUSE_ID,
                item_id=ITEM_ID,
                quantity_on_hand=10,
                average_unit_cost=25,
                last_unit_cost=25,
                last_supplier_id=SUPPLIER_ID,
                last_cost_at=now,
                updated_at=now,
            )
        )
        session.commit()

        applied = review_proposal(
            session, proposal["id"], ADMIN_USER_ID, True, "apply-unrelated-cost-change"
        )
        assert applied["status"] == "APPLIED"
        assert applied["result"]["name"] == "HAMBURGUESA SIN STALE AJENO"


def test_tdd_tc_207_diagnostic_total_and_rows_share_one_database_snapshot() -> None:
    factory = _factory()

    with factory() as session:
        executed = 0
        bind = session.get_bind()

        def count_statement(*_args: object) -> None:
            nonlocal executed
            executed += 1

        statement = sa.select(
            models.inventory_items.c.id,
            models.inventory_items.c.name,
            models.inventory_items.c.sku,
        ).order_by(models.inventory_items.c.name)
        sa.event.listen(bind, "before_cursor_execute", count_statement)
        try:
            total, rows = admin_ai._limited_missing_items(session, statement)
        finally:
            sa.event.remove(bind, "before_cursor_execute", count_statement)

        assert executed == 1
        assert total == len(rows) == 4


def test_tdd_tc_194_disabled_provider_returns_non_applicable_local_guidance() -> None:
    factory = _factory()
    with factory() as session:
        response = create_admin_ai_response(
            session, ADMIN_USER_ID, "¿Cómo funcionan los modificadores?", BRANCH_ID
        )
        assert response["status"] == "DRAFT"
        assert response["payload"]["change_set"] == []
        assert "deshabilitado" in response["payload"]["warnings"][0]
        with pytest.raises(BusinessError) as not_ready:
            review_proposal(session, response["id"], ADMIN_USER_ID, True, "must-not-apply")
        assert not_ready.value.code == "admin_ai_proposal_not_ready"


def test_tdd_tc_206_ambiguous_inventory_price_question_is_clarified_before_provider() -> None:
    factory = _factory()
    provider_was_called = False

    def provider_should_not_run(
        _prompt: str, _context: dict[str, Any], _options: AdminAiProviderOptions
    ) -> dict[str, Any]:
        nonlocal provider_was_called
        provider_was_called = True
        raise AssertionError("Ambiguous inventory price questions must not reach the provider")

    with factory() as session:
        response = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "¿Qué insumos no tienen precio?",
            BRANCH_ID,
            OPTIONS,
            provider_should_not_run,
        )

        assert provider_was_called is False
        assert response["status"] == "DRAFT"
        assert response["payload"]["change_set"] == []
        assert response["payload"]["sources"] == [
            "PRD-FR-015",
            "PRD-FR-093",
            "PRD-FR-094",
            "PRD-FR-089",
            "PRD-FR-109",
        ]
        assert len(response["payload"]["questions"]) == 1
        clarification = response["payload"]["questions"][0].casefold()
        assert "precio de compra" in clarification
        assert "costo promedio" in clarification
        assert "precio de venta" not in clarification
        assert response["payload"]["clarification"] == {
            "kind": "inventory_price_authority",
            "turn": 1,
            "options": [
                {"id": "missing_purchase_price", "label": "Precio de compra"},
                {"id": "missing_average_cost", "label": "Costo promedio"},
            ],
        }
        assert PRODUCT_ID not in response["payload"]["answer"]
        assert ITEM_ID not in response["payload"]["answer"]
        audit_payload = session.execute(
            sa.select(models.audit_events.c.payload).where(
                models.audit_events.c.entity_id == response["id"]
            )
        ).scalar_one()
        assert audit_payload["external_provider"] is False


def test_tdd_tc_209_free_text_clarification_resolves_parent_without_rephrasing() -> None:
    factory = _factory()
    private_reply_marker = "ACLARACION-PRIVADA-AIA-209"

    def provider_should_not_run(
        _prompt: str, _context: dict[str, Any], _options: AdminAiProviderOptions
    ) -> dict[str, Any]:
        raise AssertionError("Bounded price clarification must not reach the provider")

    with factory() as session:
        _seed_purchase_price(session)
        initial = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "¿Qué insumos no tienen precio?",
            BRANCH_ID,
            OPTIONS,
            provider_should_not_run,
        )

        resolved = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            f"De compra, por favor {private_reply_marker}",
            BRANCH_ID,
            OPTIONS,
            provider_should_not_run,
            parent_proposal_id=initial["id"],
            conversation_idempotency_key=_conversation_key(1),
        )

        assert resolved["payload"]["diagnostic"]["kind"] == "missing_purchase_price"
        assert resolved["payload"]["conversation"] == {
            "parent_proposal_id": initial["id"],
            "turn": 2,
            "idempotency_key": _conversation_key(1),
        }
        assert resolved["payload"]["questions"] == []
        assert private_reply_marker not in json.dumps(resolved["payload"])
        persisted_payload = session.execute(
            sa.select(models.admin_ai_proposals.c.payload).where(
                models.admin_ai_proposals.c.id == resolved["id"]
            )
        ).scalar_one()
        assert private_reply_marker not in json.dumps(persisted_payload)
        assert "prompt" not in persisted_payload
        assert "transcript" not in persisted_payload


def test_tdd_tc_209_structured_choice_resolves_and_parent_scope_fails_closed() -> None:
    factory = _factory()
    with factory() as session:
        initial = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "Lista los insumos sin precio",
            BRANCH_ID,
        )

        with pytest.raises(AdminAiError) as mismatch:
            create_admin_ai_response(
                session,
                ADMIN_USER_ID,
                "De compra",
                None,
                parent_proposal_id=initial["id"],
                conversation_idempotency_key=_conversation_key(2),
            )
        assert mismatch.value.code == "admin_ai_conversation_scope_mismatch"

        with pytest.raises(AdminAiError) as invalid_choice:
            create_admin_ai_response(
                session,
                ADMIN_USER_ID,
                "Precio de venta",
                BRANCH_ID,
                parent_proposal_id=initial["id"],
                clarification_choice="product_sale_price",
                conversation_idempotency_key=_conversation_key(3),
            )
        assert invalid_choice.value.code == "admin_ai_conversation_invalid"

        resolved = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "Costo promedio",
            BRANCH_ID,
            parent_proposal_id=initial["id"],
            clarification_choice="missing_average_cost",
            conversation_idempotency_key=_conversation_key(4),
        )
        assert resolved["payload"]["diagnostic"]["kind"] == "missing_average_cost"

        replayed = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "Costo promedio",
            BRANCH_ID,
            parent_proposal_id=initial["id"],
            clarification_choice="missing_average_cost",
            conversation_idempotency_key=_conversation_key(4),
        )
        assert replayed["id"] == resolved["id"]

        inventory_read_id = session.execute(
            sa.select(models.permissions.c.id).where(
                models.permissions.c.code == "inventory.read"
            )
        ).scalar_one()
        admin_role_ids = sa.select(models.user_roles.c.role_id).where(
            models.user_roles.c.user_id == ADMIN_USER_ID
        )
        session.execute(
            models.role_permissions.delete().where(
                models.role_permissions.c.role_id.in_(admin_role_ids),
                models.role_permissions.c.permission_id == inventory_read_id,
            )
        )
        session.commit()
        with pytest.raises(AuthorizationError) as revoked_replay:
            create_admin_ai_response(
                session,
                ADMIN_USER_ID,
                "Costo promedio",
                BRANCH_ID,
                parent_proposal_id=initial["id"],
                clarification_choice="missing_average_cost",
                conversation_idempotency_key=_conversation_key(4),
            )
        assert revoked_replay.value.code == "permission_denied"
        session.rollback()

        with pytest.raises(AdminAiError) as reused_parent:
            create_admin_ai_response(
                session,
                ADMIN_USER_ID,
                "De compra",
                BRANCH_ID,
                parent_proposal_id=initial["id"],
                conversation_idempotency_key=_conversation_key(5),
            )
        assert reused_parent.value.code == "admin_ai_conversation_invalid"


def test_tdd_tc_209_parent_is_private_to_actor_and_terminal_turns_cannot_continue() -> None:
    factory = _factory()
    with factory() as session:
        now = datetime(2026, 8, 29, 20, 0, tzinfo=UTC)
        session.execute(
            models.users.insert().values(
                id=OTHER_ADMIN_ID,
                organization_id="018f6f73-2d0a-74f0-8f1c-000000000001",
                email="other-admin@example.invalid",
                display_name="Otro administrador",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            models.user_roles.insert().values(
                user_id=OTHER_ADMIN_ID,
                role_id="018f6f73-2d0a-74f0-8f1c-000000000005",
                branch_id=None,
            )
        )
        session.commit()
        initial = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "¿Qué insumos no tienen precio?",
            BRANCH_ID,
        )

        with pytest.raises(AdminAiError) as other_actor:
            create_admin_ai_response(
                session,
                OTHER_ADMIN_ID,
                "De compra",
                BRANCH_ID,
                parent_proposal_id=initial["id"],
                conversation_idempotency_key=_conversation_key(6),
            )
        assert other_actor.value.code == "admin_ai_conversation_invalid"

        rejected = review_proposal(session, initial["id"], ADMIN_USER_ID, False)
        assert rejected["status"] == "REJECTED"
        with pytest.raises(AdminAiError) as terminal:
            create_admin_ai_response(
                session,
                ADMIN_USER_ID,
                "De compra",
                BRANCH_ID,
                parent_proposal_id=initial["id"],
                conversation_idempotency_key=_conversation_key(7),
            )
        assert terminal.value.code == "admin_ai_conversation_invalid"

        expired = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "¿Qué insumos no tienen precio?",
            BRANCH_ID,
        )
        session.execute(
            models.admin_ai_proposals.update()
            .where(models.admin_ai_proposals.c.id == expired["id"])
            .values(expires_at=datetime(2020, 1, 1, tzinfo=UTC))
        )
        session.commit()
        with pytest.raises(AdminAiError) as expired_parent:
            create_admin_ai_response(
                session,
                ADMIN_USER_ID,
                "De compra",
                BRANCH_ID,
                parent_proposal_id=expired["id"],
                conversation_idempotency_key=_conversation_key(8),
            )
        assert expired_parent.value.code == "admin_ai_conversation_invalid"

        limited = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "¿Qué insumos no tienen precio?",
            BRANCH_ID,
        )
        limited_payload = dict(limited["payload"])
        limited_payload["clarification"] = {
            **limited_payload["clarification"],
            "turn": admin_ai.ADMIN_AI_CONVERSATION_TURN_LIMIT,
        }
        session.execute(
            models.admin_ai_proposals.update()
            .where(models.admin_ai_proposals.c.id == limited["id"])
            .values(payload=limited_payload)
        )
        session.commit()
        with pytest.raises(AdminAiError) as limited_parent:
            create_admin_ai_response(
                session,
                ADMIN_USER_ID,
                "De compra",
                BRANCH_ID,
                parent_proposal_id=limited["id"],
                conversation_idempotency_key=_conversation_key(9),
            )
        assert limited_parent.value.code == "admin_ai_conversation_invalid"


def test_tdd_tc_209_each_turn_revalidates_the_requested_branch_scope() -> None:
    factory = _factory()
    branch_admin_id = "018f6f73-2d0a-74f0-8f1c-000000000705"
    branch_role_id = "018f6f73-2d0a-74f0-8f1c-000000000706"
    now = datetime(2026, 8, 29, 20, 0, tzinfo=UTC)
    with factory() as session:
        source_branch = session.execute(
            sa.select(models.branches).where(models.branches.c.id == BRANCH_ID)
        ).mappings().one()
        session.execute(
            models.branches.insert().values(
                id=OTHER_BRANCH_ID,
                organization_id=source_branch["organization_id"],
                legal_entity_id=source_branch["legal_entity_id"],
                business_unit_id=source_branch["business_unit_id"],
                name="Sucursal alterna AIA",
                code="AIA-ALT",
                timezone=source_branch["timezone"],
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        catalog_permission_id = session.execute(
            sa.select(models.permissions.c.id).where(
                models.permissions.c.code == "catalog.manage"
            )
        ).scalar_one()
        session.execute(
            models.users.insert().values(
                id=branch_admin_id,
                organization_id="018f6f73-2d0a-74f0-8f1c-000000000001",
                email="branch-admin@example.invalid",
                display_name="Administrador de sucursal",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            models.roles.insert().values(
                id=branch_role_id,
                organization_id="018f6f73-2d0a-74f0-8f1c-000000000001",
                name="Administrador de catálogo de sucursal",
                scope="branch",
                created_at=now,
            )
        )
        session.execute(
            models.role_permissions.insert().values(
                role_id=branch_role_id,
                permission_id=catalog_permission_id,
            )
        )
        session.execute(
            models.user_roles.insert().values(
                user_id=branch_admin_id,
                role_id=branch_role_id,
                branch_id=BRANCH_ID,
            )
        )
        session.commit()

        initial = create_admin_ai_response(
            session,
            branch_admin_id,
            "¿Qué insumos no tienen precio?",
            BRANCH_ID,
        )
        assert initial["status"] == "DRAFT"

        with pytest.raises(AuthorizationError) as wrong_branch:
            create_admin_ai_response(
                session,
                branch_admin_id,
                "De compra",
                OTHER_BRANCH_ID,
                parent_proposal_id=initial["id"],
                conversation_idempotency_key=_conversation_key(10),
            )
        assert wrong_branch.value.code == "permission_denied"


def test_tdd_tc_209_http_follow_up_accepts_parent_and_canonical_choice() -> None:
    factory = _factory()
    with factory() as session:
        _seed_purchase_price(session)
    client = _client(factory)
    headers = {"X-Actor-User-Id": ADMIN_USER_ID}
    idempotency_key = _conversation_key(14)

    initial = client.post(
        "/api/v1/admin-ai/proposals",
        headers=headers,
        json={"prompt": "¿Qué insumos no tienen precio?", "branch_id": BRANCH_ID},
    )
    assert initial.status_code == 200, initial.text

    resolved = client.post(
        "/api/v1/admin-ai/proposals",
        headers=headers,
        json={
            "prompt": "Precio de compra",
            "branch_id": BRANCH_ID,
            "parent_proposal_id": initial.json()["id"],
            "clarification_choice": "missing_purchase_price",
            "conversation_idempotency_key": idempotency_key,
        },
    )

    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["payload"]["diagnostic"]["kind"] == "missing_purchase_price"
    replayed = client.post(
        "/api/v1/admin-ai/proposals",
        headers=headers,
        json={
            "prompt": "Precio de compra",
            "branch_id": BRANCH_ID,
            "parent_proposal_id": initial.json()["id"],
            "clarification_choice": "missing_purchase_price",
            "conversation_idempotency_key": idempotency_key,
        },
    )
    assert replayed.status_code == 200, replayed.text
    assert replayed.json()["id"] == resolved.json()["id"]


def test_tdd_tc_207_purchase_price_diagnostic_is_exact_and_branch_scoped() -> None:
    factory = _factory()

    def provider_should_not_run(
        _prompt: str, _context: dict[str, Any], _options: AdminAiProviderOptions
    ) -> dict[str, Any]:
        raise AssertionError("Canonical purchase diagnostics must not reach the provider")

    with factory() as session:
        _seed_purchase_price(session)
        response = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "¿Qué insumos no tienen precio de compra?",
            BRANCH_ID,
            OPTIONS,
            provider_should_not_run,
        )

        assert response["status"] == "DRAFT"
        assert response["payload"]["sources"] == ["PRD-FR-093", "PRD-FR-094"]
        assert response["payload"]["change_set"] == []
        diagnostic = response["payload"]["diagnostic"]
        assert diagnostic["kind"] == "missing_purchase_price"
        assert diagnostic["total"] == 3
        assert [item["sku"] for item in diagnostic["items"]] == [
            "INV-SYRUP",
            "INV-BUN",
            "INV-POTATO",
        ]
        assert ITEM_ID not in {item["id"] for item in diagnostic["items"]}
        assert ITEM_ID not in response["payload"]["answer"]

        session.execute(
            models.supplier_branch_terms.insert().values(
                supplier_id=SUPPLIER_ID,
                branch_id=BRANCH_ID,
                is_enabled=False,
                updated_at=datetime(2026, 8, 29, 18, 5, tzinfo=UTC),
            )
        )
        session.commit()
        disabled = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "Lista los insumos sin presentación de compra",
            BRANCH_ID,
            OPTIONS,
            provider_should_not_run,
        )
        assert disabled["payload"]["diagnostic"]["total"] == 4
        assert ITEM_ID in {item["id"] for item in disabled["payload"]["diagnostic"]["items"]}

        session.execute(
            models.supplier_branch_terms.delete().where(
                models.supplier_branch_terms.c.supplier_id == SUPPLIER_ID,
                models.supplier_branch_terms.c.branch_id == BRANCH_ID,
            )
        )
        session.execute(
            models.purchase_presentations.update()
            .where(models.purchase_presentations.c.id == PRESENTATION_ID)
            .values(last_net_price=0)
        )
        session.commit()
        zero_price = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "¿Qué insumos no tienen precio de compra?",
            BRANCH_ID,
            OPTIONS,
            provider_should_not_run,
        )
        assert zero_price["payload"]["diagnostic"]["total"] == 4

        session.execute(
            models.purchase_presentations.update()
            .where(models.purchase_presentations.c.id == PRESENTATION_ID)
            .values(last_net_price=120, status="inactive")
        )
        session.commit()
        inactive_presentation = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "¿Qué insumos no tienen precio de compra?",
            BRANCH_ID,
            OPTIONS,
            provider_should_not_run,
        )
        assert inactive_presentation["payload"]["diagnostic"]["total"] == 4

        session.execute(
            models.purchase_presentations.update()
            .where(models.purchase_presentations.c.id == PRESENTATION_ID)
            .values(status="active")
        )
        session.execute(
            models.suppliers.update()
            .where(models.suppliers.c.id == SUPPLIER_ID)
            .values(status="inactive")
        )
        session.commit()
        inactive_supplier = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "¿Qué insumos no tienen precio de compra?",
            BRANCH_ID,
            OPTIONS,
            provider_should_not_run,
        )
        assert inactive_supplier["payload"]["diagnostic"]["total"] == 4

        missing_scope = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "¿Qué insumos no tienen precio de compra?",
            None,
            OPTIONS,
            provider_should_not_run,
        )
        assert missing_scope["status"] == "DRAFT"
        assert missing_scope["payload"]["diagnostic"] is None
        assert "sucursal" in missing_scope["payload"]["questions"][0].casefold()


def test_tdd_tc_207_average_cost_diagnostic_uses_confirmed_state_without_values() -> None:
    factory = _factory()

    def provider_should_not_run(
        _prompt: str, _context: dict[str, Any], _options: AdminAiProviderOptions
    ) -> dict[str, Any]:
        raise AssertionError("Canonical cost diagnostics must not reach the provider")

    with factory() as session:
        now = datetime(2026, 8, 29, 18, 10, tzinfo=UTC)
        session.execute(
            models.inventory_cost_states.insert().values(
                branch_id=BRANCH_ID,
                warehouse_id=WAREHOUSE_ID,
                item_id=ITEM_ID,
                quantity_on_hand=10,
                average_unit_cost=25,
                last_unit_cost=25,
                last_supplier_id=None,
                last_cost_at=now,
                updated_at=now,
            )
        )
        session.commit()
        response = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "¿Qué insumos no tienen costo promedio?",
            BRANCH_ID,
            OPTIONS,
            provider_should_not_run,
        )

        diagnostic = response["payload"]["diagnostic"]
        assert response["status"] == "DRAFT"
        assert response["payload"]["change_set"] == []
        assert diagnostic["kind"] == "missing_average_cost"
        assert diagnostic["scope"]["branch_id"] == BRANCH_ID
        assert diagnostic["scope"]["warehouse_id"] == WAREHOUSE_ID
        assert diagnostic["total"] == 3
        assert ITEM_ID not in {item["id"] for item in diagnostic["items"]}
        serialized = json.dumps(response["payload"], ensure_ascii=False)
        for forbidden in (
            "quantity_on_hand",
            "average_unit_cost",
            "last_unit_cost",
            "last_supplier_id",
        ):
            assert forbidden not in serialized

        session.execute(
            models.inventory_cost_states.update()
            .where(
                models.inventory_cost_states.c.branch_id == BRANCH_ID,
                models.inventory_cost_states.c.warehouse_id == WAREHOUSE_ID,
                models.inventory_cost_states.c.item_id == ITEM_ID,
            )
            .values(average_unit_cost=0, last_unit_cost=0)
        )
        session.commit()
        confirmed_zero = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "¿Qué insumos no tienen costo promedio?",
            BRANCH_ID,
            OPTIONS,
            provider_should_not_run,
        )
        assert confirmed_zero["payload"]["diagnostic"]["total"] == 3

        session.execute(
            models.inventory_cost_states.update()
            .where(
                models.inventory_cost_states.c.branch_id == BRANCH_ID,
                models.inventory_cost_states.c.warehouse_id == WAREHOUSE_ID,
                models.inventory_cost_states.c.item_id == ITEM_ID,
            )
            .values(last_cost_at=None)
        )
        session.commit()
        unconfirmed = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "¿Qué insumos no tienen costo promedio?",
            BRANCH_ID,
            OPTIONS,
            provider_should_not_run,
        )
        assert unconfirmed["payload"]["diagnostic"]["total"] == 4

        missing_scope = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "¿Qué insumos no tienen costo promedio?",
            None,
            OPTIONS,
            provider_should_not_run,
        )
        assert missing_scope["status"] == "DRAFT"
        assert missing_scope["payload"]["diagnostic"] is None
        assert "sucursal" in missing_scope["payload"]["questions"][0].casefold()


def test_tdd_tc_207_average_cost_requires_inventory_read() -> None:
    factory = _factory()

    with factory() as session:
        inventory_read_id = session.execute(
            sa.select(models.permissions.c.id).where(models.permissions.c.code == "inventory.read")
        ).scalar_one()
        session.execute(
            models.role_permissions.delete().where(
                models.role_permissions.c.permission_id == inventory_read_id
            )
        )
        session.commit()

        with pytest.raises(AuthorizationError):
            create_admin_ai_response(
                session,
                ADMIN_USER_ID,
                "¿Qué insumos no tienen costo promedio?",
                BRANCH_ID,
                OPTIONS,
                lambda *_args: pytest.fail("Unauthorized diagnostic reached the provider"),
            )

        assert (
            session.execute(
                sa.select(sa.func.count()).select_from(models.admin_ai_proposals)
            ).scalar_one()
            == 0
        )


def test_tdd_tc_207_read_and_review_revalidate_diagnostic_permission() -> None:
    factory = _factory()
    with factory() as session:
        proposal = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "¿Qué insumos no tienen costo promedio?",
            BRANCH_ID,
            OPTIONS,
            lambda *_args: pytest.fail("Canonical cost diagnostic reached provider"),
        )
        inventory_read_id = session.execute(
            sa.select(models.permissions.c.id).where(models.permissions.c.code == "inventory.read")
        ).scalar_one()
        session.execute(
            models.role_permissions.delete().where(
                models.role_permissions.c.permission_id == inventory_read_id
            )
        )
        session.commit()

        with pytest.raises(AuthorizationError):
            get_proposal(session, proposal["id"], ADMIN_USER_ID)
        with pytest.raises(AuthorizationError):
            review_proposal(session, proposal["id"], ADMIN_USER_ID, False)

        assert (
            session.execute(
                sa.select(models.admin_ai_proposals.c.status).where(
                    models.admin_ai_proposals.c.id == proposal["id"]
                )
            ).scalar_one()
            == "DRAFT"
        )


def test_tdd_tc_207_purchase_read_uses_canonical_catalog_compatibility() -> None:
    factory = _factory()
    with factory() as session:
        proposal = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "¿Qué insumos no tienen precio de compra?",
            BRANCH_ID,
            OPTIONS,
            lambda *_args: pytest.fail("Canonical purchase diagnostic reached provider"),
        )
        purchases_read_id = session.execute(
            sa.select(models.permissions.c.id).where(models.permissions.c.code == "purchases.read")
        ).scalar_one()
        session.execute(
            models.role_permissions.delete().where(
                models.role_permissions.c.permission_id == purchases_read_id
            )
        )
        session.commit()

        fetched = get_proposal(session, proposal["id"], ADMIN_USER_ID)
        rejected = review_proposal(session, proposal["id"], ADMIN_USER_ID, False)

        assert fetched["payload"]["diagnostic"]["kind"] == "missing_purchase_price"
        assert rejected["status"] == "REJECTED"


def test_tdd_tc_207_external_context_excludes_purchase_and_cost_projections() -> None:
    factory = _factory()
    with factory() as session:
        _seed_purchase_price(session)
        session.info["admin_ai_organization_id"] = str(
            session.scalar(
                sa.select(models.branches.c.organization_id).where(
                    models.branches.c.id == BRANCH_ID
                )
            )
        )
        context = build_context(session, BRANCH_ID)

    assert not {
        "diagnostic",
        "purchase_presentations",
        "supplier_price_history",
        "suppliers",
        "inventory_cost_states",
    }.intersection(context)
    serialized = json.dumps(context, ensure_ascii=False)
    assert "last_net_price" not in serialized
    assert "average_unit_cost" not in serialized


def test_tdd_tc_207_diagnostic_output_is_bounded_and_sanitizes_labels() -> None:
    factory = _factory()
    now = datetime(2026, 8, 29, 18, 20, tzinfo=UTC)
    raw_uuid = "11111111-2222-3333-4444-555555555555"
    rows = [
        {
            "id": f"20000000-0000-0000-0000-{index:012d}",
            "organization_id": "018f6f73-2d0a-74f0-8f1c-000000000001",
            "name": raw_uuid if index == 0 else f"Insumo sintético {index:03d}",
            "sku": raw_uuid if index == 0 else f"AIA-{index:03d}",
            "base_unit_id": UNIT_ID,
            "item_type": "ingredient",
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        for index in range(101)
    ]

    with factory() as session:
        session.execute(models.inventory_items.insert(), rows)
        session.commit()
        response = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "Lista los insumos sin precio de compra",
            BRANCH_ID,
            OPTIONS,
            lambda *_args: pytest.fail("Bounded diagnostic reached the provider"),
        )

    diagnostic = response["payload"]["diagnostic"]
    assert diagnostic["total"] == 105
    assert len(diagnostic["items"]) == 100
    assert diagnostic["truncated"] is True
    assert "detalle está limitado a 100 registros" in response["payload"]["answer"]
    assert raw_uuid not in response["payload"]["answer"]
    sanitized = next(item for item in diagnostic["items"] if item["id"] == rows[0]["id"])
    assert sanitized["name"] is None
    assert sanitized["sku"] is None
    assert sanitized["label"] == "Insumo sin etiqueta legible"


def test_tdd_tc_207_branch_scope_excludes_items_from_other_branch() -> None:
    factory = _factory()
    now = datetime(2026, 8, 29, 18, 30, tzinfo=UTC)
    local_item_id = "30000000-0000-0000-0000-000000000001"
    other_item_id = "30000000-0000-0000-0000-000000000002"

    with factory() as session:
        session.execute(
            models.branches.insert().values(
                id=OTHER_BRANCH_ID,
                organization_id="018f6f73-2d0a-74f0-8f1c-000000000001",
                legal_entity_id="018f6f73-2d0a-74f0-8f1c-000000000002",
                business_unit_id="018f6f73-2d0a-74f0-8f1c-000000000015",
                name="Sucursal ajena sintética",
                code="AIA-OTHER",
                timezone="America/Mazatlan",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            models.inventory_items.insert(),
            [
                {
                    "id": local_item_id,
                    "organization_id": "018f6f73-2d0a-74f0-8f1c-000000000001",
                    "name": "Insumo local",
                    "sku": "AIA-LOCAL",
                    "base_unit_id": UNIT_ID,
                    "item_type": "ingredient",
                    "catalog_scope": "branch",
                    "source_branch_id": BRANCH_ID,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": other_item_id,
                    "organization_id": "018f6f73-2d0a-74f0-8f1c-000000000001",
                    "name": "Insumo de otra sucursal",
                    "sku": "AIA-OTHER",
                    "base_unit_id": UNIT_ID,
                    "item_type": "ingredient",
                    "catalog_scope": "branch",
                    "source_branch_id": OTHER_BRANCH_ID,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )
        session.commit()
        purchase = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "¿Qué insumos no tienen precio de compra?",
            BRANCH_ID,
            OPTIONS,
            lambda *_args: pytest.fail("Scoped purchase diagnostic reached provider"),
        )
        average_cost = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "¿Qué insumos no tienen costo promedio?",
            BRANCH_ID,
            OPTIONS,
            lambda *_args: pytest.fail("Scoped cost diagnostic reached provider"),
        )

    for proposal in (purchase, average_cost):
        ids = {item["id"] for item in proposal["payload"]["diagnostic"]["items"]}
        assert local_item_id in ids
        assert other_item_id not in ids


def test_tdd_tc_207_http_boundary_serializes_canonical_diagnostic() -> None:
    client = _client(_factory())
    response = client.post(
        "/api/v1/admin-ai/proposals",
        headers={"X-Actor-User-Id": ADMIN_USER_ID},
        json={
            "prompt": "¿Qué insumos no tienen precio de compra?",
            "branch_id": BRANCH_ID,
        },
    )

    assert response.status_code == 200, response.text
    proposal = response.json()
    assert proposal["status"] == "DRAFT"
    assert proposal["payload"]["diagnostic"]["kind"] == "missing_purchase_price"
    assert proposal["payload"]["diagnostic"]["total"] == 4
    assert proposal["payload"]["change_set"] == []


def test_tdd_tc_206_configuration_prompt_with_inventory_and_price_reaches_provider() -> None:
    factory = _factory()
    prompt = "Crea insumo QUESO NUEVO SIN PRECIO SKU 9001 tipo ingredient unidad Gramo"
    raw = _result(
        "inventory_item.create",
        None,
        {
            "name": "QUESO NUEVO",
            "sku": "9001",
            "base_unit_id": UNIT_ID,
            "item_type": "ingredient",
        },
        [
            {"field": "name", "quote": "QUESO NUEVO"},
            {"field": "sku", "quote": "9001"},
            {"field": "item_type", "quote": "ingredient"},
            {"field": "base_unit_id", "quote": "unidad Gramo"},
        ],
    )
    captured: dict[str, Any] = {}

    with factory() as session:
        response = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            prompt,
            BRANCH_ID,
            OPTIONS,
            _fake(raw, captured),
        )

        assert captured["prompt"] == prompt
        assert response["status"] == "READY_FOR_REVIEW"
        assert response["payload"]["change_set"][0]["kind"] == "inventory_item.create"


def test_tdd_tc_206_provider_visible_text_cannot_expose_technical_ids() -> None:
    factory = _factory()
    raw = {
        "answer": f"El insumo {ITEM_ID} no tiene precio.",
        "sources": ["PRD-FR-093"],
        "questions": [],
        "warnings": [],
        "change_set": [],
    }

    with factory() as session:
        with pytest.raises(AdminAiError) as error:
            create_admin_ai_response(
                session,
                ADMIN_USER_ID,
                "¿Cómo se administra el catálogo?",
                BRANCH_ID,
                OPTIONS,
                _fake(raw),
            )

        assert error.value.code == "admin_ai_provider_invalid_response"


def test_tdd_tc_206_natural_inventory_cost_question_is_also_clarified() -> None:
    factory = _factory()

    def provider_should_not_run(
        _prompt: str, _context: dict[str, Any], _options: AdminAiProviderOptions
    ) -> dict[str, Any]:
        raise AssertionError("Natural ambiguous cost questions must not reach the provider")

    with factory() as session:
        response = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "¿Cuánto cuestan los ingredientes?",
            BRANCH_ID,
            OPTIONS,
            provider_should_not_run,
        )

        assert response["status"] == "DRAFT"
        assert len(response["payload"]["questions"]) == 1
        assert response["payload"]["change_set"] == []


@pytest.mark.parametrize(
    "prompt",
    [
        "¿Qué insumos debo actualizar porque no tienen precio?",
        "Crea una lista de insumos sin precio",
    ],
)
def test_tdd_tc_206_diagnostic_intent_wins_over_incidental_configuration_verbs(
    prompt: str,
) -> None:
    factory = _factory()

    def provider_should_not_run(
        _prompt: str, _context: dict[str, Any], _options: AdminAiProviderOptions
    ) -> dict[str, Any]:
        raise AssertionError("Diagnostic requests must not be reclassified by incidental verbs")

    with factory() as session:
        response = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            prompt,
            BRANCH_ID,
            OPTIONS,
            provider_should_not_run,
        )

        assert response["status"] == "DRAFT"
        assert len(response["payload"]["questions"]) == 1
        assert response["payload"]["change_set"] == []


def test_tdd_tc_206_relative_que_in_configuration_does_not_trigger_diagnostic() -> None:
    factory = _factory()
    prompt = "Crea la opción SIN QUESO que quite el ingrediente QUESO con precio 0"
    raw = {
        "answer": "Necesito que indiques el grupo de modificadores.",
        "sources": ["PRD-FR-095"],
        "questions": ["¿En qué grupo debo crear la opción SIN QUESO?"],
        "warnings": [],
        "change_set": [],
    }
    captured: dict[str, Any] = {}

    with factory() as session:
        response = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            prompt,
            BRANCH_ID,
            OPTIONS,
            _fake(raw, captured),
        )

        assert captured["prompt"] == prompt
        assert response["status"] == "DRAFT"
        assert response["payload"]["questions"] == raw["questions"]


def test_tdd_tc_209_generic_follow_up_uses_ephemeral_user_context_only() -> None:
    factory = _factory()
    original_prompt = "Crea la opción SIN QUESO con precio 0"
    initial_raw = {
        "answer": "Necesito que indiques el grupo de modificadores.",
        "sources": ["PRD-FR-095"],
        "questions": ["¿En qué grupo debo crear la opción SIN QUESO?"],
        "warnings": [],
        "change_set": [],
    }
    follow_up_raw = {
        "answer": "Ya tengo la información necesaria para orientarte.",
        "sources": ["PRD-FR-095"],
        "questions": [],
        "warnings": [],
        "change_set": [],
    }
    captured: dict[str, Any] = {}

    with factory() as session:
        initial = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            original_prompt,
            BRANCH_ID,
            OPTIONS,
            _fake(initial_raw),
        )

        with pytest.raises(AdminAiError) as missing_context:
            create_admin_ai_response(
                session,
                ADMIN_USER_ID,
                "En el grupo ADEREZOS",
                BRANCH_ID,
                OPTIONS,
                _fake(follow_up_raw),
                parent_proposal_id=initial["id"],
                conversation_idempotency_key=_conversation_key(11),
            )
        assert missing_context.value.code == "admin_ai_conversation_context_required"

        with pytest.raises(AdminAiError) as unoffered_choice:
            create_admin_ai_response(
                session,
                ADMIN_USER_ID,
                "En el grupo ADEREZOS",
                BRANCH_ID,
                OPTIONS,
                _fake(follow_up_raw),
                parent_proposal_id=initial["id"],
                clarification_choice="missing_purchase_price",
                conversation_context=[original_prompt],
                conversation_idempotency_key=_conversation_key(12),
            )
        assert unoffered_choice.value.code == "admin_ai_conversation_invalid"

        follow_up = create_admin_ai_response(
            session,
            ADMIN_USER_ID,
            "En el grupo ADEREZOS",
            BRANCH_ID,
            OPTIONS,
            _fake(follow_up_raw, captured),
            parent_proposal_id=initial["id"],
            conversation_context=[original_prompt],
            conversation_idempotency_key=_conversation_key(13),
        )

        assert original_prompt in captured["prompt"]
        assert "En el grupo ADEREZOS" in captured["prompt"]
        assert follow_up["payload"]["conversation"] == {
            "parent_proposal_id": initial["id"],
            "turn": 2,
            "idempotency_key": _conversation_key(13),
        }
        persisted = json.dumps(follow_up["payload"])
        assert original_prompt not in persisted
        assert "En el grupo ADEREZOS" not in persisted
