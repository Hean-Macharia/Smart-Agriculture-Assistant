from app.models.escrow import EscrowStatus
from app.models.order import OrderStatus
from app.models.transaction import LedgerEventType
from app.repositories.escrow_repository import EscrowRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.transaction_repository import TransactionLedgerRepository
from app.services.escrow_providers import EscrowProvider, EscrowProviderError


class EscrowAccessError(Exception):
    """Caller does not own the escrow-related order."""


class EscrowStateError(Exception):
    """Escrow release/refund conditions are not met."""


def _ledger(ledger, escrow, event_type, amount, reference, status, suffix=""):
    ledger.append({
        "event_key": f"{event_type}:{escrow['id']}:{suffix}"[:180],
        "order_id": escrow["order_id"],
        "payment_id": escrow["payment_id"],
        "event_type": event_type,
        "amount_kes": amount,
        "provider_reference": reference,
        "status": status,
    })


def request_seller_release(
    *, escrow_id: str, seller_id: str, escrows: EscrowRepository,
    orders: OrderRepository, ledger: TransactionLedgerRepository, provider: EscrowProvider,
    is_admin: bool = False,
) -> tuple[dict, str]:
    escrow = escrows.get(escrow_id)
    if escrow is None:
        raise EscrowAccessError
    order = orders.get(escrow["order_id"])
    if order is None or not is_admin and order["seller_id"] != seller_id:
        raise EscrowAccessError
    if escrows.has_unresolved_dispute(order["id"]):
        raise EscrowStateError("Payment cannot be released while a dispute is unresolved")
    if order["order_status"] != OrderStatus.COMPLETED.value:
        raise EscrowStateError("Buyer delivery confirmation is required before release")
    if escrow["status"] == EscrowStatus.SIMULATED_SETTLEMENT.value:
        return escrow, "Mock release was already simulated; no funds were transferred."
    if escrow["status"] == EscrowStatus.SETTLED.value:
        return escrow, "Provider already confirmed seller settlement."
    if escrow["status"] not in {
        EscrowStatus.PAYMENT_RECEIVED.value,
        EscrowStatus.RELEASE_REQUESTED.value,
        EscrowStatus.SETTLEMENT_FAILED.value,
    }:
        raise EscrowStateError("Escrow is not eligible for release")
    if provider.name != "mock" and not escrow["actual_funds_safeguarded"]:
        raise EscrowStateError("Funds are not confirmed as safeguarded by an authorised provider")

    release_requested = escrows.transition(
        escrow_id,
        [EscrowStatus.PAYMENT_RECEIVED.value, EscrowStatus.RELEASE_REQUESTED.value, EscrowStatus.SETTLEMENT_FAILED.value],
        EscrowStatus.RELEASE_REQUESTED.value,
    )
    if release_requested is None:
        current = escrows.get(escrow_id)
        if current and current["status"] == EscrowStatus.SIMULATED_SETTLEMENT.value:
            return current, "MOCK settlement was already simulated; no funds were transferred."
        if current and current["status"] == EscrowStatus.SETTLED.value:
            return current, "Provider already confirmed seller settlement."
        raise EscrowStateError("Escrow release is already being processed")
    _ledger(ledger, release_requested, LedgerEventType.RELEASE_REQUESTED.value, escrow["seller_amount_kes"], None, "REQUESTED")

    try:
        result = provider.release(
            idempotency_key=f"escrow:{escrow_id}:release",
            seller_amount_kes=escrow["seller_amount_kes"],
        )
    except EscrowProviderError:
        failed = escrows.transition(
            escrow_id,
            [EscrowStatus.RELEASE_REQUESTED.value],
            EscrowStatus.SETTLEMENT_FAILED.value,
        ) or escrows.get(escrow_id)
        _ledger(ledger, failed, LedgerEventType.SELLER_PAYOUT_FAILED.value, escrow["seller_amount_kes"], None, "FAILED", failed["updated_at"].isoformat())
        raise
    if result.simulated_settlement:
        updated = escrows.transition(
            escrow_id, [EscrowStatus.RELEASE_REQUESTED.value], EscrowStatus.SIMULATED_SETTLEMENT.value,
            {"last_action_reference": result.provider_reference},
        ) or escrows.get(escrow_id)
        _ledger(ledger, updated, LedgerEventType.MOCK_SETTLEMENT_SIMULATED.value, escrow["seller_amount_kes"], result.provider_reference, "SIMULATED")
        return updated, "Mock release simulated only. No real money was transferred or safeguarded."
    if result.provider_settled:
        updated = escrows.transition(
            escrow_id, [EscrowStatus.RELEASE_REQUESTED.value], EscrowStatus.SETTLED.value,
            {"provider_reference": result.provider_reference},
        ) or escrows.get(escrow_id)
        _ledger(ledger, updated, LedgerEventType.SELLER_PAYOUT_CONFIRMED.value, escrow["seller_amount_kes"], result.provider_reference, "CONFIRMED")
        if escrow["commission_kes"]:
            _ledger(ledger, updated, LedgerEventType.PLATFORM_COMMISSION_RECORDED.value, escrow["commission_kes"], result.provider_reference, "CONFIRMED")
        return updated, "Provider confirmed seller settlement."
    failed = escrows.transition(
        escrow_id,
        [EscrowStatus.RELEASE_REQUESTED.value],
        EscrowStatus.SETTLEMENT_FAILED.value,
    ) or escrows.get(escrow_id)
    _ledger(ledger, failed, LedgerEventType.SELLER_PAYOUT_FAILED.value, escrow["seller_amount_kes"], result.provider_reference, "FAILED", failed["updated_at"].isoformat())
    raise EscrowProviderError("Provider has not confirmed settlement")


def request_buyer_refund(
    *, escrow_id: str, buyer_id: str, reason: str, escrows: EscrowRepository,
    orders: OrderRepository, ledger: TransactionLedgerRepository, provider: EscrowProvider,
) -> tuple[dict, str]:
    escrow = escrows.get(escrow_id)
    if escrow is None:
        raise EscrowAccessError
    order = orders.get(escrow["order_id"])
    if order is None or order["buyer_id"] != buyer_id:
        raise EscrowAccessError
    if order["order_status"] == OrderStatus.COMPLETED.value or escrow["status"] in {EscrowStatus.SETTLED.value, EscrowStatus.SIMULATED_SETTLEMENT.value}:
        raise EscrowStateError("Refund is unavailable after seller settlement")
    if escrow["status"] == EscrowStatus.REFUND_REQUESTED.value:
        return escrow, "Refund request was already recorded."
    updated = escrows.transition(
        escrow_id,
        [EscrowStatus.PAYMENT_RECEIVED.value, EscrowStatus.RELEASE_REQUESTED.value],
        EscrowStatus.REFUND_REQUESTED.value,
        {"refund_reason": reason},
    )
    if updated is None:
        raise EscrowStateError("Escrow is not eligible for a refund request")
    _ledger(ledger, updated, LedgerEventType.REFUND_REQUESTED.value, escrow["amount_kes"], None, "REQUESTED")
    if provider.name == "mock":
        return updated, "Refund request recorded for development simulation; no real refund was initiated."
    try:
        result = provider.request_refund(idempotency_key=f"escrow:{escrow_id}:refund", amount_kes=escrow["amount_kes"])
    except EscrowProviderError:
        raise
    if result.provider_settled:
        _ledger(ledger, updated, LedgerEventType.REFUND_CONFIRMED.value, escrow["amount_kes"], result.provider_reference, "CONFIRMED")
        return updated, "Provider confirmed refund."
    return updated, "Refund request submitted to provider; settlement is not yet confirmed."
