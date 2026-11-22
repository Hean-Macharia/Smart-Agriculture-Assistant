import hashlib
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings
from app.schemas.weather import WeatherForecastPoint, WeatherObservation, WeatherResponse

OPENWEATHER_CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"
OPENWEATHER_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"


class WeatherProviderError(RuntimeError):
    pass


_weather_cache: dict[tuple, tuple[float, WeatherResponse]] = {}
_weather_cache_lock = threading.Lock()
_WEATHER_CACHE_MAX_ENTRIES = 256


def _rain_mm(payload: dict) -> float:
    rain = payload.get("rain") or {}
    return float(rain.get("1h", rain.get("3h", 0.0)) or 0.0)


def _condition(payload: dict) -> str:
    weather = payload.get("weather") or []
    if not weather or not isinstance(weather[0], dict):
        return "Unknown"
    return str(weather[0].get("description") or weather[0].get("main") or "Unknown")[:120]


def _fetch_weather_forecast_uncached(latitude: float, longitude: float, api_key: str) -> WeatherResponse:
    """Fetch current observations and five-day, three-hour forecast from OpenWeatherMap."""
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


def fetch_weather_forecast(latitude: float, longitude: float) -> WeatherResponse:
    """Return a short-lived per-location forecast cache or fetch real provider data."""
    api_key = settings.weather_api_key.strip()
    if not api_key:
        raise WeatherProviderError("Weather provider is not configured")
    ttl = settings.weather_cache_ttl_seconds
    key = (round(latitude, 5), round(longitude, 5), hashlib.sha256(api_key.encode("utf-8")).hexdigest())
    now = time.monotonic()
    if ttl > 0:
        with _weather_cache_lock:
            cached = _weather_cache.get(key)
            if cached and cached[0] > now:
                expiry = datetime.now(timezone.utc) + timedelta(seconds=cached[0] - now)
                return cached[1].model_copy(update={"cache_hit": True, "cache_valid_until": expiry})
            _weather_cache.pop(key, None)
    result = _fetch_weather_forecast_uncached(latitude, longitude, api_key)
    if ttl > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        result = result.model_copy(update={"cache_hit": False, "cache_valid_until": expires_at})
        with _weather_cache_lock:
            if len(_weather_cache) >= _WEATHER_CACHE_MAX_ENTRIES:
                oldest_key = min(_weather_cache, key=lambda item: _weather_cache[item][0])
                _weather_cache.pop(oldest_key, None)
            _weather_cache[key] = (time.monotonic() + ttl, result)
    return result


def clear_weather_cache() -> None:
    """Clear in-process weather cache (used by tests and controlled operations)."""
    with _weather_cache_lock:
        _weather_cache.clear()
