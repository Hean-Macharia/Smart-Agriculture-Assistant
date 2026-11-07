from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path

from app.core.config import settings
from app.core.dependencies import (
    escrow_provider,
    get_current_user,
    get_escrow_repository,
    get_ledger_repository,
    get_order_repository,
)
from app.models.user import UserRole
from app.repositories.escrow_repository import EscrowRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.transaction_repository import TransactionLedgerRepository
from app.schemas.escrow import EscrowActionResponse, EscrowPublic, RefundRequest
from app.schemas.user import UserPublic
from app.services.escrow_providers import EscrowProvider, EscrowProviderError
from app.services.escrow_service import (
    EscrowAccessError,
    EscrowStateError,
    request_buyer_refund,
    request_seller_release,
)

router = APIRouter(prefix="/escrow", tags=["Escrow"])
EscrowId = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]
OrderId = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Escrow transaction not found")


@router.get("/orders/{order_id}", response_model=EscrowPublic, summary="Get escrow status by order ID")
def get_escrow_for_order(
    order_id: OrderId,
    user: UserPublic = Depends(get_current_user),
    escrows: EscrowRepository = Depends(get_escrow_repository),
    orders: OrderRepository = Depends(get_order_repository),
) -> EscrowPublic:
    order = orders.get(order_id)
    if order is None or user.role != UserRole.ADMIN and user.id not in {order["buyer_id"], order["seller_id"]}:
        raise _not_found()
    escrow = escrows.get_by_order(order_id)
    if escrow is None:
        raise _not_found()
    return EscrowPublic.model_validate(escrow)


@router.get("/{escrow_id}", response_model=EscrowPublic, summary="Get escrow workflow and actual custody status")
def get_escrow(
    escrow_id: EscrowId,
    user: UserPublic = Depends(get_current_user),
    escrows: EscrowRepository = Depends(get_escrow_repository),
    orders: OrderRepository = Depends(get_order_repository),
) -> EscrowPublic:
    escrow = escrows.get(escrow_id)
    if escrow is None:
        raise _not_found()
    order = orders.get(escrow["order_id"])
    if order is None or user.role != UserRole.ADMIN and user.id not in {order["buyer_id"], order["seller_id"]}:
        raise _not_found()
    return EscrowPublic.model_validate(escrow)


@router.post("/{escrow_id}/release", response_model=EscrowActionResponse, summary="Request seller settlement after delivery confirmation")
def release_escrow(
    escrow_id: EscrowId,
    user: UserPublic = Depends(get_current_user),
    escrows: EscrowRepository = Depends(get_escrow_repository),
    orders: OrderRepository = Depends(get_order_repository),
    ledger: TransactionLedgerRepository = Depends(get_ledger_repository),
    provider: EscrowProvider = Depends(escrow_provider),
) -> EscrowActionResponse:
    if user.role not in {UserRole.FARMER, UserRole.ADMIN}:
        raise HTTPException(status_code=403, detail="Farmer or administrator role required")
    if settings.escrow_provider == "mock" and settings.app_env.lower() not in {"development", "test"}:
        raise HTTPException(status_code=503, detail="Mock settlement is disabled outside development/test")
    try:
        escrow, message = request_seller_release(
            escrow_id=escrow_id, seller_id=user.id, escrows=escrows,
            orders=orders, ledger=ledger, provider=provider,
        )
        return EscrowActionResponse(status=escrow["status"], message=message, escrow=EscrowPublic.model_validate(escrow))
    except EscrowAccessError:
        raise _not_found() from None
    except EscrowStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except EscrowProviderError:
        raise HTTPException(status_code=503, detail="Settlement provider is unavailable or not configured") from None


@router.post("/{escrow_id}/refund-request", response_model=EscrowActionResponse, summary="Request a refund review for a buyer order")
def refund_request(
    escrow_id: EscrowId,
    payload: RefundRequest,
    user: UserPublic = Depends(get_current_user),
    escrows: EscrowRepository = Depends(get_escrow_repository),
    orders: OrderRepository = Depends(get_order_repository),
    ledger: TransactionLedgerRepository = Depends(get_ledger_repository),
    provider: EscrowProvider = Depends(escrow_provider),
) -> EscrowActionResponse:
    if user.role != UserRole.BUYER:
        raise HTTPException(status_code=403, detail="Buyer role required")
    try:
        escrow, message = request_buyer_refund(
            escrow_id=escrow_id, buyer_id=user.id, reason=payload.reason,
            escrows=escrows, orders=orders, ledger=ledger, provider=provider,
        )
        return EscrowActionResponse(status=escrow["status"], message=message, escrow=EscrowPublic.model_validate(escrow))
    except EscrowAccessError:
        raise _not_found() from None
    except EscrowStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except EscrowProviderError:
        raise HTTPException(status_code=503, detail="Refund provider is unavailable or not configured") from None
