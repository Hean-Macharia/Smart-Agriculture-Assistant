"""Administrator-only operational views. Mutations remain in their domain routes."""

from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.core.config import settings
from app.core.dependencies import get_admin_repository, require_roles
from app.ml.model_loader import _asset_path
from app.models.user import UserRole
from app.repositories.admin_repository import AdminRepository
from app.schemas.admin import AdminListResponse, AdminOverview
from app.schemas.user import UserPublic
from app.services.payment_providers import get_payment_provider
from app.services.sms_providers import get_sms_provider

router = APIRouter(prefix="/admin", tags=["Administration"])
Admin = Depends(require_roles(UserRole.ADMIN))


@router.get("/overview", response_model=AdminOverview, summary="Get real administrative statistics and trends")
def get_overview(_: UserPublic = Admin, repository: AdminRepository = Depends(get_admin_repository)):
    return repository.overview()


@router.get("/people", response_model=AdminListResponse, summary="List users and role-specific account summaries")
def list_people(
    role: Literal["FARMER", "BUYER", "AGRICULTURAL_OFFICER", "ADMIN"] = "FARMER",
    search: str | None = Query(None, min_length=2, max_length=100),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: UserPublic = Admin,
    repository: AdminRepository = Depends(get_admin_repository),
):
    items, total = repository.list_people(role=role, search=search, skip=offset, limit=limit)
    return AdminListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/products", response_model=AdminListResponse, summary="Search all marketplace listings for administrative review")
def list_products(
    search: str | None = Query(None, min_length=2, max_length=100),
    county: str | None = Query(None, min_length=2, max_length=80),
    active: bool | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: UserPublic = Admin,
    repository: AdminRepository = Depends(get_admin_repository),
):
    items, total = repository.list_products(search=search, county=county, active=active, skip=offset, limit=limit)
    return AdminListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/orders", response_model=AdminListResponse, summary="Read-only administrative order monitoring")
def list_orders(
    order_status: str | None = Query(None, min_length=3, max_length=40),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: UserPublic = Admin,
    repository: AdminRepository = Depends(get_admin_repository),
):
    items, total = repository.list_orders(status=order_status.upper() if order_status else None, skip=offset, limit=limit)
    return AdminListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/escrow", response_model=AdminListResponse, summary="Read-only escrow workflow and custody monitoring")
def list_escrow(
    escrow_status: str | None = Query(None, min_length=3, max_length=40),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: UserPublic = Admin,
    repository: AdminRepository = Depends(get_admin_repository),
):
    items, total = repository.list_escrows(status=escrow_status.upper() if escrow_status else None, skip=offset, limit=limit)
    return AdminListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/disease-reports", response_model=AdminListResponse, summary="Read-only preliminary disease screening reports")
def list_disease_reports(
    case_status: str | None = Query(None, min_length=3, max_length=40),
    search: str | None = Query(None, min_length=2, max_length=100),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: UserPublic = Admin,
    repository: AdminRepository = Depends(get_admin_repository),
):
    items, total = repository.list_disease_reports(status=case_status.upper() if case_status else None, search=search, skip=offset, limit=limit)
    return AdminListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/notifications", response_model=AdminListResponse, summary="View administrative notification delivery attempts")
def list_notifications(
    delivery_status: str | None = Query(None, min_length=3, max_length=40),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: UserPublic = Admin,
    repository: AdminRepository = Depends(get_admin_repository),
):
    items, total = repository.list_notifications(status=delivery_status.upper() if delivery_status else None, skip=offset, limit=limit)
    return AdminListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/pesticides", response_model=AdminListResponse, summary="List PCPB evidence with the submitting officer identity")
def list_pesticides(
    review_status: str | None = Query(None, min_length=3, max_length=40),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: UserPublic = Admin,
    repository: AdminRepository = Depends(get_admin_repository),
):
    items, total = repository.list_pesticides(status=review_status.upper() if review_status else None, skip=offset, limit=limit)
    return AdminListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/farms", response_model=AdminListResponse, summary="List mapped farms for weather monitoring")
def list_mapped_farms(
    search: str | None = Query(None, min_length=2, max_length=100),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: UserPublic = Admin,
    repository: AdminRepository = Depends(get_admin_repository),
):
    items, total = repository.list_farms(search=search, skip=offset, limit=limit)
    return AdminListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/audit-logs", response_model=AdminListResponse, summary="Inspect append-only administrative action logs")
def list_audit_logs(
    actor_id: str | None = Query(None, min_length=24, max_length=24),
    action: str | None = Query(None, min_length=3, max_length=200),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: UserPublic = Admin,
    repository: AdminRepository = Depends(get_admin_repository),
):
    items, total = repository.list_audit(actor_id=actor_id, action=action, skip=offset, limit=limit)
    return AdminListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/settings", summary="Show safe runtime and provider configuration status")
def get_safe_settings(_: UserPublic = Admin):
    disease_model = settings.disease_model_path.strip()
    disease_labels = settings.disease_labels_path.strip()
    model_available = bool(disease_model and disease_labels and _asset_path(disease_model).is_file() and _asset_path(disease_labels).is_file())
    payment = get_payment_provider().name
    sms = get_sms_provider().name
    return {
        "app_environment": settings.app_env,
        "database": "connected",
        "disease_model_available": model_available,
        "payment_adapter": payment,
        "payment_environment": settings.mpesa_environment if payment == "daraja" else None,
        "escrow_adapter": settings.escrow_provider,
        "sms_adapter": sms,
        "weather_provider_configured": bool(settings.weather_api_key.strip()),
        "sms_delivery_boundary": "Provider acceptance is not proof of handset delivery.",
        "escrow_boundary": "Internal workflow status does not imply regulated custody; provider safeguarding is shown only when confirmed.",
    }
