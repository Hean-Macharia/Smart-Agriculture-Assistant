from typing import Annotated
from datetime import date, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Response, status

from app.core.dependencies import get_crop_repository, get_farm_repository, require_roles
from app.models.user import UserRole
from app.repositories.crop_repository import CropRepository
from app.repositories.farm_repository import FarmRepository
from app.schemas.crop import CropCreate, CropListResponse, CropPublic, CropUpdate
from app.schemas.user import UserPublic
from app.services.crop_service import create_crop, update_crop

router = APIRouter(prefix="/crops", tags=["Crops"])
CropId = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]


@router.post("", response_model=CropPublic, status_code=status.HTTP_201_CREATED, summary="Record a crop on one of my farms")
def post_crop(
    payload: CropCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=16, max_length=128),
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    crops: CropRepository = Depends(get_crop_repository),
    farms: FarmRepository = Depends(get_farm_repository),
) -> CropPublic:
    farm = farms.get(payload.farm_id)
    if farm is None or farm["owner_id"] != user.id:
        raise HTTPException(status_code=404, detail="Farm not found")
    try:
        return create_crop(crops, user.id, payload, idempotency_key=idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("", response_model=CropListResponse, summary="List my active crops, optionally filtered by farm")
def list_crops(
    farm_id: str | None = Query(default=None, pattern=r"^[0-9a-fA-F]{24}$"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    repository: CropRepository = Depends(get_crop_repository),
) -> CropListResponse:
    items, total = repository.list_for_owner(user.id, farm_id=farm_id, skip=offset, limit=limit)
    return CropListResponse(items=[CropPublic.model_validate(item) for item in items], total=total, limit=limit, offset=offset)


@router.get("/{crop_id}", response_model=CropPublic, summary="Get one of my crops")
def get_crop(
    crop_id: CropId,
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    repository: CropRepository = Depends(get_crop_repository),
) -> CropPublic:
    crop = repository.get(crop_id)
    if crop is None or crop["owner_id"] != user.id:
        raise HTTPException(status_code=404, detail="Crop not found")
    return CropPublic.model_validate(crop)


@router.patch("/{crop_id}", response_model=CropPublic, summary="Update one of my crops")
def patch_crop(
    crop_id: CropId,
    payload: CropUpdate,
    if_match: str | None = Header(default=None, alias="If-Match", max_length=100),
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    repository: CropRepository = Depends(get_crop_repository),
) -> CropPublic:
    existing = repository.get(crop_id)
    if existing is None or existing["owner_id"] != user.id:
        raise HTTPException(status_code=404, detail="Crop not found")
    changes = payload.model_dump(exclude_unset=True, mode="json")
    planting_date = date.fromisoformat(changes.get("planting_date", existing["planting_date"]))
    harvest_value = changes.get("expected_harvest_date", existing.get("expected_harvest_date"))
    if harvest_value and date.fromisoformat(harvest_value) < planting_date:
        raise HTTPException(status_code=422, detail="Expected harvest date cannot be before planting date")
    expected_updated_at = None
    if if_match is not None:
        try:
            expected_updated_at = datetime.fromisoformat(if_match.strip().strip('"').replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="If-Match must contain the crop updated_at timestamp") from exc
    crop = update_crop(repository, crop_id, user.id, payload, expected_updated_at=expected_updated_at)
    if crop is None:
        if expected_updated_at is not None and repository.get(crop_id):
            raise HTTPException(status_code=409, detail="Crop changed on the server; review the latest values before retrying")
        raise HTTPException(status_code=404, detail="Crop not found")
    return crop


@router.delete("/{crop_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Deactivate one of my crops")
def delete_crop(
    crop_id: CropId,
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    repository: CropRepository = Depends(get_crop_repository),
) -> Response:
    if not repository.deactivate(crop_id, user.id):
        raise HTTPException(status_code=404, detail="Crop not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
