from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Any, Literal, Optional, TypeVar
import uuid
from uuid import UUID

# ruff: noqa: E501, E402, I001
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from restaurant_os import models
from restaurant_os.saas_onboarding import SignUpRequest, signup_tenant
from restaurant_os.auth import create_session_token, verify_session_token
from restaurant_os.assisted_order import (
    AssistedOrderError,
    OpenRouterOptions,
    build_assisted_draft,
)
from restaurant_os.admin_ai import (
    AdminAiError,
    AdminAiProviderOptions,
    create_admin_ai_response,
    get_proposal,
    review_proposal,
)
from restaurant_os.executive_ai import (
    ExecutiveAiProviderOptions,
    generate_executive_insights,
)
from restaurant_os.inventory_ai import (
    calculate_suggested_purchases,
    audit_inventory_yield_and_waste,
    parse_supplier_invoice_data,
)
from restaurant_os.customer_ai import (
    get_customer_upsell_recommendations,
    get_crm_segments_and_churn_risk,
    generate_churn_recovery_message,
)
from restaurant_os.config import get_settings
from restaurant_os.database import get_session
from restaurant_os.legacy_import import (
    complete_legacy_import_batch,
    create_legacy_import_batch,
    ingest_legacy_import_records,
    list_branch_legacy_import_batches,
    list_legacy_import_batches,
    list_legacy_import_records,
)
from restaurant_os.recipe_ai import (
    calculate_theoretical_recipe_cost,
    match_ingredient_to_catalog,
    normalize_culinary_quantity,
    parse_recipe_text,
)
from restaurant_os.integrations import channel_service
from restaurant_os.invoicing.service import InvoicingService
from restaurant_os.operational_guard import OperationalRouteGuard

invoicing_service = InvoicingService()
from restaurant_os.operations import (
    ORGANIZATION_ID,
    AuthorizationError,
    BusinessError,
    NotFoundError,
    OperationalCloseResponse,
    ReportingProjectionService,
    UserCashCutService,
    accept_pending_order,
    accept_public_order_intent,
    acknowledge_print_attempt,
    add_customer_address,
    add_supplier_contact,
    advance_kds_task,
    amend_order,
    apply_ingredient_variation_assignments,
    apply_order_reopen_request,
    approve_physical_count_session,
    archive_cash_concept,
    archive_ingredient_variation_assignment,
    archive_modifier_group,
    archive_modifier_option,
    assign_product_category_option,
    assign_user_role,
    authenticate_user,
    authorize_branch_scope,
    authorize_cash_movement_scope,
    authorize_order_adjustment,
    authorize_supervisor_step_up,
    build_session_profile,
    bulk_order_comments,
    cancel_inventory_transfer,
    cancel_physical_count_session,
    cancel_purchase_document,
    capture_physical_count_line,
    category_option_coverage,
    claim_print_attempt,
    close_cash_shift_operationally,
    close_cash_shift_operationally_for_register,
    close_physical_count_session,
    compensate_cash_movement,
    confirm_production_batch,
    confirm_purchase_document,
    confirm_waste_record,
    consume_pos_session_handoff,
    fail_print_attempt,
    fulfill_order,
    create_branch,
    create_business_unit,
    create_cash_concept,
    create_cash_concept_version,
    create_cash_movement,
    create_customer,
    create_driver,
    create_ingredient_variation,
    create_inventory_transfer,
    create_local_order,
    create_modifier_group,
    create_modifier_option,
    clone_modifier_group,
    clone_all_modifier_groups,
    reorder_modifier_groups,
    reorder_modifier_options,
    create_order_reopen_request,
    count_pending_orders,
    create_physical_count_session,
    create_pos_session_handoff,
    create_product,
    create_production_batch,
    create_production_recipe,
    create_public_order_intent,
    create_purchase_document,
    create_purchase_presentation,
    create_role,
    create_supplier,
    create_user,
    create_variation_note,
    create_waste_reason,
    create_waste_record,
    deactivate_driver,
    decide_order_reopen_request,
    delete_branch,
    delete_product,
    delete_user,
    get_branch_context,
    get_cash_shift_summary,
    get_ingredient_variation,
    get_open_cash_shift,
    get_order_detail,
    get_public_catalog,
    get_public_order_intent,
    reject_public_order_intent,
    get_sync_status,
    issue_offline_cash_grant,
    list_attendance_checks,
    list_available_delivery_drivers,
    list_available_ingredient_extras,
    list_branch_admin_catalog_products,
    list_branch_ingredient_variations,
    list_branch_staff,
    list_branch_variation_notes,
    list_cash_concepts,
    list_cash_movement_ledger,
    list_cash_movements,
    list_customers,
    list_customers_page,
    list_driver_deliveries,
    list_drivers,
    list_effective_cash_concepts,
    list_ingredient_variations,
    list_inventory_cost_states,
    list_inventory_transfers,
    list_kds_tasks,
    list_order_accounts,
    list_order_comments,
    list_order_reopen_requests,
    list_payments,
    list_physical_count_sessions,
    list_print_jobs,
    list_queued_print_attempts,
    list_product_modifiers,
    list_production_batches,
    list_public_branches,
    list_purchase_documents,
    list_purchase_presentations,
    list_recent_orders,
    list_suppliers,
    list_sync_events,
    list_variation_notes,
    list_waste_reasons,
    list_waste_records,
    open_cash_shift_idempotently,
    pay_order,
    preview_ingredient_variation_assignments,
    preview_order_comments_bulk,
    quote_local_order,
    receive_inventory_transfer,
    receive_sync_command,
    recover_expired_print_claim,
    record_attendance_check,
    record_inventory_opening_balance,
    record_pco004_metric,
    recover_local_order_creation,
    repeat_order,
    replace_order_comment_products,
    require_permission,
    retry_print_job,
    reverse_waste_record,
    send_inventory_transfer,
    set_branch_ingredient_variation_option,
    set_branch_modifier_option,
    set_branch_product_availability,
    set_branch_variation_note,
    set_supplier_branch_terms,
    submit_physical_count_session,
    update_branch,
    update_customer,
    update_customer_address,
    update_driver,
    update_ingredient_variation,
    update_modifier_group,
    update_modifier_option,
    update_order_comment,
    update_product,
    update_purchase_presentation_price,
    update_purchase_presentation,
    update_supplier,
    delete_supplier,
    update_user,
    update_variation_note,
    update_waste_reason,
    upsert_category_option_group,
    upsert_category_option_value,
    upsert_customer_tax_profile,
)
from restaurant_os.operations import (
    cancel_order as cancel_order_operation,
)
from restaurant_os.operations import (
    get_category_option_group_coverage as get_category_option_group_coverage_operation,
)
from restaurant_os.platform_data import (
    bootstrap_status,
    get_catalog_cleanup_status,
    get_dashboard_overview,
    list_active_recipes,
    list_branches,
    list_business_units,
    list_catalog_products,
    list_inventory_kardex,
    list_inventory_stock,
    list_organizations,
    list_roles,
    list_users,
)

router = APIRouter(prefix="/api/v1", tags=["platform-api"])
operational_route_guard = OperationalRouteGuard()


SessionDep = Annotated[Session, Depends(get_session)]
ActorUserDep = Annotated[Optional[str], Header(alias="X-Actor-User-Id")]
AuthorizationDep = Annotated[Optional[str], Header(alias="Authorization")]
IdempotencyKeyDep = Annotated[Optional[str], Header(alias="Idempotency-Key")]
DeviceTokenDep = Annotated[Optional[str], Header(alias="X-Device-Token")]


class RecipeComponentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: UUID
    unit_id: UUID
    net_quantity: Decimal = Field(gt=Decimal("0"))
    waste_rate: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))

    @field_validator("waste_rate", mode="before")
    @classmethod
    def normalize_waste_rate(cls, v: Any) -> Any:
        if v is None or v == "" or v is False:
            return Decimal("0")
        val = Decimal(str(v))
        if val >= Decimal("1"):
            val = val / Decimal("100")
        if val < Decimal("0"):
            val = Decimal("0")
        if val >= Decimal("1"):
            val = Decimal("0.9999")
        return val


class RecipeVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_id: UUID | None = None
    expected_active_recipe_id: UUID | None = None
    yield_quantity: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))
    yield_unit_id: UUID | None = None
    components: list[RecipeComponentRequest] = Field(min_length=1)

    @field_validator("branch_id", "expected_active_recipe_id", "yield_unit_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: Any) -> Any:
        if v == "" or v is False:
            return None
        return v


class PrintFailureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_code: str = Field(pattern=r"^[A-Z0-9_]{1,64}$")


class AssistedOrderDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_id: UUID
    text: str = Field(min_length=3, max_length=1000)


class AdminAiPromptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=1600)
    branch_id: UUID | None = None
    parent_proposal_id: UUID | None = None
    conversation_idempotency_key: UUID | None = None
    clarification_choice: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    conversation_context: list[Annotated[str, Field(min_length=1, max_length=1600)]] = Field(
        default_factory=list, max_length=4
    )


class AdminAiReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accept: bool


class ExecutiveAiPromptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=1600)
    branch_id: UUID | None = None


class SuggestedPurchasesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_id: UUID | None = None
    days_ahead: int = Field(default=7, ge=1, le=60)


class InvoiceOcrRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invoice_text: str = Field(min_length=1, max_length=10000)


class CustomerRecommendationsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: UUID | None = None
    branch_id: UUID | None = None
    current_product_ids: list[UUID] = Field(default_factory=list)


class CustomerRetargetingMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_name: str = Field(min_length=1, max_length=160)
    favorite_product_name: str = Field(default="tus platillos favoritos", max_length=160)
    discount_code: str | None = Field(default=None, max_length=40)


ResponseT = TypeVar("ResponseT")


def _actor_from_request(actor_user_id: str | None, authorization: str | None) -> str | None:
    settings = get_settings()
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        payload = verify_session_token(token, settings.secret_key)
        if payload and (payload.get("sub") or payload.get("user_id")):
            return str(payload.get("sub") or payload.get("user_id"))
    if actor_user_id and settings.environment != "production" and os.getenv("PYTEST_CURRENT_TEST"):
        return actor_user_id
    return None


def _required_actor_from_request(actor_user_id: str | None, authorization: str | None) -> str:
    actor_id = _actor_from_request(actor_user_id, authorization)
    if not actor_id:
        raise HTTPException(
            status_code=401,
            detail={"code": "actor_required", "message": "Actor authentication is required"},
        )
    return actor_id


def _actor_org_from_request(session: Session, actor_id: str) -> str:
    actor = session.execute(sa.select(models.users).where(models.users.c.id == actor_id)).mappings().first()
    return str(actor["organization_id"]) if actor and actor.get("organization_id") else ORGANIZATION_ID



@router.get("/platform/bootstrap-status")
def get_bootstrap_status(
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    def operation() -> dict[str, Any]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        require_permission(session, actor_id, "admin.manage")
        return bootstrap_status(session)

    return _business_response(operation)


@router.get("/dashboard/overview")
def get_dashboard_overview_endpoint(
    session: SessionDep,
    branch_id: str | None = None,
    month: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    def operation() -> dict[str, Any]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        authorized_branch_id = authorize_branch_scope(
            session, actor_id, "dashboard.read", branch_id
        )
        return get_dashboard_overview(session, authorized_branch_id, month)

    return _business_response(operation)

@router.post("/auth/signup", status_code=status.HTTP_201_CREATED)
def signup_endpoint(payload: SignUpRequest, session: SessionDep) -> dict[str, Any]:
    def operation() -> dict[str, Any]:
        return signup_tenant(session, payload.model_dump())

    return _business_response(operation)


@router.post("/auth/login")
def login(payload: dict[str, Any], session: SessionDep) -> dict[str, Any]:
    email = str(payload.get("email", ""))
    password = str(payload.get("password", ""))

    def operation() -> dict[str, Any]:
        user = authenticate_user(session, email, password)
        token = create_session_token(
            {"sub": user["id"], "email": user["email"]},
            get_settings().secret_key,
        )
        return {"token": token, "user": user}

    return _business_response(operation)


@router.post("/auth/supervisor-authorize")
def supervisor_authorize_endpoint(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    pin_or_code = str(
        payload.get("supervisor_pin") or payload.get("pin") or payload.get("code") or ""
    ).strip()
    branch_id = str(payload.get("branch_id") or "").strip()
    permission_code = str(payload.get("permission_code") or "orders.discount.authorize").strip()

    def operation() -> dict[str, Any]:
        return authorize_supervisor_step_up(
            session=session,
            supervisor_code_or_password=pin_or_code,
            branch_id=branch_id,
            permission_code=permission_code,
        )

    return _business_response(operation)


@router.get("/auth/session")
def get_authenticated_session_endpoint(
    session: SessionDep,
    branch_id: str | None = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    def operation() -> dict[str, Any]:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "token_required",
                    "message": "Authorization Bearer token is required",
                },
            )
        token = authorization.removeprefix("Bearer ").strip()
        payload = verify_session_token(token, get_settings().secret_key)
        if not payload or not payload.get("sub"):
            raise HTTPException(
                status_code=401,
                detail={"code": "token_invalid", "message": "Token is invalid or expired"},
            )
        actor_id = str(payload["sub"])
        return build_session_profile(session, actor_id, branch_id)

    try:
        return _database_response(operation)
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=403, detail={"code": exc.code, "message": exc.message}
        ) from exc
    except BusinessError as exc:
        raise HTTPException(
            status_code=409, detail={"code": exc.code, "message": exc.message}
        ) from exc


@router.post("/auth/pos-handoffs")
def issue_pos_session_handoff_endpoint(
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: create_pos_session_handoff(session, actor_id))


@router.post("/auth/pos-handoffs/exchange")
def exchange_pos_session_handoff_endpoint(
    payload: dict[str, Any], session: SessionDep
) -> dict[str, Any]:
    if set(payload) != {"handoff_code"}:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "pos_handoff_invalid",
                "message": "A handoff_code is required",
            },
        )

    def operation() -> dict[str, Any]:
        consumed = consume_pos_session_handoff(session, str(payload["handoff_code"]))
        token = create_session_token(
            {"sub": consumed["user_id"], "email": consumed["email"]},
            get_settings().secret_key,
        )
        return {"token": token}

    return _business_response(operation)


@router.get("/organizations")
def get_organizations(
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    def operation() -> list[dict[str, Any]]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        require_permission(session, actor_id, "admin.manage")
        return list_organizations(session)

    return _business_response(operation)


@router.get("/branches")
def get_branches(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    def operation() -> list[dict[str, Any]]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        require_permission(session, actor_id, "admin.manage")
        return list_branches(session)

    return _business_response(operation)


@router.get("/business-units")
def get_business_units(
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    def operation() -> list[dict[str, Any]]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        require_permission(session, actor_id, "catalog.manage")
        return list_business_units(session)

    return _business_response(operation)


@router.post("/business-units")
def post_business_unit(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: create_business_unit(
            session,
            str(payload.get("name", "")),
            str(payload.get("code", "")),
            str(payload.get("unit_type", "restaurant")),
            str(payload.get("legal_entity_id", "")),
            actor_id,
        )
    )


@router.post("/branches")
def post_branch(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    name = str(payload.get("name", ""))
    code = str(payload.get("code", ""))
    business_unit_id = str(payload.get("business_unit_id", "")) or None
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: create_branch(
            session,
            name=name,
            code=code,
            actor_user_id=actor_id,
            business_unit_id=business_unit_id,
            street=payload.get("street"),
            exterior_number=payload.get("exterior_number"),
            interior_number=payload.get("interior_number"),
            neighborhood=payload.get("neighborhood"),
            postal_code=payload.get("postal_code"),
            city=payload.get("city"),
            state=payload.get("state"),
            cross_streets=payload.get("cross_streets"),
            latitude=payload.get("latitude"),
            longitude=payload.get("longitude"),
            phone=payload.get("phone"),
        )
    )


@router.get("/drivers")
def get_drivers(
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: list_drivers(session, actor_id))


@router.get("/delivery/drivers/available")
def get_available_delivery_drivers(
    branch_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: list_available_delivery_drivers(session, branch_id, actor_id))


@router.get("/drivers/{driver_id}/deliveries")
def get_driver_deliveries(
    driver_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: list_driver_deliveries(session, driver_id, actor_id))


@router.post("/drivers")
def post_driver(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: create_driver(
            session,
            str(payload.get("branch_id", "")),
            payload,
            actor_id,
        )
    )


@router.put("/drivers/{driver_id}")
def put_driver(
    driver_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: update_driver(
            session,
            driver_id,
            str(payload.get("branch_id", "")),
            payload,
            actor_id,
        )
    )


@router.delete("/drivers/{driver_id}")
def delete_driver_endpoint(
    driver_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: deactivate_driver(session, driver_id, actor_id))


@router.get("/roles")
def get_roles(
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    def operation() -> list[dict[str, Any]]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        require_permission(session, actor_id, "admin.manage")
        return list_roles(session)

    return _business_response(operation)


@router.post("/roles")
def post_role(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    name = str(payload.get("name", ""))
    scope = str(payload.get("scope", "branch"))
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: create_role(session, name, scope, actor_id))


@router.get("/users")
def get_users(
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    def operation() -> list[dict[str, Any]]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        require_permission(session, actor_id, "admin.manage")
        return list_users(session)

    return _business_response(operation)


@router.post("/users")
def post_user(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    email = str(payload.get("email", ""))
    display_name = str(payload.get("display_name", ""))
    password = payload.get("password")
    role_id = payload.get("role_id")
    branch_id = payload.get("branch_id")
    employee_code = payload.get("employee_code")
    actor_id = _actor_from_request(actor_user_id, authorization)
    normalized_password = str(password) if password else None
    return _business_response(
        lambda: create_user(
            session,
            email,
            display_name,
            actor_id,
            normalized_password,
            role_id,
            branch_id,
            employee_code,
        )
    )


@router.post("/users/{user_id}/roles")
def post_user_role(
    user_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    role_id = str(payload.get("role_id", ""))
    branch_id = payload.get("branch_id")
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: assign_user_role(session, user_id, role_id, branch_id, actor_id)
    )


@router.get("/catalog/products")
def get_catalog_products(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    def operation() -> list[dict[str, Any]]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        user_org = session.execute(
            sa.select(models.users.c.organization_id).where(models.users.c.id == actor_id)
        ).scalar()
        org_id = str(user_org) if user_org else None
        if branch_id:
            authorized_branch = authorize_branch_scope(session, actor_id, "pos.operate", branch_id)
            return list_catalog_products(session, authorized_branch, organization_id=org_id)
        return list_catalog_products(session, organization_id=org_id)

    return _business_response(operation)


@router.post("/orders/assisted-draft")
def post_assisted_order_draft(
    payload: AssistedOrderDraftRequest,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    settings = get_settings()
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    if not settings.assisted_order_enabled or not settings.openrouter_api_key:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "assisted_order_not_configured",
                "message": "Pedido asistido todavía no está configurado en esta instalación.",
            },
        )
    branch_id = authorize_branch_scope(session, actor_id, "pos.operate", str(payload.branch_id))
    catalog = list_catalog_products(session, branch_id)
    options = OpenRouterOptions(
        api_key=settings.openrouter_api_key,
        model=settings.openrouter_model,
        base_url=settings.openrouter_base_url,
        timeout_seconds=settings.openrouter_timeout_seconds,
        http_referer=settings.openrouter_http_referer,
        app_title=settings.openrouter_app_title,
    )
    try:
        draft = build_assisted_draft(
            payload.text,
            catalog,
            lambda product_id: list_product_modifiers(session, product_id, branch_id),
            options,
        )
    except AssistedOrderError as exc:
        logger.info(
            "assisted_order_draft_failed result=error branch_id=%s error_code=%s model=%s",
            branch_id,
            exc.code,
            settings.openrouter_model,
        )
        status_code = (
            422
            if exc.code in {"assisted_order_catalog_mismatch", "assisted_order_unresolved"}
            else 502
        )
        raise HTTPException(
            status_code=status_code, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    logger.info(
        "assisted_order_draft_completed result=success branch_id=%s model=%s questions=%s",
        branch_id,
        settings.openrouter_model,
        len(draft["questions"]),
    )
    return draft


@router.post("/admin-ai/proposals")
def post_admin_ai_proposal(
    payload: AdminAiPromptRequest,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    """Return local guidance or a provider-backed, Python-validated proposal."""
    actor_id = _required_actor_from_request(actor_user_id, authorization)

    def operation() -> dict[str, Any]:
        settings = get_settings()
        provider_options = None
        if settings.admin_ai_assistant_enabled and settings.openrouter_api_key:
            provider_options = AdminAiProviderOptions(
                api_key=settings.openrouter_api_key,
                model=settings.admin_ai_openrouter_model,
                base_url=settings.openrouter_base_url,
                timeout_seconds=settings.admin_ai_openrouter_timeout_seconds,
            )
        provider_mode = "external" if provider_options else "local"
        try:
            result = create_admin_ai_response(
                session,
                actor_id,
                payload.prompt,
                str(payload.branch_id) if payload.branch_id else None,
                provider_options,
                parent_proposal_id=(
                    str(payload.parent_proposal_id) if payload.parent_proposal_id else None
                ),
                clarification_choice=payload.clarification_choice,
                conversation_context=payload.conversation_context,
                conversation_idempotency_key=(
                    str(payload.conversation_idempotency_key)
                    if payload.conversation_idempotency_key
                    else None
                ),
            )
        except AdminAiError as exc:
            logger.info(
                "admin_ai_proposal result=error actor_id=%s branch_id=%s provider=%s error_code=%s",
                actor_id,
                payload.branch_id,
                provider_mode,
                exc.code,
            )
            raise HTTPException(
                status_code=exc.http_status,
                detail={"code": exc.code, "message": str(exc)},
            ) from exc
        except BusinessError as exc:
            logger.info(
                "admin_ai_proposal result=error actor_id=%s branch_id=%s provider=%s error_code=%s",
                actor_id,
                payload.branch_id,
                provider_mode,
                exc.code,
            )
            raise
        change_set = result["payload"]["change_set"]
        logger.info(
            "admin_ai_proposal result=success proposal_id=%s branch_id=%s provider=%s "
            "status=%s action=%s",
            result["id"],
            payload.branch_id,
            provider_mode,
            result["status"],
            change_set[0]["kind"] if change_set else None,
        )
        return result

    return _business_response(operation)


@router.get("/admin-ai/proposals/{proposal_id}")
def get_admin_ai_proposal(
    proposal_id: UUID,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: get_proposal(session, str(proposal_id), actor_id))


@router.post("/admin-ai/proposals/{proposal_id}/review")
def post_admin_ai_review(
    proposal_id: UUID,
    payload: AdminAiReviewRequest,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
    idempotency_key: IdempotencyKeyDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)

    def operation() -> dict[str, Any]:
        try:
            result = review_proposal(
                session, str(proposal_id), actor_id, payload.accept, idempotency_key
            )
        except BusinessError as exc:
            logger.info(
                "admin_ai_review result=error proposal_id=%s actor_id=%s decision=%s error_code=%s",
                proposal_id,
                actor_id,
                "accept" if payload.accept else "reject",
                exc.code,
            )
            raise
        logger.info(
            "admin_ai_review result=success proposal_id=%s actor_id=%s decision=%s status=%s",
            proposal_id,
            actor_id,
            "accept" if payload.accept else "reject",
            result["status"],
        )
        return result

    return _business_response(operation)


@router.post("/admin-ai/executive-insights")
def post_executive_ai_insights(
    payload: ExecutiveAiPromptRequest,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    """Provide executive insights and conversational BI grounded in deterministic SQL analytics."""
    actor_id = _required_actor_from_request(actor_user_id, authorization)

    def operation() -> dict[str, Any]:
        settings = get_settings()
        provider_options = None
        if settings.admin_ai_assistant_enabled and settings.openrouter_api_key:
            provider_options = ExecutiveAiProviderOptions(
                api_key=settings.openrouter_api_key,
                model=settings.admin_ai_openrouter_model,
                base_url=settings.openrouter_base_url,
                timeout_seconds=settings.admin_ai_openrouter_timeout_seconds,
            )
        result = generate_executive_insights(
            session,
            prompt=payload.prompt,
            branch_id=str(payload.branch_id) if payload.branch_id else None,
            provider_options=provider_options,
        )
        logger.info(
            "executive_ai_insights result=success actor_id=%s branch_id=%s prompt_len=%d",
            actor_id,
            payload.branch_id,
            len(payload.prompt),
        )
        return result

    return _business_response(operation)


@router.post("/admin-ai/suggested-purchases")
def post_suggested_purchases(
    payload: SuggestedPurchasesRequest,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    """Generate predictive purchase order proposals grouped by supplier based on demand."""
    actor_id = _required_actor_from_request(actor_user_id, authorization)

    def operation() -> dict[str, Any]:
        branch_id_str = str(payload.branch_id) if payload.branch_id else None
        proposals = calculate_suggested_purchases(
            session, branch_id=branch_id_str, days_ahead=payload.days_ahead
        )
        total_suppliers = len(proposals)
        total_items = sum(len(p.get("lines", [])) for p in proposals)
        total_estimated_cents = sum(p.get("estimated_total_cents", 0) for p in proposals)

        logger.info(
            "suggested_purchases result=success actor_id=%s branch_id=%s suppliers=%d items=%d",
            actor_id,
            payload.branch_id,
            total_suppliers,
            total_items,
        )
        return {
            "proposals": proposals,
            "summary": {
                "total_suppliers": total_suppliers,
                "total_items": total_items,
                "total_estimated_cents": total_estimated_cents,
                "days_ahead": payload.days_ahead,
            },
        }

    return _business_response(operation)


@router.get("/admin-ai/inventory-yield-audit")
def get_inventory_yield_audit(
    session: SessionDep,
    branch_id: UUID | None = None,
    days: int = 30,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    """Audit inventory yield vs waste records to detect anomalies or shrinkage."""
    actor_id = _required_actor_from_request(actor_user_id, authorization)

    def operation() -> dict[str, Any]:
        branch_id_str = str(branch_id) if branch_id else None
        results = audit_inventory_yield_and_waste(session, branch_id=branch_id_str, days=days)
        logger.info(
            "inventory_yield_audit result=success actor_id=%s branch_id=%s count=%d",
            actor_id,
            branch_id,
            len(results),
        )
        return {"audit_records": results, "period_days": days}

    return _business_response(operation)


@router.post("/admin-ai/parse-invoice-ocr")
def post_parse_invoice_ocr(
    payload: InvoiceOcrRequest,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    """Parse supplier invoice or receipt data into structured purchase order lines."""
    actor_id = _required_actor_from_request(actor_user_id, authorization)

    def operation() -> dict[str, Any]:
        parsed = parse_supplier_invoice_data(payload.invoice_text)
        logger.info(
            "parse_invoice_ocr result=success actor_id=%s lines=%d",
            actor_id,
            len(parsed.get("lines", [])),
        )
        return parsed

    return _business_response(operation)


@router.post("/public/order-upsell-recommendations")
def post_public_order_upsell_recommendations(
    payload: CustomerRecommendationsRequest,
    session: SessionDep,
) -> dict[str, Any]:
    """Generate dynamic cross-sell recommendations for online orders based on cart co-occurrences."""
    def operation() -> dict[str, Any]:
        if payload.branch_id is None:
            return {"recommendations": []}
        curr_ids = [str(pid) for pid in payload.current_product_ids]
        cust_id = str(payload.customer_id) if payload.customer_id else None
        recs = get_customer_upsell_recommendations(
            session,
            customer_id=cust_id,
            current_product_ids=curr_ids,
            branch_id=str(payload.branch_id),
        )
        return {"recommendations": recs}

    return _business_response(operation)


@router.post("/admin-ai/customer-recommendations")
def post_customer_recommendations(
    payload: CustomerRecommendationsRequest,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    """Generate predictive upsell and cross-sell suggestions for a customer."""
    actor_id = _required_actor_from_request(actor_user_id, authorization)

    def operation() -> dict[str, Any]:
        curr_ids = [str(pid) for pid in payload.current_product_ids]
        cust_id = str(payload.customer_id) if payload.customer_id else None
        recs = get_customer_upsell_recommendations(
            session,
            customer_id=cust_id,
            current_product_ids=curr_ids,
            branch_id=str(payload.branch_id) if payload.branch_id else None,
        )
        logger.info(
            "customer_recommendations result=success actor_id=%s customer_id=%s count=%d",
            actor_id,
            payload.customer_id,
            len(recs),
        )
        return {"recommendations": recs}

    return _business_response(operation)


@router.get("/admin-ai/customer-crm-segments")
def get_customer_crm_segments(
    session: SessionDep,
    branch_id: UUID | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    """Segment customers into VIPs, Churn Risk (>30d inactive), and New customers."""
    actor_id = _required_actor_from_request(actor_user_id, authorization)

    def operation() -> dict[str, Any]:
        branch_id_str = str(branch_id) if branch_id else None
        segments = get_crm_segments_and_churn_risk(session, branch_id=branch_id_str)
        logger.info(
            "customer_crm_segments result=success actor_id=%s branch_id=%s total=%d",
            actor_id,
            branch_id,
            segments.get("summary", {}).get("total_customers", 0),
        )
        return segments

    return _business_response(operation)


@router.post("/admin-ai/customer-retargeting-message")
def post_customer_retargeting_message(
    payload: CustomerRetargetingMessageRequest,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    """Generate personalized WhatsApp recovery/promotional copy."""
    actor_id = _required_actor_from_request(actor_user_id, authorization)

    def operation() -> dict[str, Any]:
        msg = generate_churn_recovery_message(
            customer_name=payload.customer_name,
            favorite_product_name=payload.favorite_product_name,
            discount_code=payload.discount_code,
        )
        logger.info(
            "customer_retargeting_message result=success actor_id=%s customer=%s",
            actor_id,
            payload.customer_name,
        )
        return {"message": msg}

    return _business_response(operation)


@router.get("/catalog/cleanup-status")
def get_catalog_cleanup_status_endpoint(
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    def operation() -> dict[str, Any]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        require_permission(session, actor_id, "catalog.manage")
        return get_catalog_cleanup_status(session)

    return _business_response(operation)


@router.post("/catalog/load-real-excels")
def post_load_real_excels_endpoint(
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    def operation() -> dict[str, Any]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        require_permission(session, actor_id, "catalog.manage")
        from .real_catalog_loader import load_real_catalog_from_excels

        candidates = [
            "/app/apps/api",
            "/app",
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")),
            ".",
        ]
        excel_dir = next(
            (p for p in candidates if os.path.exists(os.path.join(p, "INSUMOS.XLS"))), "."
        )
        summary = load_real_catalog_from_excels(
            session, excel_dir=excel_dir, import_customers=True, max_customers=5000
        )
        return {"status": "ok", "summary": summary}

    return _business_response(operation)


@router.post("/catalog/products")
def post_catalog_product(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    name = str(payload.get("name", ""))
    sku = str(payload.get("sku", ""))
    category_name = str(payload.get("category_name", ""))
    station = str(payload.get("station", "kitchen"))
    price_cents = int(payload.get("price_cents", 0))
    delivery_price_cents = int(payload["delivery_price_cents"]) if payload.get("delivery_price_cents") is not None else None
    image_url = payload.get("image_url") if "image_url" in payload else None
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: create_product(
            session, name, sku, category_name, station, price_cents, image_url, actor_id, delivery_price_cents=delivery_price_cents
        )
    )


@router.get("/inventory/stock")
def get_inventory_stock(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    def operation() -> list[dict[str, Any]]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        authorized_branch = authorize_branch_scope(session, actor_id, "inventory.read", branch_id)
        return list_inventory_stock(session, authorized_branch)

    return _business_response(operation)


@router.get("/inventory/kardex")
def get_inventory_kardex(
    session: SessionDep,
    item_id: str | None = None,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    def operation() -> list[dict[str, Any]]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        authorized_branch = authorize_branch_scope(session, actor_id, "inventory.read", branch_id)
        return list_inventory_kardex(session, item_id, authorized_branch)

    return _business_response(operation)


@router.post("/inventory/opening-balances")
def post_inventory_opening_balance(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    item_id = str(payload.get("item_id", ""))
    quantity_base_units = int(payload.get("quantity_base_units", 0))
    reason = str(payload.get("reason", "Saldo inicial"))
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: record_inventory_opening_balance(
            session,
            item_id,
            quantity_base_units,
            reason,
            actor_id,
        )
    )


@router.get("/recipes")
def get_recipes(
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    def operation() -> list[dict[str, Any]]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)

        require_permission(session, actor_id, "production.manage")
        return list_active_recipes(session)

    return _business_response(operation)


@router.get("/cash/shifts/current")
def get_current_cash_shift(
    session: SessionDep,
    branch_id: str | None = None,
    register_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    def operation() -> dict[str, Any]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        if not register_id or not register_id.strip():
            raise BusinessError("cash_shift_current_payload_invalid", "register_id is required")
        authorized_branch_id = authorize_branch_scope(
            session, actor_id, "cash.shift.read", branch_id
        )
        if not authorized_branch_id:
            raise BusinessError("cash_shift_current_payload_invalid", "branch_id is required")
        shift = get_open_cash_shift(
            session, register_code=register_id, branch_id=authorized_branch_id
        )
        closure = None
        if not shift:
            last_shift = (
                session.execute(
                    sa.select(models.cash_shifts)
                    .where(
                        models.cash_shifts.c.branch_id == authorized_branch_id,
                        models.cash_shifts.c.register_code == register_id,
                    )
                    .order_by(models.cash_shifts.c.opened_at.desc())
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if last_shift:
                closure = (
                    session.execute(
                        sa.select(models.cash_shift_closures).where(
                            models.cash_shift_closures.c.cash_shift_id == last_shift["id"]
                        )
                    )
                    .mappings()
                    .first()
                )
        return _serialize_pco_response(
            {
                "cash_shift": shift,
                "closure": dict(closure) if closure else None,
            }
        )

    return _business_response(operation)


@router.get("/cash-shifts/current")
def get_current_cash_shift_legacy(
    session: SessionDep,
    branch_id: str | None = None,
    register_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    def operation() -> dict[str, Any]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        if not register_id or not register_id.strip():
            raise BusinessError("cash_shift_current_payload_invalid", "register_id is required")
        scoped_branch = authorize_cash_movement_scope(session, actor_id, branch_id)
        if not scoped_branch:
            raise BusinessError("cash_shift_current_payload_invalid", "branch_id is required")
        return _serialize_pco_response(
            {
                "cash_shift": get_open_cash_shift(session, register_id, scoped_branch),
                "closure": None,
            }
        )

    return _business_response(operation)


@router.post("/cash/shifts/open", operation_id="open_current_cash_shift_v1_post")
@router.post("/cash-shifts/open", operation_id="open_current_cash_shift_alias_post")
def open_current_cash_shift(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
    idempotency_key: IdempotencyKeyDep = None,
) -> dict[str, Any]:
    if set(payload) != {"branch_id", "register_id", "opening_cash_cents"}:
        record_pco004_metric(
            "cash_shift_open_total", result="error", error_code="cash_shift_open_payload_invalid"
        )
        return _business_response(
            lambda: (_ for _ in ()).throw(
                BusinessError(
                    "cash_shift_open_payload_invalid",
                    "Open requires exactly branch_id, register_id and opening_cash_cents",
                )
            )
        )
    opening_cash_cents = payload.get("opening_cash_cents")
    branch_id = payload.get("branch_id")
    register_id = payload.get("register_id")
    if (
        not isinstance(opening_cash_cents, int)
        or isinstance(opening_cash_cents, bool)
        or opening_cash_cents < 0
    ):
        record_pco004_metric(
            "cash_shift_open_total",
            result="error",
            branch_id=branch_id if isinstance(branch_id, str) else None,
            error_code="cash_shift_open_payload_invalid",
        )
        return _business_response(
            lambda: (_ for _ in ()).throw(
                BusinessError(
                    "cash_shift_open_payload_invalid",
                    "opening_cash_cents must be a non-negative integer",
                )
            )
        )
    if (
        not isinstance(branch_id, str)
        or not branch_id.strip()
        or not isinstance(register_id, str)
        or not register_id.strip()
    ):
        record_pco004_metric(
            "cash_shift_open_total",
            result="error",
            branch_id=branch_id if isinstance(branch_id, str) else None,
            error_code="cash_shift_open_payload_invalid",
        )
        return _business_response(
            lambda: (_ for _ in ()).throw(
                BusinessError(
                    "cash_shift_open_payload_invalid", "branch_id and register_id are required"
                )
            )
        )
    if not idempotency_key:
        record_pco004_metric(
            "cash_shift_open_total",
            result="error",
            branch_id=branch_id,
            error_code="idempotency_key_required",
        )
        return _business_response(
            lambda: (_ for _ in ()).throw(
                BusinessError("idempotency_key_required", "Idempotency-Key is required")
            )
        )

    def operation() -> dict[str, Any]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        authorized_branch_id = authorize_branch_scope(
            session, actor_id, "cash.shift.open", branch_id
        )
        if not authorized_branch_id:
            raise BusinessError("cash_shift_open_payload_invalid", "An explicit branch is required")
        return _serialize_pco_response(
            open_cash_shift_idempotently(
                session,
                authorized_branch_id,
                register_id,
                opening_cash_cents,
                idempotency_key,
                actor_id,
            )
        )

    return _business_response(operation)


@router.get("/cash-shifts/summary")
def get_current_cash_shift_summary(
    session: SessionDep,
    branch_id: str | None = None,
    register_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    def operation() -> dict[str, Any]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        authorized_branch_id = authorize_branch_scope(
            session, actor_id, "cash.shift.read", branch_id
        )
        return get_cash_shift_summary(
            session,
            register_code=register_id or "CAJA-01",
            branch_id=authorized_branch_id,
        )

    return _business_response(operation)


@router.post("/cash-shifts/close")
def close_current_cash_shift(
    session: SessionDep,
    payload: dict[str, Any] | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
    idempotency_key: IdempotencyKeyDep = None,
) -> dict[str, Any]:
    raw_payload = payload or {}
    forbidden = {"counted_cash_cents", "expected_cash_cents", "difference_cents"}.intersection(
        raw_payload
    )
    if forbidden:
        record_pco004_metric(
            "cash_shift_operational_close_total",
            result="error",
            branch_id=raw_payload.get("branch_id")
            if isinstance(raw_payload.get("branch_id"), str)
            else None,
            error_code="cash_shift_counted_cash_forbidden",
        )
        return _business_response(
            lambda: (_ for _ in ()).throw(
                BusinessError(
                    "cash_shift_counted_cash_forbidden",
                    "Counted cash is not accepted for operational close",
                )
            )
        )
    if set(raw_payload) != {"branch_id", "register_id"}:
        record_pco004_metric(
            "cash_shift_operational_close_total",
            result="error",
            branch_id=raw_payload.get("branch_id")
            if isinstance(raw_payload.get("branch_id"), str)
            else None,
            error_code="cash_shift_close_payload_invalid",
        )
        return _business_response(
            lambda: (_ for _ in ()).throw(
                BusinessError(
                    "cash_shift_close_payload_invalid",
                    "Legacy close accepts only branch_id and register_id",
                )
            )
        )
    branch_id = raw_payload.get("branch_id")
    register_id = raw_payload.get("register_id")
    if (
        not isinstance(branch_id, str)
        or not branch_id.strip()
        or not isinstance(register_id, str)
        or not register_id.strip()
    ):
        record_pco004_metric(
            "cash_shift_operational_close_total",
            result="error",
            branch_id=branch_id if isinstance(branch_id, str) else None,
            error_code="cash_shift_close_payload_invalid",
        )
        return _business_response(
            lambda: (_ for _ in ()).throw(
                BusinessError(
                    "cash_shift_close_payload_invalid", "branch_id and register_id are required"
                )
            )
        )

    def operation() -> dict[str, Any]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        authorized_branch_id = authorize_branch_scope(
            session, actor_id, "cash.shift.close", branch_id
        )
        return _serialize_operational_close_response(
            close_cash_shift_operationally_for_register(
                session,
                str(authorized_branch_id),
                str(register_id),
                idempotency_key or "",
                actor_id,
            )
        )

    return _business_response(operation)


@router.post("/cash/shifts/{cash_shift_id}/close-operationally")
def close_cash_shift_operational_endpoint(
    cash_shift_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
    idempotency_key: IdempotencyKeyDep = None,
) -> dict[str, Any]:
    if payload != {}:
        record_pco004_metric(
            "cash_shift_operational_close_total",
            result="error",
            error_code="cash_shift_close_payload_invalid",
        )
        return _business_response(
            lambda: (_ for _ in ()).throw(
                BusinessError(
                    "cash_shift_close_payload_invalid", "Operational close requires an empty object"
                )
            )
        )
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: _serialize_operational_close_response(
            close_cash_shift_operationally(session, cash_shift_id, idempotency_key or "", actor_id)
        )
    )


@router.get("/cash/shifts")
def list_cash_shifts_endpoint(
    branch_id: str,
    session: SessionDep,
    register_id: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    def operation() -> dict[str, Any]:
        if not 1 <= limit <= 100:
            raise BusinessError("cash_shift_list_invalid", "limit must be between 1 and 100")
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        scoped_branch = authorize_branch_scope(session, actor_id, "cash.shift.read", branch_id)
        query = sa.select(models.cash_shifts).where(
            models.cash_shifts.c.organization_id == ORGANIZATION_ID,
            models.cash_shifts.c.branch_id == scoped_branch,
        )
        if register_id:
            query = query.where(models.cash_shifts.c.register_code == register_id)
        if cursor:
            cursor_at, cursor_id = _decode_cash_shift_cursor(cursor)
            query = query.where(
                sa.or_(
                    models.cash_shifts.c.opened_at < cursor_at,
                    sa.and_(
                        models.cash_shifts.c.opened_at == cursor_at,
                        models.cash_shifts.c.id < cursor_id,
                    ),
                )
            )
        rows = [
            dict(row)
            for row in session.execute(
                query.order_by(
                    models.cash_shifts.c.opened_at.desc(), models.cash_shifts.c.id.desc()
                ).limit(limit + 1)
            ).mappings()
        ]
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = f"{_serialize_api_value(last['opened_at'])}|{last['id']}"
        return _serialize_pco_response({"items": rows[:limit], "next_cursor": next_cursor})

    return _business_response(operation)


@router.get("/cash/shifts/{cash_shift_id}")
def get_cash_shift_endpoint(
    cash_shift_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    def operation() -> dict[str, Any]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        shift = (
            session.execute(
                sa.select(models.cash_shifts).where(
                    models.cash_shifts.c.id == cash_shift_id,
                    models.cash_shifts.c.organization_id == ORGANIZATION_ID,
                )
            )
            .mappings()
            .first()
        )
        if not shift:
            raise NotFoundError("cash_shift_not_found", "Cash shift was not found")
        authorize_branch_scope(session, actor_id, "cash.shift.read", str(shift["branch_id"]))
        closure = (
            session.execute(
                sa.select(models.cash_shift_closures).where(
                    models.cash_shift_closures.c.cash_shift_id == cash_shift_id
                )
            )
            .mappings()
            .first()
        )
        return _serialize_pco_response(
            {"cash_shift": dict(shift), "closure": dict(closure) if closure else None}
        )

    return _business_response(operation)


@router.post("/cash/user-cuts")
def create_user_cash_cut_endpoint(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
    idempotency_key: IdempotencyKeyDep = None,
) -> dict[str, Any]:
    return _business_response(
        lambda: _serialize_pco_response(
            UserCashCutService(session).create(
                payload,
                idempotency_key or "",
                _required_actor_from_request(actor_user_id, authorization),
            )
        )
    )


@router.get("/cash/user-cuts")
def list_user_cash_cuts_endpoint(
    session: SessionDep,
    branch_id: str,
    register_id: str | None = None,
    cashier_user_id: str | None = None,
    cash_shift_id: str | None = None,
    status: str | None = None,
    from_utc: str | None = None,
    to_utc: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    filters = {"branch_id": branch_id, "limit": limit}
    for key, value in {
        "register_id": register_id,
        "cashier_user_id": cashier_user_id,
        "cash_shift_id": cash_shift_id,
        "status": status,
        "from_utc": from_utc,
        "to_utc": to_utc,
        "cursor": cursor,
    }.items():
        if value is not None:
            filters[key] = value
    return _business_response(
        lambda: _serialize_pco_response(
            UserCashCutService(session).list(
                filters, _required_actor_from_request(actor_user_id, authorization)
            )
        )
    )


@router.get("/cash/user-cuts/{cash_cut_id}")
def get_user_cash_cut_endpoint(
    cash_cut_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    return _business_response(
        lambda: _serialize_pco_response(
            UserCashCutService(session).detail(
                cash_cut_id, _required_actor_from_request(actor_user_id, authorization)
            )
        )
    )


@router.post("/cash/user-cuts/{cash_cut_id}/counted-cash")
def count_user_cash_cut_endpoint(
    cash_cut_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
    idempotency_key: IdempotencyKeyDep = None,
) -> dict[str, Any]:
    return _business_response(
        lambda: _serialize_pco_response(
            UserCashCutService(session).counted_cash(
                cash_cut_id,
                payload,
                idempotency_key or "",
                _required_actor_from_request(actor_user_id, authorization),
            )
        )
    )


@router.post("/cash/user-cuts/{cash_cut_id}/finalize")
def finalize_user_cash_cut_endpoint(
    cash_cut_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
    idempotency_key: IdempotencyKeyDep = None,
) -> dict[str, Any]:
    return _business_response(
        lambda: _serialize_pco_response(
            UserCashCutService(session).finalize(
                cash_cut_id,
                payload,
                idempotency_key or "",
                _required_actor_from_request(actor_user_id, authorization),
            )
        )
    )


@router.post("/cash/user-cuts/{cash_cut_id}/reopen-requests")
def request_user_cash_cut_reopen_endpoint(
    cash_cut_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
    idempotency_key: IdempotencyKeyDep = None,
) -> dict[str, Any]:
    return _business_response(
        lambda: _serialize_pco_response(
            UserCashCutService(session).request_reopen(
                cash_cut_id,
                payload,
                idempotency_key or "",
                _required_actor_from_request(actor_user_id, authorization),
            )
        )
    )


@router.post("/cash/user-cuts/reopen-requests/{request_id}/approve")
def approve_user_cash_cut_reopen_endpoint(
    request_id: str,
    session: SessionDep,
    payload: dict[str, Any] | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
    idempotency_key: IdempotencyKeyDep = None,
) -> dict[str, Any]:
    def operation() -> dict[str, Any]:
        if payload not in (None, {}):
            raise BusinessError("cash_cut_scope_invalid", "Reopen decision body must be empty")
        return _serialize_pco_response(
            UserCashCutService(session).decide_reopen(
                request_id,
                "APPROVED",
                idempotency_key or "",
                _required_actor_from_request(actor_user_id, authorization),
            )
        )

    return _business_response(operation)


@router.post("/cash/user-cuts/reopen-requests/{request_id}/reject")
def reject_user_cash_cut_reopen_endpoint(
    request_id: str,
    session: SessionDep,
    payload: dict[str, Any] | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
    idempotency_key: IdempotencyKeyDep = None,
) -> dict[str, Any]:
    def operation() -> dict[str, Any]:
        if payload not in (None, {}):
            raise BusinessError("cash_cut_scope_invalid", "Reopen decision body must be empty")
        return _serialize_pco_response(
            UserCashCutService(session).decide_reopen(
                request_id,
                "REJECTED",
                idempotency_key or "",
                _required_actor_from_request(actor_user_id, authorization),
            )
        )

    return _business_response(operation)


@router.post("/cash/user-cuts/reopen-requests/{request_id}/compensate")
def compensate_user_cash_cut_reopen_endpoint(
    request_id: str,
    session: SessionDep,
    payload: dict[str, Any] | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
    idempotency_key: IdempotencyKeyDep = None,
) -> dict[str, Any]:
    def operation() -> dict[str, Any]:
        if payload not in (None, {}):
            raise BusinessError("cash_cut_scope_invalid", "Reopen compensation body must be empty")
        return _serialize_pco_response(
            UserCashCutService(session).compensate_reopen(
                request_id,
                idempotency_key or "",
                _required_actor_from_request(actor_user_id, authorization),
            )
        )

    return _business_response(operation)


@router.get("/reports/sales-monitor")
def sales_monitor_endpoint(
    from_utc: datetime,
    to_utc: datetime,
    session: SessionDep,
    branch_id: str | None = None,
    register_id: str | None = None,
    cash_shift_id: str | None = None,
    family_id: str | None = None,
    service_type: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: _serialize_api_value(
            ReportingProjectionService(session, actor_id).summary(
                {
                    "from_utc": from_utc,
                    "to_utc": to_utc,
                    "branch_id": branch_id,
                    "register_id": register_id,
                    "cash_shift_id": cash_shift_id,
                    "family_id": family_id,
                    "service_type": service_type,
                }
            )
        )
    )


@router.get("/reports/sales-monitor/drill-down")
def sales_monitor_drill_down_endpoint(
    from_utc: datetime,
    to_utc: datetime,
    metric: str,
    session: SessionDep,
    branch_id: str | None = None,
    register_id: str | None = None,
    cash_shift_id: str | None = None,
    family_id: str | None = None,
    service_type: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: _serialize_api_value(
            ReportingProjectionService(session, actor_id).drill_down(
                {
                    "from_utc": from_utc,
                    "to_utc": to_utc,
                    "branch_id": branch_id,
                    "register_id": register_id,
                    "cash_shift_id": cash_shift_id,
                    "family_id": family_id,
                    "service_type": service_type,
                    "metric": metric,
                    "limit": limit,
                    "cursor": cursor,
                }
            )
        )
    )


@router.get("/reports/ingredient-sales")
def ingredient_sales_report_endpoint(
    from_utc: datetime,
    to_utc: datetime,
    session: SessionDep,
    branch_id: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: _serialize_api_value(
            ReportingProjectionService(session, actor_id).ingredient_sales(
                {
                    "from_utc": from_utc,
                    "to_utc": to_utc,
                    "branch_id": branch_id,
                    "limit": limit,
                    "cursor": cursor,
                }
            )
        )
    )


@router.get("/reports/expenses")
def expenses_report_endpoint(
    from_utc: datetime,
    to_utc: datetime,
    session: SessionDep,
    branch_id: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: _serialize_api_value(
            ReportingProjectionService(session, actor_id).expenses(
                {
                    "from_utc": from_utc,
                    "to_utc": to_utc,
                    "branch_id": branch_id,
                    "limit": limit,
                    "cursor": cursor,
                }
            )
        )
    )


class ReconciliationAuditRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    branch_id: str
    date: str
    reviewed: bool
    notes: str | None = None


@router.get("/reports/branch-reconciliation/daily")
def branch_reconciliation_daily_endpoint(
    branch_id: str,
    date: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    from restaurant_os.reconciliation_reports import get_branch_daily_reconciliation

    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: get_branch_daily_reconciliation(session, branch_id, date, actor_id)
    )


@router.get("/reports/branch-reconciliation/consolidated")
def branch_reconciliation_consolidated_endpoint(
    date_from: str,
    date_to: str,
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    from restaurant_os.reconciliation_reports import get_multi_branch_consolidated_report

    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: get_multi_branch_consolidated_report(
            session, date_from, date_to, branch_id, actor_id
        )
    )


@router.post("/reports/branch-reconciliation/audit")
def branch_reconciliation_audit_endpoint(
    payload: ReconciliationAuditRequest,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    from restaurant_os.reconciliation_reports import update_reconciliation_audit_status

    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: update_reconciliation_audit_status(
            session, payload.branch_id, payload.date, payload.reviewed, payload.notes, actor_id
        )
    )


@router.get("/reports/branch-reconciliation/export")
def branch_reconciliation_export_endpoint(
    branch_id: str,
    month: int,
    year: int,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> Response:
    from restaurant_os.reconciliation_reports import export_reconciliation_workbook

    actor_id = _required_actor_from_request(actor_user_id, authorization)
    excel_stream = _business_response(
        lambda: export_reconciliation_workbook(session, branch_id, month, year, actor_id)
    )
    return Response(
        content=excel_stream.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="Corte_{branch_id}_{year}_{month:02d}.xlsx"'
        },
    )


@router.get("/orders")
def get_recent_orders(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    def operation() -> list[dict[str, Any]]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        authorized_branch_id = authorize_branch_scope(session, actor_id, "orders.read", branch_id)
        return list_recent_orders(session, authorized_branch_id)

    return _business_response(operation)


@router.get("/orders/accounts")
def get_order_accounts(
    session: SessionDep,
    branch_id: str | None = None,
    from_utc: str | None = None,
    to_utc: str | None = None,
    cash_shift_id: str | None = None,
    register_code: str | None = None,
    service_type: str | None = None,
    q: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: list_order_accounts(
            session,
            {
                "branch_id": branch_id,
                "from_utc": from_utc,
                "to_utc": to_utc,
                "cash_shift_id": cash_shift_id,
                "register_code": register_code,
                "service_type": service_type,
                "q": q,
                "limit": limit,
                "cursor": cursor,
            },
            actor_id,
        )
    )


@router.get("/orders/pending-count")
def get_pending_order_count(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, int]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: count_pending_orders(session, branch_id, actor_id))


@router.post("/orders/{order_id}/reopen-requests")
def create_order_reopen_request_endpoint(
    order_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: create_order_reopen_request(session, order_id, payload, idempotency_key, actor_id)
    )


@router.get("/orders/reopen-requests")
def get_order_reopen_requests(
    session: SessionDep,
    branch_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: list_order_reopen_requests(
            session,
            {"branch_id": branch_id, "status": status, "limit": limit, "cursor": cursor},
            actor_id,
        )
    )


@router.post("/orders/reopen-requests/{request_id}/approve")
def approve_order_reopen_request_endpoint(
    request_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: decide_order_reopen_request(
            session, request_id, "APPROVED", payload, idempotency_key, actor_id
        )
    )


@router.post("/orders/reopen-requests/{request_id}/reject")
def reject_order_reopen_request_endpoint(
    request_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: decide_order_reopen_request(
            session, request_id, "REJECTED", payload, idempotency_key, actor_id
        )
    )


@router.post("/orders/reopen-requests/{request_id}/apply")
def apply_order_reopen_request_endpoint(
    request_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: apply_order_reopen_request(session, request_id, payload, idempotency_key, actor_id)
    )


@router.post("/orders/quote")
def quote_order(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    def operation() -> dict[str, Any]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        branch_id = authorize_branch_scope(
            session,
            actor_id,
            "orders.create",
            str(payload.get("branch_id") or "") or None,
        )
        if not branch_id:
            raise BusinessError("branch_scope_required", "A branch scope is required")
        return quote_local_order(
            session,
            list(payload.get("lines", [])),
            branch_id,
            actor_id,
            str(payload.get("adjustment_authorization_id") or "").strip() or None,
        )

    return _business_response(operation)


@router.post("/orders/adjustments/authorize")
def authorize_order_adjustment_endpoint(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    def operation() -> dict[str, Any]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        branch_id = authorize_branch_scope(
            session,
            actor_id,
            "orders.create",
            str(payload.get("branch_id") or "") or None,
        )
        if not branch_id:
            raise BusinessError("branch_scope_required", "A branch scope is required")
        adjustment = payload.get("adjustment")
        if not isinstance(adjustment, dict):
            raise BusinessError("invalid_order_adjustment", "Adjustment details are required")
        return authorize_order_adjustment(
            session=session,
            lines=list(payload.get("lines", [])),
            branch_id=branch_id,
            actor_user_id=actor_id,
            supervisor_code_or_password=str(payload.get("supervisor_pin") or ""),
            adjustment_type=str(adjustment.get("type") or ""),
            adjustment_value=adjustment.get("value"),
            reason=str(adjustment.get("reason") or ""),
        )

    return _business_response(operation)


@router.post("/orders/{order_id}/fulfillment/{command}")
def fulfill_order_endpoint(
    order_id: str,
    command: str,
    session: SessionDep,
    idempotency_key: IdempotencyKeyDep = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: fulfill_order(session, order_id, command, idempotency_key, actor_id)
    )


@router.post(
    "/orders",
    openapi_extra={
        "parameters": [
            {
                "name": "Idempotency-Key",
                "in": "header",
                "required": True,
                "schema": {"type": "string", "minLength": 12, "maxLength": 160},
            }
        ]
    },
)
def create_order(
    payload: dict[str, Any],
    request: Request,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    idempotency_key = request.headers.get("Idempotency-Key")
    lines = payload.get("lines", [])
    owner_name = payload.get("owner_name")
    order_type = str(payload.get("order_type", "dine-in"))
    branch_id = payload.get("branch_id")
    register_id = payload.get("register_id")
    customer_id = payload.get("customer_id")
    delivery_address_id = payload.get("delivery_address_id")
    payment_method_intent = payload.get("payment_method_intent")
    driver_id = payload.get("driver_id")
    adjustment_authorization_id = (
        str(payload.get("adjustment_authorization_id") or "").strip() or None
    )

    def operation() -> dict[str, Any]:
        if "ingredient_extras" in payload or "comment_preset_ids" in payload:
            raise BusinessError(
                "order_line_modifiers_required",
                "Comments and ingredient extras must belong to a specific order line",
            )
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        settings = get_settings()
        is_test_actor_header = bool(
            actor_user_id
            and settings.environment != "production"
            and os.getenv("PYTEST_CURRENT_TEST")
        )
        if not idempotency_key and not is_test_actor_header:
            raise BusinessError("idempotency_key_required", "Idempotency-Key is required")
        authorized_branch_id = authorize_branch_scope(session, actor_id, "orders.create", branch_id)
        return create_local_order(
            session,
            lines,
            owner_name,
            order_type,
            authorized_branch_id,
            register_id,
            actor_id,
            customer_id,
            delivery_address_id,
            payment_method_intent,
            driver_id,
            adjustment_authorization_id,
            idempotency_key,
        )

    return _business_response(operation)


@router.post(
    "/orders/recover",
    openapi_extra={
        "parameters": [
            {
                "name": "Idempotency-Key",
                "in": "header",
                "required": True,
                "schema": {"type": "string", "minLength": 12, "maxLength": 160},
            }
        ]
    },
)
def recover_order_creation(
    payload: dict[str, Any],
    request: Request,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    def operation() -> dict[str, Any]:
        if payload != {}:
            raise BusinessError(
                "order_recovery_payload_invalid", "Recovery requires an empty object"
            )
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        return recover_local_order_creation(
            session, request.headers.get("Idempotency-Key"), actor_id
        )

    return _business_response(operation)


@router.get("/public/branches")
def public_branches_endpoint(
    request: Request,
    session: SessionDep,
    lat: float | None = None,
    lng: float | None = None,
) -> list[dict[str, Any]]:
    return _business_response(
        lambda: list_public_branches(
            session,
            customer_lat=lat,
            customer_lng=lng,
            include_public_key=bool(
                getattr(request.app.state, "public_order_intents_enabled", False)
            ),
        )
    )


@router.get("/catalog/mobile-theme")
@router.get("/public/mobile-theme")
def get_mobile_theme_endpoint(session: SessionDep) -> dict[str, Any]:
    theme_val = "light"
    try:
        val = session.execute(
            sa.select(models.organizations.c.mobile_theme).where(
                models.organizations.c.id == ORGANIZATION_ID
            )
        ).scalar_one_or_none()
        if val:
            theme_val = str(val)
    except Exception:
        pass
    return {"mobile_theme": theme_val}


@router.put("/catalog/mobile-theme")
def set_mobile_theme_endpoint(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")
    theme = str(payload.get("mobile_theme") or payload.get("theme") or "light").lower().strip()
    if theme not in ("light", "dark"):
        theme = "light"
    session.execute(
        models.organizations.update()
        .where(models.organizations.c.id == ORGANIZATION_ID)
        .values(mobile_theme=theme, updated_at=_now())
    )
    session.commit()
    return {"status": "ok", "mobile_theme": theme}


from restaurant_os.whatsapp_menu import get_public_menu_for_branch, submit_whatsapp_order


@router.get("/public/catalog")
def public_catalog_endpoint(session: SessionDep) -> dict[str, Any]:
    return _business_response(lambda: get_public_catalog(session))


@router.get("/public/menu")
@router.get("/v1/public/menu")
def public_menu_endpoint(
    session: SessionDep,
    branch_id: str,
) -> dict[str, Any]:
    return get_public_menu_for_branch(session, branch_id)


@router.post("/public/whatsapp-orders")
@router.post("/v1/public/whatsapp-orders")
def public_whatsapp_orders_endpoint(
    payload: dict[str, Any],
    session: SessionDep,
) -> dict[str, Any]:
    return submit_whatsapp_order(session, payload)


from restaurant_os.superadmin import (
    require_superadmin,
    get_saas_metrics,
    list_tenants,
    create_tenant_by_admin,
    update_tenant_status,
    update_tenant_plan,
    impersonate_tenant,
    parse_and_import_menu_ai,
)


@router.get("/superadmin/metrics")
@router.get("/v1/superadmin/metrics")
def get_superadmin_metrics_endpoint(
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_superadmin(session, actor_id)
    return get_saas_metrics(session)


@router.get("/superadmin/tenants")
@router.get("/v1/superadmin/tenants")
def get_superadmin_tenants_endpoint(
    session: SessionDep,
    search: str | None = None,
    status: str | None = None,
    plan: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_superadmin(session, actor_id)
    return list_tenants(session, search=search, status=status, plan=plan)


@router.post("/superadmin/tenants", status_code=201)
@router.post("/v1/superadmin/tenants", status_code=201)
def post_superadmin_tenants_endpoint(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_superadmin(session, actor_id)
    return create_tenant_by_admin(session, payload)


@router.patch("/superadmin/tenants/{tenant_id}/status")
@router.patch("/v1/superadmin/tenants/{tenant_id}/status")
def patch_superadmin_tenant_status_endpoint(
    tenant_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_superadmin(session, actor_id)
    status = str(payload.get("status", "active"))
    reason = payload.get("reason")
    return update_tenant_status(session, tenant_id, status=status, reason=reason)


@router.patch("/superadmin/tenants/{tenant_id}/plan")
@router.patch("/v1/superadmin/tenants/{tenant_id}/plan")
def patch_superadmin_tenant_plan_endpoint(
    tenant_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_superadmin(session, actor_id)
    plan = str(payload.get("plan", "starter_349"))
    monthly_fee = payload.get("monthly_fee_cents")
    return update_tenant_plan(session, tenant_id, plan=plan, monthly_fee_cents=monthly_fee)


@router.post("/superadmin/tenants/{tenant_id}/impersonate")
@router.post("/v1/superadmin/tenants/{tenant_id}/impersonate")
def post_superadmin_tenant_impersonate_endpoint(
    tenant_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_superadmin(session, actor_id)
    return impersonate_tenant(session, tenant_id, actor_superadmin_id=actor_id)


@router.post("/superadmin/tenants/{tenant_id}/ai-menu-import")
@router.post("/v1/superadmin/tenants/{tenant_id}/ai-menu-import")
def post_superadmin_ai_menu_import_endpoint(
    tenant_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_superadmin(session, actor_id)
    branch_id = payload.get("branch_id")
    if not branch_id:
        branch = session.execute(
            sa.select(models.branches.c.id).where(models.branches.c.organization_id == tenant_id)
        ).scalar_one_or_none()
        branch_id = str(branch)
    raw_text = str(payload.get("menu_text", ""))
    imported = parse_and_import_menu_ai(session, tenant_id, branch_id, raw_text)
    return {"imported_products": imported, "count": len(imported)}


class PublicOrderModifier(BaseModel):
    model_config = ConfigDict(extra="forbid")
    option_id: str = Field(min_length=1, max_length=36)
    text: str | None = Field(default=None, max_length=500)


class PublicIngredientExtra(BaseModel):
    model_config = ConfigDict(extra="forbid")
    extra_id: str = Field(min_length=1, max_length=36)
    portions: int = Field(default=1, ge=1, le=99)


class PublicOrderIntentLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: str = Field(min_length=1, max_length=36)
    quantity: int = Field(ge=1, le=99)
    notes: str | None = Field(default=None, max_length=500)
    modifiers: list[PublicOrderModifier] = Field(default_factory=list, max_length=30)
    comment_preset_ids: list[str] = Field(default_factory=list, max_length=20)
    ingredient_extras: list[PublicIngredientExtra] = Field(default_factory=list, max_length=20)


class PublicDeliveryAddress(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address_text: str = Field(min_length=1, max_length=500)
    notes: str | None = Field(default=None, max_length=500)


class PublicOrderIntentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_name: str = Field(min_length=1, max_length=255)
    customer_phone: str = Field(min_length=10, max_length=32)
    order_type: Literal["takeout", "delivery", "dine-in"]
    lines: list[PublicOrderIntentLine] = Field(min_length=1, max_length=100)
    order_notes: str | None = Field(default=None, max_length=500)
    delivery_address: PublicDeliveryAddress | None = None

    @model_validator(mode="after")
    def delivery_requires_address(self) -> PublicOrderIntentPayload:
        if self.order_type == "delivery" and self.delivery_address is None:
            raise ValueError("delivery orders require delivery_address")
        return self


class PublicOrderIntentAcceptance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class PublicOrderIntentRejection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=10, max_length=500)


def _public_order_error(code: str, status_code: int) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": "Public order request was rejected"},
    )


def _resolve_active_public_order_key(session: Session, public_key: str) -> dict[str, Any] | None:
    """Resolve bounded opaque keys before rate limiting or catalog projection."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", public_key):
        return None
    row = (
        session.execute(
            sa.select(models.public_order_keys)
            .join(models.branches, models.branches.c.id == models.public_order_keys.c.branch_id)
            .where(
                models.public_order_keys.c.public_key == public_key,
                models.public_order_keys.c.status == "active",
                models.branches.c.status == "active",
                models.public_order_keys.c.organization_id == models.branches.c.organization_id,
            )
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


@router.get("/public/branches/{public_key}/catalog")
def public_catalog_by_key_endpoint(public_key: str, session: SessionDep) -> dict[str, Any]:
    def operation() -> dict[str, Any]:
        key = _resolve_active_public_order_key(session, public_key)
        if not key:
            raise NotFoundError("public_branch_not_found", "Public branch was not found")
        return get_public_catalog(session, branch_id=str(key["branch_id"]))

    return _business_response(operation)


@router.post("/public/branches/{public_key}/order-intents")
def create_public_order_intent_endpoint(
    public_key: str,
    payload: dict[str, Any],
    request: Request,
    response: Response,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    try:
        parsed = PublicOrderIntentPayload.model_validate(payload)
    except ValidationError as exc:
        raise _public_order_error("public_order_schema_invalid", 422) from exc
    return _business_response(
        lambda: _create_public_order_intent_with_runtime(
            session, public_key, parsed.model_dump(), idempotency_key or "", response, request
        )
    )


def _create_public_order_intent_with_runtime(
    session: Session,
    public_key: str,
    payload: dict[str, Any],
    idempotency_key: str,
    response: Response,
    request: Request,
) -> dict[str, Any]:
    if not bool(getattr(request.app.state, "public_order_intents_enabled", False)):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "public_order_unavailable",
                "message": "Public ordering is unavailable",
            },
        )
    if not _resolve_active_public_order_key(session, public_key):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "public_order_unavailable",
                "message": "Public ordering is unavailable",
            },
        )
    limiter = getattr(request.app.state, "public_order_rate_limiter", None)
    if limiter is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "public_order_unavailable",
                "message": "Public ordering is unavailable",
            },
        )

    client_host = ""
    if request.client and request.client.host:
        client_host = request.client.host
    elif request.headers.get("x-forwarded-for"):
        client_host = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    elif request.headers.get("x-real-ip"):
        client_host = request.headers.get("x-real-ip", "").strip()
    else:
        client_host = "127.0.0.1"

    # Direct ASGI peer plus a bounded UA improves client partitioning without trusting
    # spoofable forwarding headers. The limiter HMACs this signal before Redis.
    user_agent = request.headers.get("user-agent", "")[:256]
    client_signal = f"{client_host}\n{user_agent}"
    try:
        allowed = bool(limiter.allow(public_key, client_signal))
    except Exception as exc:
        logger.info(
            "public_order_rate_limit",
            extra={"metric": "public_order_rate_limit", "result": "unavailable"},
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "public_order_unavailable",
                "message": "Public ordering is unavailable",
            },
        ) from exc
    if not allowed:
        logger.info(
            "public_order_rate_limit",
            extra={"metric": "public_order_rate_limit", "result": "limited"},
        )
        raise HTTPException(
            status_code=429,
            detail={
                "code": "public_order_rate_limited",
                "message": "Public ordering is rate limited",
            },
        )
    logger.info(
        "public_order_rate_limit", extra={"metric": "public_order_rate_limit", "result": "allowed"}
    )
    result, created = create_public_order_intent(session, public_key, payload, idempotency_key)
    response.status_code = 201 if created else 200
    hook = getattr(request.app.state, "public_order_after_commit_hook", None)
    if hook:
        hook()
    return result


@router.get("/public/order-intents/{public_reference}")
def get_public_order_intent_endpoint(public_reference: str, session: SessionDep) -> dict[str, Any]:
    return _business_response(lambda: get_public_order_intent(session, public_reference))


class CustomerFeedbackPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_id: str = Field(min_length=1, max_length=36)
    rating: int = Field(ge=1, le=5)
    order_folio: str | None = Field(default=None, max_length=64)
    customer_name: str | None = Field(default=None, max_length=160)
    comment: str | None = Field(default=None, max_length=1000)


@router.post("/public/feedback", status_code=201)
def submit_customer_feedback_endpoint(
    payload: CustomerFeedbackPayload,
    session: SessionDep,
) -> dict[str, Any]:
    branch = (
        session.execute(
            sa.select(models.branches.c.id, models.branches.c.organization_id).where(
                models.branches.c.id == payload.branch_id,
                models.branches.c.status == "active",
            )
        )
        .mappings()
        .first()
    )
    if not branch:
        raise HTTPException(
            status_code=404,
            detail={"code": "branch_not_found", "message": "Branch not found or inactive"},
        )

    feedback_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    session.execute(
        models.customer_feedbacks.insert().values(
            id=feedback_id,
            organization_id=branch["organization_id"],
            branch_id=payload.branch_id,
            order_folio=payload.order_folio.strip() if payload.order_folio else None,
            rating=payload.rating,
            customer_name=payload.customer_name.strip() if payload.customer_name else None,
            comment=payload.comment.strip() if payload.comment else None,
            created_at=now,
        )
    )
    session.commit()
    return {"id": feedback_id, "status": "recorded"}


@router.get("/admin/feedbacks")
def list_admin_feedbacks_endpoint(
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
    branch_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "orders.read")

    query = (
        sa.select(
            models.customer_feedbacks.c.id,
            models.customer_feedbacks.c.branch_id,
            models.customer_feedbacks.c.order_folio,
            models.customer_feedbacks.c.rating,
            models.customer_feedbacks.c.customer_name,
            models.customer_feedbacks.c.comment,
            models.customer_feedbacks.c.created_at,
            models.branches.c.name.label("branch_name"),
            models.branches.c.code.label("branch_code"),
        )
        .select_from(
            models.customer_feedbacks.join(
                models.branches,
                models.customer_feedbacks.c.branch_id == models.branches.c.id,
            )
        )
        .where(models.customer_feedbacks.c.organization_id == ORGANIZATION_ID)
    )
    if branch_id:
        query = query.where(models.customer_feedbacks.c.branch_id == branch_id)

    rows = session.execute(
        query.order_by(models.customer_feedbacks.c.created_at.desc()).limit(limit)
    ).mappings()
    return [dict(r) for r in rows]


@router.post("/order-intents/{intent_id}/accept")
def accept_public_order_intent_endpoint(
    intent_id: str,
    payload: PublicOrderIntentAcceptance,
    response: Response,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    result, created = _business_response(
        lambda: accept_public_order_intent(
            session, intent_id, payload.expected_version, idempotency_key or "", actor_id
        )
    )
    response.status_code = 201 if created else 200
    return result


@router.post("/order-intents/{intent_id}/reject")
def reject_public_order_intent_endpoint(
    intent_id: str,
    payload: PublicOrderIntentRejection,
    response: Response,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    result, created = _business_response(
        lambda: reject_public_order_intent(
            session,
            intent_id,
            payload.expected_version,
            payload.reason,
            idempotency_key or "",
            actor_id,
        )
    )
    response.status_code = 201 if created else 200
    return result


@router.post("/public/orders")
def public_create_order() -> None:
    raise _public_order_error("public_order_unavailable", 503)


@router.get("/orders/{order_id}")
def get_order_detail_endpoint(
    order_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: get_order_detail(session, order_id, actor_id))


@router.post("/orders/{order_id}/accept")
def accept_order_endpoint(
    order_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)

    def operation() -> dict[str, Any]:
        intent = (
            session.execute(
                sa.select(models.public_order_intents).where(
                    models.public_order_intents.c.id == order_id
                )
            )
            .mappings()
            .first()
        )
        if intent:
            result, _ = accept_public_order_intent(
                session,
                intent_id=order_id,
                expected_version=int(intent["version"]),
                idempotency_key=f"pos-accept-{order_id}-{intent['version']}",
                actor_user_id=actor_id,
            )
            return result
        return accept_pending_order(session, order_id, actor_id)

    return _business_response(operation)


@router.post("/orders/{order_id}/amendments")
def amend_order_endpoint(
    order_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: amend_order(
            session,
            order_id,
            list(payload.get("lines", [])),
            int(payload.get("expected_version", 0)),
            idempotency_key or "",
            actor_id,
        )
    )


@router.post("/orders/{order_id}/cancel")
def cancel_order_endpoint(
    order_id: str,
    payload: dict[str, Any] | None,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    reason = str((payload or {}).get("reason", "Cancelacion solicitada en POS"))
    classification = (payload or {}).get("classification")
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: cancel_order_operation(session, order_id, reason, classification, actor_id)
    )


@router.post(
    "/orders/{order_id}/payments",
    openapi_extra={
        "parameters": [
            {
                "name": "Idempotency-Key",
                "in": "header",
                "required": True,
                "schema": {"type": "string", "minLength": 12, "maxLength": 160},
            }
        ]
    },
)
def create_order_payment(
    order_id: str,
    payload: dict[str, Any],
    request: Request,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    idempotency_key = (
        request.headers.get("Idempotency-Key")
        or request.headers.get("idempotency-key")
        or str((payload or {}).get("idempotency_key", "")).strip()
        or None
    )
    amount_cents = int(payload.get("amount_cents", 0))
    method = str(payload.get("method", "cash"))
    register_id = str(payload.get("register_id", "")).strip()

    def operation() -> dict[str, Any]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        settings = get_settings()
        is_test_actor_header = bool(
            actor_user_id
            and settings.environment != "production"
            and os.getenv("PYTEST_CURRENT_TEST")
        )
        if not idempotency_key and not is_test_actor_header:
            raise BusinessError("idempotency_key_required", "Idempotency-Key is required")
        return pay_order(
            session,
            order_id,
            amount_cents,
            method,
            actor_id,
            register_id,
            idempotency_key=idempotency_key,
        )

    return _business_response(operation)


@router.post("/orders/{order_id}/repeat")
def repeat_order_endpoint(
    order_id: str,
    payload: dict[str, Any] | None,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    register_id = str((payload or {}).get("register_id", "CAJA-01"))
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: repeat_order(session, order_id, register_id, actor_id))


@router.get("/payments")
def get_payments(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    def operation() -> list[dict[str, Any]]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        authorized_branch_id = authorize_branch_scope(session, actor_id, "payments.read", branch_id)
        return list_payments(session, authorized_branch_id)

    return _business_response(operation)


@router.get("/kds/tasks")
def get_kds_tasks(
    session: SessionDep,
    branch_id: str | None = None,
    authorization: AuthorizationDep = None,
    device_token: DeviceTokenDep = None,
) -> list[dict[str, Any]]:
    if device_token:
        actor = operational_route_guard.require_device_for_capability(
            session, device_token, "kds.operate"
        )
    else:
        actor = operational_route_guard.require_human(
            session, authorization, "kds.tasks.operate", branch_id
        )
    return _database_response(lambda: list_kds_tasks(session, actor.branch_id or ""))


@router.post("/kds/tasks/{task_id}/transition")
def transition_kds_task(
    task_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    authorization: AuthorizationDep = None,
    device_token: DeviceTokenDep = None,
) -> dict[str, Any]:
    status = str(payload.get("status", ""))
    if device_token:
        actor = operational_route_guard.require_device_for_capability(
            session, device_token, "kds.operate"
        )
        actor_user_id, actor_device_id = None, actor.user_id
    else:
        requested_branch_id = str(payload.get("branch_id", "")).strip() or None
        actor = operational_route_guard.require_human(
            session, authorization, "kds.tasks.operate", requested_branch_id
        )
        actor_user_id, actor_device_id = actor.user_id, None
    return _business_response(
        lambda: advance_kds_task(
            session,
            task_id,
            status,
            actor.branch_id or "",
            actor_user_id=actor_user_id,
            actor_device_id=actor_device_id,
        )
    )


@router.get("/print-jobs")
def get_print_jobs(
    session: SessionDep,
    branch_id: str | None = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor = operational_route_guard.require_human(
        session, authorization, "print.jobs.read", branch_id
    )
    return _database_response(lambda: list_print_jobs(session, actor.branch_id or ""))


@router.post("/print-jobs/{job_id}/retry")
def retry_print_job_endpoint(
    job_id: str,
    session: SessionDep,
    branch_id: str | None = None,
    authorization: AuthorizationDep = None,
    idempotency_key: IdempotencyKeyDep = None,
) -> dict[str, Any]:
    actor = operational_route_guard.require_human(
        session, authorization, "print.jobs.retry", branch_id
    )
    return _business_response(
        lambda: retry_print_job(
            session,
            job_id,
            idempotency_key or "",
            actor.branch_id or "",
            actor_user_id=actor.user_id,
        )
    )


@router.get("/print-attempts/pull")
def pull_print_attempts(
    session: SessionDep, device_token: DeviceTokenDep = None
) -> list[dict[str, Any]]:
    actor = operational_route_guard.require_device_for_capability(
        session, device_token, "print.agent"
    )
    return _database_response(
        lambda: list_queued_print_attempts(session, actor.organization_id, actor.branch_id or "")
    )


@router.post("/print-attempts/{attempt_id}/claim")
def claim_print_attempt_endpoint(
    attempt_id: str, session: SessionDep, device_token: DeviceTokenDep = None
) -> dict[str, Any]:
    attempt = (
        session.execute(
            models.print_attempts.select().where(models.print_attempts.c.id == attempt_id)
        )
        .mappings()
        .first()
    )
    if not attempt:
        operational_route_guard.deny(session, "device_scope_denied", "print.agent", None)
    actor = operational_route_guard.require_device(
        session, device_token, "print.agent", attempt["organization_id"], attempt["branch_id"]
    )
    return _business_response(lambda: claim_print_attempt(session, attempt_id, actor.user_id))


@router.post("/print-attempts/{attempt_id}/ack")
def acknowledge_print_attempt_endpoint(
    attempt_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    device_token: DeviceTokenDep = None,
) -> dict[str, Any]:
    attempt = (
        session.execute(
            models.print_attempts.select().where(models.print_attempts.c.id == attempt_id)
        )
        .mappings()
        .first()
    )
    if not attempt:
        operational_route_guard.deny(session, "device_scope_denied", "print.agent", None)
    actor = operational_route_guard.require_device(
        session, device_token, "print.agent", attempt["organization_id"], attempt["branch_id"]
    )
    return _business_response(
        lambda: acknowledge_print_attempt(
            session, attempt_id, actor.user_id, str(payload.get("acknowledgement", ""))
        )
    )


@router.post("/print-attempts/{attempt_id}/fail")
def fail_print_attempt_endpoint(
    attempt_id: str,
    payload: PrintFailureRequest,
    session: SessionDep,
    device_token: DeviceTokenDep = None,
) -> dict[str, Any]:
    attempt = (
        session.execute(
            models.print_attempts.select().where(models.print_attempts.c.id == attempt_id)
        )
        .mappings()
        .first()
    )
    if not attempt:
        operational_route_guard.deny(session, "device_scope_denied", "print.agent", None)
    actor = operational_route_guard.require_device(
        session, device_token, "print.agent", attempt["organization_id"], attempt["branch_id"]
    )
    return _business_response(
        lambda: fail_print_attempt(session, attempt_id, actor.user_id, payload.error_code)
    )


@router.post("/print-attempts/{attempt_id}/recover-expired-claim")
def recover_expired_print_claim_endpoint(
    attempt_id: str, session: SessionDep, device_token: DeviceTokenDep = None
) -> dict[str, Any]:
    actor = operational_route_guard.require_device_for_capability(
        session, device_token, "print.agent"
    )

    def operation() -> dict[str, Any]:
        try:
            return recover_expired_print_claim(
                session,
                attempt_id,
                actor.organization_id,
                actor.branch_id or "",
            )
        except BusinessError as exc:
            if exc.code == "device_scope_denied":
                operational_route_guard.deny(
                    session,
                    exc.code,
                    "print.agent",
                    actor.branch_id,
                    device_id=actor.user_id,
                    organization_id=actor.organization_id,
                )
            raise

    return _business_response(operation)


@router.post("/sync/commands")
def sync_command(
    payload: dict[str, Any], session: SessionDep, device_token: DeviceTokenDep = None
) -> dict[str, Any]:
    actor = operational_route_guard.require_device_for_capability(
        session, device_token, "gateway.sync"
    )
    if (
        payload.get("organization_id") != actor.organization_id
        or payload.get("branch_id") != actor.branch_id
        or payload.get("source_device_id") != actor.user_id
    ):
        operational_route_guard.deny(
            session,
            "device_scope_denied",
            "gateway.sync",
            actor.branch_id,
            device_id=actor.user_id,
            organization_id=actor.organization_id,
        )
    return _business_response(
        lambda: receive_sync_command(
            session,
            payload,
            actor_device_id=actor.user_id,
        )
    )


@router.post("/auth/offline-grants")
def offline_cash_grant(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    if set(payload) != {"branch_id", "source_device_id"}:
        raise HTTPException(status_code=422, detail={"code": "offline_grant_payload_invalid"})
    return _business_response(
        lambda: issue_offline_cash_grant(
            session,
            actor_user_id=actor_id,
            organization_id=ORGANIZATION_ID,
            branch_id=str(payload["branch_id"]),
            source_device_id=str(payload["source_device_id"]),
        )
    )


@router.get("/sync/events")
def get_sync_events(
    session: SessionDep,
    after_checkpoint: int = 0,
    branch_id: str | None = None,
    authorization: AuthorizationDep = None,
    device_token: DeviceTokenDep = None,
) -> list[dict[str, Any]]:
    if device_token:
        actor = operational_route_guard.require_device_for_capability(
            session, device_token, "gateway.sync"
        )
    else:
        actor = operational_route_guard.require_human(
            session, authorization, "sync.events.read", branch_id
        )
    return _database_response(
        lambda: list_sync_events(
            session,
            actor.organization_id,
            actor.branch_id or "",
            after_checkpoint,
        )
    )


@router.get("/sync/status")
def sync_status(
    session: SessionDep,
    branch_id: str | None = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor = operational_route_guard.require_human(
        session, authorization, "sync.events.read", branch_id
    )
    return _database_response(
        lambda: get_sync_status(session, actor.organization_id, actor.branch_id or "")
    )


@router.put("/users/{user_id}")
def put_user(
    user_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    email = payload.get("email")
    display_name = payload.get("display_name")
    role_id = payload.get("role_id")
    password = payload.get("password")
    branch_id = payload.get("branch_id")
    employee_code = payload.get("employee_code") if "employee_code" in payload else None
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: update_user(
            session,
            user_id,
            email,
            display_name,
            actor_id,
            role_id,
            password,
            branch_id,
            employee_code,
        )
    )


@router.post("/attendance/checks")
def post_attendance_check(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: record_attendance_check(
            session,
            str(payload.get("employee_code", "")),
            str(payload.get("branch_id", "")),
            actor_id,
        )
    )


@router.get("/attendance/checks")
def get_attendance_checks(
    session: SessionDep,
    employee_code: str | None = None,
    day: str | None = None,
    month: str | None = None,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: list_attendance_checks(
            session,
            actor_id,
            employee_code=employee_code,
            day=day,
            month=month,
            branch_id=branch_id,
        )
    )


@router.delete("/users/{user_id}")
def delete_user_endpoint(
    user_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: delete_user(session, user_id, actor_id))


@router.put("/branches/{branch_id}")
def put_branch(
    branch_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    name = payload.get("name")
    code = payload.get("code")
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: update_branch(
            session,
            branch_id,
            name=name,
            code=code,
            actor_user_id=actor_id,
            extra_payload=payload,
        )
    )


@router.delete("/branches/{branch_id}")
def delete_branch_endpoint(
    branch_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: delete_branch(session, branch_id, actor_id))


@router.put("/catalog/products/{product_id}")
def put_catalog_product(
    product_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    name = payload.get("name")
    sku = payload.get("sku")
    price_cents = payload.get("price_cents")
    image_url = payload.get("image_url") if "image_url" in payload else None
    category_name = payload.get("category_name")
    station = payload.get("station")
    status = payload.get("status")
    delivery_price_cents = int(payload["delivery_price_cents"]) if payload.get("delivery_price_cents") is not None else None
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: update_product(
            session,
            product_id,
            name,
            sku,
            price_cents,
            image_url,
            category_name,
            station,
            status,
            actor_id,
            delivery_price_cents=delivery_price_cents,
        )
    )


@router.delete("/catalog/products/{product_id}")
def delete_catalog_product_endpoint(
    product_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: delete_product(session, product_id, actor_id))


def _database_response(operation: Callable[[], ResponseT]) -> ResponseT:
    try:
        return operation()
    except SQLAlchemyError as exc:
        import logging
        import traceback

        logger = logging.getLogger(__name__)
        logger.error(f"Database error: {traceback.format_exc()}")
        raise HTTPException(status_code=503, detail=f"database_unavailable: {repr(exc)}") from exc


def _serialize_api_value(value: Any) -> Any:
    """Render timestamps at the HTTP boundary as canonical RFC3339 UTC strings."""
    if isinstance(value, datetime):
        utc_value = (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        )
        return utc_value.isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {key: _serialize_api_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_api_value(item) for item in value]
    return value


def _serialize_pco_response(response: dict[str, Any]) -> dict[str, Any]:
    serialized = _serialize_api_value(response)
    if not isinstance(serialized, dict):
        raise BusinessError("pco004_response_invalid", "PCO-004 response must be an object")
    return serialized


def _serialize_operational_close_response(
    response: OperationalCloseResponse,
) -> dict[str, Any]:
    serialized_shift = _serialize_api_value(response["cash_shift"])
    serialized_closure = _serialize_api_value(response["closure"])
    if not isinstance(serialized_shift, dict) or not isinstance(serialized_closure, dict):
        raise BusinessError(
            "cash_shift_response_invalid",
            "Operational close response must contain cash shift and closure objects",
        )
    return {"cash_shift": serialized_shift, "closure": serialized_closure}


def _decode_cash_shift_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw_timestamp, cash_shift_id = cursor.rsplit("|", 1)
        timestamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
        UUID(cash_shift_id)
    except ValueError as exc:
        raise BusinessError("cash_shift_cursor_invalid", "cursor is invalid") from exc
    if timestamp.tzinfo is None:
        raise BusinessError("cash_shift_cursor_invalid", "cursor is invalid")
    return timestamp.astimezone(timezone.utc), cash_shift_id


def _business_response(operation: Callable[[], ResponseT]) -> ResponseT:
    try:
        return _database_response(operation)
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=403,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except NotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except BusinessError as exc:
        status_code = {
            "public_order_unavailable": 503,
            "public_order_rate_limited": 429,
            "public_order_schema_invalid": 422,
        }.get(exc.code, 409)
        raise HTTPException(
            status_code=status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


from restaurant_os.operations import (
    create_warehouse,
    delete_role,
    update_role,
    update_role_permissions,
    update_warehouse,
)
from restaurant_os.platform_data import (
    list_permissions,
    list_role_permissions,
    list_warehouses,
)


@router.put("/roles/{role_id}")
def put_role(
    role_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    name = payload.get("name")
    scope = payload.get("scope")
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: update_role(session, role_id, name, scope, actor_id))


@router.delete("/roles/{role_id}")
def delete_role_endpoint(
    role_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: delete_role(session, role_id, actor_id))


@router.get("/permissions")
def get_permissions(
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    def operation() -> list[dict[str, Any]]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        require_permission(session, actor_id, "admin.manage")
        return list_permissions(session)

    return _business_response(operation)


@router.get("/roles/{role_id}/permissions")
def get_role_permissions(
    role_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[str]:
    def operation() -> list[str]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        require_permission(session, actor_id, "admin.manage")
        return list_role_permissions(session, role_id)

    return _business_response(operation)


@router.put("/roles/{role_id}/permissions")
def put_role_permissions(
    role_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    permission_ids = payload.get("permission_ids", [])
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: update_role_permissions(session, role_id, permission_ids, actor_id)
    )


@router.get("/warehouses")
def get_warehouses(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    def operation() -> list[dict[str, Any]]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        authorized_branch = authorize_branch_scope(session, actor_id, "catalog.manage", branch_id)
        return list_warehouses(session, authorized_branch)

    return _business_response(operation)


@router.post("/warehouses")
def post_warehouse(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    branch_id = str(payload.get("branch_id", ""))
    name = str(payload.get("name", ""))
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: create_warehouse(session, branch_id, name, actor_id))


@router.put("/warehouses/{warehouse_id}")
def put_warehouse(
    warehouse_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    name = payload.get("name")
    status = payload.get("status")
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: update_warehouse(session, warehouse_id, name, status, actor_id)
    )


from restaurant_os.operations import (
    create_inventory_item,
    create_inventory_unit,
    update_inventory_item,
    update_inventory_unit,
)
from restaurant_os.platform_data import (
    list_inventory_items,
    list_inventory_units,
)


@router.get("/inventory/units")
def get_inventory_units(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    def operation() -> list[dict[str, Any]]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        authorize_branch_scope(session, actor_id, "inventory.read", branch_id)
        return list_inventory_units(session)

    return _business_response(operation)


@router.post("/inventory/units")
def post_inventory_unit(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    code = str(payload.get("code", ""))
    name = str(payload.get("name", ""))
    precision_scale = int(payload.get("precision_scale", 0))
    dimension = str(payload.get("dimension", "discrete"))
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: create_inventory_unit(session, code, name, precision_scale, dimension, actor_id)
    )


@router.put("/inventory/units/{unit_id}")
def put_inventory_unit(
    unit_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    name = payload.get("name")
    precision_scale = payload.get("precision_scale")
    if precision_scale is not None:
        precision_scale = int(precision_scale)
    dimension = payload.get("dimension")
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: update_inventory_unit(session, unit_id, name, precision_scale, dimension, actor_id)
    )


@router.get("/inventory/items")
def get_inventory_items(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    def operation() -> list[dict[str, Any]]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        authorized_branch = authorize_branch_scope(session, actor_id, "inventory.read", branch_id)
        return list_inventory_items(session, authorized_branch)

    return _business_response(operation)


@router.post("/inventory/items")
def post_inventory_item(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    name = str(payload.get("name", ""))
    sku = str(payload.get("sku", ""))
    base_unit_id = str(payload.get("base_unit_id", ""))
    item_type = str(payload.get("item_type", "ingredient"))
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: create_inventory_item(session, name, sku, base_unit_id, item_type, actor_id)
    )


@router.put("/inventory/items/{item_id}")
def put_inventory_item(
    item_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    name = payload.get("name")
    base_unit_id = payload.get("base_unit_id")
    item_type = payload.get("item_type")
    status = payload.get("status")
    category_name = payload.get("category_name")
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: update_inventory_item(
            session,
            item_id,
            name,
            base_unit_id,
            item_type,
            status,
            category_name,
            actor_id,
        )
    )


from restaurant_os.operations import (
    create_category,
    get_effective_product_recipe,
    get_recipes_workspace,
    update_category,
    update_product_recipe_versioned,
)
from restaurant_os.platform_data import (
    list_categories,
)


@router.get("/categories")
@router.get("/catalog/categories")
def get_categories(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    def operation() -> list[dict[str, Any]]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        user_org = session.execute(
            sa.select(models.users.c.organization_id).where(models.users.c.id == actor_id)
        ).scalar()
        org_id = str(user_org) if user_org else None
        if branch_id:
            authorized_branch = authorize_branch_scope(session, actor_id, "pos.operate", branch_id)
            return list_categories(session, authorized_branch, organization_id=org_id)
        return list_categories(session, organization_id=org_id)

    return _business_response(operation)


@router.post("/categories")
def post_category(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    name = str(payload.get("name", ""))
    display_order = int(payload.get("display_order", 0))
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: create_category(session, name, display_order, actor_id))


@router.put("/categories/{category_id}")
def put_category(
    category_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    name = payload.get("name")
    display_order = payload.get("display_order")
    if display_order is not None:
        display_order = int(display_order)
    status = payload.get("status")
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: update_category(session, category_id, name, display_order, status, actor_id)
    )


@router.get("/categories/{category_id}/selection-group")
def get_category_selection_group(
    category_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: category_option_coverage(session, category_id, actor_id))


@router.post("/categories/{category_id}/selection-group")
def post_category_selection_group(
    category_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: upsert_category_option_group(session, category_id, payload, actor_id)
    )


@router.get("/catalog/category-option-groups/{group_id}/coverage")
def get_category_option_group_coverage(
    group_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: get_category_option_group_coverage_operation(session, group_id, actor_id)
    )


@router.post("/catalog/category-option-groups/{group_id}/values")
def post_category_option_value(
    group_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: upsert_category_option_value(session, group_id, payload, actor_user_id=actor_id)
    )


@router.put("/catalog/category-option-groups/{group_id}/values/{value_id}")
def put_category_option_value(
    group_id: str,
    value_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: upsert_category_option_value(session, group_id, payload, value_id, actor_id)
    )


@router.put("/catalog/category-option-groups/{group_id}/assignments/{product_id}")
def put_product_category_option_assignment(
    group_id: str,
    product_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: assign_product_category_option(
            session, group_id, product_id, str(payload.get("option_value_id", "")), actor_id
        )
    )


@router.get("/products/{product_id}/recipe")
def get_recipe(
    product_id: str,
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    recipe = _business_response(
        lambda: get_effective_product_recipe(session, product_id, branch_id, actor_id)
    )
    return recipe or {"components": []}


@router.get("/recipes/workspace")
def get_recipes_workspace_route(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: get_recipes_workspace(session, actor_id, branch_id))


class RecipeAiParseRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    raw_text: str = Field(..., min_length=5)
    product_id: str | None = None
    sale_price: Decimal | None = None
    yield_portions: Decimal | None = Field(default=Decimal("1"))


@router.post("/recipes/ai-parse")
def post_recipe_ai_parse(
    payload: RecipeAiParseRequest,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    def operation() -> dict[str, Any]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        require_permission(session, actor_id, "catalog.manage")

        # 1. Fetch available supplies with base units and costs
        items_query = (
            sa.select(
                models.inventory_items.c.id,
                models.inventory_items.c.name,
                models.inventory_items.c.sku,
                models.inventory_units.c.code.label("unit"),
                sa.func.coalesce(models.purchase_presentations.c.cost_per_base_unit, 0).label(
                    "cost"
                ),
            )
            .select_from(
                models.inventory_items.join(
                    models.inventory_units,
                    models.inventory_items.c.base_unit_id == models.inventory_units.c.id,
                ).outerjoin(
                    models.purchase_presentations,
                    sa.and_(
                        models.purchase_presentations.c.item_id == models.inventory_items.c.id,
                        models.purchase_presentations.c.is_preferred.is_(True),
                    ),
                )
            )
            .where(
                models.inventory_items.c.organization_id == ORGANIZATION_ID,
                models.inventory_items.c.status == "active",
            )
        )
        catalog_supplies = [dict(row) for row in session.execute(items_query).mappings().all()]

        # 2. If product_id given, lookup product sale price if not explicitly provided
        sale_price = payload.sale_price or Decimal("0")
        product_name = ""
        if payload.product_id:
            prod_row = (
                session.execute(
                    sa.select(
                        models.products.c.name,
                        models.price_versions.c.price_cents,
                    )
                    .select_from(
                        models.products.outerjoin(
                            models.price_versions,
                            sa.and_(
                                models.price_versions.c.product_id == models.products.c.id,
                                models.price_versions.c.valid_to.is_(None),
                            ),
                        )
                    )
                    .where(
                        models.products.c.id == payload.product_id,
                        models.products.c.organization_id == ORGANIZATION_ID,
                    )
                )
                .mappings()
                .first()
            )
            if prod_row:
                product_name = prod_row["name"]
                if sale_price == 0 and prod_row["price_cents"]:
                    sale_price = Decimal(prod_row["price_cents"]) / Decimal("100")

        # 3. Parse free-form recipe text
        parsed = parse_recipe_text(payload.raw_text)

        # 4. Semantic match and unit normalization for each ingredient
        matched_ingredients = []
        for ing in parsed["ingredients"]:
            match = match_ingredient_to_catalog(ing["raw_name"], catalog_supplies)
            if match:
                target_base_unit = match["base_unit"]
                normalized_qty = normalize_culinary_quantity(
                    quantity=ing["quantity"],
                    unit=ing["unit"],
                    target_base_unit=target_base_unit,
                    density_hint=ing["raw_name"],
                )
                unit_cost = match["unit_cost"]
                matched_ingredients.append(
                    {
                        "raw_name": ing["raw_name"],
                        "quantity": ing["quantity"],
                        "unit": ing["unit"],
                        "matched_item_id": match["matched_item_id"],
                        "matched_item_name": match["matched_item_name"],
                        "base_unit": target_base_unit,
                        "normalized_quantity": normalized_qty,
                        "unit_cost": unit_cost,
                        "confidence_score": match["confidence_score"],
                        "status": "matched",
                    }
                )
            else:
                matched_ingredients.append(
                    {
                        "raw_name": ing["raw_name"],
                        "quantity": ing["quantity"],
                        "unit": ing["unit"],
                        "matched_item_id": None,
                        "matched_item_name": None,
                        "base_unit": "KILO"
                        if "g" in ing["unit"] or "kg" in ing["unit"]
                        else (
                            "LITRO"
                            if "l" in ing["unit"] or "taza" in ing["unit"] or "cda" in ing["unit"]
                            else "PIEZA"
                        ),
                        "normalized_quantity": ing["quantity"],
                        "unit_cost": Decimal("0.00"),
                        "confidence_score": 0.0,
                        "status": "unmatched",
                    }
                )

        # 5. Calculate theoretical cost and margins
        cost_analysis = calculate_theoretical_recipe_cost(
            ingredients=matched_ingredients,
            yield_portions=payload.yield_portions or Decimal("1"),
            sale_price=sale_price,
        )

        return {
            "title": product_name or parsed["title"],
            "product_id": payload.product_id,
            "steps": parsed["steps"],
            **cost_analysis,
        }

    return _business_response(operation)


@router.put("/products/{product_id}/recipe")
def put_recipe(
    product_id: UUID,
    payload: RecipeVersionRequest,
    session: SessionDep,
    idempotency_key: IdempotencyKeyDep = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    if not idempotency_key:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "idempotency_key_required",
                "message": "Idempotency-Key is required",
            },
        )
    body = payload.model_dump(mode="json")
    branch_id = body.pop("branch_id")
    expected_active_recipe_id = body.pop("expected_active_recipe_id")
    return _business_response(
        lambda: update_product_recipe_versioned(
            session,
            str(product_id),
            body,
            branch_id,
            expected_active_recipe_id,
            idempotency_key,
            actor_id,
        )
    )


@router.get("/products/{product_id}/modifiers")
def get_product_modifiers(
    product_id: str,
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    def operation() -> list[dict[str, Any]]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        authorized_branch = authorize_branch_scope(session, actor_id, "pos.operate", branch_id)
        return list_product_modifiers(session, product_id, authorized_branch)

    return _business_response(operation)


@router.post("/products/{product_id}/modifier-groups")
def post_modifier_group(
    product_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: create_modifier_group(session, product_id, payload, actor_id))


@router.get("/products/{product_id}/modifier-groups")
def get_modifier_catalog_groups(
    product_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)

    def operation() -> list[dict[str, Any]]:
        require_permission(session, actor_id, "catalog.manage")
        return list_product_modifiers(session, product_id, catalog_view=True)

    return _business_response(operation)


@router.patch("/modifier-groups/{group_id}")
def patch_modifier_group(
    group_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: update_modifier_group(session, group_id, payload, actor_id))


@router.delete("/modifier-groups/{group_id}")
def delete_modifier_group_endpoint(
    group_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: archive_modifier_group(session, group_id, actor_id))


@router.get("/catalog/variation-notes")
def get_variation_notes(
    product_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: list_variation_notes(session, product_id, actor_id))


@router.post("/products/{product_id}/variation-notes")
def post_variation_note(
    product_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: create_variation_note(session, product_id, payload, actor_id))


@router.put("/variation-notes/{option_id}")
def put_variation_note(
    option_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: update_variation_note(session, option_id, payload, actor_id))


@router.get("/catalog/order-comments")
def get_order_comments(
    session: SessionDep,
    status: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: list_order_comments(session, status, actor_id))


@router.post("/catalog/order-comments/bulk/preview")
def post_order_comments_bulk_preview(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: preview_order_comments_bulk(session, payload, actor_id))


@router.post("/catalog/order-comments/bulk")
def post_order_comments_bulk(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: bulk_order_comments(session, payload, actor_id))


@router.put("/catalog/order-comments/{comment_id}")
def put_order_comment(
    comment_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: update_order_comment(session, comment_id, payload, actor_id))


@router.put("/catalog/order-comments/{comment_id}/products")
def put_order_comment_products(
    comment_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: replace_order_comment_products(session, comment_id, payload, actor_id)
    )


@router.get("/catalog/ingredient-extras/available")
def get_available_ingredient_extras(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: list_available_ingredient_extras(session, actor_id, branch_id)
    )


@router.get("/catalog/ingredient-variations")
def get_ingredient_variations(
    session: SessionDep,
    search: str = "",
    status: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: list_ingredient_variations(session, search, status, actor_id))


@router.post("/catalog/ingredient-variations")
def post_ingredient_variation(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: create_ingredient_variation(session, payload, actor_id))


@router.post("/catalog/seed-starter-template")
def post_seed_starter_template(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "catalog.manage")
    template_type = str(payload.get("template_type") or "general").strip()
    branch_id = payload.get("branch_id")
    from restaurant_os.saas_onboarding import seed_starter_catalog_for_org
    from restaurant_os.operations import ORGANIZATION_ID
    return _business_response(
        lambda: seed_starter_catalog_for_org(
            session=session,
            organization_id=ORGANIZATION_ID,
            branch_id=branch_id,
            business_type=template_type,
        )
    )


@router.post("/catalog/parse-menu-file")
def post_parse_menu_file(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "catalog.manage")
    file_base64 = str(payload.get("file_base64") or "").strip()
    mime_type = str(payload.get("mime_type") or "").strip()
    filename = str(payload.get("filename") or "menu").strip()
    if not file_base64:
        raise HTTPException(status_code=400, detail="Se requiere el archivo en base64.")

    from restaurant_os.assisted_order import OpenRouterOptions
    from restaurant_os.config import get_settings
    from restaurant_os.menu_parser import parse_menu_document

    settings = get_settings()
    custom_key = str(payload.get("api_key") or "").strip()
    api_key = custom_key or settings.openrouter_api_key

    options = OpenRouterOptions(
        api_key=api_key or "",
        model=settings.openrouter_model,
        base_url=settings.openrouter_base_url,
        timeout_seconds=settings.openrouter_timeout_seconds,
        http_referer=settings.openrouter_http_referer,
        app_title=settings.openrouter_app_title,
    )

    try:
        return parse_menu_document(file_base64, mime_type, filename, options)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/catalog/import-custom-catalog")
def post_import_custom_catalog(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "catalog.manage")
    categories = payload.get("categories") or []
    branch_id = payload.get("branch_id")
    mobile_theme = payload.get("mobile_theme")
    from restaurant_os.saas_onboarding import import_custom_catalog_for_org
    from restaurant_os.operations import ORGANIZATION_ID

    res = import_custom_catalog_for_org(
        session=session,
        organization_id=ORGANIZATION_ID,
        branch_id=branch_id,
        catalog_data=categories,
        mobile_theme=mobile_theme,
    )
    session.commit()
    return res


@router.get("/catalog/ingredient-variations/{variation_id}")
def get_ingredient_variation_endpoint(
    variation_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: get_ingredient_variation(session, variation_id, actor_id))


@router.put("/catalog/ingredient-variations/{variation_id}")
def put_ingredient_variation(
    variation_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: update_ingredient_variation(session, variation_id, payload, actor_id)
    )


@router.post("/catalog/ingredient-variations/{variation_id}/assignments/preview")
def post_ingredient_variation_assignment_preview(
    variation_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: preview_ingredient_variation_assignments(session, variation_id, payload, actor_id)
    )


@router.put("/catalog/ingredient-variations/{variation_id}/assignments")
def put_ingredient_variation_assignments(
    variation_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    idempotency_key: IdempotencyKeyDep = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: apply_ingredient_variation_assignments(
            session, variation_id, payload, idempotency_key or "", actor_id
        )
    )


@router.put("/catalog/ingredient-variations/{variation_id}/assignments/{product_id}")
def put_ingredient_variation_assignment(
    variation_id: str,
    product_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    idempotency_key: IdempotencyKeyDep = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: apply_ingredient_variation_assignments(
            session,
            variation_id,
            {**payload, "product_ids": [product_id], "category_ids": []},
            idempotency_key or "",
            actor_id,
            assignment_update=True,
        )
    )


@router.delete("/catalog/ingredient-variations/{variation_id}/assignments/{product_id}")
def delete_ingredient_variation_assignment(
    variation_id: str,
    product_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: archive_ingredient_variation_assignment(session, variation_id, product_id, actor_id)
    )


@router.post("/modifier-groups/{group_id}/options")
def post_modifier_option(
    group_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: create_modifier_option(session, group_id, payload, actor_id))


@router.put("/modifier-groups/{group_id}")
def put_modifier_group(
    group_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: update_modifier_group(session, group_id, payload, actor_id))


@router.delete("/modifier-groups/{group_id}")
def delete_modifier_group(
    group_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: archive_modifier_group(session, group_id, actor_id))


@router.put("/modifier-options/{option_id}")
def put_modifier_option(
    option_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: update_modifier_option(session, option_id, payload, actor_id))


@router.delete("/modifier-options/{option_id}")
def delete_modifier_option(
    option_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: archive_modifier_option(session, option_id, actor_id))


@router.post("/modifier-groups/{group_id}/clone")
def post_clone_modifier_group(
    group_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: clone_modifier_group(
            session, group_id, str(payload.get("target_product_id")), actor_id
        )
    )


@router.post("/products/{product_id}/clone-modifiers")
def post_clone_all_modifiers(
    product_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: clone_all_modifier_groups(
            session, product_id, str(payload.get("target_product_id")), actor_id
        )
    )


@router.put("/products/{product_id}/modifier-groups/reorder")
def put_reorder_modifier_groups(
    product_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: reorder_modifier_groups(
            session, product_id, list(payload.get("ordered_ids", [])), actor_id
        )
    )


@router.put("/modifier-groups/{group_id}/options/reorder")
def put_reorder_modifier_options(
    group_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: reorder_modifier_options(
            session, group_id, list(payload.get("ordered_ids", [])), actor_id
        )
    )


@router.patch("/modifier-options/{option_id}")
def patch_modifier_option(
    option_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: update_modifier_option(session, option_id, payload, actor_id))


@router.delete("/modifier-options/{option_id}")
def delete_modifier_option_endpoint(
    option_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: archive_modifier_option(session, option_id, actor_id))


@router.put("/modifier-options/{option_id}/branches/{branch_id}")
def put_branch_modifier_option(
    option_id: str,
    branch_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: set_branch_modifier_option(session, option_id, branch_id, payload, actor_id)
    )


@router.post("/production-recipes")
def post_production_recipe(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: create_production_recipe(
            session,
            str(payload.get("output_item_id", "")),
            list(payload.get("components", [])),
            payload.get("yield_quantity", 1),
            str(payload.get("yield_unit_id", "")),
            payload.get("branch_id"),
            actor_id,
        )
    )


@router.get("/production-batches")
def get_production_batches(
    branch_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    def operation() -> list[dict[str, Any]]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        authorized_branch = authorize_branch_scope(
            session, actor_id, "production.manage", branch_id
        )
        return list_production_batches(session, authorized_branch)

    return _business_response(operation)


@router.post("/production-batches")
def post_production_batch(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: create_production_batch(session, payload, actor_id))


@router.post("/production-batches/{batch_id}/confirm")
def post_confirm_production_batch(
    batch_id: str,
    session: SessionDep,
    idempotency_key: IdempotencyKeyDep = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: confirm_production_batch(session, batch_id, idempotency_key or "", actor_id)
    )


@router.get("/customers")
def get_customers(
    session: SessionDep,
    phone: str | None = None,
    branch_id: str | None = None,
    q: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> Any:
    def operation() -> Any:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        authorized_branch = authorize_branch_scope(session, actor_id, "orders.read", branch_id)
        if limit is not None or q is not None:
            return list_customers_page(session, authorized_branch, q, phone, limit or 50, offset)
        return list_customers(session, phone, authorized_branch)

    return _business_response(operation)


@router.post("/customers")
def post_customer(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    branch_id = payload.get("branch_id")

    def operation() -> dict[str, Any]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        authorized_branch = authorize_branch_scope(session, actor_id, "orders.create", branch_id)
        return create_customer(
            session,
            str(payload.get("name", "")),
            payload.get("email"),
            list(payload.get("phones", [])),
            authorized_branch,
            actor_id,
        )

    return _business_response(operation)


@router.post("/customers/{customer_id}/addresses")
def post_customer_address(
    customer_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    branch_id = payload.get("branch_id")

    def operation() -> dict[str, Any]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        authorized_branch = authorize_branch_scope(session, actor_id, "orders.create", branch_id)
        return add_customer_address(session, customer_id, payload, authorized_branch, actor_id)

    return _business_response(operation)


@router.put("/customers/{customer_id}")
def put_customer(
    customer_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    branch_id = payload.get("branch_id")

    def operation() -> dict[str, Any]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        authorized_branch = authorize_branch_scope(session, actor_id, "orders.create", branch_id)
        return update_customer(session, customer_id, payload, authorized_branch, actor_id)

    return _business_response(operation)


@router.put("/customers/{customer_id}/addresses/{address_id}")
def put_customer_address(
    customer_id: str,
    address_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    branch_id = payload.get("branch_id")

    def operation() -> dict[str, Any]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        authorized_branch = authorize_branch_scope(session, actor_id, "orders.create", branch_id)
        return update_customer_address(
            session, customer_id, address_id, payload, authorized_branch, actor_id
        )

    return _business_response(operation)


@router.put("/customers/{customer_id}/tax-profile")
def put_customer_tax_profile(
    customer_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    branch_id = payload.get("branch_id")

    def operation() -> dict[str, Any]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        authorized_branch = authorize_branch_scope(session, actor_id, "orders.create", branch_id)
        return upsert_customer_tax_profile(
            session, customer_id, payload, authorized_branch, actor_id
        )

    return _business_response(operation)


@router.get("/suppliers")
def get_suppliers(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    authorize_branch_scope(session, actor_id, "purchases.read", branch_id)
    return _database_response(lambda: list_suppliers(session))


@router.post("/suppliers")
def post_supplier(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: create_supplier(session, payload, actor_id))


@router.put("/suppliers/{supplier_id}")
def put_supplier(
    supplier_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: update_supplier(session, supplier_id, payload, actor_id))


@router.delete("/suppliers/{supplier_id}")
def delete_supplier_route(
    supplier_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: delete_supplier(session, supplier_id, actor_id))


@router.post("/suppliers/{supplier_id}/contacts")
def post_supplier_contact(
    supplier_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: add_supplier_contact(session, supplier_id, payload, actor_id))


@router.put("/suppliers/{supplier_id}/branches/{branch_id}")
def put_supplier_branch_terms(
    supplier_id: str,
    branch_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: set_supplier_branch_terms(session, supplier_id, branch_id, payload, actor_id)
    )


@router.get("/purchase-presentations")
def get_purchase_presentations(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    def operation() -> list[dict[str, Any]]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        authorize_branch_scope(session, actor_id, "purchases.read", branch_id)
        return list_purchase_presentations(session)

    return _business_response(operation)


@router.post("/purchase-presentations")
def post_purchase_presentation(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: create_purchase_presentation(session, payload, actor_id))


@router.put("/purchase-presentations/{presentation_id}")
def put_purchase_presentation(
    presentation_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: update_purchase_presentation(session, presentation_id, payload, actor_id)
    )


@router.put("/purchase-presentations/{presentation_id}/price")
def put_purchase_presentation_price(
    presentation_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: update_purchase_presentation_price(
            session, presentation_id, payload.get("net_price"), actor_id
        )
    )


@router.get("/purchases")
def get_purchases(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    authorized_branch = authorize_branch_scope(session, actor_id, "purchases.read", branch_id)
    return _database_response(lambda: list_purchase_documents(session, authorized_branch))


@router.post("/purchases")
def post_purchase(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: create_purchase_document(session, payload, actor_id))


@router.post("/purchases/{purchase_id}/confirm")
def confirm_purchase_endpoint(
    purchase_id: str,
    payload: dict[str, Any] | None,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
    idempotency_key_header: IdempotencyKeyDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    idempotency_key = idempotency_key_header or str((payload or {}).get("idempotency_key", ""))
    register_id = str((payload or {}).get("register_id", ""))
    return _business_response(
        lambda: confirm_purchase_document(
            session, purchase_id, idempotency_key, register_id, actor_id
        )
    )


@router.post("/purchases/{purchase_id}/cancel")
def cancel_purchase_endpoint(
    purchase_id: str,
    payload: dict[str, Any] | None,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    reason = str((payload or {}).get("reason", ""))
    return _business_response(
        lambda: cancel_purchase_document(session, purchase_id, reason, actor_id)
    )


@router.get("/cash/concepts/effective")
def get_effective_cash_concepts(
    session: SessionDep,
    movement_type: str,
    effective_at: datetime | None = None,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: list_effective_cash_concepts(
            session,
            movement_type,
            effective_at or datetime.now(timezone.utc),
            actor_id,
            branch_id,
        )
    )


@router.get("/cash/concepts")
def get_cash_concepts(
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: list_cash_concepts(session, actor_id))


@router.post("/cash/concepts")
def post_cash_concept(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
    idempotency_key: IdempotencyKeyDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: create_cash_concept(session, payload, idempotency_key or "", actor_id)
    )


@router.put("/cash/concepts/{concept_id}/versions")
def put_cash_concept_version(
    concept_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
    idempotency_key: IdempotencyKeyDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: create_cash_concept_version(
            session, concept_id, payload, idempotency_key or "", actor_id
        )
    )


@router.post("/cash/concepts/{concept_id}/archive")
def post_cash_concept_archive(
    concept_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
    idempotency_key: IdempotencyKeyDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: archive_cash_concept(session, concept_id, idempotency_key or "", actor_id)
    )


@router.post("/cash/movements")
def post_cash_movement(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
    idempotency_key: IdempotencyKeyDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: create_cash_movement(session, payload, idempotency_key or "", actor_id)
    )


@router.post("/cash/movements/{movement_id}/compensations")
def post_cash_movement_compensation(
    movement_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
    idempotency_key: IdempotencyKeyDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: compensate_cash_movement(
            session, movement_id, payload, idempotency_key or "", actor_id
        )
    )


@router.get("/cash/movements")
def get_cash_movement_ledger(
    branch_id: str,
    session: SessionDep,
    register_id: str | None = None,
    cash_shift_id: str | None = None,
    movement_type: str | None = None,
    from_utc: datetime | None = None,
    to_utc: datetime | None = None,
    limit: int = 50,
    cursor: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: list_cash_movement_ledger(
            session,
            actor_id,
            branch_id,
            register_id,
            cash_shift_id,
            movement_type,
            from_utc,
            to_utc,
            limit,
            cursor,
        )
    )


@router.get("/cash-movements")
def get_cash_movements(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    authorized_branch = authorize_branch_scope(session, actor_id, "cash.shift.read", branch_id)
    return _database_response(lambda: list_cash_movements(session, authorized_branch))


@router.get("/inventory/costs")
def get_inventory_costs(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    authorized_branch = authorize_branch_scope(session, actor_id, "inventory.read", branch_id)
    return _database_response(lambda: list_inventory_cost_states(session, authorized_branch))


@router.get("/inventory/waste-reasons")
def get_waste_reasons(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    def operation() -> list[dict[str, Any]]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        authorize_branch_scope(session, actor_id, "inventory.read", branch_id)
        return list_waste_reasons(session)

    return _business_response(operation)


@router.post("/inventory/waste-reasons")
def post_waste_reason(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: create_waste_reason(session, payload, actor_id))


@router.put("/inventory/waste-reasons/{reason_id}")
def put_waste_reason(
    reason_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: update_waste_reason(session, reason_id, payload, actor_id))


@router.get("/inventory/wastes")
def get_waste_records_endpoint(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    authorized_branch = authorize_branch_scope(session, actor_id, "inventory.read", branch_id)
    return _database_response(lambda: list_waste_records(session, authorized_branch))


@router.post("/inventory/wastes")
def post_waste_record_endpoint(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:

    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: create_waste_record(session, payload, actor_id))


@router.post("/inventory/wastes/{waste_id}/confirm")
def confirm_waste_record_endpoint(
    waste_id: str,
    session: SessionDep,
    idempotency_key: IdempotencyKeyDep = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: confirm_waste_record(session, waste_id, idempotency_key or "", actor_id)
    )


@router.post("/inventory/wastes/{waste_id}/reverse")
def reverse_waste_record_endpoint(
    waste_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    idempotency_key: IdempotencyKeyDep = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: reverse_waste_record(
            session, waste_id, str(payload.get("reason", "")), idempotency_key or "", actor_id
        )
    )


@router.get("/inventory/transfers")
def get_inventory_transfers_endpoint(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    authorized_branch = authorize_branch_scope(session, actor_id, "inventory.read", branch_id)
    return _database_response(lambda: list_inventory_transfers(session, authorized_branch))


@router.post("/inventory/transfers")
def post_inventory_transfer_endpoint(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: create_inventory_transfer(session, payload, actor_id))


@router.post("/inventory/transfers/{transfer_id}/send")
def send_inventory_transfer_endpoint(
    transfer_id: str,
    session: SessionDep,
    idempotency_key: IdempotencyKeyDep = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: send_inventory_transfer(session, transfer_id, idempotency_key or "", actor_id)
    )


@router.post("/inventory/transfers/{transfer_id}/receive")
def receive_inventory_transfer_endpoint(
    transfer_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    idempotency_key: IdempotencyKeyDep = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: receive_inventory_transfer(
            session, transfer_id, list(payload.get("lines", [])), idempotency_key or "", actor_id
        )
    )


@router.post("/inventory/transfers/{transfer_id}/cancel")
def cancel_inventory_transfer_endpoint(
    transfer_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: cancel_inventory_transfer(
            session, transfer_id, str(payload.get("reason", "")), actor_id
        )
    )


@router.get("/inventory/physical-counts")
def get_physical_counts_endpoint(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    authorized_branch = authorize_branch_scope(session, actor_id, "inventory.count", branch_id)
    return _database_response(lambda: list_physical_count_sessions(session, authorized_branch))


@router.post("/inventory/physical-counts")
def post_physical_count_endpoint(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: create_physical_count_session(session, payload, actor_id))


@router.put("/inventory/physical-counts/{count_id}/lines/{line_id}")
def put_physical_count_line_endpoint(
    count_id: str,
    line_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: capture_physical_count_line(
            session,
            count_id,
            line_id,
            payload.get("counted_quantity", 0),
            payload.get("notes"),
            actor_id,
        )
    )


@router.post("/inventory/physical-counts/{count_id}/submit")
def submit_physical_count_endpoint(
    count_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: submit_physical_count_session(session, count_id, actor_id))


@router.post("/inventory/physical-counts/{count_id}/approve")
def approve_physical_count_endpoint(
    count_id: str,
    session: SessionDep,
    idempotency_key: IdempotencyKeyDep = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: approve_physical_count_session(session, count_id, idempotency_key or "", actor_id)
    )


@router.post("/inventory/physical-counts/{count_id}/close")
def close_physical_count_endpoint(
    count_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: close_physical_count_session(session, count_id, actor_id))


@router.post("/inventory/physical-counts/{count_id}/cancel")
def cancel_physical_count_endpoint(
    count_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: cancel_physical_count_session(
            session, count_id, str(payload.get("reason", "")), actor_id
        )
    )


# ---------------------------------------------------------------------------
# Branch administration (BA-001)
# ---------------------------------------------------------------------------


@router.get("/branch-administration/context")
def get_branch_admin_context(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: get_branch_context(session, actor_id, branch_id))


@router.get("/branch-administration/staff")
def get_branch_admin_staff(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: list_branch_staff(session, actor_id, branch_id))


@router.get("/branch-administration/catalog/products")
def get_branch_admin_catalog_products(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: list_branch_admin_catalog_products(session, actor_id, branch_id)
    )


@router.get("/branch-administration/catalog/variation-notes")
def get_branch_admin_variation_notes(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: list_branch_variation_notes(session, actor_id, branch_id))


@router.get("/branch-administration/imports")
def get_branch_admin_imports(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: list_branch_legacy_import_batches(session, actor_id, branch_id)
    )


@router.put("/branch-administration/catalog/products/{product_id}/availability")
def put_branch_admin_availability(
    product_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    action = str(payload.get("action", ""))
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: set_branch_product_availability(session, actor_id, product_id, action, branch_id)
    )


@router.put("/branch-administration/catalog/variation-notes/{option_id}")
def put_branch_admin_variation_note(
    option_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: set_branch_variation_note(
            session, actor_id, option_id, str(payload.get("action", "")), branch_id
        )
    )


@router.get("/branch-administration/catalog/ingredient-variations")
def get_branch_admin_ingredient_variations(
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: list_branch_ingredient_variations(session, actor_id, branch_id)
    )


@router.put("/branch-administration/catalog/ingredient-variations/{option_id}")
def put_branch_admin_ingredient_variation(
    option_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    branch_id: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: set_branch_ingredient_variation_option(
            session, actor_id, option_id, str(payload.get("action", "")), branch_id
        )
    )


# ---------------------------------------------------------------------------
# Legacy branch catalog imports (DATA-001)
# ---------------------------------------------------------------------------


@router.post("/legacy-imports")
def post_legacy_import_batch(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: create_legacy_import_batch(
            session,
            actor_id,
            str(payload.get("branch_id", "")),
            str(payload.get("source_system", "")),
            str(payload.get("manifest_checksum", "")),
            dict(payload.get("manifest") or {}),
        )
    )


@router.get("/legacy-imports")
def get_legacy_import_batches(
    branch_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: list_legacy_import_batches(session, actor_id, branch_id))


@router.post("/legacy-imports/{batch_id}/records")
def post_legacy_import_records(
    batch_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: ingest_legacy_import_records(
            session, actor_id, batch_id, list(payload.get("records") or [])
        )
    )


@router.get("/legacy-imports/{batch_id}/records")
def get_legacy_import_records(
    batch_id: str,
    session: SessionDep,
    status: str | None = None,
    entity_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(
        lambda: list_legacy_import_records(
            session, actor_id, batch_id, status, limit, offset, entity_type
        )
    )


@router.post("/legacy-imports/{batch_id}/complete")
def post_complete_legacy_import(
    batch_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    return _business_response(lambda: complete_legacy_import_batch(session, actor_id, batch_id))


# ---------------------------------------------------------------------------
# Integrations Hub: Delivery Channels & Global Kill-Switch
# ---------------------------------------------------------------------------

from restaurant_os.integrations.kill_switch import get_channels_status, toggle_kill_switch


@router.post("/integrations/kill-switch")
@router.post("/v1/integrations/kill-switch")
def post_kill_switch(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    def operation() -> dict[str, Any]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        return toggle_kill_switch(session, actor_id, payload)

    return _business_response(operation)


@router.get("/integrations/channels/status")
@router.get("/v1/integrations/channels/status")
def get_integrations_channels_status(
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    def operation() -> list[dict[str, Any]]:
        actor_id = _required_actor_from_request(actor_user_id, authorization)
        return get_channels_status(session, actor_id)

    return _business_response(operation)



@router.post("/integrations/uber-eats/webhook")
@router.post("/v1/integrations/uber-eats/webhook")
async def post_uber_eats_webhook(
    request: Request,
    session: SessionDep,
) -> dict[str, Any]:
    body_bytes = await request.body()
    signature = request.headers.get("x-uber-signature") or request.headers.get("X-Uber-Signature")

    config = channel_service.get_config(session, ORGANIZATION_ID, "UBER_EATS")
    webhook_secret = config.get("webhook_secret") if config else None

    # Validate HMAC signature if secret is configured
    if webhook_secret:
        is_valid = channel_service.uber_adapter.verify_webhook_signature(
            body_bytes, signature, webhook_secret
        )
        if not is_valid:
            channel_service.log_webhook(
                session,
                ORGANIZATION_ID,
                "UBER_EATS",
                "unauthorized_webhook",
                None,
                signature,
                {"error": "Firma HMAC inválida", "headers": dict(request.headers)},
                "rejected",
                "Firma HMAC inválida o ausente.",
            )
            raise HTTPException(status_code=401, detail="Firma de webhook inválida.")

    try:
        payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
    except Exception:
        raise HTTPException(status_code=400, detail="Cuerpo JSON inválido.") from None

    event_type, event_id = channel_service.uber_adapter.parse_webhook_event(payload)

    # Log webhook
    channel_service.log_webhook(
        session,
        ORGANIZATION_ID,
        "UBER_EATS",
        event_type,
        event_id,
        signature,
        payload,
        "received",
    )

    # Process order if it is an order event or full order payload
    if (
        event_type in ("orders.notification", "order.created", "order.new")
        or "cart" in payload
        or "eater" in payload
    ):
        try:
            result = channel_service.process_webhook_order(
                session, ORGANIZATION_ID, "UBER_EATS", payload
            )
            return {"status": "ok", "result": result}
        except Exception as e:
            logger.exception("Error procesando orden de Uber Eats")
            channel_service.log_webhook(
                session,
                ORGANIZATION_ID,
                "UBER_EATS",
                event_type,
                event_id,
                signature,
                payload,
                "error",
                str(e),
            )
            # Return 200 to acknowledge webhook receipt even on domain processing issues
            return {"status": "error_logged", "detail": str(e)}

    return {"status": "acknowledged", "event_type": event_type}


@router.get("/integrations/uber-eats/config")
def get_uber_eats_config(
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")
    org_id = _actor_org_from_request(session, actor_id)
    config = channel_service.get_config(session, org_id, "UBER_EATS")
    return config or {
        "is_enabled": False,
        "environment": "sandbox",
        "client_id": "",
        "client_secret": "",
        "webhook_secret": "",
        "auto_accept": True,
        "default_prep_time_minutes": 20,
    }


@router.put("/integrations/uber-eats/config")
def put_uber_eats_config(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")
    org_id = _actor_org_from_request(session, actor_id)
    return channel_service.save_config(session, org_id, "UBER_EATS", payload)


@router.get("/integrations/uber-eats/stores")
def get_uber_eats_store_mappings(
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")
    org_id = _actor_org_from_request(session, actor_id)
    return channel_service.list_store_mappings(session, org_id, "UBER_EATS")


@router.post("/integrations/uber-eats/stores")
def post_uber_eats_store_mapping(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")
    branch_id = str(payload.get("branch_id", "")).strip()
    external_store_id = str(payload.get("external_store_id", "")).strip()
    is_active = bool(payload.get("is_active", True))
    if not branch_id or not external_store_id:
        raise HTTPException(
            status_code=400, detail="branch_id y external_store_id son obligatorios."
        )
    org_id = _actor_org_from_request(session, actor_id)
    return channel_service.save_store_mapping(
        session, org_id, "UBER_EATS", branch_id, external_store_id, is_active
    )


@router.delete("/integrations/uber-eats/stores/{mapping_id}")
def delete_uber_eats_store_mapping(
    mapping_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")
    org_id = _actor_org_from_request(session, actor_id)
    channel_service.delete_store_mapping(session, org_id, mapping_id)
    return {"deleted": True, "mapping_id": mapping_id}


@router.get("/integrations/uber-eats/logs")
def get_uber_eats_webhook_logs(
    session: SessionDep,
    limit: int = 50,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")
    org_id = _actor_org_from_request(session, actor_id)
    return channel_service.list_webhook_logs(session, org_id, "UBER_EATS", limit)


@router.post("/integrations/uber-eats/test-order")
def post_uber_eats_test_order(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")

    customer_name = payload.get("customer_name") or "Carlos M. (Prueba)"
    items_count = int(payload.get("items_count") or 1)
    store_id = payload.get("store_id") or "d0e94168-bf1b-49cb-a49b-02df1ff9b68e"

    simulated_order = {
        "id": f"uber-test-{uuid.uuid4().hex[:8]}",
        "display_id": f"U{uuid.uuid4().hex[:4].upper()}",
        "event_type": "orders.notification",
        "store": {"id": store_id, "name": "Restaurante Demo"},
        "eater": {"first_name": customer_name, "last_name": "", "phone": "+526671234567"},
        "delivery": {"notes": "Timbre no funciona, llamar al llegar."},
        "cart": {
            "items": [
                {
                    "id": f"item-{i}",
                    "title": f"Hamburguesa Especial #{i + 1}",
                    "quantity": 1,
                    "unit_price_cents": 12000,
                    "special_instructions": "Sin cebolla, extra aderezo" if i == 0 else "",
                }
                for i in range(items_count)
            ]
        },
        "payment": {"charges": {"total": {"amount": 12000 * items_count, "currency_code": "MXN"}}},
        "currency": "MXN",
    }

    result = channel_service.process_webhook_order(
        session, ORGANIZATION_ID, "UBER_EATS", simulated_order
    )

    channel_service.log_webhook(
        session,
        ORGANIZATION_ID,
        "UBER_EATS",
        "orders.notification",
        simulated_order["id"],
        "simulated-hmac-sha256",
        simulated_order,
        "processed",
    )

    return {"simulated_order": simulated_order, "result": result}


# ---------------------------------------------------------------------------
# Integrations Hub: DiDi Food Marketplace & Channels
# ---------------------------------------------------------------------------


@router.post("/integrations/didi-food/webhook")
@router.post("/v1/integrations/didi-food/webhook")
async def post_didi_food_webhook(
    request: Request,
    session: SessionDep,
) -> dict[str, Any]:
    body_bytes = await request.body()
    signature = (
        request.headers.get("x-didi-signature")
        or request.headers.get("X-DiDi-Signature")
        or request.headers.get("sign")
        or request.headers.get("Sign")
    )

    config = channel_service.get_config(session, ORGANIZATION_ID, "DIDI_FOOD")
    webhook_secret = config.get("webhook_secret") if config else None

    # Validate HMAC signature if secret is configured
    if webhook_secret:
        is_valid = channel_service.didi_adapter.verify_webhook_signature(
            body_bytes, signature, webhook_secret
        )
        if not is_valid:
            channel_service.log_webhook(
                session,
                ORGANIZATION_ID,
                "DIDI_FOOD",
                "unauthorized_webhook",
                None,
                signature,
                {"error": "Firma HMAC inválida", "headers": dict(request.headers)},
                "rejected",
                "Firma HMAC inválida o ausente.",
            )
            raise HTTPException(status_code=401, detail="Firma de webhook inválida.")

    try:
        payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
    except Exception:
        raise HTTPException(status_code=400, detail="Cuerpo JSON inválido.") from None

    event_type, event_id = channel_service.didi_adapter.parse_webhook_event(payload)

    # Log webhook
    channel_service.log_webhook(
        session,
        ORGANIZATION_ID,
        "DIDI_FOOD",
        event_type,
        event_id,
        signature,
        payload,
        "received",
    )

    # Process order if it is an order event or full order payload
    if (
        event_type in ("orders.notification", "order.created", "order.new", "order.create")
        or "items" in payload
        or "cart" in payload
        or "shop_id" in payload
    ):
        try:
            result = channel_service.process_webhook_order(
                session, ORGANIZATION_ID, "DIDI_FOOD", payload
            )
            return {"status": "ok", "result": result}
        except Exception as e:
            logger.exception("Error procesando orden de DiDi Food")
            channel_service.log_webhook(
                session,
                ORGANIZATION_ID,
                "DIDI_FOOD",
                event_type,
                event_id,
                signature,
                payload,
                "error",
                str(e),
            )
            return {"status": "error_logged", "detail": str(e)}

    return {"status": "acknowledged", "event_type": event_type}


@router.get("/integrations/didi-food/config")
def get_didi_food_config(
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")
    org_id = _actor_org_from_request(session, actor_id)
    config = channel_service.get_config(session, org_id, "DIDI_FOOD")
    return config or {
        "is_enabled": False,
        "environment": "sandbox",
        "client_id": "",
        "client_secret": "",
        "webhook_secret": "",
        "auto_accept": True,
        "default_prep_time_minutes": 20,
    }


@router.put("/integrations/didi-food/config")
def put_didi_food_config(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")
    org_id = _actor_org_from_request(session, actor_id)
    return channel_service.save_config(session, org_id, "DIDI_FOOD", payload)


@router.get("/integrations/didi-food/stores")
def get_didi_food_store_mappings(
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")
    org_id = _actor_org_from_request(session, actor_id)
    return channel_service.list_store_mappings(session, org_id, "DIDI_FOOD")


@router.post("/integrations/didi-food/stores")
def post_didi_food_store_mapping(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")
    branch_id = str(payload.get("branch_id", "")).strip()
    external_store_id = str(payload.get("external_store_id", "")).strip()
    is_active = bool(payload.get("is_active", True))
    if not branch_id or not external_store_id:
        raise HTTPException(
            status_code=400, detail="branch_id y external_store_id son obligatorios."
        )
    org_id = _actor_org_from_request(session, actor_id)
    return channel_service.save_store_mapping(
        session, org_id, "DIDI_FOOD", branch_id, external_store_id, is_active
    )


@router.delete("/integrations/didi-food/stores/{mapping_id}")
def delete_didi_food_store_mapping(
    mapping_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")
    org_id = _actor_org_from_request(session, actor_id)
    channel_service.delete_store_mapping(session, org_id, mapping_id)
    return {"deleted": True, "mapping_id": mapping_id}


@router.get("/integrations/didi-food/logs")
def get_didi_food_webhook_logs(
    session: SessionDep,
    limit: int = 50,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")
    org_id = _actor_org_from_request(session, actor_id)
    return channel_service.list_webhook_logs(session, org_id, "DIDI_FOOD", limit)


@router.post("/integrations/didi-food/simulate")
@router.post("/integrations/didi-food/test-order")
def post_didi_food_test_order(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")

    customer_name = payload.get("customer_name") or "Carlos D. (Prueba)"
    customer_phone = payload.get("customer_phone") or "+526671234567"
    store_id = (
        payload.get("store_id")
        or payload.get("shop_id")
        or payload.get("external_store_id")
        or "didi_shop_guadalajara_01"
    )
    branch_id = payload.get("branch_id")
    raw_items = payload.get("items") or []

    if branch_id and not payload.get("shop_id"):
        mappings = channel_service.list_store_mappings(session, ORGANIZATION_ID, "DIDI_FOOD")
        matched = next(
            (m for m in mappings if m["branch_id"] == branch_id and m.get("is_active")), None
        )
        if matched:
            store_id = matched["external_store_id"]
        else:
            store_id = f"didi_shop_{branch_id[:8]}"
            channel_service.save_store_mapping(
                session, ORGANIZATION_ID, "DIDI_FOOD", branch_id, store_id, True
            )

    sim_id = f"didi-test-{uuid.uuid4().hex[:8]}"
    display_id = f"D{uuid.uuid4().hex[:4].upper()}"

    if raw_items:
        items_payload = []
        total_cents = 0
        for i, itm in enumerate(raw_items):
            qty = int(itm.get("quantity") or 1)
            price_val = itm.get("unit_price") or itm.get("price") or 120.0
            price_cents = (
                int(round(price_val * 100))
                if isinstance(price_val, float)
                else int(itm.get("unit_price_cents") or 12000)
            )
            items_payload.append(
                {
                    "item_id": itm.get("item_id") or f"item-{i}",
                    "name": itm.get("name") or itm.get("title") or f"Producto DiDi #{i + 1}",
                    "quantity": qty,
                    "unit_price_cents": price_cents,
                    "special_instructions": itm.get("special_instructions") or "",
                }
            )
            total_cents += price_cents * qty
        if payload.get("total"):
            total_cents = int(round(payload["total"] * 100))
    else:
        items_count = int(payload.get("items_count") or 1)
        items_payload = [
            {
                "item_id": f"item-{i}",
                "name": f"Hamburguesa DiDi #{i + 1}",
                "quantity": 1,
                "unit_price_cents": 12000,
                "special_instructions": "Sin cebolla" if i == 0 else "",
            }
            for i in range(items_count)
        ]
        total_cents = 12000 * items_count

    simulated_order = {
        "order_id": sim_id,
        "display_id": display_id,
        "event_type": "order.created",
        "shop_id": store_id,
        "customer": {"name": customer_name, "phone": customer_phone},
        "delivery_notes": payload.get("delivery_notes") or "Pedido de prueba DiDi Food Sandbox.",
        "items": items_payload,
        "total_cents": total_cents,
        "currency": "MXN",
    }

    result = channel_service.process_webhook_order(
        session, ORGANIZATION_ID, "DIDI_FOOD", simulated_order
    )

    channel_service.log_webhook(
        session,
        ORGANIZATION_ID,
        "DIDI_FOOD",
        "order.created",
        sim_id,
        "simulated-didi-signature",
        simulated_order,
        "processed",
    )

    return {
        "status": "ok",
        "simulated_order": simulated_order,
        "result": {
            "order_id": result.get("order_id"),
            "external_order_id": sim_id,
            "folio": f"DIDI-{display_id}",
            "status": result.get("status", "created"),
        },
    }


# ---------------------------------------------------------------------------
# Channel Integrations: Rappi Restaurante
# ---------------------------------------------------------------------------


@router.post("/integrations/rappi/webhook")
@router.post("/v1/integrations/rappi/webhook")
async def post_rappi_webhook(
    request: Request,
    session: SessionDep,
) -> dict[str, Any]:
    body_bytes = await request.body()
    signature = (
        request.headers.get("rappi-signature")
        or request.headers.get("Rappi-Signature")
        or request.headers.get("x-rappi-signature")
        or request.headers.get("X-Rappi-Signature")
        or request.headers.get("sign")
        or request.headers.get("Sign")
    )

    config = channel_service.get_config(session, ORGANIZATION_ID, "RAPPI")
    webhook_secret = config.get("webhook_secret") if config else None

    # Validate HMAC signature if secret is configured
    if webhook_secret:
        is_valid = channel_service.rappi_adapter.verify_webhook_signature(
            body_bytes, signature, webhook_secret
        )
        if not is_valid:
            channel_service.log_webhook(
                session,
                ORGANIZATION_ID,
                "RAPPI",
                "unauthorized_webhook",
                None,
                signature,
                {"error": "Firma HMAC inválida", "headers": dict(request.headers)},
                "rejected",
                "Firma HMAC inválida o ausente.",
            )
            raise HTTPException(status_code=401, detail="Firma de webhook inválida.")

    try:
        payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
    except Exception:
        raise HTTPException(status_code=400, detail="Cuerpo JSON inválido.") from None

    event_type, event_id = channel_service.rappi_adapter.parse_webhook_event(payload)

    # Log webhook
    channel_service.log_webhook(
        session,
        ORGANIZATION_ID,
        "RAPPI",
        event_type,
        event_id,
        signature,
        payload,
        "received",
    )

    # Process order if it is an order event or full order payload
    if (
        event_type
        in ("NEW_ORDER", "order.created", "order.new", "order.create", "orders.notification")
        or "items" in payload
        or "products" in payload
        or "cart" in payload
        or "order" in payload
        or "store_id" in payload
    ):
        try:
            result = channel_service.process_webhook_order(
                session, ORGANIZATION_ID, "RAPPI", payload
            )
            return {"status": "ok", "result": result}
        except Exception as e:
            logger.exception("Error procesando orden de Rappi")
            channel_service.log_webhook(
                session,
                ORGANIZATION_ID,
                "RAPPI",
                event_type,
                event_id,
                signature,
                payload,
                "error",
                str(e),
            )
            return {"status": "error_logged", "detail": str(e)}

    return {"status": "acknowledged", "event_type": event_type}


@router.get("/integrations/rappi/config")
def get_rappi_config(
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")
    org_id = _actor_org_from_request(session, actor_id)
    config = channel_service.get_config(session, org_id, "RAPPI")
    return config or {
        "is_enabled": False,
        "environment": "sandbox",
        "client_id": "",
        "client_secret": "",
        "webhook_secret": "",
        "auto_accept": True,
        "default_prep_time_minutes": 20,
    }


@router.put("/integrations/rappi/config")
def put_rappi_config(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")
    org_id = _actor_org_from_request(session, actor_id)
    return channel_service.save_config(session, org_id, "RAPPI", payload)


@router.get("/integrations/rappi/stores")
def get_rappi_store_mappings(
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")
    org_id = _actor_org_from_request(session, actor_id)
    return channel_service.list_store_mappings(session, org_id, "RAPPI")


@router.post("/integrations/rappi/stores")
def post_rappi_store_mapping(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")
    branch_id = str(payload.get("branch_id", "")).strip()
    external_store_id = str(payload.get("external_store_id", "")).strip()
    is_active = bool(payload.get("is_active", True))
    if not branch_id or not external_store_id:
        raise HTTPException(
            status_code=400, detail="branch_id y external_store_id son obligatorios."
        )
    org_id = _actor_org_from_request(session, actor_id)
    return channel_service.save_store_mapping(
        session, org_id, "RAPPI", branch_id, external_store_id, is_active
    )


@router.delete("/integrations/rappi/stores/{mapping_id}")
def delete_rappi_store_mapping(
    mapping_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")
    org_id = _actor_org_from_request(session, actor_id)
    channel_service.delete_store_mapping(session, org_id, mapping_id)
    return {"deleted": True, "mapping_id": mapping_id}


@router.get("/integrations/rappi/logs")
def get_rappi_webhook_logs(
    session: SessionDep,
    limit: int = 50,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")
    org_id = _actor_org_from_request(session, actor_id)
    return channel_service.list_webhook_logs(session, org_id, "RAPPI", limit)


@router.post("/integrations/rappi/simulate")
@router.post("/integrations/rappi/test-order")
def post_rappi_test_order(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")

    customer_name = payload.get("customer_name") or "Sofia R. (Prueba Rappi)"
    customer_phone = payload.get("customer_phone") or "+525598765432"
    store_id = (
        payload.get("store_id")
        or payload.get("shop_id")
        or payload.get("external_store_id")
        or "rappi_store_guadalajara_01"
    )
    branch_id = payload.get("branch_id")
    raw_items = payload.get("items") or []

    if branch_id and not payload.get("store_id"):
        mappings = channel_service.list_store_mappings(session, ORGANIZATION_ID, "RAPPI")
        matched = next(
            (m for m in mappings if m["branch_id"] == branch_id and m.get("is_active")), None
        )
        if matched:
            store_id = matched["external_store_id"]
        else:
            store_id = f"rappi_store_{branch_id[:8]}"
            channel_service.save_store_mapping(
                session, ORGANIZATION_ID, "RAPPI", branch_id, store_id, True
            )

    sim_id = f"rappi-test-{uuid.uuid4().hex[:8]}"
    display_id = f"R{uuid.uuid4().hex[:4].upper()}"

    if raw_items:
        items_payload = []
        total_cents = 0
        for i, itm in enumerate(raw_items):
            qty = int(itm.get("quantity") or 1)
            price_val = itm.get("unit_price") or itm.get("price") or 135.0
            price_cents = (
                int(round(price_val * 100))
                if isinstance(price_val, float)
                else int(itm.get("unit_price_cents") or 13500)
            )
            items_payload.append(
                {
                    "item_id": itm.get("item_id") or f"item-{i}",
                    "name": itm.get("name") or itm.get("title") or f"Producto Rappi #{i + 1}",
                    "quantity": qty,
                    "unit_price_cents": price_cents,
                    "special_instructions": itm.get("special_instructions") or "",
                }
            )
            total_cents += price_cents * qty
        if payload.get("total"):
            total_cents = int(round(payload["total"] * 100))
    else:
        items_count = int(payload.get("items_count") or 1)
        items_payload = [
            {
                "item_id": f"item-{i}",
                "name": f"Combo Hamburguesa Rappi #{i + 1}",
                "quantity": 1,
                "unit_price_cents": 13500,
                "special_instructions": "Papas extra crujientes" if i == 0 else "",
            }
            for i in range(items_count)
        ]
        total_cents = 13500 * items_count

    simulated_order = {
        "order_id": sim_id,
        "display_id": display_id,
        "event_type": "NEW_ORDER",
        "store_id": store_id,
        "customer": {"name": customer_name, "phone": customer_phone},
        "delivery_notes": payload.get("delivery_notes")
        or "Pedido de prueba Rappi Restaurante Sandbox.",
        "items": items_payload,
        "total_cents": total_cents,
        "currency": "MXN",
    }

    result = channel_service.process_webhook_order(
        session, ORGANIZATION_ID, "RAPPI", simulated_order
    )

    channel_service.log_webhook(
        session,
        ORGANIZATION_ID,
        "RAPPI",
        "NEW_ORDER",
        sim_id,
        "simulated-rappi-signature",
        simulated_order,
        "processed",
    )

    return {
        "status": "ok",
        "simulated_order": simulated_order,
        "result": {
            "order_id": result.get("order_id"),
            "external_order_id": sim_id,
            "folio": f"RAPPI-{display_id}",
            "status": result.get("status", "created"),
        },
    }


# ---------------------------------------------------------------------------
# POS Endpoints: Uber Eats / DiDi Food / Rappi Orders Monitor
# ---------------------------------------------------------------------------


@router.get("/pos/uber-eats/orders")
def get_pos_uber_eats_orders(
    branch_id: str,
    session: SessionDep,
    status: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    authorize_branch_scope(session, actor_id, "orders.read", branch_id)
    return channel_service.list_pos_orders(session, branch_id, "UBER_EATS", status)


@router.post("/pos/uber-eats/orders/{order_id}/status")
def post_pos_uber_eats_order_status(
    order_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    new_status = str(payload.get("status", "")).strip().upper()
    if not new_status:
        raise HTTPException(status_code=400, detail="status es requerido.")
    return channel_service.update_order_status(session, order_id, new_status, actor_id)


@router.get("/pos/didi-food/orders")
def get_pos_didi_food_orders(
    branch_id: str,
    session: SessionDep,
    status: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    authorize_branch_scope(session, actor_id, "orders.read", branch_id)
    return channel_service.list_pos_orders(session, branch_id, "DIDI_FOOD", status)


@router.post("/pos/didi-food/orders/{order_id}/status")
def post_pos_didi_food_order_status(
    order_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    new_status = str(payload.get("status", "")).strip().upper()
    if not new_status:
        raise HTTPException(status_code=400, detail="status es requerido.")
    return channel_service.update_order_status(session, order_id, new_status, actor_id)


@router.get("/pos/rappi/orders")
def get_pos_rappi_orders(
    branch_id: str,
    session: SessionDep,
    status: str | None = None,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    authorize_branch_scope(session, actor_id, "orders.read", branch_id)
    return channel_service.list_pos_orders(session, branch_id, "RAPPI", status)


@router.post("/pos/rappi/orders/{order_id}/status")
def post_pos_rappi_order_status(
    order_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    new_status = str(payload.get("status", "")).strip().upper()
    if not new_status:
        raise HTTPException(status_code=400, detail="status es requerido.")
    return channel_service.update_order_status(session, order_id, new_status, actor_id)


# ---------------------------------------------------------------------------
# Invoicing Endpoints: Facturapi & CFDI 4.0
# ---------------------------------------------------------------------------


from restaurant_os.invoicing.self_invoicing import (
    emit_self_invoice,
    lookup_ticket_for_self_invoicing,
)


@router.get("/self-invoice/lookup")
@router.get("/v1/self-invoice/lookup")
def get_self_invoice_lookup(
    folio: str,
    session: SessionDep,
) -> dict[str, Any]:
    return lookup_ticket_for_self_invoicing(session, folio)


@router.post("/self-invoice/emit")
@router.post("/v1/self-invoice/emit")
def post_self_invoice_emit(
    payload: dict[str, Any],
    session: SessionDep,
) -> dict[str, Any]:
    return emit_self_invoice(session, payload)


@router.get("/integrations/facturapi/config")
def get_facturapi_config(
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")
    actor = session.execute(sa.select(models.users).where(models.users.c.id == actor_id)).mappings().first()
    org_id = str(actor["organization_id"]) if actor and actor.get("organization_id") else ORGANIZATION_ID
    cfg = invoicing_service.get_config(session, org_id)
    return cfg or {
        "is_enabled": False,
        "environment": "sandbox",
        "organization_rfc": "",
        "organization_legal_name": "",
        "organization_tax_system": "601",
        "organization_zip": "",
        "default_product_sat_key": "90101501",
        "default_unit_sat_key": "E48",
        "series": "F",
        "enable_self_invoicing": True,
        "self_invoicing_domain": "demo",
        "self_invoicing_days_valid": 30,
        "print_qr_on_ticket": True,
    }


@router.post("/integrations/facturapi/config")
def save_facturapi_config(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")
    actor = session.execute(sa.select(models.users).where(models.users.c.id == actor_id)).mappings().first()
    org_id = str(actor["organization_id"]) if actor and actor.get("organization_id") else ORGANIZATION_ID
    return invoicing_service.save_config(session, org_id, payload)


@router.post("/integrations/facturapi/test-connection")
def test_facturapi_connection(
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")
    actor = session.execute(sa.select(models.users).where(models.users.c.id == actor_id)).mappings().first()
    org_id = str(actor["organization_id"]) if actor and actor.get("organization_id") else ORGANIZATION_ID
    return invoicing_service.test_connection(session, org_id)


@router.get("/invoicing/invoices")
def list_cfdi_invoices(
    session: SessionDep,
    branch_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> list[dict[str, Any]]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "orders.read")
    return invoicing_service.list_invoices(
        session, ORGANIZATION_ID, branch_id, status, limit, offset
    )


@router.get("/invoicing/invoices/{invoice_id}")
def get_cfdi_invoice_detail(
    invoice_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "orders.read")
    inv = invoicing_service.get_invoice_detail(session, ORGANIZATION_ID, invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Factura no encontrada.")
    return inv


@router.post("/invoicing/invoices/issue")
def issue_cfdi_invoice(
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "orders.read")

    order_ids = payload.get("order_ids") or []
    if isinstance(order_ids, str):
        order_ids = [order_ids]
    if not order_ids:
        raise HTTPException(
            status_code=400, detail="Debe seleccionar al menos un pedido para facturar."
        )

    branch_id = payload.get("branch_id")
    if not branch_id:
        # Resolve branch from first order
        first_order = session.execute(
            sa.select(models.orders.c.branch_id).where(models.orders.c.id == order_ids[0])
        ).scalar_one_or_none()
        branch_id = str(first_order) if first_order else "00000000-0000-0000-0000-000000000002"

    receptor = payload.get("receptor") or {}
    try:
        return invoicing_service.issue_invoice(
            session, ORGANIZATION_ID, branch_id, order_ids, receptor
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/invoicing/invoices/{invoice_id}/cancel")
def cancel_cfdi_invoice(
    invoice_id: str,
    payload: dict[str, Any],
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    actor_id = _required_actor_from_request(actor_user_id, authorization)
    require_permission(session, actor_id, "admin.manage")
    motive = str(payload.get("motive") or "02")
    substitution_uuid = payload.get("substitution_uuid")
    try:
        return invoicing_service.cancel_invoice(
            session, ORGANIZATION_ID, invoice_id, motive, substitution_uuid
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/invoicing/orders/{order_id}/receipt")
def generate_order_receipt(
    order_id: str,
    session: SessionDep,
    actor_user_id: ActorUserDep = None,
    authorization: AuthorizationDep = None,
) -> dict[str, Any]:
    _required_actor_from_request(actor_user_id, authorization)
    first_order = session.execute(
        sa.select(models.orders.c.branch_id).where(models.orders.c.id == order_id)
    ).scalar_one_or_none()
    if not first_order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado.")
    branch_id = str(first_order)

    try:
        return invoicing_service.create_receipt_for_order(
            session, ORGANIZATION_ID, branch_id, order_id
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
