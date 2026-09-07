"""Architecture checks for POS-CUST-001 phone-first customer checkout."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POS_SOURCE = (
    ROOT / "apps" / "pos-web" / "src" / "features" / "pos" / "PointOfSale.tsx"
).read_text(encoding="utf-8")


def test_checkout_validates_mexican_phone_before_lookup() -> None:
    assert "function validMexicanPhone" in POS_SOURCE
    assert "digits.length === 10" in POS_SOURCE
    assert "digits.length === 12 && digits.startsWith('52')" in POS_SOURCE
    lookup_effect = POS_SOURCE.split("// Búsqueda exacta por teléfono", 1)[1].split(
        "const selectCustomer", 1
    )[0]
    assert "if (!branchId || !phone)" in lookup_effect


def test_lookup_uses_phone_and_canonical_branch_never_free_text_q() -> None:
    lookup_effect = POS_SOURCE.split("// Búsqueda exacta por teléfono", 1)[1].split(
        "const selectCustomer", 1
    )[0]
    assert "branch_id: branchId" in lookup_effect
    assert "phone," in lookup_effect
    assert "limit: '20'" in lookup_effect
    assert "q:" not in lookup_effect
    assert "AbortController" in lookup_effect


def test_phone_results_show_names_and_active_address_counts() -> None:
    assert 'aria-label="Clientes encontrados por teléfono"' in POS_SOURCE
    assert "<div style={{ fontWeight: 600 }}>{c.name}</div>" in POS_SOURCE
    assert "a.status === 'active'" in POS_SOURCE
    assert "{addrCount} domicilio(s)" in POS_SOURCE


def test_not_found_phone_offers_inline_customer_registration() -> None:
    assert "customerLookupStatus === 'not-found'" in POS_SOURCE
    assert "Teléfono no registrado" in POS_SOURCE
    assert "Registrar y seleccionar cliente" in POS_SOURCE
    assert "phones: [{ number: phone, is_primary: true, type: 'mobile' }]" in POS_SOURCE
    assert "selectCustomer(customer)" in POS_SOURCE


def test_account_selects_order_type_before_modal_and_modal_exposes_delivery_addresses() -> None:
    before_payment_modal, payment_modal = POS_SOURCE.split(
        'title="Cobrar pedido"', maxsplit=1
    )
    for label in ("En sucursal", "Para llevar", "A domicilio"):
        assert label in before_payment_modal
    assert "Tipo de pedido" not in payment_modal
    assert "Domicilio de entrega" in payment_modal
    assert "setSelectedAddressId(a.id)" in payment_modal
    assert "+ Agregar domicilio" in payment_modal


def test_legacy_import_does_not_treat_customer_key_as_phone() -> None:
    importer = (ROOT / "tools" / "import_legacy_branch_catalogs.py").read_text(
        encoding="utf-8"
    )
    customer_mapping = importer.split('if entity_type == "customer":', 1)[1].split(
        'if entity_type == "inventory_item":', 1
    )[0]
    assert 'row.get("NOMBRE"' in customer_mapping
    assert 'row.get("DIRECCION"' in customer_mapping
    assert 'row.get("CLAVE"' not in customer_mapping
    assert "phone" not in customer_mapping.casefold()


def test_phone_flow_specification_is_traceable() -> None:
    bdd = (ROOT / "docs" / "03-BDD-pos-phone-customer-flow.md").read_text(
        encoding="utf-8"
    )
    tdd = (ROOT / "docs" / "04-TDD-pos-phone-customer-flow.md").read_text(
        encoding="utf-8"
    )
    matrix = (ROOT / "docs" / "05-matriz-trazabilidad.md").read_text(
        encoding="utf-8"
    )
    for scenario in range(163, 168):
        assert f"BDD-SC-{scenario}" in bdd
    assert "TDD-TS-056" in tdd and "TDD-TC-049" in tdd
    assert "PRD-FR-698" in matrix
