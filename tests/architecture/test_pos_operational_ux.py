"""Architecture checks for POS-UX-001 operational checkout and inventory."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POS = ROOT / "apps" / "pos-web" / "src"
DOCS = ROOT / "docs"


def _pos_source(relative_path: str) -> str:
    return (POS / relative_path).read_text(encoding="utf-8")


def test_checkout_uses_only_canonical_branch_context() -> None:
    source = _pos_source("features/pos/PointOfSale.tsx")
    assert "session?.active_branch?.id || ''" in source
    assert "resolvePosBranchId" not in source
    assert "branch_id: branchId" in source


def test_customer_search_is_remote_debounced_and_cancelable() -> None:
    source = _pos_source("features/pos/PointOfSale.tsx")
    assert "phone," in source
    assert "validMexicanPhone(customerPhone)" in source
    assert "q: query" not in source
    assert "limit: '20'" in source
    assert "window.setTimeout" in source and ", 300)" in source
    assert "AbortController" in source
    assert "controller.abort()" in source


def test_customer_selection_is_independent_from_search_results() -> None:
    source = _pos_source("features/pos/PointOfSale.tsx")
    assert "const [selectedCustomer, setSelectedCustomer]" in source
    select_body = source.split("const selectCustomer", 1)[1].split(
        "const clearCustomer", 1
    )[0]
    assert "setSelectedCustomer(customer)" in select_body
    assert "setSearchResults([])" in select_body
    assert "setSelectedAddressId" in select_body


def test_checkout_address_form_is_complete_and_branch_scoped() -> None:
    source = _pos_source("features/pos/PointOfSale.tsx")
    for field in (
        "alias",
        "street",
        "exterior_number",
        "interior_number",
        "neighborhood",
        "postal_code",
        "city",
        "municipality",
        "state",
        "cross_streets",
        "references",
        "delivery_instructions",
        "is_default",
    ):
        assert field in source
    assert "JSON.stringify({ ...form, branch_id: branchId })" in source
    assert "setSelectedAddressId(addr.id)" in source


def test_legacy_address_is_reference_only_and_copy_is_explicit() -> None:
    source = _pos_source("features/pos/PointOfSale.tsx")
    assert "Domicilio heredado por confirmar" in source
    assert "Copiar domicilio heredado a Referencias" in source
    assert "set('references', legacyAddressReference)" in source
    initial_form = source.split("const [form, setForm]", 1)[1].split(");", 1)[0]
    assert "references: ''" in initial_form


def test_delivery_requires_customer_and_active_address() -> None:
    source = _pos_source("features/pos/PointOfSale.tsx")
    assert "a.status === 'active'" in source
    assert "orderType !== 'delivery'" in source
    assert "(selectedCustomer && selectedAddressId)" in source
    assert (
        "disabled={checkoutState === 'submitting' || !canCheckout || quoteState !== 'ready' || "
        "(!paymentMethod && !editingOrder)}"
    ) in source
    assert "Falta seleccionar domicilio de entrega" in source


def test_pos_keeps_horizontal_catalog_hierarchy_and_right_cart() -> None:
    source = _pos_source("features/pos/PointOfSale.tsx")
    styles = _pos_source("App.css")
    for class_name in (
        "pos-sale-menu",
        "pos-sale-products",
        "pos-sale-complements",
        "pos-sale-cart",
    ):
        assert f'className="{class_name}"' in source or class_name in source
        assert f".{class_name}" in styles
    assert source.index('className="pos-sale-menu"') < source.index(
        'className="pos-sale-products"'
    )
    assert source.index('className="pos-sale-products"') < source.index(
        "pos-sale-complements"
    )


def test_pos_requires_and_sends_explicit_payment_method() -> None:
    source = _pos_source("features/pos/PointOfSale.tsx")
    for method in ("cash", "debit_card", "credit_card", "transfer"):
        assert method in source
    assert "method: paymentMethod" in source
    assert (
        "disabled={checkoutState === 'submitting' || !canCheckout || quoteState !== 'ready' || "
        "(!paymentMethod && !editingOrder)}"
    ) in source
    assert "setPaymentMethod(null)" in source


def test_pos_navigation_excludes_dashboard_and_inventory_shortcuts() -> None:
    layout = _pos_source("components/PosLayout.tsx")
    app = _pos_source("App.tsx")
    admin_hub = _pos_source("features/admin/AdminHub.tsx")
    nav_section = layout.split("const navItems = [", 1)[1].split("];", 1)[0]

    assert "Panel Principal" not in nav_section
    assert "Inventario" not in nav_section
    for label in ("Punto de Venta", "Clientes", "Pedidos", "Administración"):
        assert label in nav_section
    assert '<Navigate to="/pos" replace />' in app
    assert '<Navigate to="/administration/inventory" replace />' in app
    assert 'path="administration/inventory"' in app
    assert "to: '/administration/inventory'" not in admin_hub
    assert "label: 'Inventario'" not in admin_hub


def test_category_menu_uses_five_groups_and_large_dynamic_category_cards() -> None:
    source = _pos_source("features/pos/PointOfSale.tsx")
    styles = _pos_source("App.css")

    assert "CATALOG_MENU_GROUPS.map" in source
    assert "categoriesForCatalogMenuGroup" in source
    assert "categoryChoices.map" in source
    assert "toggleFavoriteProduct" in source
    assert "pos_product_favorites_v1" in source
    assert "pos_category_favorites_v1" not in source
    assert "CATEGORY_PAGE_SIZE" not in source
    assert "categoryPage" not in source
    assert "pos-sale-menu-page-control" not in source
    menu_rules = re.search(r"\.pos-sale-menu\s*\{(?P<rules>[^}]*)\}", styles, re.S)
    assert menu_rules
    assert "display: grid" in menu_rules.group("rules")
    assert "grid-template-columns: repeat(5, minmax(92px, 1fr))" in menu_rules.group("rules")
    assert "width: 100%" in menu_rules.group("rules")
    category_card_rules = re.search(
        r"\.pos-sale-category-card\s*\{(?P<rules>[^}]*)\}", styles, re.S
    )
    assert category_card_rules
    assert "min-height: 158px" in category_card_rules.group("rules")
    assert ".pos-sale-menu-page-control" not in styles
    progressive_bdd = (DOCS / "03-BDD-pos-progressive-catalog.md").read_text(
        encoding="utf-8"
    )
    assert "FAVORITOS" in progressive_bdd


def test_checkout_has_no_dead_controls_or_raw_fetch() -> None:
    source = _pos_source("features/pos/PointOfSale.tsx")
    for forbidden in ("Tables", "Discount", "Save Bill", "Voucher", "Order Details"):
        assert forbidden not in source
    assert re.search(r"\bfetch\s*\(", source) is None
    assert "fetchApi" in source


def test_inventory_uses_only_the_branch_stock_contract() -> None:
    source = _pos_source("features/inventory/PosInventory.tsx")
    assert "session?.active_branch?.id || ''" in source
    assert "/inventory/stock?branch_id=${encodeURIComponent(branchId)}" in source
    assert source.count("/inventory/") == 1
    assert "resolvePosBranchId" not in source


def test_inventory_states_are_ledger_based_without_arbitrary_threshold() -> None:
    source = _pos_source("features/inventory/PosInventory.tsx")
    for label in (
        "Existencias teóricas derivadas de movimientos",
        "Con existencia",
        "Sin existencia",
        "Existencia negativa",
        "Último movimiento",
    ):
        assert label in source
    assert "qty > 0" in source
    assert "qty === 0" in source
    assert "qty < 0" in source
    assert "qty < 20" not in source


def test_pos_ux_specification_and_traceability_exist() -> None:
    bdd = (DOCS / "03-BDD-pos-operational-ux.md").read_text(encoding="utf-8")
    tdd = (DOCS / "04-TDD-pos-operational-ux.md").read_text(encoding="utf-8")
    matrix = (DOCS / "05-matriz-trazabilidad.md").read_text(encoding="utf-8")
    for scenario in (*range(156, 163), 231, 236, 237, 238):
        assert f"BDD-SC-{scenario}" in bdd
    for test_id in ("TDD-TS-055", "TDD-TC-048", "TDD-TC-064", "TDD-TS-070", "TDD-TC-066"):
        assert test_id in tdd
    assert "PRD-NFR-518" in matrix
    assert "TDD-TS-055" in matrix
    assert "PRD-FR-709" in matrix
