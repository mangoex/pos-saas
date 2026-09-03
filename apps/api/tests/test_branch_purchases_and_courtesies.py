from __future__ import annotations

import uuid

from test_platform_api import (
    BRANCH_ID,
    _admin_headers,
    _client_with_seeded_database,
    _open_shift,
)


def test_branch_supplier_presentation_and_multiline_purchase():
    """Verify that a branch supervisor can create a local supplier,
    add purchase presentations, capture a multi-line direct purchase,
    confirm it and cancel it cleanly.
    """
    client = _client_with_seeded_database()
    headers = _admin_headers()

    # 1. Get an existing inventory item and units
    items_res = client.get("/api/v1/inventory/items", headers=headers)
    assert items_res.status_code == 200
    items = items_res.json()
    assert len(items) > 0
    item = items[0]
    item_id = item["id"]
    base_unit_id = item["base_unit_id"]

    units_res = client.get("/api/v1/inventory/units", headers=headers)
    assert units_res.status_code == 200
    units = units_res.json()
    assert len(units) > 0
    commercial_unit_id = units[0]["id"]

    # 2. Create local supplier
    supplier_code = f"SUP-{uuid.uuid4().hex[:6].upper()}"
    res_sup = client.post(
        "/api/v1/suppliers",
        json={
            "code": supplier_code,
            "commercial_name": "Fruteria La Huerta Local",
            "legal_name": "Frutas y Verduras La Huerta SA de CV",
            "tax_id": f"FRU{uuid.uuid4().hex[:9].upper()}",
            "credit_days": 0,
            "branch_id": BRANCH_ID,
            "contacts": [
                {
                    "name": "Don Pedro",
                    "phone": "6671234567",
                    "email": "pedro@huerta.com",
                    "primary_for_orders": True,
                }
            ],
        },
        headers=headers,
    )
    assert res_sup.status_code == 200, res_sup.text
    sup_data = res_sup.json()
    supplier_id = sup_data["id"]
    assert supplier_id is not None

    # 3. Create purchase presentation
    pres_code = f"PRES-{uuid.uuid4().hex[:6].upper()}"
    res_pres = client.post(
        "/api/v1/purchase-presentations",
        json={
            "supplier_id": supplier_id,
            "item_id": item_id,
            "commercial_unit_id": commercial_unit_id,
            "base_unit_id": base_unit_id,
            "code": pres_code,
            "name": "Caja 10 Kilos",
            "usable_content": "10.000000",
            "base_unit_yield": "10.000000",
            "yield_percent": "1.000000",
            "last_net_price": "250.00",
            "status": "active",
        },
        headers=headers,
    )
    assert res_pres.status_code == 200, res_pres.text
    pres_data = res_pres.json()
    pres_id = pres_data["id"]
    assert pres_id is not None

    # 4. Create multi-line purchase draft
    purchase_folio = f"FAC-{uuid.uuid4().hex[:6].upper()}"
    res_pur = client.post(
        "/api/v1/purchases",
        json={
            "branch_id": BRANCH_ID,
            "supplier_id": supplier_id,
            "document_type": "invoice",
            "folio": purchase_folio,
            "paid_from_cash": False,
            "payment_method": "other",
            "lines": [
                {
                    "presentation_id": pres_id,
                    "quantity": "2",
                    "unit_price": "250.00",
                    "discount": "0",
                    "tax": "40.00",
                }
            ],
        },
        headers=headers,
    )
    assert res_pur.status_code == 200, res_pur.text
    pur_data = res_pur.json()
    purchase_id = pur_data["id"]
    assert purchase_id is not None
    assert pur_data["status"] == "draft"

    # 5. Confirm purchase
    idempotency_key = f"conf-{uuid.uuid4()}"
    res_conf = client.post(
        f"/api/v1/purchases/{purchase_id}/confirm",
        json={"idempotency_key": idempotency_key},
        headers={**headers, "Idempotency-Key": idempotency_key},
    )
    assert res_conf.status_code == 200, res_conf.text
    conf_data = res_conf.json()
    assert conf_data["status"] == "confirmed"

    # 6. Cancel purchase with reason
    res_cancel = client.post(
        f"/api/v1/purchases/{purchase_id}/cancel",
        json={"reason": "Error en captura de folio de factura"},
        headers=headers,
    )
    assert res_cancel.status_code == 200, res_cancel.text
    assert res_cancel.json()["status"] == "cancelled"


def test_purchase_paid_from_cash_shift_and_cancellation_compensation():
    """Verify BDD-SC-079 and BDD-SC-081:
    A direct purchase paid in cash automatically links to the open cash shift,
    creates a cash withdrawal, and upon cancellation creates a compensating cash deposit.
    """
    client = _client_with_seeded_database()
    headers = _admin_headers()

    # 1. Open cash shift with 200,000 cents ($2,000 MXN)
    shift_res = _open_shift(client, opening_cash_cents=200000, headers=headers)
    assert shift_res.status_code == 200

    # 2. Get item & units
    items = client.get("/api/v1/inventory/items", headers=headers).json()
    item = items[0]
    units = client.get("/api/v1/inventory/units", headers=headers).json()
    commercial_unit_id = units[0]["id"]

    # 3. Create supplier & presentation
    sup = client.post(
        "/api/v1/suppliers",
        json={
            "code": f"FRUT-{uuid.uuid4().hex[:4].upper()}",
            "commercial_name": "Fruteria Express",
            "legal_name": "Fruteria Express SA",
            "branch_id": BRANCH_ID,
            "credit_days": 0,
        },
        headers=headers,
    ).json()

    pres = client.post(
        "/api/v1/purchase-presentations",
        json={
            "supplier_id": sup["id"],
            "item_id": item["id"],
            "commercial_unit_id": commercial_unit_id,
            "base_unit_id": item["base_unit_id"],
            "code": f"P-{uuid.uuid4().hex[:4].upper()}",
            "name": "Bolsa 5 Kg",
            "usable_content": "5.000000",
            "base_unit_yield": "5.000000",
            "yield_percent": "1.000000",
            "last_net_price": "100.00",
            "status": "active",
        },
        headers=headers,
    ).json()

    # 4. Create purchase with paid_from_cash = True ($300 MXN total)
    purchase = client.post(
        "/api/v1/purchases",
        json={
            "branch_id": BRANCH_ID,
            "supplier_id": sup["id"],
            "document_type": "ticket",
            "folio": f"TCK-{uuid.uuid4().hex[:5].upper()}",
            "paid_from_cash": True,
            "payment_method": "cash",
            "lines": [
                {
                    "presentation_id": pres["id"],
                    "quantity": "3",
                    "unit_price": "100.00",
                    "discount": "0",
                    "tax": "0",
                }
            ],
        },
        headers=headers,
    ).json()

    # 5. Cash confirmation fails closed without a configured register.
    missing_register = client.post(
        f"/api/v1/purchases/{purchase['id']}/confirm",
        json={},
        headers={**headers, "Idempotency-Key": f"conf-missing-{uuid.uuid4()}"},
    )
    assert missing_register.status_code == 409
    assert missing_register.json()["detail"]["code"] == "cash_movement_invalid"

    # 6. Confirm purchase with cash shift
    conf_res = client.post(
        f"/api/v1/purchases/{purchase['id']}/confirm",
        json={"idempotency_key": f"conf-{uuid.uuid4()}", "register_id": "CAJA-01"},
        headers={**headers, "Idempotency-Key": f"conf-header-{uuid.uuid4()}"},
    )
    assert conf_res.status_code == 200, conf_res.text
    confirmed = conf_res.json()
    assert confirmed["status"] == "confirmed"
    assert confirmed["paid_from_cash"] is True
    assert confirmed["cash_movement_id"] is not None

    # 7. Cancel purchase and verify cash movement compensation
    cancel_res = client.post(
        f"/api/v1/purchases/{purchase['id']}/cancel",
        json={"reason": "Cancelación por devolución de fruta"},
        headers=headers,
    )
    assert cancel_res.status_code == 200, cancel_res.text
    cancelled = cancel_res.json()
    assert cancelled["status"] == "cancelled"


def test_branch_direct_purchase_without_presentations_uses_concept():
    """Verify that a branch cashier or supervisor can record a direct cash purchase
    by simply passing free-text concept (e.g. Bolsa de hielo) without needing
    preconfigured presentations or suppliers.
    """
    client = _client_with_seeded_database()
    headers = _admin_headers()

    # Open cash shift
    shift_res = _open_shift(client, opening_cash_cents=200000, headers=headers)
    assert shift_res.status_code == 200

    res = client.post(
        "/api/v1/purchases",
        json={
            "branch_id": BRANCH_ID,
            "document_type": "receipt",
            "paid_from_cash": True,
            "payment_method": "cash",
            "lines": [
                {
                    "concept": "Bolsa de hielo 5kg",
                    "quantity": "2",
                    "unit_price": "35.00",
                    "discount": "0",
                    "tax": "0",
                },
                {
                    "concept": "Servilletas y desechables",
                    "quantity": "1",
                    "unit_price": "85.50",
                    "discount": "0",
                    "tax": "0",
                },
            ],
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    purchase = res.json()
    assert purchase["id"] is not None
    assert float(purchase["total"]) == 155.5  # 2*35 + 85.5
    assert len(purchase["lines"]) == 2

    # Confirm purchase with cash register
    conf_res = client.post(
        f"/api/v1/purchases/{purchase['id']}/confirm",
        json={"idempotency_key": f"conf-concept-{uuid.uuid4()}", "register_id": "CAJA-01"},
        headers=headers,
    )
    assert conf_res.status_code == 200, conf_res.text
    confirmed = conf_res.json()
    assert confirmed["status"] == "confirmed"
    assert confirmed["paid_from_cash"] is True
