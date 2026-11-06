"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.core.database import close_mongo_connection
from app.routes.health import router as health_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    close_mongo_connection()


app = FastAPI(
    title=settings.app_name,
    description="Backend API for agricultural advice and produce market linkage.",
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)
app.include_router(health_router)
