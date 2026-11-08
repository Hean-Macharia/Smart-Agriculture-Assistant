from datetime import datetime

from pydantic import BaseModel, Field


class WeatherObservation(BaseModel):
    observed_at: datetime
    temperature_c: float
    rainfall_mm: float
    humidity_percent: int = Field(ge=0, le=100)
    conditions: str


class WeatherForecastPoint(BaseModel):
    forecast_at: datetime
    temperature_c: float
    rainfall_mm: float
    humidity_percent: int = Field(ge=0, le=100)
    conditions: str


class WeatherResponse(BaseModel):
    latitude: float
    longitude: float
    source: str
    retrieved_at: datetime
    current: WeatherObservation
    forecast: list[WeatherForecastPoint]
