from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Response, UploadFile, status

from app.core.config import settings
from app.core.dependencies import (
    get_current_user,
    get_disease_followup_repository,
    get_disease_report_repository,
    get_disease_treatment_repository,
    get_pesticide_repository,
    require_roles,
)
from app.ml.image_preprocessing import InvalidDiseaseImage
from app.ml.model_loader import DiseaseModelUnavailable
from app.models.user import UserRole
from app.repositories.disease_followup_repository import DiseaseFollowupRepository, FollowupIdempotencyConflict
from app.repositories.disease_report_repository import DiseaseReportRepository
from app.repositories.disease_treatment_repository import DiseaseTreatmentRepository, TreatmentIdempotencyConflict
from app.schemas.disease import (
    DiseaseFollowupPublic,
    DiseaseKnowledgeList,
    DiseaseKnowledgePublic,
    DiseaseMonitoringResponse,
    DiseaseOfficerReviewRequest,
    DiseasePredictionList,
    DiseasePredictionPublic,
    DiseaseTreatmentCreate,
    DiseaseTreatmentPublic,
)
from app.schemas.user import UserPublic
from app.services.disease_service import create_disease_report
from app.services.disease_knowledge_service import get_disease_knowledge, list_disease_knowledge
from app.services.disease_monitoring_service import (
    ApprovedPesticideRecordRequired,
    DiseaseReportNotFound,
    DiseaseCaseTransitionConflict,
    create_followup_screening,
    create_treatment_record,
    get_disease_monitoring,
    request_officer_review,
    resolve_disease_case,
    review_disease_case,
)
from app.repositories.pesticide_repository import PesticideRepository

router = APIRouter(prefix="/disease-detection", tags=["Disease Detection"])
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


async def _read_valid_image(image: UploadFile) -> bytes:
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
    return image_bytes


@router.get(
    "/knowledge",
    response_model=DiseaseKnowledgeList,
    summary="List source-backed general guidance for supported disease classes",
    description="Public educational material; the classifier is not a diagnosis and no pesticide products are recommended.",
)
def disease_knowledge(crop_name: str | None = Query(None, min_length=2, max_length=40)):
    items = list_disease_knowledge(crop_name)
    return DiseaseKnowledgeList(items=items, total=len(items))


@router.get(
    "/knowledge/{model_label}",
    response_model=DiseaseKnowledgePublic,
    summary="Get general guidance for one exact model output label",
    responses={404: {"description": "No knowledge record exists for this label."}},
)
def disease_knowledge_for_label(model_label: str):
    knowledge = get_disease_knowledge(model_label)
    if knowledge is None:
        raise HTTPException(status_code=404, detail="No disease guidance is available for this model label")
    return knowledge


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
    try:
        image_bytes = await _read_valid_image(image)
    except HTTPException:
        raise
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


@router.post(
    "/{report_id}/treatments",
    response_model=DiseaseTreatmentPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Record a farmer-entered action taken for a disease report",
    description="This logs history only; it does not prescribe or endorse treatment. Chemical logs require an approved PCPB record whose registered use includes the report crop and disease.",
    responses={404: {"description": "Disease report is not found or is not owned by the farmer."}, 409: {"description": "Idempotency key is already used for another report."}, 422: {"description": "Chemical record is not approved for the crop and disease."}},
)
def post_treatment_record(
    report_id: str,
    payload: DiseaseTreatmentCreate,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    reports: DiseaseReportRepository = Depends(get_disease_report_repository),
    treatments: DiseaseTreatmentRepository = Depends(get_disease_treatment_repository),
    pesticides: PesticideRepository = Depends(get_pesticide_repository),
):
    try:
        record, created = create_treatment_record(
            reports=reports,
            treatments=treatments,
            pesticides=pesticides,
            farmer_id=user.id,
            report_id=report_id,
            idempotency_key=idempotency_key,
            values=payload.model_dump(),
        )
    except DiseaseReportNotFound:
        raise HTTPException(status_code=404, detail="Disease report not found") from None
    except ApprovedPesticideRecordRequired:
        raise HTTPException(status_code=422, detail="Chemical history requires an approved PCPB record matching the crop and disease") from None
    except TreatmentIdempotencyConflict:
        raise HTTPException(status_code=409, detail="Idempotency key is already used for another treatment record") from None
    if not created:
        response.status_code = status.HTTP_200_OK
    return DiseaseTreatmentPublic.model_validate(record)


@router.post(
    "/{report_id}/followups",
    response_model=DiseaseFollowupPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a follow-up crop image for the disease report",
    description="Runs the configured model and stores prediction metadata plus a hash; original image bytes are not retained.",
    responses={404: {"description": "Disease report is not found or is not owned by the farmer."}, 413: {"description": "Image exceeds configured upload size."}, 415: {"description": "Unsupported image type."}, 422: {"description": "Invalid image or idempotency key conflict."}, 503: {"description": "Model assets or inference dependencies are unavailable."}},
)
async def post_followup_screening(
    report_id: str,
    image: Annotated[UploadFile, File(description="JPEG, PNG, or WebP follow-up photo")],
    response: Response,
    observation: Annotated[str | None, Form(max_length=500)] = None,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    reports: DiseaseReportRepository = Depends(get_disease_report_repository),
    followups: DiseaseFollowupRepository = Depends(get_disease_followup_repository),
):
    try:
        image_bytes = await _read_valid_image(image)
        record, created = create_followup_screening(
            reports=reports,
            followups=followups,
            farmer_id=user.id,
            report_id=report_id,
            idempotency_key=idempotency_key,
            filename=image.filename or "followup-crop-image",
            content_type=image.content_type or "application/octet-stream",
            image_bytes=image_bytes,
            observation=observation,
        )
    except HTTPException:
        raise
    except InvalidDiseaseImage as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except DiseaseModelUnavailable:
        raise HTTPException(status_code=503, detail="Disease detection service is unavailable; a trained model and label map are required") from None
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Disease detection image processing dependencies are unavailable") from None
    except DiseaseReportNotFound:
        raise HTTPException(status_code=404, detail="Disease report not found") from None
    except FollowupIdempotencyConflict:
        raise HTTPException(status_code=409, detail="Idempotency key is already used for another follow-up") from None
    if not created:
        response.status_code = status.HTTP_200_OK
    return DiseaseFollowupPublic.model_validate(record)


@router.get(
    "/{report_id}/monitoring",
    response_model=DiseaseMonitoringResponse,
    summary="Get the farmer's disease report, action log, and follow-up history",
    responses={404: {"description": "Disease report is not found or is not owned by the farmer."}},
)
def disease_monitoring(
    report_id: str,
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    reports: DiseaseReportRepository = Depends(get_disease_report_repository),
    followups: DiseaseFollowupRepository = Depends(get_disease_followup_repository),
    treatments: DiseaseTreatmentRepository = Depends(get_disease_treatment_repository),
):
    try:
        data = get_disease_monitoring(
            reports=reports,
            followups=followups,
            treatments=treatments,
            farmer_id=user.id,
            report_id=report_id,
        )
    except DiseaseReportNotFound:
        raise HTTPException(status_code=404, detail="Disease report not found") from None
    return DiseaseMonitoringResponse.model_validate(data)


@router.post(
    "/{report_id}/review-request",
    response_model=DiseasePredictionPublic,
    summary="Request an agricultural officer review of a disease screening",
    responses={404: {"description": "Disease report not found or not owned by this farmer."}, 409: {"description": "Review was already requested or the case is resolved."}},
)
def post_review_request(
    report_id: str,
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    reports: DiseaseReportRepository = Depends(get_disease_report_repository),
):
    try:
        return DiseasePredictionPublic.model_validate(request_officer_review(reports=reports, farmer_id=user.id, report_id=report_id))
    except DiseaseCaseTransitionConflict:
        if reports.get_for_farmer(report_id, user.id) is None:
            raise HTTPException(status_code=404, detail="Disease report not found") from None
        raise HTTPException(status_code=409, detail="This case cannot accept another review request") from None


@router.post(
    "/{report_id}/resolve",
    response_model=DiseasePredictionPublic,
    summary="Mark the farmer's disease monitoring case as resolved",
    description="This records the farmer's self-reported status; it is not clinical or model verification that the crop is disease-free.",
    responses={404: {"description": "Disease report not found or not owned by this farmer."}, 409: {"description": "Case is already resolved or cannot transition."}},
)
def post_resolve_disease_case(
    report_id: str,
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    reports: DiseaseReportRepository = Depends(get_disease_report_repository),
):
    try:
        return DiseasePredictionPublic.model_validate(resolve_disease_case(reports=reports, farmer_id=user.id, report_id=report_id))
    except DiseaseCaseTransitionConflict:
        if reports.get_for_farmer(report_id, user.id) is None:
            raise HTTPException(status_code=404, detail="Disease report not found") from None
        raise HTTPException(status_code=409, detail="This case cannot be marked resolved") from None


@router.get(
    "/review-queue",
    response_model=DiseasePredictionList,
    summary="List farmer-requested disease reviews for agricultural officers",
)
def disease_review_queue(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: UserPublic = Depends(require_roles(UserRole.AGRICULTURAL_OFFICER, UserRole.ADMIN)),
    reports: DiseaseReportRepository = Depends(get_disease_report_repository),
):
    items, total = reports.list_review_requested(skip=offset, limit=limit)
    return DiseasePredictionList(items=items, total=total, limit=limit, offset=offset)


@router.patch(
    "/{report_id}/review",
    response_model=DiseasePredictionPublic,
    summary="Add an audited agricultural officer response to a review request",
    responses={404: {"description": "Review request not found."}, 409: {"description": "Review request is no longer pending."}},
)
def patch_disease_case_review(
    report_id: str,
    payload: DiseaseOfficerReviewRequest,
    user: UserPublic = Depends(require_roles(UserRole.AGRICULTURAL_OFFICER, UserRole.ADMIN)),
    reports: DiseaseReportRepository = Depends(get_disease_report_repository),
):
    try:
        reviewed = review_disease_case(reports=reports, officer_id=user.id, report_id=report_id, note=payload.note)
    except DiseaseCaseTransitionConflict:
        raise HTTPException(status_code=409, detail="This review request is no longer pending") from None
    return DiseasePredictionPublic.model_validate(reviewed)
