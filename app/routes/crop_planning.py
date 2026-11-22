from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.core.dependencies import get_advisory_repository, get_crop_repository, get_farm_repository, require_roles
from app.models.user import UserRole
from app.repositories.advisory_repository import AdvisoryRepository
from app.repositories.crop_repository import CropRepository
from app.repositories.farm_repository import FarmRepository
from app.schemas.advisory import CropCalendarResponse, SoilGuidanceRequest, SoilGuidanceResponse
from app.schemas.user import UserPublic
from app.services.crop_planning_service import CropPlanningNotFound, create_crop_calendar, create_soil_guidance

router = APIRouter(prefix="/crop-planning", tags=["Crop Calendar and Soil Guidance"])
CropId = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]


@router.get("/crops/{crop_id}/calendar", response_model=CropCalendarResponse, summary="Get a source-linked, crop-stage checklist for one of my crops")
def crop_calendar(
    crop_id: CropId,
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    crops: CropRepository = Depends(get_crop_repository),
    farms: FarmRepository = Depends(get_farm_repository),
):
    try:
        return create_crop_calendar(crops=crops, farms=farms, farmer_id=user.id, crop_id=crop_id)
    except CropPlanningNotFound:
        raise HTTPException(status_code=404, detail="Crop not found or no verified stage guide is available for this crop") from None


@router.post("/soil-guidance", response_model=SoilGuidanceResponse, status_code=status.HTTP_201_CREATED, summary="Save general soil-test-first guidance for my farm and crop")
def soil_guidance(
    payload: SoilGuidanceRequest,
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    repository: AdvisoryRepository = Depends(get_advisory_repository),
    crops: CropRepository = Depends(get_crop_repository),
    farms: FarmRepository = Depends(get_farm_repository),
):
    try:
        return create_soil_guidance(
            repository=repository,
            crops=crops,
            farms=farms,
            farmer_id=user.id,
            farm_id=payload.farm_id,
            crop_id=payload.crop_id,
            soil_test_date=payload.soil_test_date,
            soil_test_reference=payload.soil_test_reference,
        )
    except CropPlanningNotFound:
        raise HTTPException(status_code=404, detail="Farm or crop not found") from None
