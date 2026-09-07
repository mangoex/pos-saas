from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_pco_002_specs_and_traceability_are_explicit() -> None:
    prd = (ROOT / "docs/01-PRD.md").read_text(encoding="utf-8")
    bdd = (ROOT / "docs/03-BDD-pos-cash-ops.md").read_text(encoding="utf-8")
    tdd = (ROOT / "docs/04-TDD-pos-cash-ops.md").read_text(encoding="utf-8")
    matrix = (ROOT / "docs/05-matriz-trazabilidad.md").read_text(encoding="utf-8")
    adr = (ROOT / "docs/08-adrs-propuestas.md").read_text(encoding="utf-8")

    assert "PRD-FR-716" in prd and "PRD-FR-716" in matrix
    assert "BDD-SC-301" in bdd and "cash_concept_code_immutable" in bdd
    assert "TDD-TC-084" in tdd
    assert "BDD-SC-301" in matrix and "TDD-TC-084" in matrix
    assert "SDD-ADR-024" in adr


def test_pco_002_catalog_is_preserved_with_additive_pco_003_ledger_routes() -> None:
    models = (ROOT / "apps/api/restaurant_os/models.py").read_text(encoding="utf-8")
    operations = (ROOT / "apps/api/restaurant_os/operations.py").read_text(encoding="utf-8")
    api = (ROOT / "apps/api/restaurant_os/api.py").read_text(encoding="utf-8")
    migration = (
        ROOT
        / "apps/api/alembic/versions/202608110100_0036_cash_concepts.py"
    ).read_text(encoding="utf-8")
    ledger_migration = (
        ROOT
        / "apps/api/alembic/versions/202608110200_0037_cash_movement_ledger.py"
    ).read_text(encoding="utf-8")

    for table in (
        "cash_movement_concepts",
        "cash_movement_concept_versions",
        "cash_concept_commands",
    ):
        assert table in models
        assert table in migration
    assert "def create_cash_concept(" in operations
    assert "def create_cash_concept_version(" in operations
    assert "def archive_cash_concept(" in operations
    assert "def list_effective_cash_concepts(" in operations
    assert '@router.post("/cash/concepts")' in api
    assert '@router.put("/cash/concepts/{concept_id}/versions")' in api
    assert '@router.post("/cash/concepts/{concept_id}/archive")' in api
    assert "0036_cash_concepts" in ledger_migration
    assert "cash_movement_commands" in models
    assert "cash_movement_commands" in ledger_migration
    assert "def create_cash_movement(" in operations
    assert "def compensate_cash_movement(" in operations
    assert '@router.post("/cash/movements")' in api
    assert '@router.post("/cash/movements/{movement_id}/compensations")' in api
    assert '@router.get("/cash/movements")' in api


def test_owner_admin_concepts_and_pos_ledger_are_additive() -> None:
    app = (ROOT / "apps/admin-web/src/App.tsx").read_text(encoding="utf-8")
    layout = (ROOT / "apps/admin-web/src/components/AdminLayout.tsx").read_text(encoding="utf-8")
    manager = (
        ROOT / "apps/admin-web/src/features/cash/CashConceptsManager.tsx"
    ).read_text(encoding="utf-8")
    state = (
        ROOT / "apps/admin-web/src/features/cash/cashConceptState.ts"
    ).read_text(encoding="utf-8")
    pos = (ROOT / "apps/pos-web/src/App.tsx").read_text(encoding="utf-8")
    pos_ledger = (
        ROOT / "apps/pos-web/src/features/cash/CashMovements.tsx"
    ).read_text(encoding="utf-8")

    subnav = (
        ROOT / "apps/admin-web/src/components/CategorySubNav.tsx"
    ).read_text(encoding="utf-8")

    assert 'path="cash-concepts"' in app
    assert "canManageCashConcepts" in app
    assert "cash.concept.manage" in state
    assert "Conceptos de Caja" in subnav or "Conceptos de caja" in layout
    assert "/cash/concepts" in manager
    assert "Idempotency-Key" in manager
    assert "CashMovements" in pos
    assert "/cash/concepts/effective" in pos_ledger
    assert "/cash/movements" in pos_ledger
    assert "cash.concept.manage" not in pos
    assert (ROOT / "tests/frontend/test_admin_cash_concepts.mjs").is_file()
