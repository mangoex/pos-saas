"""Integration test for POST /recipes/ai-parse endpoint."""

# ruff: noqa: E501

from pathlib import Path

import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.database import get_session
from restaurant_os.main import create_app
from sqlalchemy.orm import Session

EXCEL_DIR = str(Path(__file__).resolve().parents[3])


def test_post_recipe_ai_parse_endpoint(tmp_path: Path):
    if not all((Path(EXCEL_DIR) / name).is_file() for name in ("INSUMOS.XLS", "PRESENTACIONES.XLS", "PRODUCTOS.XLS")):
        import pytest
        pytest.skip("real catalog Excel fixtures are not present")
    from restaurant_os.real_catalog_loader import load_real_catalog_from_excels
    db_path = tmp_path / "test_api_ai.db"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    models.metadata.create_all(engine)

    org_id = "018f6f73-2d0a-74f0-8f1c-000000000001"
    branch_id = "018f6f73-2d0a-74f0-8f1c-000000000010"
    user_id = "018f6f73-2d0a-74f0-8f1c-000000000002"
    now = sa.func.now()

    with Session(engine) as session:
        # Organization and topology
        session.execute(models.organizations.insert().values(
            id=org_id, name="Kiwi Comida Natural", status="active", created_at=now, updated_at=now
        ))
        session.execute(models.legal_entities.insert().values(
            id="legal-kiwi", organization_id=org_id, name="Aurora Cristina Mejia Casas", tax_id="MECA9102201G4",
            status="active", created_at=now, updated_at=now
        ))
        session.execute(models.business_units.insert().values(
            id="unit-kiwi", organization_id=org_id, legal_entity_id="legal-kiwi", name="Kiwi Culiacán",
            code="KIWI-CUL", unit_type="restaurant", status="active", created_at=now, updated_at=now
        ))
        session.execute(models.branches.insert().values(
            id=branch_id, organization_id=org_id, legal_entity_id="legal-kiwi", business_unit_id="unit-kiwi",
            name="Sucursal Cinepolis", code="BR-CINEPOLIS", status="active", created_at=now, updated_at=now
        ))
        session.execute(models.warehouses.insert().values(
            id="wh-cinepolis", organization_id=org_id, branch_id=branch_id, name="Almacén Cinepolis",
            status="active", created_at=now, updated_at=now
        ))

        # Admin user and permissions
        session.execute(models.users.insert().values(
            id=user_id, organization_id=org_id, email="admin@kiwi.mx", display_name="Admin Kiwi",
            status="active", created_at=now, updated_at=now
        ))
        session.execute(models.roles.insert().values(
            id="role-admin", organization_id=org_id, name="admin", scope="organization", created_at=now
        ))
        session.execute(models.user_roles.insert().values(
            user_id=user_id, role_id="role-admin", branch_id=None
        ))
        session.execute(models.permissions.insert().values(
            id="perm-catalog", code="catalog.manage", description="Catalog Manage", created_at=now
        ))
        session.execute(models.role_permissions.insert().values(
            role_id="role-admin", permission_id="perm-catalog"
        ))
        session.commit()

        # Load real supplies from Excel
        load_real_catalog_from_excels(
            session=session,
            excel_dir=EXCEL_DIR,
            organization_id=org_id,
            branch_id=branch_id,
            import_customers=False,
        )

    app = create_app()

    def override_get_session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)

    recipe_text = """
    Prepara un delicioso baguette de pollo BBQ calentado con queso fundido y cebolla morada en pocos minutos.
    Ingredientes
    1 pan baguette fresco.
    250 g de pechuga de pollo (cocida y deshebrada o en tiras).
    1/4 de taza de salsa BBQ.
    1/2 taza de queso mozzarella o cheddar rallado.
    1/4 de cebolla morada en rodajas finas.
    Cilantro fresco picado al gusto.
    1 cucharada de aceite de oliva o mantequilla.
    Preparación
    Calienta el pollo en sartén.
    Hornea a 200 °C durante 5 a 8 minutos.
    """

    # Call AI Parse Endpoint
    response = client.post(
        "/api/v1/recipes/ai-parse",
        json={
            "raw_text": recipe_text,
            "sale_price": "130.00",
            "yield_portions": "1.0",
        },
        headers={
            "X-Actor-User-Id": user_id,
            "X-Branch-Id": branch_id,
        },
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "feature_out_of_saas_scope"

    app.dependency_overrides.clear()
