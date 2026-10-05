"""Split payment API - prototype under test.

Feature: a single order total is paid with 2-4 instruments (cards and
wallets) in one request. The design decisions visible here are the ones the
test strategy targets:

* amounts use Decimal and are validated to the cent (risk R2)
* every request carries an Idempotency-Key (risk R1)
* a failed split compensates the already captured splits (risk R3)
* the feature sits behind SPLIT_PAYMENT_ENABLED so it can be switched off
  without a deployment (rollback evidence)
"""
import os
import uuid
from decimal import Decimal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import psp as psp_module
from app.money import AmountError, parse_amount, validate_split_plan
from app.psp import (
    CompensationFailed,
    InsufficientFunds,
    MockPSP,
    ProviderDeclined,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.store import Conflict, Store

app = FastAPI(title="Split Payment API", version="1.0.0")

store = Store()
provider = MockPSP()

PROVIDER_ERRORS = (
    ProviderDeclined,
    ProviderTimeout,
    ProviderUnavailable,
    InsufficientFunds,
)


def reset_state() -> None:
    """Test hook: clear all state between test cases."""
    global provider
    store.reset()
    provider = MockPSP()


def feature_enabled() -> bool:
    return os.getenv("SPLIT_PAYMENT_ENABLED", "true").lower() == "true"


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"code": code, "message": message})


def owner_of(split: dict) -> str | None:
    if split.get("instrument") == "card":
        return psp_module.CARD_TOKENS.get(split.get("token"))
    wallet = provider.wallets.get(split.get("wallet_id"))
    return wallet["owner"] if wallet else None


@app.get("/healthz")
def healthz():
    return {"status": "ok", "split_payment_enabled": feature_enabled()}


@app.get("/v1/payments/{payment_id}")
def get_payment(payment_id: str):
    payment = store.payments.get(payment_id)
    if payment is None:
        return error(404, "NOT_FOUND", "payment not found")
    return payment


@app.get("/v1/orders/{order_id}/captures")
def get_captures(order_id: str):
    """Audit endpoint - the evidence source for double-charge assertions."""
    active = store.active_captures(order_id)
    return {
        "order_id": order_id,
        "count": len(active),
        "total": str(store.captured_total(order_id)),
        "captures": [
            {k: str(v) if isinstance(v, Decimal) else v for k, v in c.items()}
            for c in active
        ],
    }


@app.get("/v1/ops/manual-queue")
def get_manual_queue():
    return {"count": len(store.manual_queue), "items": store.manual_queue,
            "alerts": store.alerts}


@app.post("/v1/payments/split")
async def create_split_payment(request: Request):
    if not feature_enabled():
        return error(404, "FEATURE_DISABLED", "split payment is not enabled")

    user_id = request.headers.get("X-User-Id")
    if not user_id:
        return error(401, "UNAUTHENTICATED", "X-User-Id header is required")

    key = request.headers.get("Idempotency-Key")
    if not key:
        return error(400, "IDEMPOTENCY_KEY_REQUIRED",
                     "Idempotency-Key header is required")

    try:
        body = await request.json()
    except Exception:
        return error(400, "VALIDATION_ERROR", "request body is not valid JSON")

    order_id = body.get("order_id")
    splits = body.get("splits")
    if not order_id or not isinstance(splits, list):
        return error(400, "VALIDATION_ERROR", "order_id and splits are required")

    # --- amount validation (nothing is charged before this passes) ----
    try:
        total = parse_amount(body.get("total"))
        amounts = [parse_amount(s.get("amount")) for s in splits]
        validate_split_plan(total, amounts)
    except AmountError as exc:
        return error(400, exc.code, exc.message)

    # --- authorisation: every instrument must belong to the caller ----
    for split in splits:
        if owner_of(split) != user_id:
            return error(403, "FORBIDDEN_INSTRUMENT",
                         "an instrument in this request does not belong to the caller")

    # --- idempotency gate ---------------------------------------------
    try:
        replay = store.begin(key, body)
    except Conflict as exc:
        return error(409, exc.code, exc.message)
    if replay is not None:
        return JSONResponse(status_code=200, content=replay)

    payment_id = f"pay_{uuid.uuid4().hex[:12]}"
    captured: list[tuple[str, dict, Decimal]] = []

    try:
        for index, (split, amount) in enumerate(zip(splits, amounts)):
            ref = f"{payment_id}_{index}"
            if split["instrument"] == "card":
                capture_id = provider.capture_card(split["token"], amount, ref)
                reference = split["token"]
            else:
                capture_id = provider.capture_wallet(split["wallet_id"], amount, ref)
                reference = split["wallet_id"]
            store.add_capture(order_id, payment_id, split["instrument"],
                              reference, amount, capture_id)
            captured.append((capture_id, split, amount))
    except PROVIDER_ERRORS as exc:
        compensation = compensate(captured, order_id, payment_id, exc.code)
        response = {
            "payment_id": payment_id,
            "order_id": order_id,
            "status": "FAILED",
            "code": exc.code,
            "message": str(exc),
            "compensation": compensation,
        }
        store.save_payment(response)
        store.complete(key, response)
        return JSONResponse(status_code=402, content=response)

    response = {
        "payment_id": payment_id,
        "order_id": order_id,
        "status": "PAID",
        "total": str(total),
        "splits": [
            {"instrument": s["instrument"], "amount": str(a), "capture_id": c}
            for c, s, a in captured
        ],
    }
    store.save_payment(response)
    store.complete(key, response)
    return JSONResponse(status_code=201, content=response)


def compensate(captured, order_id: str, payment_id: str, cause: str) -> str:
    """Reverse already captured splits. Never fails silently."""
    failures = []
    for capture_id, split, amount in captured:
        try:
            if split["instrument"] == "card":
                provider.void_card(capture_id, split["token"])
            else:
                provider.void_wallet(capture_id, split["wallet_id"], amount)
            store.mark_voided(capture_id)
        except CompensationFailed as exc:
            failures.append(capture_id)
            store.enqueue_manual(
                {"order_id": order_id, "payment_id": payment_id,
                 "capture_id": capture_id, "amount": str(amount), "cause": cause},
                f"COMPENSATION_FAILED order={order_id} capture={capture_id}: {exc}",
            )
    return "COMPLETED" if not failures else "MANUAL_INTERVENTION_REQUIRED"
