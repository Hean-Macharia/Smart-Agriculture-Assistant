"""FastAPI application entry point."""

import logging
import re
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pymongo.errors import PyMongoError
from bson import ObjectId

from app.core.config import settings
from app.core.database import close_mongo_connection
from app.core.database import get_database
from app.core.security import decode_access_token
from app.core.dependencies import (
    get_admin_repository,
    get_buyer_repository,
    get_crop_repository,
    get_farm_repository,
    get_farmer_repository,
    get_marketplace_repository,
    get_order_repository,
    get_escrow_repository,
    get_ledger_repository,
    get_payment_repository,
    get_user_repository,
    get_delivery_repository,
    get_dispute_repository,
    get_advisory_repository,
    get_market_price_repository,
    get_notification_repository,
    get_sms_preferences_repository,
    get_disease_report_repository,
    get_pesticide_repository,
    get_disease_followup_repository,
    get_disease_treatment_repository,
)
from app.routes.auth import router as auth_router
from app.routes.buyers import router as buyers_router
from app.routes.crops import router as crops_router
from app.routes.farms import router as farms_router
from app.routes.farmers import router as farmers_router
from app.routes.health import router as health_router
from app.routes.marketplace import router as marketplace_router
from app.routes.orders import router as orders_router
from app.routes.payments import router as payments_router
from app.routes.transactions import router as transactions_router
from app.routes.escrow import router as escrow_router
from app.routes.deliveries import router as deliveries_router
from app.routes.disputes import router as disputes_router
from app.routes.payouts import router as payouts_router
from app.routes.weather import router as weather_router
from app.routes.advisory import router as advisory_router
from app.routes.market_prices import router as market_prices_router
from app.routes.notifications import router as notifications_router
from app.routes.disease_detection import router as disease_detection_router
from app.routes.pesticides import router as pesticides_router
from app.routes.crop_planning import router as crop_planning_router
from app.routes.pest_knowledge import router as pest_knowledge_router
from app.routes.admin import router as admin_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    get_user_repository.cache_clear()
    get_admin_repository.cache_clear()
    get_farmer_repository.cache_clear()
    get_buyer_repository.cache_clear()
    get_farm_repository.cache_clear()
    get_crop_repository.cache_clear()
    get_marketplace_repository.cache_clear()
    get_order_repository.cache_clear()
    get_payment_repository.cache_clear()
    get_escrow_repository.cache_clear()
    get_ledger_repository.cache_clear()
    get_delivery_repository.cache_clear()
    get_dispute_repository.cache_clear()
    get_advisory_repository.cache_clear()
    get_market_price_repository.cache_clear()
    get_notification_repository.cache_clear()
    get_sms_preferences_repository.cache_clear()
    get_disease_report_repository.cache_clear()
    get_pesticide_repository.cache_clear()
    get_disease_followup_repository.cache_clear()
    get_disease_treatment_repository.cache_clear()
    close_mongo_connection()


app = FastAPI(
    title=settings.app_name,
    description="Backend API for agricultural advice and produce market linkage.",
    version="0.8.0",
    # Never expose debug tracebacks when the deployment identifies itself as
    # production, even if DEBUG was accidentally left enabled.
    debug=settings.debug and settings.app_env.lower() not in {"production", "prod"},
    lifespan=lifespan,
)
cors_origins = [
    origin.strip().rstrip("/")
    for origin in settings.cors_allowed_origins.split(",")
    if origin.strip()
]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Admin-Bootstrap-Token"],
    )
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(farmers_router)
app.include_router(buyers_router)
app.include_router(farms_router)
app.include_router(crops_router)
app.include_router(marketplace_router)
app.include_router(orders_router)
app.include_router(payments_router)
app.include_router(escrow_router)
app.include_router(transactions_router)
app.include_router(deliveries_router)
app.include_router(disputes_router)
app.include_router(payouts_router)
app.include_router(weather_router)
app.include_router(advisory_router)
app.include_router(market_prices_router)
app.include_router(notifications_router)
app.include_router(disease_detection_router)
app.include_router(pesticides_router)
app.include_router(crop_planning_router)
app.include_router(pest_knowledge_router)
app.include_router(admin_router)


@app.middleware("http")
async def append_admin_audit_event(request: Request, call_next):
    response = await call_next(request)
    method = request.method.upper()
    path = request.url.path
    admin_mutations = (
        path == "/auth/admin/users" and method == "POST"
        or path == "/notifications/send" and method == "POST"
        or path == "/advisories" and method == "POST"
        or path.startswith("/advisories/") and method == "PATCH"
        or path.startswith("/disputes/") and path.endswith("/review") and method == "PATCH"
        or path.startswith("/disease-detection/") and path.endswith("/review") and method == "PATCH"
        or path.startswith("/pesticide-records/") and path.endswith("/review") and method == "PATCH"
        or path.startswith("/market-prices/") and path.endswith("/revision") and method == "POST"
        or path == "/market-prices" and method == "POST"
        or path.startswith("/escrow/") and path.endswith("/release") and method == "POST"
    )
    # Dependency overrides are active in the isolated test suite; keep those tests
    # detached from the configured live database.
    if admin_mutations and not app.dependency_overrides:
        authorization = request.headers.get("authorization", "")
        token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
        claims = decode_access_token(token) if token else None
        actor_id = claims.get("sub") if claims and claims.get("role") == "ADMIN" else None
        if actor_id and ObjectId.is_valid(actor_id):
            try:
                get_database()["audit_logs"].insert_one({
                    "actor_id": ObjectId(actor_id),
                    "action": f"{method} {path}",
                    "method": method,
                    "resource": path[:200],
                    "status_code": response.status_code,
                    "succeeded": 200 <= response.status_code < 400,
                    "timestamp": datetime.now(timezone.utc),
                })
            except PyMongoError as exc:
                logger.error("Admin audit event write failed: type=%s, code=%s", type(exc).__name__, getattr(exc, "code", None))
    return response

# Serve the built single-page frontend when a frontend build is present.
frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")


@app.exception_handler(PyMongoError)
async def database_error_handler(_: Request, exc: PyMongoError) -> JSONResponse:
    # Keep the driver message out of logs: some driver errors can contain
    # connection details. Log only a small, allowlisted diagnostic category.
    details = getattr(exc, "details", None)
    message = details.get("errmsg", "") if isinstance(details, dict) else ""
    normalized = message.lower()
    category = "operation_failed"
    action = "unknown"
    if "authentication failed" in normalized or "bad auth" in normalized:
        category = "authentication_failed"
    elif "not authorized" in normalized or "not allowed to do action" in normalized:
        category = "authorization_denied"
        match = re.search(r"not allowed to do action \[([a-zA-Z]+)\]", message, re.IGNORECASE)
        if match:
            candidate = match.group(1).lower()
            if candidate in {"createindex", "insert", "update", "find", "delete", "listcollections"}:
                action = candidate

    logger.error(
        "MongoDB operation failed: category=%s, action=%s, type=%s, code=%s, code_name=%s",
        category,
        action,
        type(exc).__name__,
        getattr(exc, "code", None),
        getattr(exc, "code_name", None),
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "Database temporarily unavailable"},
    )
