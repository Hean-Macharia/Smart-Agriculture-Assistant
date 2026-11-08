from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query, status

from app.core.dependencies import get_advisory_repository, get_crop_repository, get_current_user, get_farm_repository, require_roles
from app.models.user import UserRole
from app.repositories.advisory_repository import AdvisoryRepository
from app.repositories.crop_repository import CropRepository
from app.repositories.farm_repository import FarmRepository
from app.schemas.advisory import AdvisoryCreate, AdvisoryListResponse, AdvisoryPublic, AdvisoryUpdate, WeatherRecommendationRequest
from app.schemas.user import UserPublic
from app.services.advisory_service import AdvisoryAccessError, create_officer_advisory, create_weather_recommendation, update_officer_advisory
from app.services.weather_service import WeatherProviderError, fetch_weather_forecast
from app.services.notification_service import dispatch_sms_event

router = APIRouter(prefix="/advisories", tags=["Agricultural Advisory"])
AdvisoryId = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]


@router.post("", response_model=AdvisoryPublic, status_code=status.HTTP_201_CREATED, summary="Create an officer-authored agricultural advisory")
def post_advisory(payload: AdvisoryCreate, user: UserPublic = Depends(require_roles(UserRole.ADMIN, UserRole.AGRICULTURAL_OFFICER)), repo: AdvisoryRepository = Depends(get_advisory_repository)):
    values = payload.model_dump()
    return AdvisoryPublic.model_validate(create_officer_advisory(repo, user.id, values))


@router.get("", response_model=AdvisoryListResponse, summary="List relevant advisories and my weather recommendation history")
def list_advisories(crop_name: str | None = Query(None, min_length=2, max_length=100), county: str | None = Query(None, min_length=2, max_length=80), limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), user: UserPublic = Depends(get_current_user), repo: AdvisoryRepository = Depends(get_advisory_repository)):
    if user.role == UserRole.FARMER:
        items, total = repo.list_for_farmer(farmer_id=user.id, crop_name=crop_name, county=county, skip=offset, limit=limit)
    elif user.role in {UserRole.ADMIN, UserRole.AGRICULTURAL_OFFICER}:
        items, total = repo.list_all(skip=offset, limit=limit)
    else:
        raise HTTPException(status_code=403, detail="Farmer, agricultural officer, or administrator role required")
    return AdvisoryListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/mine", response_model=AdvisoryListResponse, summary="List my farm-linked weather recommendation history")
def my_advisories(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), user: UserPublic = Depends(require_roles(UserRole.FARMER)), repo: AdvisoryRepository = Depends(get_advisory_repository)):
    items, total = repo.list_for_farmer_history(user.id, skip=offset, limit=limit)
    return AdvisoryListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/recommendations/weather", response_model=AdvisoryPublic, status_code=status.HTTP_201_CREATED, summary="Create and store a crop-linked weather rule recommendation")
def weather_recommendation(payload: WeatherRecommendationRequest, background_tasks: BackgroundTasks, user: UserPublic = Depends(require_roles(UserRole.FARMER)), repo: AdvisoryRepository = Depends(get_advisory_repository), farms: FarmRepository = Depends(get_farm_repository), crops: CropRepository = Depends(get_crop_repository)):
    try:
        weather = fetch_weather_forecast(payload.latitude, payload.longitude)
        result = create_weather_recommendation(repository=repo, farms=farms, crops=crops, farmer_id=user.id, farm_id=payload.farm_id, crop_id=payload.crop_id, weather=weather)
        background_tasks.add_task(dispatch_sms_event, recipient_user_id=user.id, event="AGRICULTURAL_ADVISORY", event_id=result["id"], message=f"New weather guidance is available for {result['crop_name']} on your farm. Review it in your account.")
        return AdvisoryPublic.model_validate(result)
    except AdvisoryAccessError:
        raise HTTPException(status_code=404, detail="Farm or crop not found") from None
    except WeatherProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@router.patch("/{advisory_id}", response_model=AdvisoryPublic, summary="Update or deactivate an officer advisory")
def patch_advisory(advisory_id: AdvisoryId, payload: AdvisoryUpdate, user: UserPublic = Depends(require_roles(UserRole.ADMIN, UserRole.AGRICULTURAL_OFFICER)), repo: AdvisoryRepository = Depends(get_advisory_repository)):
    try:
        advisory = update_officer_advisory(repo, advisory_id, user.id, payload.model_dump(exclude_unset=True), is_admin=user.role == UserRole.ADMIN)
        return AdvisoryPublic.model_validate(advisory)
    except AdvisoryAccessError:
        raise HTTPException(status_code=404, detail="Officer advisory not found") from None
