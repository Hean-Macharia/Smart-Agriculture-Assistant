from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.schemas.weather import WeatherForecastPoint, WeatherObservation, WeatherResponse

OPENWEATHER_CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"
OPENWEATHER_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"


class WeatherProviderError(RuntimeError):
    pass


def _rain_mm(payload: dict) -> float:
    rain = payload.get("rain") or {}
    return float(rain.get("1h", rain.get("3h", 0.0)) or 0.0)


def _condition(payload: dict) -> str:
    weather = payload.get("weather") or []
    if not weather or not isinstance(weather[0], dict):
        return "Unknown"
    return str(weather[0].get("description") or weather[0].get("main") or "Unknown")[:120]


def fetch_weather_forecast(latitude: float, longitude: float) -> WeatherResponse:
    """Fetch current observations and five-day, three-hour forecast from OpenWeatherMap."""
    api_key = settings.weather_api_key.strip()
    if not api_key:
        raise WeatherProviderError("Weather provider is not configured")
    params = {"lat": latitude, "lon": longitude, "appid": api_key, "units": "metric"}
    try:
        with httpx.Client(timeout=httpx.Timeout(10.0, connect=4.0)) as client:
            current_response = client.get(OPENWEATHER_CURRENT_URL, params=params)
            forecast_response = client.get(OPENWEATHER_FORECAST_URL, params=params)
            current_response.raise_for_status()
            forecast_response.raise_for_status()
            current_data = current_response.json()
            forecast_data = forecast_response.json()
        current = WeatherObservation(
            observed_at=datetime.fromtimestamp(current_data["dt"], tz=timezone.utc),
            temperature_c=float(current_data["main"]["temp"]),
            rainfall_mm=_rain_mm(current_data),
            humidity_percent=int(current_data["main"]["humidity"]),
            conditions=_condition(current_data),
        )
        points = [
            WeatherForecastPoint(
                forecast_at=datetime.fromtimestamp(item["dt"], tz=timezone.utc),
                temperature_c=float(item["main"]["temp"]),
                rainfall_mm=_rain_mm(item),
                humidity_percent=int(item["main"]["humidity"]),
                conditions=_condition(item),
            )
            for item in forecast_data.get("list", [])
        ]
        if not points:
            raise WeatherProviderError("Weather provider returned no forecast points")
        return WeatherResponse(
            latitude=latitude,
            longitude=longitude,
            source="OpenWeatherMap",
            retrieved_at=datetime.now(timezone.utc),
            current=current,
            forecast=points,
        )
    except WeatherProviderError:
        raise
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        # Keep provider responses and request URLs private; URLs contain the API key.
        raise WeatherProviderError("Weather provider is temporarily unavailable or returned invalid data") from exc
