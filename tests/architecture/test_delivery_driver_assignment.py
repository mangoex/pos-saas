"""Architecture contract for historical PRD-FR-711 delivery driver assignment."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_payment_modal_reuses_order_type_and_scopes_driver_picker_to_delivery() -> None:
    source = _read("apps/pos-web/src/features/pos/PointOfSale.tsx")
    payment_modal = source.split('title="Cobrar pedido"', maxsplit=1)[1]
    assert "Tipo de pedido" not in payment_modal
    assert "orderType === 'delivery'" in payment_modal
    assert "Asignar repartidor" in payment_modal
    assert "/delivery/drivers/available" in source
    assert "driver_id:" in source


def test_assignment_is_validated_persisted_and_exposed_as_history() -> None:
    operations = _read("apps/api/restaurant_os/operations.py")
    api = _read("apps/api/restaurant_os/api.py")
    migration = _read(
        "apps/api/alembic/versions/202607230230_0031_delivery_assignments.py"
    )
    assert "driver_assignment_delivery_only" in operations
    assert "delivery_driver_unavailable" in operations
    assert "models.delivery_assignments.insert()" in operations
    assert 'event_type="DRIVER_ASSIGNED"' in operations
    assert 'action="delivery.driver_assigned"' in operations
    assert '@router.get("/delivery/drivers/available")' in api
    assert '@router.get("/drivers/{driver_id}/deliveries")' in api
    assert "Cannot downgrade 0031 while delivery assignments exist" in migration


def test_admin_driver_history_shows_operational_delivery_facts() -> None:
    source = _read("apps/admin-web/src/features/delivery/DriversList.tsx")
    assert "/deliveries" in source
    for label in (
        "Historial de entregas",
        "Pedido",
        "Cliente",
        "Importe",
        "Líneas",
        "Unidades",
    ):
        assert label in source


def test_delivery_assignment_specs_and_traceability_exist() -> None:
    prd = _read("docs/01-PRD.md")
    bdd = _read("docs/03-BDD-delivery-driver-assignment.md")
    tdd = _read("docs/04-TDD-delivery-driver-assignment.md")
    matrix = _read("docs/05-matriz-trazabilidad.md")
    assert "PRD-FR-711" in prd and "PRD-FR-711" in matrix
    for scenario in range(243, 248):
        assert f"BDD-SC-{scenario}" in bdd
        assert f"BDD-SC-{scenario}" in matrix
    assert "TDD-TS-072" in tdd and "TDD-TC-068" in tdd
    assert "TDD-TS-072" in matrix and "TDD-TC-068" in matrix
