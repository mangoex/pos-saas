"""
TDD-TC-248: Public storefront and public catalog must accurately reflect
whether an active cash shift exists for a branch (has_active_shift).
"""

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import get_public_catalog
from restaurant_os.public_storefront import resolve_storefront
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def test_storefront_and_catalog_report_active_cash_shift_status():
    engine = sa.create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    models.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    org_id = "test-restaurant"
    branch_id = "branch-centro"
    public_key = "pk_test_centro"

    with Session(engine) as session:
        session.execute(
            models.organizations.insert().values(
                id=org_id,
                name="Tacos El Centro",
                slug=org_id,
                status="active",
                subscription_status="active",
                mobile_theme="light",
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            models.legal_entities.insert().values(
                id="legal-1",
                organization_id=org_id,
                name="Tacos SA",
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            models.business_units.insert().values(
                id="bu-1",
                organization_id=org_id,
                legal_entity_id="legal-1",
                name="Tacos Unit",
                code="TU",
                unit_type="restaurant",
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            models.branches.insert().values(
                id=branch_id,
                organization_id=org_id,
                legal_entity_id="legal-1",
                business_unit_id="bu-1",
                name="Sucursal Centro",
                code="CENTRO",
                status="active",
                timezone="UTC",
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            models.public_order_keys.insert().values(
                public_key=public_key,
                organization_id=org_id,
                branch_id=branch_id,
                status="active",
                created_at=now,
            )
        )
        # Create a product & category
        cat_id = str(uuid.uuid4())
        prod_id = str(uuid.uuid4())
        session.execute(
            models.product_categories.insert().values(
                id=cat_id,
                organization_id=org_id,
                name="Tacos",
                status="active",
                display_order=1,
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            models.products.insert().values(
                id=prod_id,
                organization_id=org_id,
                category_id=cat_id,
                name="Taco de Asada",
                sku="TACO-01",
                station="cocina",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            models.price_versions.insert().values(
                id=str(uuid.uuid4()),
                organization_id=org_id,
                product_id=prod_id,
                price_cents=4500,
                currency="MXN",
                valid_from=now,
                created_at=now,
            )
        )
        session.commit()

        # 1. Sin turnos de caja registrados -> has_active_shift debe ser False
        sf = resolve_storefront(session, org_id)
        assert len(sf["branches"]) == 1
        assert sf["branches"][0]["has_active_shift"] is False

        cat = get_public_catalog(session, branch_id)
        assert cat["has_active_shift"] is False

        # 2. Abrir turno de caja para la sucursal (OPEN)
        shift_id = str(uuid.uuid4())
        session.execute(
            models.cash_shifts.insert().values(
                id=shift_id,
                organization_id=org_id,
                branch_id=branch_id,
                register_code="CAJA-1",
                status="OPEN",
                opening_cash_cents=10000,
                cashier_user_id=None,
                opened_at=now,
                created_at=now,
            )
        )
        session.commit()

        # Con turno abierto -> has_active_shift debe ser True
        sf_open = resolve_storefront(session, org_id)
        assert sf_open["branches"][0]["has_active_shift"] is True

        cat_open = get_public_catalog(session, branch_id)
        assert cat_open["has_active_shift"] is True

        # 3. Cerrar el turno de caja (CLOSED)
        session.execute(
            models.cash_shifts.update()
            .where(models.cash_shifts.c.id == shift_id)
            .values(status="CLOSED", closed_at=now)
        )
        session.commit()

        # Turno cerrado -> has_active_shift debe volver a ser False
        sf_closed = resolve_storefront(session, org_id)
        assert sf_closed["branches"][0]["has_active_shift"] is False

        cat_closed = get_public_catalog(session, branch_id)
        assert cat_closed["has_active_shift"] is False
