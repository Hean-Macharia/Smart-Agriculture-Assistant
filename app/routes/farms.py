from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Response, status

from app.core.dependencies import get_farm_repository, require_roles
from app.models.user import UserRole
from app.repositories.farm_repository import FarmRepository
from app.schemas.farm import FarmCreate, FarmListResponse, FarmPublic, FarmUpdate
from app.schemas.user import UserPublic
from app.services.farm_service import create_farm, update_farm

router = APIRouter(prefix="/farms", tags=["Farms"])
FarmId = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]


@router.post("", response_model=FarmPublic, status_code=status.HTTP_201_CREATED, summary="Register a farm")
def post_farm(
    payload: FarmCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=16, max_length=128),
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    repository: FarmRepository = Depends(get_farm_repository),
) -> FarmPublic:
    try:
        return create_farm(repository, user.id, payload, idempotency_key=idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("", response_model=FarmListResponse, summary="List my active farms")
def list_farms(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    repository: FarmRepository = Depends(get_farm_repository),
) -> FarmListResponse:
    items, total = repository.list_for_owner(user.id, skip=offset, limit=limit)
    return FarmListResponse(items=[FarmPublic.model_validate(item) for item in items], total=total, limit=limit, offset=offset)


@router.get("/{farm_id}", response_model=FarmPublic, summary="Get one of my farms")
def get_farm(
    farm_id: FarmId,
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    repository: FarmRepository = Depends(get_farm_repository),
) -> FarmPublic:
    farm = repository.get(farm_id)
    if farm is None or farm["owner_id"] != user.id:
        raise HTTPException(status_code=404, detail="Farm not found")
    return FarmPublic.model_validate(farm)


@router.patch("/{farm_id}", response_model=FarmPublic, summary="Update one of my farms")
def patch_farm(
    farm_id: FarmId,
    payload: FarmUpdate,
    if_match: str | None = Header(default=None, alias="If-Match", max_length=100),
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    repository: FarmRepository = Depends(get_farm_repository),
) -> FarmPublic:
    expected_updated_at = None
    if if_match is not None:
        try:
            expected_updated_at = datetime.fromisoformat(if_match.strip().strip('"').replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="If-Match must contain the farm updated_at timestamp") from exc
    farm = update_farm(repository, farm_id, user.id, payload, expected_updated_at=expected_updated_at)
    if farm is None:
        if expected_updated_at is not None and repository.get(farm_id):
            raise HTTPException(status_code=409, detail="Farm changed on the server; review the latest values before retrying")
        raise HTTPException(status_code=404, detail="Farm not found")
    return farm


@router.delete("/{farm_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Deactivate one of my farms")
def delete_farm(
    farm_id: FarmId,
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    repository: FarmRepository = Depends(get_farm_repository),
) -> Response:
    if not repository.deactivate(farm_id, user.id):
        raise HTTPException(status_code=404, detail="Farm not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
