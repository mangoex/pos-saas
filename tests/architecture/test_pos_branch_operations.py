"""Architecture contract for BA-003 POS branch operations."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POS_SRC = ROOT / "apps" / "pos-web" / "src"
DOCS = ROOT / "docs"


def _read(relative: str) -> str:
    return (POS_SRC / relative).read_text(encoding="utf-8")


def test_navigation_remains_permission_driven() -> None:
    layout = _read("components/PosLayout.tsx")
    assert "hasPermission('branch.admin.access')" in layout
    assert "Supervisor" not in layout
    assert not re.search(r"roles.*(?:includes|some|===)", layout)


def test_hub_has_local_operational_routes_including_variations() -> None:
    hub = _read("features/admin/AdminHub.tsx")
    assert re.findall(r"to: '(/[^']+)'", hub) == [
        "/administration/attendance",
        "/sales-monitor",
        "/administration/products",
        "/administration/suppliers",
        "/administration/purchases",
        "/administration/waste",
    ]
    assert "window.location" not in hub
    assert 'href="/admin' not in hub


def test_hub_excludes_corporate_catalogs() -> None:
    hub = _read("features/admin/AdminHub.tsx")
    for forbidden in (
        "Sucursales",
        "Sucursal activa",
        "Usuarios",
        "Roles",
        "Personal de sucursal",
    ):
        assert forbidden not in hub


def test_operational_routes_have_granular_guards() -> None:
    app = _read("App.tsx")
    expected = {
        "administration/variations": "catalog.branch.manage",
        "administration/suppliers": "purchases.read",
        "administration/purchases": "purchases.read",
        "administration/production": "production.manage",
        "administration/waste": "inventory.waste",
        "administration/transfers": "inventory.transfer.send",
        "administration/counts": "inventory.count",
    }
    for route, permission in expected.items():
        pattern = (
            rf'path="{re.escape(route)}".*?'
            rf'<PermissionRoute permission="{re.escape(permission)}">'
        )
        assert re.search(pattern, app, re.DOTALL), (
            f"{route} must require {permission}"
        )
    assert 'path="administration/staff"' not in app
    assert 'path="administration/branch"' not in app


def test_operations_use_canonical_active_branch() -> None:
    operations = _read("features/admin/BranchAdminOperations.tsx")
    assert "session?.active_branch?.id" in operations
    assert "branch_id=${encodeURIComponent(branchId)}" in operations
    assert "localStorage.getItem('pos_branch_id')" not in operations
    assert "admin_branch_id" not in operations


def test_operations_consume_existing_scoped_contracts() -> None:
    operations = _read("features/admin/BranchAdminOperations.tsx")
    for endpoint in (
        "/suppliers",
        "/purchase-presentations",
        "/purchases",
        "/production-batches",
        "/inventory/wastes",
        "/inventory/transfers",
        "/inventory/physical-counts",
    ):
        assert endpoint in operations


def test_supplier_surface_is_read_only() -> None:
    operations = _read("features/admin/BranchAdminOperations.tsx")
    supplier_section = operations.split(
        "export function BranchAdminSuppliers", 1
    )[1].split("interface Purchase", 1)[0]
    for forbidden in (
        "method: 'POST'",
        'method: "POST"',
        "method: 'PUT'",
        'method: "PUT"',
        "method: 'DELETE'",
        'method: "DELETE"',
    ):
        assert forbidden not in supplier_section
    assert "catálogo central permanece en Administración corporativa" in supplier_section


def test_common_page_preserves_pos_visual_context() -> None:
    page = _read("features/admin/BranchAdminPage.tsx")
    products = _read("features/admin/BranchAdminProducts.tsx")
    operations = _read("features/admin/BranchAdminOperations.tsx")
    assert 'to="/administration"' in page
    assert "usePosSession" in page
    assert "session?.active_branch" in page
    assert "padding: 32" in page
    assert "#10b981" in page
    assert "<BranchAdminPage" in products
    assert operations.count("<BranchAdminPage") == 6


def test_variations_use_canonical_branch_contract_and_touch_controls() -> None:
    variations = _read("features/admin/BranchAdminVariations.tsx")
    pos = _read("features/pos/PointOfSale.tsx")
    assert "/branch-administration/catalog/variation-notes" in variations
    assert "session?.active_branch?.name" in variations
    assert "localStorage.getItem('pos_branch_id')" not in variations
    assert "variation_kind === 'order_comment'" in pos
    assert "comment_preset_ids" in pos
    assert "aria-pressed" in pos
    assert "modifierLoadError" in pos


def test_hub_hides_variations_without_catalog_branch_manage() -> None:
    hub = _read("features/admin/AdminHub.tsx")
    assert "branchAdministrationCards" in hub
    assert "canManageVariations" in hub
    assert "hasPermission('catalog.branch.manage')" in hub


def test_bdd_tdd_and_traceability_cover_ba003() -> None:
    bdd = (DOCS / "03-BDD-pos-branch-operations.md").read_text(encoding="utf-8")
    tdd = (DOCS / "04-TDD-pos-branch-operations.md").read_text(encoding="utf-8")
    matrix = (DOCS / "05-matriz-trazabilidad.md").read_text(encoding="utf-8")
    for scenario in range(136, 144):
        token = f"BDD-SC-{scenario}"
        assert token in bdd
        assert token in matrix
    assert "TDD-TS-052" in tdd
    assert "TDD-TC-045" in tdd
    assert "TDD-TS-052" in matrix
    assert "TDD-TC-045" in matrix
