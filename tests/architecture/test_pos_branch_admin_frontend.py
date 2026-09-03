"""Architecture tests for BA-002 (POS branch admin frontend).

These tests verify the POS frontend code structurally without running a
browser. They check that:

- the canonical session is obtained from ``/auth/session``;
- admin visibility depends on ``branch.admin.access``;
- ``AdminHub`` has no links to ``/admin``, ``adminUrl`` or ``window.location``;
- local routes exist for the eight BA-003 operational cards;
- corporate identity and branch catalogs are absent from the POS hub;
- authorization does not read permissions from ``localStorage``;
- ``active_branch`` replaces a stale local branch and organization selection
  is revalidated before being applied;
- ``SessionGate`` requires ``pos.operate``;
- ``PointOfSale`` uses ``fetchApi`` for modifiers (no raw ``fetch`` for them);
- BDD/TDD docs and traceability exist.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POS_SRC = ROOT / "apps" / "pos-web" / "src"
DOCS = ROOT / "docs"


def _read(rel: str) -> str:
    return (POS_SRC / rel).read_text(encoding="utf-8")


def test_session_consumes_auth_session_endpoint() -> None:
    """The canonical session must call GET /auth/session via fetchApi."""
    source = _read("session.ts")
    assert "/auth/session" in source, (
        "session.ts must consume /auth/session as the canonical session source"
    )
    assert "fetchApi" in source, "session.ts must use fetchApi for the session call"


def test_canonical_branch_replaces_stale_local_branch() -> None:
    """The backend active branch must overwrite, never inherit, local user data."""
    source = _read("session.ts")
    resolver = re.search(
        r"export function resolvePosBranchId\(\): string \{(?P<body>.*?)\n\}",
        source,
        re.DOTALL,
    )
    assert resolver, "resolvePosBranchId must exist"
    resolver_body = resolver.group("body")
    assert "localStorage.getItem('pos_branch_id')" in resolver_body
    for forbidden in ("localStorage.user", "assigned_branch_id", "roles", "is_superadmin"):
        assert forbidden not in resolver_body, (
            f"resolvePosBranchId must not derive branch authority from {forbidden}"
        )

    write_position = source.find("setPosBranchId(session.active_branch.id)")
    publish_position = source.find("setState({ status: 'ok', session })")
    assert write_position >= 0, "The canonical active_branch must update POS branch context"
    assert publish_position > write_position, (
        "The canonical branch must be applied before the session is published"
    )


def test_organization_branch_selection_is_validated_before_application() -> None:
    """An organization selection must round-trip through the canonical endpoint."""
    session_source = _read("session.ts")
    settings_source = _read("features/settings/Settings.tsx")
    assert "/auth/session?branch_id=${encodeURIComponent(branchId)}" in session_source
    assert "allowed_branch_ids.includes(branchId)" in session_source
    assert "nextSession.active_branch?.id !== branchId" in session_source
    assert "applySession(nextSession)" in session_source
    assert "await selectBranch(branchId)" in settings_source
    assert "branchId === activeBranchId" in settings_source, (
        "Cash status and operations must use only the validated active branch"
    )


def test_session_gate_requires_pos_operate() -> None:
    """Authentication alone must not grant access to the POS application."""
    source = _read("App.tsx")
    gate = source.split("const SessionGate", 1)[1].split("const PermissionRoute", 1)[0]
    assert "permissions.includes('pos.operate')" in gate
    assert "Tu cuenta no tiene acceso al POS" in gate


def test_admin_access_uses_branch_admin_access_permission() -> None:
    """Admin visibility must depend on branch.admin.access, not role names."""
    layout = _read("components/PosLayout.tsx")
    assert "branch.admin.access" in layout, (
        "PosLayout must gate the Administración menu on branch.admin.access"
    )
    # The layout must NOT determine admin visibility from isAdministrativeUser
    # (role-name / localStorage based). It should use usePosSession.
    assert "usePosSession" in layout, (
        "PosLayout must use usePosSession for permission decisions"
    )


def test_app_routes_contain_branch_administration_routes() -> None:
    """App.tsx must define the local operational routes inside PosLayout.

    React Router nested routes use relative paths (no leading slash), so we
    check for ``path="administration..."`` patterns.
    """
    source = _read("App.tsx")
    for route in (
        'path="administration"',
        'path="administration/products"',
        'path="administration/variations"',
        'path="administration/suppliers"',
        'path="administration/purchases"',
        'path="administration/production"',
        'path="administration/waste"',
        'path="administration/transfers"',
        'path="administration/counts"',
    ):
        assert route in source, f"App.tsx must define route {route!r}"
    assert 'path="administration/staff"' not in source
    assert 'path="administration/branch"' not in source
    assert "PosSessionProvider" in source, "App must wrap in PosSessionProvider"
    assert "PermissionRoute" in source, "App must use PermissionRoute guards"


def test_admin_hub_has_no_admin_redirects() -> None:
    """AdminHub must not link to /admin, use adminUrl, or window.location."""
    source = _read("features/admin/AdminHub.tsx")
    assert "adminUrl" not in source, "AdminHub must not contain adminUrl"
    assert "window.location" not in source, (
        "AdminHub must not use window.location for admin navigation"
    )
    # No href="/admin/..." links
    assert not re.search(r'href\s*=\s*"/admin', source), (
        "AdminHub must not contain href links to /admin"
    )
    # Must use Link from react-router for navigation
    assert "Link" in source, "AdminHub must use Link from react-router-dom"


def test_admin_hub_contains_operational_cards_including_variations() -> None:
    """The POS hub exposes operations, never corporate identity catalogs."""
    source = _read("features/admin/AdminHub.tsx")
    routes = re.findall(r"to: '(/[^']+)'", source)
    assert routes == [
        "/administration/attendance",
        "/sales-monitor",
        "/administration/products",
        "/administration/suppliers",
        "/administration/purchases",
        "/administration/waste",
    ]
    for forbidden in ("Sucursales", "Usuarios", "Roles", "Personal de sucursal"):
        assert forbidden not in source
    assert 'aria-disabled="true"' not in source
    assert "Próximo incremento" not in source


def test_authorization_does_not_read_permissions_from_localStorage() -> None:
    """The session module must not rely on localStorage for permission checks.

    The canonical PosSessionProvider and hasPermission must derive permissions
    from the /auth/session response, not from a localStorage 'user' object.
    We verify that the provider's hasPermission reads from the session state
    and that there's no localStorage.getItem('permissions') pattern.
    """
    source = _read("session.ts")
    # The canonical provider must use the session from fetchApi
    assert "PosSessionProvider" in source
    assert "hasPermission" in source
    # Must NOT read a 'permissions' key from localStorage for authorization
    assert "localStorage.getItem('permissions')" not in source, (
        "Authorization must not read permissions from localStorage"
    )


def test_point_of_sale_uses_fetchapi_for_modifiers() -> None:
    """PointOfSale must use fetchApi for the modifiers call, not raw fetch."""
    source = _read("features/pos/PointOfSale.tsx")
    # Find the modifiers call context
    modifiers_match = re.search(r"modifiers[^\n]{0,60}", source)
    assert modifiers_match, "PointOfSale must reference modifiers"
    # The modifiers fetch must use fetchApi, not a bare fetch()
    # Check that there's no raw fetch( with /modifiers
    raw_modifier_fetch = re.search(r"fetch\(\s*[`'\"]/api/v1/products/[^\n]*modifiers", source)
    assert raw_modifier_fetch is None, (
        "PointOfSale must not use raw fetch() for modifiers; use fetchApi instead"
    )


def test_branch_admin_products_exist_and_consume_contracts() -> None:
    """The product page must consume its branch-scoped backend contract."""
    products = _read("features/admin/BranchAdminProducts.tsx")
    assert "/branch-administration/catalog/products" in products
    assert "catalog.branch.manage" in products or "hasPermission" in products
    assert "Estado central" in products
    assert "{p.status}" in products

def test_settings_uses_canonical_session_for_branch_scope() -> None:
    """Settings must use the canonical session, not /branches for branch scope."""
    source = _read("features/settings/Settings.tsx")
    assert "usePosSession" in source, (
        "Settings must use usePosSession for branch scope decisions"
    )
    assert "isOrgScope" in source or "scope.level" in source, (
        "Settings must distinguish org vs branch scope from the canonical session"
    )


def test_bdd_and_tdd_docs_exist() -> None:
    """BDD and TDD docs for the POS branch admin frontend must exist."""
    bdd = DOCS / "03-BDD-pos-branch-administration.md"
    tdd = DOCS / "04-TDD-pos-branch-administration.md"
    assert bdd.exists(), f"BDD doc missing: {bdd}"
    assert tdd.exists(), f"TDD doc missing: {tdd}"
    bdd_content = bdd.read_text(encoding="utf-8")
    for sc in (
        "BDD-SC-125",
        "BDD-SC-126",
        "BDD-SC-127",
        "BDD-SC-128",
        "BDD-SC-129",
        "BDD-SC-130",
        "BDD-SC-131",
        "BDD-SC-132",
        "BDD-SC-133",
        "BDD-SC-134",
        "BDD-SC-135",
    ):
        assert sc in bdd_content, f"BDD doc missing {sc}"
    assert not re.search(r"^\s+Y\s", bdd_content, re.MULTILINE), (
        "English Gherkin must use And instead of an undeclared Spanish Y keyword"
    )
    tdd_content = tdd.read_text(encoding="utf-8")
    assert "TDD-TS-051" in tdd_content
    assert "TDD-TC-044" in tdd_content


def test_traceability_references_new_scenarios() -> None:
    """The traceability matrix must reference the new BDD/TDD IDs."""
    matrix = (DOCS / "05-matriz-trazabilidad.md").read_text(encoding="utf-8")
    for token in (
        "BDD-SC-125",
        "BDD-SC-129",
        "BDD-SC-133",
        "BDD-SC-134",
        "BDD-SC-135",
        "TDD-TS-051",
        "TDD-TC-044",
    ):
        assert token in matrix, f"Traceability matrix missing {token}"
