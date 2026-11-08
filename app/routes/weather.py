from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.dependencies import require_roles
from app.models.user import UserRole
from app.schemas.user import UserPublic
from app.schemas.weather import WeatherResponse
from app.services.weather_service import WeatherProviderError, fetch_weather_forecast

router = APIRouter(prefix="/weather", tags=["Weather"])


@router.get("/forecast", response_model=WeatherResponse, summary="Get current weather and five-day forecast for coordinates")
def forecast(
    latitude: Annotated[float, Query(ge=-90, le=90)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
    _: UserPublic = Depends(require_roles(UserRole.FARMER, UserRole.AGRICULTURAL_OFFICER, UserRole.ADMIN)),
) -> WeatherResponse:
    try:
        return fetch_weather_forecast(latitude, longitude)
    except WeatherProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
