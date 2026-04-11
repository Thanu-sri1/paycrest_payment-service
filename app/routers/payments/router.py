from __future__ import annotations

from datetime import datetime
from json import JSONDecodeError
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ...core.config import settings
from ...core.security import require_roles
from .service import get_db
from ...models.enums import LoanStatus, Roles
from .service import add_money, cashfree_create_order, cashfree_get_order, pay_emi_any_gateway, pay_emi_any_wallet, credit_wallet, verify_mpin, get_wallet_balance
from ...utils.id import loan_id_filter

router = APIRouter(prefix="", tags=["payments"])


class CreateEmiCashfreeOrderOut(BaseModel):
    order_id: str
    order_amount: float
    order_currency: str = "INR"
    payment_session_id: str | None = None
    payment_link: str | None = None
    cashfree: dict | None = None


def _extract_order_id(payload: dict) -> str | None:
    for path in (
        ("order_id",),
        ("data", "order", "order_id"),
        ("data", "order_id"),
        ("order", "order_id"),
    ):
        cur = payload
        ok = True
        for k in path:
            if not isinstance(cur, dict) or k not in cur:
                ok = False
                break
            cur = cur[k]
        if ok and isinstance(cur, str) and cur.strip():
            return cur.strip()
    return None


def _extract_payment_link(cf: dict | None) -> str | None:
    if not isinstance(cf, dict):
        return None
    # Try common shapes/keys without hard dependency on SDK docs
    for k in ("payment_link", "paymentLink", "payment_url", "paymentUrl"):
        v = cf.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    payments = cf.get("payments")
    if isinstance(payments, dict):
        for k in ("url", "payment_url", "paymentLink", "payment_link"):
            v = payments.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


async def _find_active_loan_any(db, loan_id: str, customer_id: str | int) -> tuple[str, dict]:
    filt = loan_id_filter(loan_id)
    filt["customer_id"] = customer_id

    for coll in ("personal_loans", "vehicle_loans", "education_loans", "home_loans"):
        loan = await db[coll].find_one(filt)
        if loan and loan.get("status") == LoanStatus.ACTIVE:
            return coll, loan
    raise HTTPException(status_code=400, detail="Loan not active or not found")


async def _compute_total_due(db, loan: dict, customer_id: str | int) -> float:
    emi = float(loan.get("emi_per_month") or 0)
    if emi <= 0:
        raise HTTPException(status_code=400, detail="Invalid EMI amount for loan")

    next_emi = await db.emi_schedules.find_one(
        {
            "loan_id": loan.get("loan_id"),
            "customer_id": customer_id,
            "status": {"$in": ["pending", "overdue"]},
        },
        sort=[("due_date", 1)],
    )
    penalty_amount = float(next_emi.get("penalty_amount") or 0) if next_emi else 0.0
    return float(round(emi + penalty_amount, 2))


class CreateWalletTopupCashfreeIn(BaseModel):
    amount: float
    mpin: str | None = None
    description: str | None = "Cashfree wallet top-up"


class CreateWalletTopupCashfreeOut(BaseModel):
    order_id: str
    order_amount: float
    order_currency: str = "INR"
    payment_session_id: str | None = None
    payment_link: str | None = None
    cashfree: dict | None = None


async def _process_paid_cashfree_order(db, doc: dict):
    """Apply side-effects for a paid Cashfree order (idempotent)."""
    if doc.get("status") == "succeeded":
        return {"ok": True, "already": True}

    order_id = doc.get("order_id")
    purpose = doc.get("purpose")
    customer_id = doc.get("customer_id")
    amount = float(doc.get("amount") or 0)

    if not order_id or not purpose or not customer_id or amount <= 0:
        await db.cashfree_payments.update_one(
            {"order_id": order_id},
            {"$set": {"status": "failed", "error": "Invalid payment record", "updated_at": datetime.utcnow()}},
        )
        raise HTTPException(status_code=500, detail="Invalid payment record")

    # Claim processing (idempotent).
    claimed = await db.cashfree_payments.update_one(
        {"order_id": order_id, "status": {"$nin": ["processing", "succeeded"]}},
        {"$set": {"status": "processing", "updated_at": datetime.utcnow()}},
    )
    if claimed.matched_count == 0:
        # someone else is processing / already succeeded
        doc2 = await db.cashfree_payments.find_one({"order_id": order_id})
        return {"ok": True, "status": doc2.get("status")}

    try:
        if purpose == "wallet_topup":
            desc = doc.get("description") or "Cashfree wallet top-up"
            txn = await credit_wallet(customer_id, amount, str(desc))
            await db.cashfree_payments.update_one(
                {"order_id": order_id},
                {
                    "$set": {
                        "status": "succeeded",
                        "completed_at": datetime.utcnow(),
                        "wallet_txn": txn,
                        "updated_at": datetime.utcnow(),
                    }
                },
            )
            return {"ok": True, "purpose": purpose, "amount": amount}

        if purpose == "wallet_topup_then_emi":
            loan_id = doc.get("loan_id")
            emi_total_due = float(doc.get("emi_total_due") or 0)
            if not loan_id or emi_total_due <= 0:
                raise HTTPException(status_code=500, detail="Missing loan_id/emi_total_due for hybrid EMI payment")

            topup_txn = await credit_wallet(customer_id, amount, "Cashfree wallet top-up (EMI)")
            emi_res = await pay_emi_any_wallet(str(loan_id), customer_id)

            await db.cashfree_payments.update_one(
                {"order_id": order_id},
                {
                    "$set": {
                        "status": "succeeded",
                        "completed_at": datetime.utcnow(),
                        "wallet_topup_txn": topup_txn,
                        "emi_result": emi_res,
                        "updated_at": datetime.utcnow(),
                    }
                },
            )
            return {
                "ok": True,
                "purpose": purpose,
                "topup_amount": amount,
                "emi_amount": emi_total_due,
            }

        if purpose == "emi":
            loan_id = doc.get("loan_id")
            if not loan_id:
                raise HTTPException(status_code=500, detail="Missing loan_id for EMI payment")
            topup_txn = await credit_wallet(customer_id, amount, "Cashfree wallet top-up (EMI direct)")
            emi_res = await pay_emi_any_wallet(str(loan_id), customer_id)
            await db.cashfree_payments.update_one(
                {"order_id": order_id},
                {
                    "$set": {
                        "status": "succeeded",
                        "completed_at": datetime.utcnow(),
                        "wallet_topup_txn": topup_txn,
                        "emi_result": emi_res,
                        "updated_at": datetime.utcnow(),
                    }
                },
            )
            return {"ok": True, "purpose": purpose, "amount": amount}

        # Fallback: just credit internal account
        await add_money(customer_id, amount)
        await db.cashfree_payments.update_one(
            {"order_id": order_id},
            {"$set": {"status": "succeeded", "completed_at": datetime.utcnow(), "updated_at": datetime.utcnow()}},
        )
        return {"ok": True, "purpose": purpose, "amount": amount}
    except Exception as e:
        await db.cashfree_payments.update_one(
            {"order_id": order_id},
            {"$set": {"status": "failed", "error": str(e), "updated_at": datetime.utcnow()}},
        )
        raise


@router.post("/cashfree/emi/{loan_id}/create", response_model=CreateEmiCashfreeOrderOut)
async def create_cashfree_emi_order(
    loan_id: str, user=Depends(require_roles(Roles.CUSTOMER))
):
    """
    Create a Cashfree order for paying the next EMI (amount includes any penalty on next due installment).

    This does not change existing EMI logic: on successful payment confirmation we will credit the customer's
    internal account by the paid amount and then call the existing `pay_emi_any(...)`.
    """
    db = await get_db()
    customer_id = user.get("customer_id") or user.get("_id")
    if customer_id is None:
        raise HTTPException(status_code=401, detail="Missing customer id in session")

    _, loan = await _find_active_loan_any(db, loan_id, customer_id)
    total_due = await _compute_total_due(db, loan, customer_id)

    # Stable prefix for easier ops/searching.
    order_id = f"{settings.CASHFREE_ORDER_PREFIX}{customer_id}_{uuid4().hex}"

    doc = {
        "gateway": "cashfree",
        "purpose": "emi",
        "order_id": order_id,
        "loan_id": loan_id,
        "loan_numeric_id": loan.get("loan_id"),
        "customer_id": customer_id,
        "amount": total_due,
        "currency": "INR",
        "status": "created",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    await db.cashfree_payments.update_one(
        {"order_id": order_id},
        {"$setOnInsert": doc},
        upsert=True,
    )

    customer_email = user.get("email") or "customer@example.com"
    customer_phone = user.get("phone") or user.get("phone_number") or "9999999999"

    payload = {
        "order_id": order_id,
        "order_amount": total_due,
        "order_currency": "INR",
        "customer_details": {
            "customer_id": str(customer_id),
            "customer_email": customer_email,
            "customer_phone": str(customer_phone),
        },
        "order_meta": {
            "return_url": f"{settings.CASHFREE_RETURN_URL_EMI}?cf_order_id={order_id}",
            "notify_url": settings.CASHFREE_WEBHOOK_URL,
        },
        "order_note": f"EMI payment for loan {loan_id}",
    }

    cf = await cashfree_create_order(payload)
    payment_session_id = cf.get("payment_session_id") if isinstance(cf, dict) else None
    payment_link = _extract_payment_link(cf if isinstance(cf, dict) else None)

    await db.cashfree_payments.update_one(
        {"order_id": order_id},
        {
            "$set": {
                "cashfree_order": cf,
                "payment_session_id": payment_session_id,
                "payment_link": payment_link,
                "updated_at": datetime.utcnow(),
            }
        },
    )

    return CreateEmiCashfreeOrderOut(
        order_id=order_id,
        order_amount=total_due,
        order_currency="INR",
        payment_session_id=payment_session_id,
        payment_link=payment_link,
        cashfree=cf,
    )

class HybridStartIn(BaseModel):
    mpin: str


@router.post("/cashfree/emi/{loan_id}/hybrid/start")
async def start_hybrid_emi_payment(loan_id: str, payload: HybridStartIn, user=Depends(require_roles(Roles.CUSTOMER))):
    """
    Hybrid EMI flow:
    - If wallet has enough balance -> pay EMI from wallet immediately.
    - Else -> create a Cashfree wallet top-up order for the shortfall and after payment success
      the webhook/confirm will auto-pay EMI from wallet.
    """
    db = await get_db()
    customer_id = user.get("customer_id") or user.get("_id")
    if customer_id is None:
        raise HTTPException(status_code=401, detail="Missing customer id in session")

    await verify_mpin(customer_id, payload.mpin)

    _, loan = await _find_active_loan_any(db, loan_id, customer_id)
    total_due = await _compute_total_due(db, loan, customer_id)

    wallet = await get_wallet_balance(customer_id)
    wallet_balance = float(wallet.get("balance") or 0)

    if wallet_balance >= total_due:
        res = await pay_emi_any_wallet(str(loan_id), customer_id)
        return {"paid": True, "mode": "wallet", "amount": total_due, "result": res}

    shortfall = float(round(max(0.0, total_due - wallet_balance), 2))
    if shortfall <= 0:
        res = await pay_emi_any_wallet(str(loan_id), customer_id)
        return {"paid": True, "mode": "wallet", "amount": total_due, "result": res}

    order_id = f"{settings.CASHFREE_ORDER_PREFIX}{customer_id}_{uuid4().hex}"
    doc = {
        "gateway": "cashfree",
        "purpose": "wallet_topup_then_emi",
        "order_id": order_id,
        "loan_id": str(loan_id),
        "loan_numeric_id": loan.get("loan_id"),
        "customer_id": customer_id,
        "amount": shortfall,
        "emi_total_due": total_due,
        "currency": "INR",
        "status": "created",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    await db.cashfree_payments.update_one(
        {"order_id": order_id},
        {"$setOnInsert": doc},
        upsert=True,
    )

    customer_email = user.get("email") or "customer@example.com"
    customer_phone = user.get("phone") or user.get("phone_number") or "9999999999"

    cf_payload = {
        "order_id": order_id,
        "order_amount": shortfall,
        "order_currency": "INR",
        "customer_details": {
            "customer_id": str(customer_id),
            "customer_email": customer_email,
            "customer_phone": str(customer_phone),
        },
        "order_meta": {
            "return_url": f"{settings.CASHFREE_RETURN_URL_EMI}?cf_order_id={order_id}",
            "notify_url": settings.CASHFREE_WEBHOOK_URL,
        },
        "order_note": f"Wallet top-up for EMI payment (loan {loan_id})",
    }

    cf = await cashfree_create_order(cf_payload)
    payment_session_id = cf.get("payment_session_id") if isinstance(cf, dict) else None
    payment_link = _extract_payment_link(cf if isinstance(cf, dict) else None)

    await db.cashfree_payments.update_one(
        {"order_id": order_id},
        {
            "$set": {
                "cashfree_order": cf,
                "payment_session_id": payment_session_id,
                "payment_link": payment_link,
                "updated_at": datetime.utcnow(),
            }
        },
    )

    return {
        "paid": False,
        "mode": "cashfree_topup_then_wallet_emi",
        "order_id": order_id,
        "topup_amount": shortfall,
        "emi_amount": total_due,
        "payment_session_id": payment_session_id,
        "payment_link": payment_link,
        "cashfree": cf,
    }


@router.post("/cashfree/wallet/topup/create", response_model=CreateWalletTopupCashfreeOut)
async def create_cashfree_wallet_topup_order(
    payload: CreateWalletTopupCashfreeIn, user=Depends(require_roles(Roles.CUSTOMER))
):
    db = await get_db()
    customer_id = user.get("customer_id") or user.get("_id")
    if customer_id is None:
        raise HTTPException(status_code=401, detail="Missing customer id in session")

    amt = float(payload.amount or 0)
    if amt <= 0:
        raise HTTPException(status_code=400, detail="amount must be > 0")

    # Keep M-PIN optional for wallet top-up. Debit/EMI paths still enforce verification.
    if payload.mpin:
        await verify_mpin(customer_id, payload.mpin)

    order_id = f"{settings.CASHFREE_ORDER_PREFIX}{customer_id}_{uuid4().hex}"
    doc = {
        "gateway": "cashfree",
        "purpose": "wallet_topup",
        "order_id": order_id,
        "customer_id": customer_id,
        "amount": amt,
        "currency": "INR",
        "description": payload.description or "Cashfree wallet top-up",
        "status": "created",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    await db.cashfree_payments.update_one(
        {"order_id": order_id},
        {"$setOnInsert": doc},
        upsert=True,
    )

    customer_email = user.get("email") or "customer@example.com"
    customer_phone = user.get("phone") or user.get("phone_number") or "9999999999"

    cf_payload = {
        "order_id": order_id,
        "order_amount": amt,
        "order_currency": "INR",
        "customer_details": {
            "customer_id": str(customer_id),
            "customer_email": customer_email,
            "customer_phone": str(customer_phone),
        },
        "order_meta": {
            "return_url": f"{settings.CASHFREE_RETURN_URL_WALLET}?cf_order_id={order_id}",
            "notify_url": settings.CASHFREE_WEBHOOK_URL,
        },
        "order_note": "Wallet top-up",
    }

    cf = await cashfree_create_order(cf_payload)
    payment_session_id = cf.get("payment_session_id") if isinstance(cf, dict) else None
    payment_link = _extract_payment_link(cf if isinstance(cf, dict) else None)

    await db.cashfree_payments.update_one(
        {"order_id": order_id},
        {
            "$set": {
                "cashfree_order": cf,
                "payment_session_id": payment_session_id,
                "payment_link": payment_link,
                "updated_at": datetime.utcnow(),
            }
        },
    )

    return CreateWalletTopupCashfreeOut(
        order_id=order_id,
        order_amount=amt,
        order_currency="INR",
        payment_session_id=payment_session_id,
        payment_link=payment_link,
        cashfree=cf,
    )


@router.get("/cashfree/orders/{order_id}")
async def get_cashfree_order_status(order_id: str, user=Depends(require_roles(Roles.CUSTOMER))):
    db = await get_db()
    customer_id = user.get("customer_id") or user.get("_id")
    doc = await db.cashfree_payments.find_one({"order_id": order_id, "customer_id": customer_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")
    return {
        "order_id": order_id,
        "purpose": doc.get("purpose"),
        "status": doc.get("status"),
        "order_status": doc.get("order_status"),
        "amount": doc.get("amount"),
        "updated_at": doc.get("updated_at"),
    }


@router.post("/cashfree/orders/{order_id}/confirm")
async def confirm_cashfree_order(order_id: str, user=Depends(require_roles(Roles.CUSTOMER))):
    """
    Confirm order status directly with Cashfree (useful in local dev where webhooks can't reach your machine).
    If paid, applies the corresponding business logic (wallet top-up / emi / etc).
    """
    db = await get_db()
    customer_id = user.get("customer_id") or user.get("_id")
    doc = await db.cashfree_payments.find_one({"order_id": order_id, "customer_id": customer_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")

    cf_order = await cashfree_get_order(order_id)
    order_status = (cf_order.get("order_status") or cf_order.get("orderStatus") or "").upper()
    is_paid = order_status in {"PAID", "SUCCESS", "COMPLETED"}

    await db.cashfree_payments.update_one(
        {"order_id": order_id},
        {"$set": {"cashfree_order_latest": cf_order, "order_status": order_status, "updated_at": datetime.utcnow()}},
    )

    if not is_paid:
        return {"ok": True, "paid": False, "order_status": order_status}

    res = await _process_paid_cashfree_order(db, doc)
    return {"ok": True, "paid": True, "order_status": order_status, **(res or {})}


@router.post("/cashfree/webhook")
async def cashfree_webhook(request: Request):
    db = await get_db()
    try:
        payload = await request.json()
    except JSONDecodeError:
        raw_body = await request.body()
        if not raw_body or not raw_body.strip():
            raise HTTPException(status_code=400, detail="Empty webhook payload")
        raise HTTPException(status_code=400, detail="Invalid webhook payload: expected JSON")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid webhook payload: expected JSON object")

    order_id = _extract_order_id(payload)
    if not order_id:
        raise HTTPException(status_code=400, detail="Missing order_id in webhook payload")

    doc = await db.cashfree_payments.find_one({"order_id": order_id})
    if not doc:
        # Accept webhook even if order was not created through our API.
        await db.cashfree_payments.insert_one(
            {
                "gateway": "cashfree",
                "purpose": "unknown",
                "order_id": order_id,
                "status": "webhook_received",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "webhook_payload": payload,
            }
        )
        doc = await db.cashfree_payments.find_one({"order_id": order_id})

    if doc.get("status") == "succeeded":
        return {"ok": True}

    await db.cashfree_payments.update_one(
        {"order_id": order_id},
        {"$set": {"status": "webhook_received", "webhook_payload": payload, "updated_at": datetime.utcnow()}},
    )

    cf_order = await cashfree_get_order(order_id)
    order_status = (cf_order.get("order_status") or cf_order.get("orderStatus") or "").upper()
    is_paid = order_status in {"PAID", "SUCCESS", "COMPLETED"}

    await db.cashfree_payments.update_one(
        {"order_id": order_id},
        {"$set": {"cashfree_order_latest": cf_order, "order_status": order_status, "updated_at": datetime.utcnow()}},
    )

    if not is_paid:
        return {"ok": True, "paid": False, "order_status": order_status}

    await _process_paid_cashfree_order(db, doc)
    return {"ok": True, "paid": True}



class MockVerifyIn(BaseModel):
    amount: float
    order_id: str

@router.post("/verify")
async def mock_verify_payment(
    payload: MockVerifyIn,
    user=Depends(require_roles(Roles.CUSTOMER)),
):
    db = await get_db()
    customer_id = user.get("customer_id") or user.get("_id")
    if customer_id is None:
        raise HTTPException(status_code=401, detail="Missing customer id in session")
    amt = float(payload.amount or 0)
    if amt <= 0:
        raise HTTPException(status_code=400, detail="amount must be > 0")
    txn = await credit_wallet(customer_id, amt, f"Mock payment - order {payload.order_id}")
    await db.cashfree_payments.update_one(
        {"order_id": payload.order_id, "customer_id": customer_id},
        {"$set": {"status": "succeeded", "order_status": "PAID",
                  "completed_at": datetime.utcnow(), "wallet_txn": txn,
                  "updated_at": datetime.utcnow()}},
    )
    return {"ok": True, "paid": True, "order_id": payload.order_id,
            "amount": amt, "wallet_txn": txn, "mock": True}
