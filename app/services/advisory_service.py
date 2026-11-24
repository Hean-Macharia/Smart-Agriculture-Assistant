from app.models.advisory import AdvisoryKind
from app.repositories.advisory_repository import AdvisoryRepository
from app.repositories.crop_repository import CropRepository
from app.repositories.farm_repository import FarmRepository
from app.schemas.weather import WeatherResponse


class AdvisoryAccessError(Exception):
    pass


def create_officer_advisory(repository: AdvisoryRepository, author_id: str, payload: dict) -> dict:
    return repository.create({**payload, "kind": AdvisoryKind.OFFICER.value, "author_id": author_id, "is_active": True, "farm_id": None, "farmer_id": None, "weather_data": None, "rules_applied": []})


def update_officer_advisory(repository: AdvisoryRepository, advisory_id: str, author_id: str, changes: dict, *, is_admin: bool):
    advisory = repository.update_officer(advisory_id, author_id, changes, is_admin=is_admin)
    if advisory is None:
        raise AdvisoryAccessError
    return advisory


def create_weather_recommendation(*, repository: AdvisoryRepository, farms: FarmRepository, crops: CropRepository, farmer_id: str, farm_id: str, crop_id: str, weather: WeatherResponse):
    farm = farms.get(farm_id)
    crop = crops.get(crop_id)
    if farm is None or farm["owner_id"] != farmer_id or crop is None or crop["owner_id"] != farmer_id or crop["farm_id"] != farm_id:
        raise AdvisoryAccessError

    next_24h = weather.forecast[:8]
    rainfall_24h = round(sum(point.rainfall_mm for point in next_24h), 1)
    rules = []
    messages = []
    crop_name = crop["name"]
    if rainfall_24h < 5:
        rules.append("LOW_RAINFALL_24H")
        messages.append(f"For {crop_name}, the forecast shows {rainfall_24h} mm rainfall over approximately 24 hours. Check soil moisture and crop stage before deciding whether irrigation is needed.")
    if rainfall_24h >= 25:
        rules.append("HIGH_RAINFALL_24H")
        messages.append(f"For {crop_name}, the forecast shows {rainfall_24h} mm rainfall over approximately 24 hours. Monitor field drainage and local weather alerts.")
    if not messages:
        messages.append(f"For {crop_name}, the forecast shows {rainfall_24h} mm rainfall over approximately 24 hours. Use local soil and crop-stage observations when planning field work.")
    crop_context = {
        "planting_date": str(crop.get("planting_date")) if crop.get("planting_date") else None,
        "expected_harvest_date": str(crop.get("expected_harvest_date")) if crop.get("expected_harvest_date") else None,
        "growth_information": str(crop.get("growth_information") or "")[:300] or None,
    }
    location = ", ".join(part for part in (farm.get("location"), farm.get("county")) if part)
    context_parts = []
    if location:
        context_parts.append(f"Farm location on record: {location}.")
    if crop_context["planting_date"]:
        context_parts.append(f"Crop record planting date: {crop_context['planting_date']}.")
    if crop_context["expected_harvest_date"]:
        context_parts.append(f"Expected harvest recorded: {crop_context['expected_harvest_date']}.")
    if crop_context["growth_information"]:
        context_parts.append(f"Farmer-recorded growth notes: {crop_context['growth_information']}.")
    if context_parts:
        context_parts.append("Use these recorded details with direct field observations; the project rules do not infer a verified crop growth stage.")
        messages.append(" ".join(context_parts))
    messages.append("This is a weather-triggered rule-based prompt, not a diagnosis or guaranteed agronomic recommendation. Confirm crop decisions with a county agricultural extension officer.")
    current = weather.current
    summary = {
        "source": weather.source,
        "retrieved_at": weather.retrieved_at.isoformat(),
        "temperature_c": current.temperature_c,
        "rainfall_mm": current.rainfall_mm,
        "humidity_percent": current.humidity_percent,
        "conditions": current.conditions,
        "forecast_rainfall_24h_mm": rainfall_24h,
        "farm_location": location or None,
        "crop_context": crop_context,
    }
    return repository.create({
        "kind": AdvisoryKind.WEATHER_RULE.value,
        "title": f"Weather guidance for {crop_name}",
        "message": " ".join(messages),
        "crop_name": crop_name,
        "county": farm["county"],
        "farm_id": farm_id,
        "farmer_id": farmer_id,
        "author_id": None,
        "source_name": "OpenWeatherMap forecast plus transparent project rules",
        "weather_data": summary,
        "rules_applied": rules,
        "is_active": True,
    })
