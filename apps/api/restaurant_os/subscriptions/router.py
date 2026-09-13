from typing import Any
from fastapi import APIRouter
from restaurant_os.subscriptions.webhooks import router as webhooks_router
from restaurant_os.subscriptions.service import create_subscription

router = APIRouter()

@router.post("/api/subscriptions", status_code=201)
async def create_subscription_endpoint(payload: dict[str, Any]) -> dict[str, str]:
    # payload has package_name, card_token, user_email
    package_name = str(payload.get("package_name", ""))
    card_token = str(payload.get("card_token", ""))
    user_email = str(payload.get("user_email", ""))
    
    await create_subscription(
        package_name=package_name,
        card_token=card_token,
        user_email=user_email
    )
    return {"status": "success"}

router.include_router(webhooks_router)
