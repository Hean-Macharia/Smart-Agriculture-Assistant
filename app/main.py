"""FastAPI application entry point."""

import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from app.core.config import settings
from app.core.database import close_mongo_connection
from app.core.dependencies import (
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
    get_disease_report_repository,
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

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    get_user_repository.cache_clear()
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
    get_disease_report_repository.cache_clear()
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
