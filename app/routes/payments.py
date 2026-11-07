from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, status

from app.core.config import settings
from app.core.dependencies import (
    escrow_provider,
    get_current_user,
    get_escrow_repository,
    get_ledger_repository,
    get_order_repository,
    get_payment_repository,
    payment_provider,
    require_roles,
)
from app.models.user import UserRole
from app.repositories.escrow_repository import EscrowRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.payment_repository import PaymentConflictError, PaymentRepository
from app.repositories.transaction_repository import TransactionLedgerRepository
from app.schemas.payment import MockCallbackSimulation, PaymentInitiateRequest, PaymentListResponse, PaymentPublic
from app.schemas.user import UserPublic
from app.services.escrow_providers import EscrowProvider
from app.services.payment_providers import PaymentProvider, PaymentProviderError
from app.services.payment_service import (
    PaymentAccessError,
    PaymentConfigurationError,
    PaymentStateError,
    PaymentVerificationError,
    initiate_payment,
    list_payment_history,
    process_daraja_callback,
    process_mock_callback,
)

router = APIRouter(prefix="/payments", tags=["Payments"])
PaymentId = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Payment not found")


@router.post("/initiate", response_model=PaymentPublic, status_code=status.HTTP_201_CREATED, summary="Initiate a payment for my unpaid order")
def post_initiate_payment(
    payload: PaymentInitiateRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
    user: UserPublic = Depends(require_roles(UserRole.BUYER)),
    orders: OrderRepository = Depends(get_order_repository),
    payments: PaymentRepository = Depends(get_payment_repository),
    ledger: TransactionLedgerRepository = Depends(get_ledger_repository),
    provider: PaymentProvider = Depends(payment_provider),
) -> PaymentPublic:
    if settings.payment_provider == "mock" and settings.app_env.lower() not in {"development", "test"}:
        raise HTTPException(status_code=503, detail="Mock payment provider is disabled outside development/test")
    try:
        return PaymentPublic.model_validate(initiate_payment(
            orders=orders, payments=payments, ledger=ledger, provider=provider,
            buyer_id=user.id, payload=payload, idempotency_key=idempotency_key,
        ))
    except PaymentAccessError:
        raise HTTPException(status_code=404, detail="Order not found") from None
    except PaymentStateError:
        raise HTTPException(status_code=409, detail="Order is not eligible for another payment") from None
    except PaymentConfigurationError as exc:
        code = 422 if "Idempotency-Key" in str(exc) else 503
        raise HTTPException(status_code=code, detail=str(exc)) from None
    except PaymentConflictError:
        raise HTTPException(status_code=409, detail="Payment already exists or idempotency key conflicts") from None


@router.post("/callback/daraja", summary="Daraja STK Push callback")
async def daraja_callback(
    request: Request,
    payments: PaymentRepository = Depends(get_payment_repository),
    orders: OrderRepository = Depends(get_order_repository),
    ledger: TransactionLedgerRepository = Depends(get_ledger_repository),
    escrows: EscrowRepository = Depends(get_escrow_repository),
    provider: PaymentProvider = Depends(payment_provider),
    safeguarding_provider: EscrowProvider = Depends(escrow_provider),
) -> dict:
    try:
        callback = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Malformed JSON callback") from None
    try:
        result = process_daraja_callback(
            callback=callback, payments=payments, orders=orders,
            ledger=ledger, escrow_repo=escrows, escrow_provider=safeguarding_provider, provider=provider,
        )
        return {key: result[key] for key in ("accepted", "result_code", "result_description")}
    except PaymentVerificationError as exc:
        # A retryable verification failure receives 503 so Daraja/callback forwarding can retry.
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except PaymentConflictError:
        raise HTTPException(status_code=409, detail="Conflicting or duplicate callback") from None
    except PaymentStateError:
        raise HTTPException(status_code=409, detail="Order state does not allow payment confirmation") from None


@router.post("/mock/{payment_id}/callback", response_model=PaymentPublic, summary="Development-only mock payment confirmation")
def mock_callback(
    payment_id: PaymentId,
    payload: MockCallbackSimulation,
    user: UserPublic = Depends(require_roles(UserRole.BUYER)),
    payments: PaymentRepository = Depends(get_payment_repository),
    orders: OrderRepository = Depends(get_order_repository),
    ledger: TransactionLedgerRepository = Depends(get_ledger_repository),
    escrows: EscrowRepository = Depends(get_escrow_repository),
    safeguarding_provider: EscrowProvider = Depends(escrow_provider),
) -> PaymentPublic:
    if settings.app_env.lower() not in {"development", "test"} or settings.payment_provider != "mock":
        raise HTTPException(status_code=404, detail="Mock payment simulation is disabled")
    try:
        result = process_mock_callback(
            payment_id=payment_id, buyer_id=user.id, success=payload.success,
            amount_kes=payload.amount_kes, payments=payments, orders=orders,
            ledger=ledger, escrow_repo=escrows, escrow_provider=safeguarding_provider,
        )
        return PaymentPublic.model_validate(result["payment"])
    except PaymentAccessError:
        raise _not_found() from None
    except PaymentVerificationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except (PaymentStateError, PaymentConflictError):
        raise HTTPException(status_code=409, detail="Payment is not eligible for mock confirmation") from None


@router.get("/mine", response_model=PaymentListResponse, summary="List my payment history")
def my_payments(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: UserPublic = Depends(require_roles(UserRole.BUYER)),
    payments: PaymentRepository = Depends(get_payment_repository),
) -> PaymentListResponse:
    items, total = list_payment_history(payments, user.id, skip=offset, limit=limit)
    return PaymentListResponse(items=[PaymentPublic.model_validate(item) for item in items], total=total, limit=limit, offset=offset)


@router.get("/admin/history", response_model=PaymentListResponse, summary="List platform payment history")
def admin_payment_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: UserPublic = Depends(require_roles(UserRole.ADMIN)),
    payments: PaymentRepository = Depends(get_payment_repository),
) -> PaymentListResponse:
    items, total = payments.list_all(skip=offset, limit=limit)
    return PaymentListResponse(items=[PaymentPublic.model_validate(item) for item in items], total=total, limit=limit, offset=offset)


@router.get("/{payment_id}", response_model=PaymentPublic, summary="Get my payment")
def get_payment(
    payment_id: PaymentId,
    user: UserPublic = Depends(get_current_user),
    payments: PaymentRepository = Depends(get_payment_repository),
) -> PaymentPublic:
    payment = payments.get(payment_id)
    if payment is None or user.role != UserRole.ADMIN and payment["buyer_id"] != user.id:
        raise _not_found()
    return PaymentPublic.model_validate(payment)


@router.get("/{payment_id}/provider-status", summary="Query the configured provider without changing local payment/order status")
def provider_status(
    payment_id: PaymentId,
    user: UserPublic = Depends(get_current_user),
    payments: PaymentRepository = Depends(get_payment_repository),
    provider: PaymentProvider = Depends(payment_provider),
) -> dict:
    payment = payments.get(payment_id)
    if payment is None or user.role != UserRole.ADMIN and payment["buyer_id"] != user.id:
        raise _not_found()
    if not payment.get("checkout_request_id"):
        return {"payment_id": payment_id, "local_status": payment["status"], "provider_status": "NOT_AVAILABLE", "payment_confirmed": payment["status"] == "SUCCEEDED", "actual_mpesa_transaction": payment["provider"] == "daraja" and payment["status"] == "SUCCEEDED"}
    try:
        provider_result = provider.query_stk_status(payment["checkout_request_id"])
    except PaymentProviderError:
        raise HTTPException(status_code=503, detail="Provider status is temporarily unavailable") from None
    safe = {key: provider_result.get(key) for key in ("ResponseCode", "ResponseDescription", "ResultCode", "ResultDesc", "CheckoutRequestID") if key in provider_result}
    return {"payment_id": payment_id, "local_status": payment["status"], "provider_result": safe, "payment_confirmed": payment["status"] == "SUCCEEDED", "note": "A provider query does not mutate local order/payment state; only verified callback processing does."}
