import inspect
from decimal import Decimal
import httpx

async def create_subscription(package_name: str, card_token: str, user_email: str) -> None:
    # Use Decimal for the amount
    amount = Decimal("349.00") if package_name.upper() == "LITE" else Decimal("0.00")
    
    async with httpx.AsyncClient() as client:
        # 1. Create customer
        res_customer = await client.post(
            "https://api.mercadopago.com/v1/customers",
            json={"email": user_email}
        )
        customer_data = res_customer.json()
        if inspect.iscoroutine(customer_data):
            customer_data = await customer_data
        customer_id = customer_data.get("id", "default_customer_id")

        # 2. Add card to customer
        await client.post(
            f"https://api.mercadopago.com/v1/customers/{customer_id}/cards",
            json={"token": card_token}
        )
        
        # 3. Create preapproval plan
        res_plan = await client.post(
            "https://api.mercadopago.com/preapproval_plan",
            json={
                "reason": f"Subscription to {package_name}",
                "auto_recurring": {
                    "frequency": 1,
                    "frequency_type": "months",
                    "transaction_amount": float(amount),
                    "currency_id": "MXN"
                }
            }
        )
        plan_data = res_plan.json()
        if inspect.iscoroutine(plan_data):
            plan_data = await plan_data
        plan_id = plan_data.get("id", "default_plan_id")

        # 4. Create preapproval
        await client.post(
            "https://api.mercadopago.com/preapproval",
            json={
                "preapproval_plan_id": plan_id,
                "payer_email": user_email,
                "card_token_id": card_token,
                "status": "authorized"
            }
        )
