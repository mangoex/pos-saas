"""Architecture contract for historical PRD-FR-712 attendance clock."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_pos_menu_places_attendance_between_orders_and_administration() -> None:
    layout = _read("apps/pos-web/src/components/PosLayout.tsx")
    assert layout.index("label: 'Pedidos'") < layout.index("label: 'Checador'")
    assert layout.index("label: 'Checador'") < layout.index("label: 'Administración'")
    assert "AttendanceClockModal" in layout
    modal = _read("apps/pos-web/src/features/attendance/AttendanceClockModal.tsx")
    assert 'type="password"' in modal
    assert "Clave del empleado" in modal
    assert "Registrar checada" in modal
    assert "setInterval" in modal
    assert "/attendance/checks" in modal


def test_attendance_report_route_filters_and_state_labels_exist() -> None:
    app = _read("apps/pos-web/src/App.tsx")
    hub = _read("apps/pos-web/src/features/admin/AdminHub.tsx")
    report = _read("apps/pos-web/src/features/attendance/AttendanceReport.tsx")
    assert 'path="administration/attendance"' in app
    assert "permissions={['branch.staff.read', 'admin.manage']}" in app
    assert "to: '/administration/attendance'" in hub
    for token in (
        "employee_code",
        'type="date"',
        'type="month"',
        "branch_id",
        "Una checada",
        "Entrada",
        "Salida",
        "#2563eb",
        "#15803d",
        "#b91c1c",
    ):
        assert token in report


def test_employee_code_is_exposed_in_both_admin_catalogs() -> None:
    users = _read("apps/admin-web/src/features/users/UsersList.tsx")
    drivers = _read("apps/admin-web/src/features/delivery/DriversList.tsx")
    for source in (users, drivers):
        assert "employee_code" in source
        assert "Código del empleado" in source
        assert "Sin código" in source
        assert "maxLength={6}" in source
        assert 'pattern="[A-Za-z0-9]{6}"' in source


def test_attendance_domain_is_server_authoritative_and_audited() -> None:
    operations = _read("apps/api/restaurant_os/operations.py")
    migration = _read(
        "apps/api/alembic/versions/202608080100_0032_attendance_clock.py"
    )
    assert "checked_at = _now()" in operations
    assert "ZoneInfo" in operations
    assert 'action="attendance.checked"' in operations
    assert '"attendance_daily_limit_reached"' in operations
    assert '"employee_code_already_exists"' in operations
    assert 'r"^[A-Z0-9]{6}$"' in operations
    assert '"employee_code_registry"' in migration
    assert 'sa.String(6)' in migration
    assert "daily_sequence IN (1, 2)" in migration
    assert "Cannot downgrade 0032" in migration


def test_attendance_specs_and_traceability_exist() -> None:
    prd = _read("docs/01-PRD.md")
    bdd = _read("docs/03-BDD-attendance-clock.md")
    tdd = _read("docs/04-TDD-attendance-clock.md")
    matrix = _read("docs/05-matriz-trazabilidad.md")
    assert "PRD-FR-712" in prd and "PRD-FR-712" in matrix
    for scenario in range(249, 255):
        assert f"BDD-SC-{scenario}" in bdd
        assert f"BDD-SC-{scenario}" in matrix
    assert "TDD-TS-074" in tdd and "TDD-TC-070" in tdd
    assert "TDD-TS-074" in matrix and "TDD-TC-070" in matrix
