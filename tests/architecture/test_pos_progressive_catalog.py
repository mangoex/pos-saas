"""Architecture contract for POS-UX-003 progressive catalog presentation."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_pos_progressive_catalog_specs_traceability_and_presentation_boundary_exist() -> None:
    prd = _read("docs/01-PRD.md")
    bdd = _read("docs/03-BDD-pos-progressive-catalog.md")
    tdd = _read("docs/04-TDD-pos-progressive-catalog.md")
    matrix = _read("docs/05-matriz-trazabilidad.md")
    pos = _read("apps/pos-web/src/features/pos/PointOfSale.tsx")
    helper = _read("apps/pos-web/src/features/pos/progressiveCatalogFlow.ts")

    assert "PRD-FR-729" in prd and "PRD-FR-729" in matrix
    assert "POS-UX-003" in bdd
    assert "BDD-FEAT-094" in bdd and "TDD-TS-098" in tdd and "TDD-TC-193" in tdd
    for identifier in range(425, 431):
        assert f"BDD-SC-{identifier}" in bdd and f"BDD-SC-{identifier}" in matrix
    assert "progressiveCatalogStage" in helper
    assert "modifierSelectionsMeetMinimums" in helper
    assert "price_delta_cents" not in helper
    assert "pos-sale-progressive-context" in pos
    assert "pos-sale-modifier-tabs" in pos
    assert "activeModifierGroup" in pos
    assert "startsAtProducts: activeMenuGroup === 'favorites'" in pos
    assert "Productos favoritos" in pos
    assert "activeMenuGroup === 'favorites' ? <span>Productos favoritos</span>" in pos
    assert "Cambiar categoría</button>" in pos


def test_progressive_catalog_ids_are_unique_and_category_stage_uses_the_central_body() -> None:
    bdd_sources = list((ROOT / "docs").glob("03-BDD*.md"))
    tdd_sources = list((ROOT / "docs").glob("04-TDD*.md"))
    bdd_text = "\n".join(path.read_text(encoding="utf-8") for path in bdd_sources)
    tdd_text = "\n".join(path.read_text(encoding="utf-8") for path in tdd_sources)
    css = _read("apps/pos-web/src/App.css")
    pos = _read("apps/pos-web/src/features/pos/PointOfSale.tsx")

    assert len(re.findall(r"\bBDD-FEAT-094\b", bdd_text)) == 1
    for identifier in range(425, 431):
        assert len(re.findall(rf"\bBDD-SC-{identifier}\b", bdd_text)) == 1
    assert len(re.findall(r"\bTDD-TC-193\b", tdd_text)) == 1

    category_panel = re.search(r"\.pos-sale-category-panel\s*\{(?P<rules>[^}]*)\}", css, re.S)
    category_grid = re.search(r"\.pos-sale-category-grid\s*\{(?P<rules>[^}]*)\}", css, re.S)
    category_card = re.search(r"\.pos-sale-category-card\s*\{(?P<rules>[^}]*)\}", css, re.S)
    assert category_panel and category_grid and category_card
    assert "flex: 1" in category_panel.group("rules")
    assert "min-height: 0" in category_panel.group("rules")
    assert "max-height" not in category_panel.group("rules")
    assert "minmax(150px, 1fr)" in category_grid.group("rules")
    assert "min-height: 158px" in category_card.group("rules")
    assert "getProductIcon(cat.name, 42)" in pos

    modifier_stage = re.search(r"\.pos-sale-complements\.is-open\s*\{(?P<rules>[^}]*)\}", css, re.S)
    modifier_content = re.search(r"\.pos-sale-complement-content\s*\{(?P<rules>[^}]*)\}", css, re.S)
    modifier_option = re.search(
        r"\.pos-sale-complement-option button\s*\{(?P<rules>[^}]*)\}", css, re.S
    )
    assert modifier_stage and modifier_content and modifier_option
    assert "flex: 1" in modifier_stage.group("rules")
    assert "min-height: 0" in modifier_stage.group("rules")
    assert "overflow-y: auto" in modifier_stage.group("rules")
    assert "grid-template-rows: auto auto minmax(0, 1fr) auto" in modifier_content.group("rules")
    assert "min-height: 48px" in modifier_option.group("rules")
    assert ".pos-sale-product-card-shell { padding: 0; }" in css
    assert ".pos-sale-product-card {" in css
    product_card = re.search(
        r"\.pos-sale-product-card\s*\{(?P<rules>[^}]*)\}", css, re.S
    )
    assert product_card
    assert "padding: 12px" in product_card.group("rules")
