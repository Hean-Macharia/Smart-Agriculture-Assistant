from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.core.dependencies import get_current_user, get_dispute_repository, get_order_repository, require_roles
from app.models.dispute import DisputeStatus
from app.models.user import UserRole
from app.repositories.dispute_repository import DisputeRepository
from app.repositories.order_repository import OrderRepository
from app.schemas.dispute import DisputeCreate, DisputeListResponse, DisputePublic, DisputeReview
from app.schemas.user import UserPublic
from app.services.dispute_service import DisputeAccessError, DisputeStateError, create_dispute, review_dispute

router = APIRouter(prefix="/disputes", tags=["Disputes"])
DisputeId = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]


def _not_found():
    return HTTPException(status_code=404, detail="Dispute not found")


@router.post("", response_model=DisputePublic, status_code=status.HTTP_201_CREATED, summary="Open a dispute for a paid order")
def post_dispute(payload: DisputeCreate, user: UserPublic = Depends(get_current_user), disputes: DisputeRepository = Depends(get_dispute_repository), orders: OrderRepository = Depends(get_order_repository)):
    if user.role not in {UserRole.BUYER, UserRole.FARMER}:
        raise HTTPException(status_code=403, detail="Buyer or farmer role required")
    values = payload.model_dump()
    values["evidence_urls"] = [str(url) for url in payload.evidence_urls]
    try:
        return DisputePublic.model_validate(create_dispute(order_id=payload.order_id, user_id=user.id, values=values, disputes=disputes, orders=orders))
    except DisputeAccessError:
        raise HTTPException(status_code=404, detail="Order not found") from None
    except DisputeStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.get("/mine", response_model=DisputeListResponse, summary="List disputes for the current farmer or buyer")
def my_disputes(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), user: UserPublic = Depends(require_roles(UserRole.FARMER, UserRole.BUYER)), disputes: DisputeRepository = Depends(get_dispute_repository)):
    items, total = disputes.list_for_user(user.id, skip=offset, limit=limit)
    return DisputeListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("", response_model=DisputeListResponse, summary="Admin list of disputes")
def all_disputes(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), user: UserPublic = Depends(require_roles(UserRole.ADMIN)), disputes: DisputeRepository = Depends(get_dispute_repository)):
    items, total = disputes.list_all(skip=offset, limit=limit)
    return DisputeListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{dispute_id}", response_model=DisputePublic, summary="Get a dispute visible to its participants or admin")
def get_dispute(dispute_id: DisputeId, user: UserPublic = Depends(get_current_user), disputes: DisputeRepository = Depends(get_dispute_repository)):
    item = disputes.get(dispute_id)
    if item is None or user.role != UserRole.ADMIN and user.id not in {item["buyer_id"], item["seller_id"]}:
        raise _not_found()
    return DisputePublic.model_validate(item)


@router.patch("/{dispute_id}/review", response_model=DisputePublic, summary="Record an audited administrator dispute decision")
def patch_review(dispute_id: DisputeId, payload: DisputeReview, user: UserPublic = Depends(require_roles(UserRole.ADMIN)), disputes: DisputeRepository = Depends(get_dispute_repository), orders: OrderRepository = Depends(get_order_repository)):
    try:
        item = review_dispute(dispute_id=dispute_id, admin_id=user.id, status=payload.status, decision=payload.decision, resolution=payload.resolution, disputes=disputes, orders=orders)
        return DisputePublic.model_validate(item)
    except DisputeAccessError:
        raise _not_found() from None
    except DisputeStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
