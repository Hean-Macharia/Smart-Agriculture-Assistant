from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query, status

from app.core.dependencies import get_current_user, get_delivery_repository, get_order_repository, require_roles
from app.models.user import UserRole
from app.repositories.delivery_repository import DeliveryRepository
from app.repositories.order_repository import OrderRepository
from app.schemas.delivery import DeliveryCreate, DeliveryListResponse, DeliveryPublic, DeliveryStatusUpdate
from app.schemas.user import UserPublic
from app.services.delivery_service import DeliveryAccessError, DeliveryStateError, confirm_delivery, create_delivery, update_delivery
from app.services.notification_service import dispatch_sms_event

router = APIRouter(prefix="/deliveries", tags=["Deliveries"])
DeliveryId = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]
OrderId = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]


def _not_found():
    return HTTPException(status_code=404, detail="Delivery not found")


@router.post("/orders/{order_id}", response_model=DeliveryPublic, status_code=status.HTTP_201_CREATED, summary="Create delivery details for a seller order")
def post_delivery(order_id: OrderId, payload: DeliveryCreate, user: UserPublic = Depends(require_roles(UserRole.FARMER)), deliveries: DeliveryRepository = Depends(get_delivery_repository), orders: OrderRepository = Depends(get_order_repository)):
    try:
        return DeliveryPublic.model_validate(create_delivery(order_id=order_id, seller_id=user.id, payload=payload.model_dump(), deliveries=deliveries, orders=orders))
    except DeliveryAccessError:
        raise _not_found() from None
    except DeliveryStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.get("/mine", response_model=DeliveryListResponse, summary="List deliveries for the current buyer or farmer")
def my_deliveries(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), user: UserPublic = Depends(get_current_user), deliveries: DeliveryRepository = Depends(get_delivery_repository)):
    if user.role not in {UserRole.FARMER, UserRole.BUYER}:
        raise HTTPException(status_code=403, detail="Farmer or buyer role required")
    field = "seller_id" if user.role == UserRole.FARMER else "buyer_id"
    items, total = deliveries.list_for_user(field, user.id, skip=offset, limit=limit)
    return DeliveryListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{delivery_id}", response_model=DeliveryPublic, summary="Get delivery tracking details")
def get_delivery(delivery_id: DeliveryId, user: UserPublic = Depends(get_current_user), deliveries: DeliveryRepository = Depends(get_delivery_repository)):
    item = deliveries.get(delivery_id)
    if item is None or user.role != UserRole.ADMIN and user.id not in {item["buyer_id"], item["seller_id"]}:
        raise _not_found()
    return DeliveryPublic.model_validate(item)


@router.patch("/{delivery_id}/status", response_model=DeliveryPublic, summary="Seller or admin updates delivery progress")
def patch_delivery(delivery_id: DeliveryId, payload: DeliveryStatusUpdate, background_tasks: BackgroundTasks, user: UserPublic = Depends(get_current_user), deliveries: DeliveryRepository = Depends(get_delivery_repository), orders: OrderRepository = Depends(get_order_repository)):
    if user.role not in {UserRole.FARMER, UserRole.ADMIN}:
        raise HTTPException(status_code=403, detail="Farmer or administrator role required")
    try:
        delivery = DeliveryPublic.model_validate(update_delivery(delivery_id=delivery_id, actor_id=user.id, is_admin=user.role == UserRole.ADMIN, target=payload.status, note=payload.note, deliveries=deliveries, orders=orders))
        background_tasks.add_task(dispatch_sms_event, recipient_user_id=delivery.buyer_id, event="DELIVERY_UPDATE", event_id=f"{delivery.id}:{delivery.status.value}", message=f"Delivery for order {delivery.order_id} is now {delivery.status.value}.")
        return delivery
    except DeliveryAccessError:
        raise _not_found() from None
    except DeliveryStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.post("/{delivery_id}/confirm", response_model=DeliveryPublic, summary="Buyer confirms receipt and completes the order")
def post_confirm(delivery_id: DeliveryId, background_tasks: BackgroundTasks, user: UserPublic = Depends(require_roles(UserRole.BUYER)), deliveries: DeliveryRepository = Depends(get_delivery_repository), orders: OrderRepository = Depends(get_order_repository)):
    try:
        delivery = DeliveryPublic.model_validate(confirm_delivery(delivery_id=delivery_id, buyer_id=user.id, deliveries=deliveries, orders=orders))
        background_tasks.add_task(dispatch_sms_event, recipient_user_id=delivery.seller_id, event="DELIVERY_UPDATE", event_id=f"{delivery.id}:{delivery.status.value}", message=f"Buyer confirmed delivery for order {delivery.order_id}.")
        return delivery
    except DeliveryAccessError:
        raise _not_found() from None
    except DeliveryStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
