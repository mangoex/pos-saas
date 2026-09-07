"""Architecture contract for POS-VAR-001 preset variations."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_preset_variation_documents_and_traceability_are_complete() -> None:
    prd = _read("docs/01-PRD.md")
    bdd = _read("docs/03-BDD-pos-preset-variations.md")
    tdd = _read("docs/04-TDD-pos-preset-variations.md")
    matrix = _read("docs/05-matriz-trazabilidad.md")
    assert "PRD-FR-699" in prd and "PRD-FR-699" in matrix
    assert "BDD-FEAT-057" in bdd
    for scenario in range(168, 175):
        assert f"BDD-SC-{scenario}" in bdd and f"BDD-SC-{scenario}" in matrix
    assert "TDD-TS-057" in tdd and "TDD-TC-050" in tdd


def test_preset_variations_use_existing_modifier_motor_without_free_text_input() -> None:
    operations = _read("apps/api/restaurant_os/operations.py")
    pos = _read("apps/pos-web/src/features/pos/PointOfSale.tsx")
    assert "effect_type\": \"preset_instruction\"" in operations
    assert "price_delta_cents\": 0" in operations
    assert "variation_note.branch_configured" in operations
    assert "variation_kind === 'order_comment'" in pos
    assert "comment_preset_ids: item.commentPresets.map((comment) => comment.id)" in pos
    assert "aria-pressed" in pos
    assert "modifierLoadError" in pos and "Reintentar" in pos
    assert "shouldAddProductWithoutModifiers" in pos
    assert "resetModifierModal();\n        addToCart(product);" in pos


def test_administration_routes_keep_corporate_and_branch_permissions_separate() -> None:
    admin = _read("apps/admin-web/src/App.tsx")
    pos = _read("apps/pos-web/src/App.tsx")
    branch = _read("apps/pos-web/src/features/admin/BranchAdminVariations.tsx")
    assert 'path="variations"' in admin
    assert 'path="administration/variations"' in pos
    assert 'permission="catalog.branch.manage"' in pos
    assert "catalog.branch.manage" in branch
    assert "localStorage" not in branch


def test_audit_corrections_guard_group_retries_hub_and_corporate_feedback() -> None:
    operations = _read("apps/api/restaurant_os/operations.py")
    hub = _read("apps/pos-web/src/features/admin/AdminHub.tsx")
    admin = _read("apps/admin-web/src/features/catalog/VariationNotes.tsx")
    assert "variation_group_conflict" in operations
    assert "_is_safe_preset_variation_group" in operations
    assert "invalid_variation_display_order" in operations
    assert "branchAdministrationCards(hasPermission('catalog.branch.manage'))" in hub
    assert "products.isError" in admin and "notes.isError" in admin
    assert "title={statusActionLabel}" in admin
    assert "Archivar comentario" in admin and "Reactivar comentario" in admin
