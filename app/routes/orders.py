from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status

from app.core.dependencies import get_current_user, get_marketplace_repository, get_order_repository, require_roles
from app.models.order import OrderStatus
from app.models.user import UserRole
from app.repositories.marketplace_repository import MarketplaceRepository
from app.repositories.order_repository import OrderRepository
from app.schemas.order import OrderCreate, OrderListResponse, OrderPublic, OrderStatusUpdate
from app.schemas.user import UserPublic
from app.services.order_service import (
    OrderAccessError,
    OrderStateConflictError,
    StockUnavailableError,
    cancel_order,
    place_order,
    update_seller_order_status,
)

router = APIRouter(prefix="/orders", tags=["Orders"])
OrderId = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]


def _access_error() -> HTTPException:
    return HTTPException(status_code=404, detail="Order not found")


@router.post("", response_model=OrderPublic, status_code=status.HTTP_201_CREATED, summary="Place an order and reserve stock")
def post_order(
    payload: OrderCreate,
    user: UserPublic = Depends(require_roles(UserRole.BUYER)),
    orders: OrderRepository = Depends(get_order_repository),
    products: MarketplaceRepository = Depends(get_marketplace_repository),
) -> OrderPublic:
    try:
        return OrderPublic.model_validate(place_order(orders, products, user.id, payload))
    except StockUnavailableError:
        raise HTTPException(status_code=409, detail="Product is unavailable or has insufficient stock") from None
    except OrderAccessError:
        raise HTTPException(status_code=409, detail="You cannot order your own listing") from None


@router.get("/buyer", response_model=OrderListResponse, summary="List my buyer orders")
def buyer_orders(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: UserPublic = Depends(require_roles(UserRole.BUYER)),
    orders: OrderRepository = Depends(get_order_repository),
) -> OrderListResponse:
    items, total = orders.list_for_user("buyer_id", user.id, skip=offset, limit=limit)
    return OrderListResponse(items=[OrderPublic.model_validate(item) for item in items], total=total, limit=limit, offset=offset)


@router.get("/seller", response_model=OrderListResponse, summary="List orders for my products")
def seller_orders(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    orders: OrderRepository = Depends(get_order_repository),
) -> OrderListResponse:
    items, total = orders.list_for_user("seller_id", user.id, skip=offset, limit=limit)
    return OrderListResponse(items=[OrderPublic.model_validate(item) for item in items], total=total, limit=limit, offset=offset)


@router.get("/{order_id}", response_model=OrderPublic, summary="Get an order visible to me")
def get_order(
    order_id: OrderId,
    user: UserPublic = Depends(get_current_user),
    orders: OrderRepository = Depends(get_order_repository),
) -> OrderPublic:
    order = orders.get(order_id)
    if order is None or user.role != UserRole.ADMIN and user.id not in {order["buyer_id"], order["seller_id"]}:
        raise _access_error()
    return OrderPublic.model_validate(order)


@router.post("/{order_id}/cancel", response_model=OrderPublic, summary="Cancel an unpaid order and release reserved stock")
def post_cancel_order(
    order_id: OrderId,
    user: UserPublic = Depends(require_roles(UserRole.BUYER)),
    orders: OrderRepository = Depends(get_order_repository),
    products: MarketplaceRepository = Depends(get_marketplace_repository),
) -> OrderPublic:
    try:
        return OrderPublic.model_validate(cancel_order(orders, products, order_id, user.id))
    except OrderAccessError:
        raise _access_error() from None
    except OrderStateConflictError:
        raise HTTPException(status_code=409, detail="Only an unpaid order awaiting payment can be cancelled") from None


@router.patch("/{order_id}/status", response_model=OrderPublic, summary="Advance a paid seller order")
def patch_order_status(
    order_id: OrderId,
    payload: OrderStatusUpdate,
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    orders: OrderRepository = Depends(get_order_repository),
) -> OrderPublic:
    try:
        return OrderPublic.model_validate(update_seller_order_status(orders, order_id, user.id, payload.order_status))
    except OrderAccessError:
        raise _access_error() from None
    except OrderStateConflictError:
        raise HTTPException(status_code=409, detail="Order status transition is not allowed") from None
