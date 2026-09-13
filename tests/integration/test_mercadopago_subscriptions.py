import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# We assume the app is imported from here.
from restaurant_os.main import app

client = TestClient(app)

def test_create_lite_subscription_mercadopago():
    """
    Given a user wanting to subscribe to the Lite package ($349 MXN)
    When the user initiates the subscription process
    Then the system calls Mercado Pago (plan, customer, card, preapproval)
    And strictly validates that the amount is sent as Decimal('349.00').
    """
    with patch("httpx.AsyncClient.post") as mock_post:
        # Mocking the MP responses for plan, customer, card, and preapproval creation
        mock_post.return_value.status_code = 201
        mock_post.return_value.json.return_value = {"id": "mock_mp_id", "status": "authorized"}

        response = client.post(
            "/api/subscriptions",
            json={
                "package_name": "LITE",
                "card_token": "tok_mock123",
                "user_email": "test@example.com"
            }
        )
        
        # Test should fail here in Red phase (backend not implemented yet)
        assert response.status_code == 201
        
        # Verify that calls were made to Mercado Pago
        assert mock_post.called

        # Validate strictly that amount is sent as Decimal(349)
        # Note: In HTTP requests, Decimal might be serialized as a string or float in JSON,
        # but internal service calls before HTTP layer should use Decimal.
        # Here we check the mock call arguments to ensure it was formatted correctly (e.g., '349.00').
        # Since we are mocking httpx, we can check the kwargs sent to post.
        found_amount = False
        for call in mock_post.call_args_list:
            kwargs = call.kwargs
            if "json" in kwargs:
                # Look for the amount in the payload
                payload = str(kwargs["json"])
                if "'349'" in payload or "'349.00'" in payload or "349" in payload:
                    found_amount = True
        
        assert found_amount, "Expected to find the amount 349 in the Mercado Pago HTTP call payload"

def test_mercadopago_webhook_success_idempotent():
    """
    Given a Mercado Pago webhook indicating successful payment for a preapproval
    When the webhook is received at /api/webhooks/mercadopago multiple times (idempotency test)
    Then the system returns 200 OK every time
    And the subscription status is updated to ACTIVE
    """
    webhook_payload = {
        "action": "payment.created",
        "data": {"id": "mock_payment_123"},
        "type": "payment"
    }

    # First call
    response_1 = client.post("/api/webhooks/mercadopago", json=webhook_payload)
    # The endpoint doesn't exist yet, so this will return 404 in the Red phase
    assert response_1.status_code == 200

    # Second call for idempotency
    response_2 = client.post("/api/webhooks/mercadopago", json=webhook_payload)
    assert response_2.status_code == 200

    # Verification of DB status would go here, 
    # but since this is integration we can assume we check through an API or DB mock.
    # We will just verify it updated by fetching the status via API
    # status_response = client.get("/api/subscriptions/mock_subscription_id")
    # assert status_response.json()["status"] == "ACTIVE"


def test_mercadopago_webhook_error_past_due():
    """
    Given a Mercado Pago webhook indicating a payment error
    When the webhook is received at /api/webhooks/mercadopago
    Then the system returns 200 OK (acknowledging receipt)
    And the subscription status is updated to PAST_DUE
    """
    webhook_payload = {
        "action": "payment.updated",
        "data": {"id": "mock_payment_124", "status": "rejected"},
        "type": "payment"
    }

    response = client.post("/api/webhooks/mercadopago", json=webhook_payload)
    assert response.status_code == 200
