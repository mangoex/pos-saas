"""Facturapi v2 HTTP REST Client."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

FACTURAPI_BASE_URL = "https://www.facturapi.io/v2"


class FacturapiClient:
    """HTTP Client for Facturapi v2 REST API."""

    def __init__(self, api_key: str | None = None, is_mock: bool = False):
        self.api_key = api_key
        # The service decides whether a configured sandbox is an explicit simulation.
        # An absent credential must never turn a fiscal operation into a fake success.
        self.is_mock = is_mock

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "RestaurantOS-Kiwi/1.0",
        }

    def _request(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.is_mock:
            return self._mock_response(method, endpoint, data)

        url = f"{FACTURAPI_BASE_URL}{endpoint}"
        body_bytes = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers=self._headers(),
            method=method,
        )

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                resp_data = resp.read().decode("utf-8")
                return json.loads(resp_data) if resp_data else {}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            logger.error("Facturapi HTTP error %s: %s", e.code, err_body)
            try:
                err_json = json.loads(err_body)
                msg = err_json.get("message") or err_json.get("detail") or str(err_json)
            except Exception:
                msg = err_body
            raise RuntimeError(f"Error Facturapi ({e.code}): {msg}") from e
        except Exception as e:
            logger.exception("Facturapi connection error")
            raise RuntimeError(f"No se pudo conectar con Facturapi: {e}") from e

    def _mock_response(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Deterministic sandbox / mock generator for local development and tests."""
        import uuid

        mock_id = f"facturapi-{uuid.uuid4().hex[:12]}"
        mock_uuid = str(uuid.uuid4()).upper()

        if "/receipts" in endpoint and method == "POST":
            domain = "demo"
            return {
                "id": mock_id,
                "created_at": "2026-08-31T20:00:00.000Z",
                "status": "open",
                "total": data.get("total", 100.0) if data else 100.0,
                "key": f"KEY-{uuid.uuid4().hex[:6].upper()}",
                "self_invoice_url": f"https://factura.space/{domain}/self-invoice/{mock_id}",
            }

        if "/invoices" in endpoint and method == "POST":
            return {
                "id": mock_id,
                "created_at": "2026-08-31T20:00:00.000Z",
                "status": "valid",
                "uuid": mock_uuid,
                "folio_number": data.get("folio_number", 101) if data else 101,
                "series": data.get("series", "F") if data else "F",
                "total": data.get("total", 250.0) if data else 250.0,
                "verification_url": f"https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx?id={mock_uuid}",
                "customer": data.get("customer", {}) if data else {},
                "cancellation_status": "none",
            }

        if "/cancel" in endpoint:
            return {
                "id": mock_id,
                "status": "canceled",
                "cancellation_status": "accepted",
            }

        if "/test" in endpoint or "/organizations/me" in endpoint:
            return {
                "status": "ok",
                "legal_name": "RESTAURANTE KIWI SA DE CV",
                "rfc": "KIW210101ABC",
                "is_active": True,
            }

        return {"id": mock_id, "status": "ok"}

    def validate_api_key(self) -> dict[str, Any]:
        return self._request("GET", "/organizations/me")

    def create_receipt(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/receipts", payload)

    def create_invoice(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/invoices", payload)

    def get_invoice(self, invoice_id: str) -> dict[str, Any]:
        return self._request("GET", f"/invoices/{invoice_id}")

    def get_receipt(self, receipt_id: str) -> dict[str, Any]:
        return self._request("GET", f"/receipts/{receipt_id}")

    def cancel_invoice(
        self, invoice_id: str, motive: str = "02", substitution_id: str | None = None
    ) -> dict[str, Any]:
        params = f"?motive={motive}"
        if substitution_id:
            params += f"&substitution={substitution_id}"
        return self._request("DELETE", f"/invoices/{invoice_id}{params}")

    def send_email(self, invoice_id: str, email: str) -> dict[str, Any]:
        return self._request("POST", f"/invoices/{invoice_id}/email", {"email": email})
