"""Architecture contract for POS-CAT-004 category option selection."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_pos_category_option_specs_and_traceability_exist() -> None:
    prd = _read("docs/01-PRD.md")
    bdd = _read("docs/03-BDD-pos-category-option-first.md")
    tdd = _read("docs/04-TDD-pos-category-option-first.md")
    matrix = _read("docs/05-matriz-trazabilidad.md")
    assert "PRD-FR-713" in prd and "PRD-FR-713" in matrix
    assert "POS-CAT-004" in bdd
    assert "BDD-FEAT-074" in bdd
    for identifier in range(255, 264):
        assert f"BDD-SC-{identifier}" in bdd and f"BDD-SC-{identifier}" in matrix
    assert "TDD-TS-075" in tdd and "TDD-TC-071" in tdd


def test_percent_safe_alembic_adapter_maps_to_its_technical_bdd_scenario() -> None:
    bdd = _read("docs/03-BDD-pos-category-option-first.md")
    tdd = _read("docs/04-TDD-pos-category-option-first.md")
    matrix = _read("docs/05-matriz-trazabilidad.md")
    report = _read("docs/implementation-reports/POS-CAT-004.md")
    nfr_row = next(line for line in matrix.splitlines() if line.startswith("| PRD-NFR-517 |"))
    assert "BDD-SC-264" in bdd
    assert "URL percent-encoded se conserva a través de ConfigParser" in bdd
    assert "driver recupera exactamente el URL lógico original" in bdd
    assert "no se imprime la URL ni sus credenciales" in bdd
    assert "BDD-SC-264" in tdd
    assert "BDD-SC-264" in nfr_row
    assert "BDD-SC-261" not in nfr_row
    assert "BDD-SC-264" in report


def test_selection_schema_and_migration_are_linear() -> None:
    models = _read("apps/api/restaurant_os/models.py")
    migration = _read("apps/api/alembic/versions/202608090200_0034_category_option_selection.py")
    for table in (
        "category_option_groups",
        "category_option_values",
        "product_option_value_assignments",
    ):
        assert table in models and f'"{table}"' in migration
    assert 'down_revision: str | None = "0033_restore_superadmin_role"' in migration
    assert "uq_category_option_groups_organization_category" in migration
    assert "uq_category_option_groups_organization_code" not in migration
    assert "ck_category_option_groups_status" in migration
    assert "ck_category_option_values_status" in migration
    assert "uq_product_option_value_assignments_product_group" in migration


def test_backend_uses_one_fail_closed_projection_and_audited_corporate_routes() -> None:
    platform_data = _read("apps/api/restaurant_os/platform_data.py")
    operations = _read("apps/api/restaurant_os/operations.py")
    api = _read("apps/api/restaurant_os/api.py")
    assert "project_pos_catalog" in platform_data
    assert "selection_group" in platform_data and '"selection"' in platform_data
    assert "category_option_group_incomplete" in operations
    assert 'require_permission(session, actor_id, "catalog.manage")' in operations
    assert "category_option_projection_error" in platform_data
    assert '"category_option_group.created"' in operations
    assert '"category_option_group.updated"' in operations
    assert "/categories/{category_id}/selection-group" in api
    assert "/catalog/category-option-groups/{group_id}/coverage" in api


def test_pos_flow_is_pure_and_does_not_price_or_add_an_option() -> None:
    helper = _read("apps/pos-web/src/features/pos/categoryOptionFlow.ts")
    pos = _read("apps/pos-web/src/features/pos/PointOfSale.tsx")
    assert "resolveCategoryOptionState" in helper
    assert "filterProductsForCategoryOption" in helper
    assert "price_delta_cents" not in helper
    assert "Selecciona {activeSelectionGroup.name}" in pos
    assert "categoryOptionFlow" in pos
    assert "resetCatalogTransientState" in pos


def test_admin_exposes_corporate_option_configuration_not_branch_administration() -> None:
    app = _read("apps/admin-web/src/App.tsx")
    editor = _read("apps/admin-web/src/features/catalog/CategoryOptionManager.tsx")
    assert "CategoryOptionManager" in app
    assert 'path="category-options"' in app
    assert "CatalogManageRoute" in app
    assert "categoryOptionEditorHydrationKey" in editor
    css = _read("apps/pos-web/src/App.css")
    for label in ("Selector previo", "Cobertura", "Productos de la categoría", "Reintentar"):
        assert label in editor
    for text in (
        "Guardar opción",
        "Cancelar",
        "pos-sale-selection-control",
        "pos-sale-retry-control",
    ):
        assert text in editor or text in css
    assert ".pos-sale-selection-control" in css
    assert ".pos-sale-retry-control" in css
