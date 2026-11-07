"""Payment orchestration and Daraja callback verification."""

import hashlib
from typing import Any

from app.core.config import settings
from app.models.escrow import CustodyStatus
from app.models.order import OrderStatus, PaymentStatus
from app.models.payment import PaymentRecordStatus
from app.models.transaction import LedgerEventType
from app.repositories.escrow_repository import EscrowRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.payment_repository import PaymentConflictError, PaymentRepository
from app.repositories.transaction_repository import TransactionLedgerRepository
from app.schemas.payment import PaymentInitiateRequest
from app.services.escrow_providers import EscrowProvider, EscrowProviderError
from app.services.payment_providers import PaymentProvider, PaymentProviderError


class PaymentAccessError(Exception):
    """The caller does not own the order/payment."""


class PaymentStateError(Exception):
    """Order/payment state is not eligible for the operation."""


class PaymentVerificationError(Exception):
    """A callback could not be matched or verified."""


class PaymentConfigurationError(Exception):
    """Payment provider configuration is missing or incomplete."""


def _event_key(event_type: str, payment_id: str, suffix: str = "") -> str:
    return f"{event_type}:{payment_id}:{suffix}"[:180]


def _append_ledger(
    ledger: TransactionLedgerRepository,
    *,
    order_id: str,
    payment_id: str,
    event_type: LedgerEventType,
    amount_kes: int,
    provider_reference: str | None,
    status: str,
    suffix: str = "",
) -> None:
    ledger.append({
        "event_key": _event_key(event_type.value, payment_id, suffix),
        "order_id": order_id,
        "payment_id": payment_id,
        "event_type": event_type.value,
        "amount_kes": amount_kes,
        "provider_reference": provider_reference,
        "status": status,
    })


def initiate_payment(
    *,
    orders: OrderRepository,
    payments: PaymentRepository,
    ledger: TransactionLedgerRepository,
    provider: PaymentProvider,
    buyer_id: str,
    payload: PaymentInitiateRequest,
    idempotency_key: str,
) -> dict:
    order = orders.get(payload.order_id)
    if order is None or order["buyer_id"] != buyer_id:
        raise PaymentAccessError
    if order["order_status"] != OrderStatus.AWAITING_PAYMENT.value or order["payment_status"] != PaymentStatus.UNPAID.value:
        raise PaymentStateError
    if order.get("payment_id"):
        existing = payments.get(order["payment_id"])
        if existing and existing["status"] in {"PENDING", "INITIATING", "INITIATED"}:
            return existing
        if existing and existing["status"] in {"SUCCEEDED", "SUCCEEDED_REVIEW"}:
            raise PaymentStateError
    if len(idempotency_key) < 8 or len(idempotency_key) > 128:
        raise PaymentConfigurationError("Idempotency-Key must contain 8 to 128 characters")
    values = {
        "order_id": payload.order_id,
        "buyer_id": buyer_id,
        "provider": provider.name,
        "amount_kes": order["total_amount_kes"],
        "phone_number": payload.phone_number,
        "merchant_reference": f"ORD-{payload.order_id[-10:]}",
        "idempotency_key": idempotency_key,
    }
    payment = payments.create_pending(values)
    if payment["status"] in {"INITIATING", "INITIATED", "SUCCEEDED", "SUCCEEDED_REVIEW"}:
        return payment
    claimed = payments.claim_initiation(payment["id"])
    if claimed is None:
        current = payments.get(payment["id"])
        if current is not None:
            return current
        raise PaymentStateError
    try:
        result = provider.initiate_stk_push(
            amount_kes=order["total_amount_kes"],
            phone_number=payload.phone_number,
            account_reference=payment["merchant_reference"],
            description=f"Order {payment['merchant_reference']}",
        )
    except PaymentProviderError:
        payments.set_initiation_failed(payment["id"], "Payment provider request failed; check provider configuration and logs.")
        raise PaymentConfigurationError("Payment provider could not initiate the request") from None
    initiated = payments.set_initiated(payment["id"], result.merchant_request_id, result.checkout_request_id)
    if initiated is None:
        # A very fast callback can complete while the STK Push request is returning.
        current = payments.get(payment["id"])
        if current is not None:
            return current
        raise PaymentStateError
    return initiated


def _callback_metadata(callback: dict[str, Any]) -> dict[str, Any]:
    metadata = callback.get("CallbackMetadata") or {}
    items = metadata.get("Item") or []
    result = {}
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("Name"), str):
            result[item["Name"]] = item.get("Value")
    return result


def _query_confirms_result(result: dict[str, Any], checkout_id: str, result_code: int) -> bool:
    return (
        str(result.get("CheckoutRequestID", "")) == checkout_id
        and str(result.get("ResponseCode", "")) == "0"
        and str(result.get("ResultCode", "")) == str(result_code)
    )


def _mark_order_paid(orders: OrderRepository, payment: dict) -> None:
    updated = orders.mark_paid(payment["order_id"], payment["id"])
    if updated is None:
        order = orders.get(payment["order_id"])
        if not order or order.get("payment_id") != payment["id"] or order["payment_status"] != "PAID":
            raise PaymentStateError


def _create_internal_escrow(
    *,
    escrow_repo: EscrowRepository,
    ledger: TransactionLedgerRepository,
    provider: EscrowProvider,
    order: dict,
    payment: dict,
) -> dict:
    existing = escrow_repo.get_by_order(order["id"])
    if existing:
        return existing
    commission = (payment["amount_kes"] * settings.platform_commission_bps) // 10000
    try:
        safeguard = provider.confirm_safeguarding(
            payment_reference=payment.get("provider_receipt") or payment.get("checkout_request_id") or payment["id"],
            amount_kes=payment["amount_kes"],
        )
    except EscrowProviderError:
        # Payment receipt is real; custody is not asserted unless partner confirmation exists.
        from app.services.escrow_providers import SafeguardResult

        safeguard = SafeguardResult(False, None, "Safeguarded-funds partner confirmation unavailable")
    custody_status = CustodyStatus.PROVIDER_SAFEGUARDED.value if safeguard.provider_safeguarded else CustodyStatus.NOT_SAFEGUARDED.value
    escrow = escrow_repo.create_for_payment({
        "order_id": order["id"],
        "payment_id": payment["id"],
        "provider": provider.name,
        "amount_kes": payment["amount_kes"],
        "commission_kes": commission,
        "seller_amount_kes": payment["amount_kes"] - commission,
        "provider_reference": safeguard.provider_reference,
        "custody_status": custody_status,
        "actual_funds_safeguarded": safeguard.provider_safeguarded,
    })
    if safeguard.provider_safeguarded:
        _append_ledger(ledger, order_id=order["id"], payment_id=payment["id"], event_type=LedgerEventType.PROVIDER_SAFEGUARD_CONFIRMED, amount_kes=payment["amount_kes"], provider_reference=safeguard.provider_reference, status="CONFIRMED")
    return escrow


def process_daraja_callback(
    *,
    callback: dict,
    payments: PaymentRepository,
    orders: OrderRepository,
    ledger: TransactionLedgerRepository,
    escrow_repo: EscrowRepository,
    escrow_provider: EscrowProvider,
    provider: PaymentProvider,
) -> dict:
    try:
        stk = callback["Body"]["stkCallback"]
        checkout_id = str(stk["CheckoutRequestID"])
        result_code = int(stk["ResultCode"])
    except (KeyError, TypeError, ValueError):
        raise PaymentVerificationError("Malformed Daraja callback") from None

    payment = payments.get_by_checkout(checkout_id)
    if payment is None or payment["provider"] != "daraja":
        raise PaymentVerificationError("Callback does not match a Daraja payment")
    order = orders.get(payment["order_id"])
    if order is None:
        raise PaymentVerificationError("Order for callback was not found")
    metadata = _callback_metadata(stk)
    if result_code != 0:
        try:
            query_result = provider.query_stk_status(checkout_id)
        except PaymentProviderError:
            raise PaymentVerificationError("Daraja transaction status could not be verified yet") from None
        if not _query_confirms_result(query_result, checkout_id, result_code):
            raise PaymentVerificationError("Daraja STK Push Query did not confirm the callback result")
        updated = payments.complete_callback(
            payment["id"], status=PaymentRecordStatus.FAILED, receipt=None,
            callback_amount=int(metadata.get("Amount", 0) or 0),
            callback_phone=str(metadata.get("PhoneNumber", "")) or None,
            failure_reason="Daraja reported an unsuccessful STK transaction",
        )
        _append_ledger(ledger, order_id=order["id"], payment_id=payment["id"], event_type=LedgerEventType.PAYMENT_FAILED, amount_kes=payment["amount_kes"], provider_reference=checkout_id, status="FAILED")
        return {"accepted": True, "result_code": 0, "result_description": "Failure callback recorded", "payment": updated}

    try:
        callback_amount = int(metadata["Amount"])
        callback_phone = str(int(metadata["PhoneNumber"]))
        receipt = str(metadata["MpesaReceiptNumber"])
    except (KeyError, TypeError, ValueError):
        raise PaymentVerificationError("Successful callback is missing amount, phone number, or receipt") from None
    if callback_amount != order["total_amount_kes"] or callback_amount != payment["amount_kes"]:
        raise PaymentVerificationError("Callback amount does not match the order")
    if callback_phone != payment["phone_number"]:
        raise PaymentVerificationError("Callback phone number does not match the payment request")
    if len(receipt) < 5 or len(receipt) > 32:
        raise PaymentVerificationError("Callback receipt reference is invalid")

    try:
        query_result = provider.query_stk_status(checkout_id)
    except PaymentProviderError:
        raise PaymentVerificationError("Daraja transaction status could not be verified yet") from None
    if not _query_confirms_result(query_result, checkout_id, 0):
        raise PaymentVerificationError("Daraja STK Push Query did not confirm a successful transaction")

    updated = payments.complete_callback(
        payment["id"], status=PaymentRecordStatus.SUCCEEDED, receipt=receipt,
        callback_amount=callback_amount, callback_phone=callback_phone,
    )
    _mark_order_paid(orders, updated)
    _append_ledger(ledger, order_id=order["id"], payment_id=payment["id"], event_type=LedgerEventType.PAYMENT_RECEIVED, amount_kes=callback_amount, provider_reference=receipt, status="CONFIRMED")
    paid_order = orders.get(order["id"])
    escrow = _create_internal_escrow(escrow_repo=escrow_repo, ledger=ledger, provider=escrow_provider, order=paid_order, payment=updated)
    return {"accepted": True, "result_code": 0, "result_description": "Payment verified", "payment": updated, "escrow": escrow}


def process_mock_callback(
    *, payment_id: str, buyer_id: str, success: bool, amount_kes: int | None,
    payments: PaymentRepository, orders: OrderRepository,
    ledger: TransactionLedgerRepository, escrow_repo: EscrowRepository,
    escrow_provider: EscrowProvider,
) -> dict:
    payment = payments.get(payment_id)
    if payment is None or payment["buyer_id"] != buyer_id:
        raise PaymentAccessError
    if payment["provider"] != "mock":
        raise PaymentStateError
    order = orders.get(payment["order_id"])
    if order is None:
        raise PaymentStateError
    reported_amount = amount_kes if amount_kes is not None else payment["amount_kes"]
    if success and reported_amount != payment["amount_kes"]:
        raise PaymentVerificationError("Simulated callback amount does not match expected amount")
    if not success:
        updated = payments.complete_callback(payment["id"], status=PaymentRecordStatus.FAILED, receipt=None, callback_amount=reported_amount, callback_phone=payment["phone_number"], failure_reason="Mock payment marked failed by development simulation")
        _append_ledger(ledger, order_id=order["id"], payment_id=payment["id"], event_type=LedgerEventType.PAYMENT_FAILED, amount_kes=payment["amount_kes"], provider_reference=payment["checkout_request_id"], status="MOCK_FAILED")
        return {"payment": updated, "escrow": None, "simulated": True}
    receipt = "MOCK-" + hashlib.sha256(payment["checkout_request_id"].encode()).hexdigest()[:12].upper()
    updated = payments.complete_callback(payment["id"], status=PaymentRecordStatus.SUCCEEDED, receipt=receipt, callback_amount=reported_amount, callback_phone=payment["phone_number"])
    _mark_order_paid(orders, updated)
    _append_ledger(ledger, order_id=order["id"], payment_id=payment["id"], event_type=LedgerEventType.PAYMENT_RECEIVED, amount_kes=payment["amount_kes"], provider_reference=receipt, status="MOCK_SIMULATED")
    paid_order = orders.get(order["id"])
    escrow = _create_internal_escrow(escrow_repo=escrow_repo, ledger=ledger, provider=escrow_provider, order=paid_order, payment=updated)
    return {"payment": updated, "escrow": escrow, "simulated": True}


def list_payment_history(payments: PaymentRepository, user_id: str, *, skip: int, limit: int):
    return payments.list_for_buyer(user_id, skip=skip, limit=limit)
