from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path

from app.core.config import settings
from app.core.dependencies import escrow_provider, get_current_user, get_escrow_repository, get_ledger_repository, get_order_repository, require_roles
from app.models.user import UserRole
from app.repositories.escrow_repository import EscrowRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.transaction_repository import TransactionLedgerRepository
from app.schemas.escrow import EscrowActionResponse, EscrowPublic
from app.schemas.user import UserPublic
from app.services.escrow_providers import EscrowProvider, EscrowProviderError
from app.services.escrow_service import EscrowAccessError, EscrowStateError
from app.services.payout_service import request_payout

router = APIRouter(prefix="/payouts", tags=["Payouts"])
EscrowId = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]


@router.get("/{escrow_id}", response_model=EscrowPublic, summary="View payout and escrow status")
def payout_status(escrow_id: EscrowId, user: UserPublic = Depends(get_current_user), escrows: EscrowRepository = Depends(get_escrow_repository), orders: OrderRepository = Depends(get_order_repository)):
    escrow = escrows.get(escrow_id)
    if escrow is None:
        raise HTTPException(status_code=404, detail="Payout not found")
    order = orders.get(escrow["order_id"])
    if order is None or user.role != UserRole.ADMIN and user.id not in {order["seller_id"], order["buyer_id"]}:
        raise HTTPException(status_code=404, detail="Payout not found")
    return EscrowPublic.model_validate(escrow)


@router.post("/{escrow_id}/release", response_model=EscrowActionResponse, summary="Request payout after delivery confirmation")
def release_payout(escrow_id: EscrowId, user: UserPublic = Depends(require_roles(UserRole.FARMER, UserRole.ADMIN)), escrows: EscrowRepository = Depends(get_escrow_repository), orders: OrderRepository = Depends(get_order_repository), ledger: TransactionLedgerRepository = Depends(get_ledger_repository), provider: EscrowProvider = Depends(escrow_provider)):
    if settings.escrow_provider == "mock" and settings.app_env.lower() not in {"development", "test"}:
        raise HTTPException(status_code=503, detail="Mock settlement is disabled outside development/test")
    try:
        escrow, message = request_payout(escrow_id=escrow_id, seller_id=user.id, escrows=escrows, orders=orders, ledger=ledger, provider=provider, is_admin=user.role == UserRole.ADMIN)
        return EscrowActionResponse(status=escrow["status"], message=message, escrow=EscrowPublic.model_validate(escrow))
    except EscrowAccessError:
        raise HTTPException(status_code=404, detail="Payout not found") from None
    except EscrowStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except EscrowProviderError:
        raise HTTPException(status_code=503, detail="Payout provider is unavailable or did not confirm settlement") from None
