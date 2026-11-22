from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.dependencies import get_current_user, get_pesticide_repository, require_roles
from app.models.pesticide import PesticideReviewStatus
from app.models.user import UserRole
from app.repositories.pesticide_repository import PesticideRegistrationConflict, PesticideRepository
from app.schemas.pesticide import (
    PesticideRecordCreate,
    PesticideRecordList,
    PesticideRecordPublic,
    PesticideReviewRequest,
)
from app.schemas.user import UserPublic

router = APIRouter(prefix="/pesticide-records", tags=["Pesticide Evidence"])


@router.post(
    "",
    response_model=PesticideRecordPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Submit PCPB registration and approved-label evidence for review",
    description="Creates a pending record only. Submission does not make a pesticide recommendation available to farmers.",
    responses={409: {"description": "Registration number already exists."}},
)
def create_pesticide_record(
    payload: PesticideRecordCreate,
    user: UserPublic = Depends(require_roles(UserRole.ADMIN, UserRole.AGRICULTURAL_OFFICER)),
    repository: PesticideRepository = Depends(get_pesticide_repository),
):
    try:
        return repository.create_draft(user.id, payload.model_dump())
    except PesticideRegistrationConflict:
        raise HTTPException(status_code=409, detail="A record for this PCPB registration number already exists") from None


@router.get(
    "",
    response_model=PesticideRecordList,
    summary="List pesticide evidence records for administrators and officers",
)
def list_pesticide_records(
    review_status: PesticideReviewStatus | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: UserPublic = Depends(require_roles(UserRole.ADMIN, UserRole.AGRICULTURAL_OFFICER)),
    repository: PesticideRepository = Depends(get_pesticide_repository),
):
    items, total = repository.list_records(
        skip=offset,
        limit=limit,
        review_status=review_status.value if review_status else None,
    )
    return PesticideRecordList(items=items, total=total, limit=limit, offset=offset)


@router.patch(
    "/{record_id}/review",
    response_model=PesticideRecordPublic,
    summary="Approve or reject a pending PCPB evidence record",
    description="ADMIN only. Approval requires explicit confirmation that both the current PCPB record and approved label were checked. Every decision is appended to the record history.",
)
def review_pesticide_record(
    record_id: str,
    payload: PesticideReviewRequest,
    user: UserPublic = Depends(require_roles(UserRole.ADMIN)),
    repository: PesticideRepository = Depends(get_pesticide_repository),
):
    updated = repository.review(record_id, user.id, payload.model_dump())
    if updated is not None:
        return updated
    existing = repository.get(record_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Pesticide evidence record not found")
    raise HTTPException(status_code=409, detail="Only pending records can receive a review decision")


@router.get(
    "/approved",
    response_model=PesticideRecordList,
    summary="List approved pesticide label records",
    description="Farmer-visible records only. Approval records source review; product use must still follow the approved label and local professional advice.",
)
def list_approved_pesticides(
    crop_name: str | None = Query(None, min_length=2, max_length=100),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: UserPublic = Depends(require_roles(UserRole.FARMER)),
    repository: PesticideRepository = Depends(get_pesticide_repository),
):
    items, total = repository.list_approved(crop_name=crop_name, skip=offset, limit=limit)
    return PesticideRecordList(items=items, total=total, limit=limit, offset=offset)
