from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path

from app.core.dependencies import get_current_user, get_ledger_repository, get_order_repository
from app.models.user import UserRole
from app.repositories.order_repository import OrderRepository
from app.repositories.transaction_repository import TransactionLedgerRepository
from app.schemas.transaction import LedgerEventPublic, LedgerListResponse
from app.schemas.user import UserPublic

router = APIRouter(prefix="/transactions", tags=["Transactions"])
OrderId = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]


@router.get("/orders/{order_id}/ledger", response_model=LedgerListResponse, summary="View append-only financial events for an order")
def order_ledger(
    order_id: OrderId,
    user: UserPublic = Depends(get_current_user),
    orders: OrderRepository = Depends(get_order_repository),
    ledger: TransactionLedgerRepository = Depends(get_ledger_repository),
) -> LedgerListResponse:
    order = orders.get(order_id)
    if order is None or user.role != UserRole.ADMIN and user.id not in {order["buyer_id"], order["seller_id"]}:
        raise HTTPException(status_code=404, detail="Order not found")
    items = [LedgerEventPublic.model_validate(item) for item in ledger.list_for_order(order_id)]
    return LedgerListResponse(items=items, total=len(items))
