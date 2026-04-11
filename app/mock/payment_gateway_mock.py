"""
MOCK PAYMENT GATEWAY
====================
This replaces Cashfree for DevOps training purposes.
No real money moves. All operations update MongoDB directly.
"""

import logging
from datetime import datetime
from bson import ObjectId

logger = logging.getLogger(__name__)


async def mock_create_payment_order(
    user_id: str,
    amount: float,
    currency: str = "INR",
    reference_id: str = None,
    db=None
) -> dict:
    """
    Mock: Replaces Cashfree create_order API call.
    Returns a fake payment session that the frontend can use.
    """
    mock_order_id = f"MOCK_ORDER_{ObjectId()}"
    mock_session_id = f"MOCK_SESSION_{ObjectId()}"

    logger.info(f"[MOCK PAYMENT] Creating order for user={user_id}, amount=₹{amount}")

    return {
        "success": True,
        "order_id": mock_order_id,
        "payment_session_id": mock_session_id,
        "amount": amount,
        "currency": currency,
        "status": "ACTIVE",
        "mock": True
    }


async def mock_verify_payment(
    order_id: str,
    user_id: str,
    amount: float,
    db=None
) -> dict:
    """
    Mock: Replaces Cashfree payment verification webhook/polling.
    Immediately marks payment as SUCCESS and updates wallet in DB.
    """
    logger.info(f"[MOCK PAYMENT] Verifying payment order={order_id}, user={user_id}, amount=₹{amount}")

    # Update wallet balance directly in MongoDB
    if db is not None:
        await db["wallets"].update_one(
            {"user_id": user_id},
            {
                "$inc": {"balance": amount},
                "$set": {"updated_at": datetime.utcnow()}
            },
            upsert=True
        )

        # Record transaction
        transaction = {
            "user_id": user_id,
            "type": "CREDIT",
            "amount": amount,
            "description": "Wallet top-up (Mock Payment)",
            "reference_id": order_id,
            "status": "SUCCESS",
            "created_at": datetime.utcnow(),
            "mock": True
        }
        await db["transactions"].insert_one(transaction)

        logger.info(f"[MOCK PAYMENT] ✅ ₹{amount} credited to wallet for user={user_id}")

    return {
        "success": True,
        "order_id": order_id,
        "payment_status": "SUCCESS",
        "amount": amount,
        "message": "Mock payment processed successfully",
        "mock": True
    }


async def mock_payment_webhook_handler(payload: dict, db=None) -> dict:
    """
    Mock: Replaces Cashfree webhook handler.
    Accepts any webhook payload and returns success.
    """
    logger.info(f"[MOCK PAYMENT] Webhook received: {payload}")
    return {"status": "ok", "mock": True}


async def mock_refund_payment(
    order_id: str,
    refund_amount: float,
    user_id: str,
    db=None
) -> dict:
    """
    Mock: Replaces Cashfree refund API.
    Directly deducts from wallet balance in MongoDB.
    """
    logger.info(f"[MOCK PAYMENT] Refund for order={order_id}, amount=₹{refund_amount}, user={user_id}")

    if db is not None:
        await db["wallets"].update_one(
            {"user_id": user_id},
            {
                "$inc": {"balance": -refund_amount},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )

    return {
        "success": True,
        "refund_id": f"MOCK_REFUND_{ObjectId()}",
        "order_id": order_id,
        "refund_amount": refund_amount,
        "status": "SUCCESS",
        "mock": True
    }
