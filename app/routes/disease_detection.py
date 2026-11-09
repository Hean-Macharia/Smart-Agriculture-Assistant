from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from app.core.config import settings
from app.core.dependencies import get_current_user, get_disease_report_repository, require_roles
from app.ml.image_preprocessing import InvalidDiseaseImage
from app.ml.model_loader import DiseaseModelUnavailable
from app.models.user import UserRole
from app.repositories.disease_report_repository import DiseaseReportRepository
from app.schemas.disease import DiseasePredictionList, DiseasePredictionPublic
from app.schemas.user import UserPublic
from app.services.disease_service import create_disease_report

router = APIRouter(prefix="/disease-detection", tags=["Disease Detection"])
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.post(
    "/predict",
    response_model=DiseasePredictionPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a crop image for model-based disease screening",
    responses={
        401: {"description": "Authentication required"},
        403: {"description": "Farmer role required"},
        413: {"description": "Image exceeds the configured upload limit"},
        415: {"description": "Unsupported image content type"},
        422: {"description": "Invalid or empty image"},
        503: {"description": "Model assets or image processing dependencies are unavailable"},
    },
)
async def predict_crop_disease(
    image: Annotated[UploadFile, File(description="JPEG, PNG, or WebP crop photo; maximum 8 MiB by default")],
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    reports: DiseaseReportRepository = Depends(get_disease_report_repository),
):
    if image.content_type not in ALLOWED_CONTENT_TYPES:
        await image.close()
        raise HTTPException(status_code=415, detail="Upload a JPEG, PNG, or WebP image")
    try:
        image_bytes = await image.read(settings.disease_image_max_bytes + 1)
    finally:
        await image.close()
    if len(image_bytes) > settings.disease_image_max_bytes:
        raise HTTPException(status_code=413, detail="Image exceeds the configured upload size limit")
    if not image_bytes:
        raise HTTPException(status_code=422, detail="Image file is empty")
    try:
        result = create_disease_report(
            reports,
            farmer_id=user.id,
            filename=image.filename or "crop-image",
            content_type=image.content_type,
            image_bytes=image_bytes,
        )
    except InvalidDiseaseImage as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except DiseaseModelUnavailable:
        raise HTTPException(status_code=503, detail="Disease detection service is unavailable; a trained model and label map are required") from None
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Disease detection image processing dependencies are unavailable") from None
    return DiseasePredictionPublic.model_validate(result)


@router.get("/mine", response_model=DiseasePredictionList, summary="List the authenticated farmer's disease screening history")
def my_disease_reports(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    reports: DiseaseReportRepository = Depends(get_disease_report_repository),
):
    items, total = reports.list_for_farmer(user.id, skip=offset, limit=limit)
    return DiseasePredictionList(items=items, total=total, limit=limit, offset=offset)
