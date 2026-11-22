"""Source-linked crop-stage prompts and conservative soil education."""

from app.models.advisory import AdvisoryKind

CHECKED_AT = "2026-11-22"

_CALENDARS = {
    "maize": {
        "name": "Maize",
        "sources": [{"organization": "KALRO", "title": "Maize Good Agricultural Practices", "url": "https://keep.kalro.org/good-agricultural-practices/Maize", "checked_at": CHECKED_AT}],
        "stages": [
            {"stage": "Before planting", "actions": ["Review local county and agro-ecological guidance for variety and planting timing.", "Check that the field is well drained and prepare the site using locally recommended practice."]},
            {"stage": "Establishment and vegetative growth", "actions": ["Record emergence and crop observations.", "Check the field regularly for weeds, water stress, and unusual leaf symptoms.", "Use soil-test or extension advice for nutrient decisions; no fertilizer rate is inferred here."]},
            {"stage": "Reproductive growth", "actions": ["Continue crop-health scouting and record changes.", "Use local extension advice when weather, pests, or disease concerns affect the crop."]},
            {"stage": "Harvest and post-harvest", "actions": ["Use maturity and safe handling guidance from the KALRO reference and local extension staff.", "Record the actual harvest date for future farm planning."]},
        ],
    },
    "tomato": {
        "name": "Tomato",
        "sources": [{"organization": "KALRO", "title": "Tomato Value Chain: Agronomic Practices in Open Field Tomato Cultivation", "url": "https://keep.kalro.org/appfiles/media/vc_files/tomato-training-manual-8-12-20.pdf", "checked_at": CHECKED_AT}],
        "stages": [
            {"stage": "Site preparation", "actions": ["Review site suitability, drainage, and land preparation with local extension guidance.", "Plan access to water and record the planting or transplanting date."]},
            {"stage": "Establishment", "actions": ["Monitor transplant establishment and field moisture using direct observation.", "Keep records of crop condition and seek soil-test guidance before choosing nutrient inputs."]},
            {"stage": "Crop maintenance", "actions": ["Scout for weeds and unusual symptoms; record what is observed.", "Use locally appropriate guidance for irrigation, support, pruning, and nutrition; practices vary by production system."]},
            {"stage": "Harvest and post-harvest", "actions": ["Use maturity, harvesting, and handling guidance from the KALRO manual and local extension staff.", "Record harvest observations and any quality issues."]},
        ],
    },
    "potato": {
        "name": "Potato",
        "sources": [{"organization": "KALRO", "title": "Good Agricultural Practices and Food Safety Management Systems: Potato Value Chain", "url": "https://keep.kalro.org/appfiles/media/vc_files/Potato-ToT-8-June-2021.pdf", "checked_at": CHECKED_AT}],
        "stages": [
            {"stage": "Before planting", "actions": ["Use locally suitable planting-material and field-selection guidance from KALRO or county extension.", "Plan field hygiene and risk-prevention practices."]},
            {"stage": "Establishment and crop growth", "actions": ["Scout and keep records of crop condition, weeds, and unusual symptoms.", "Use integrated crop and pest management principles and seek local advice when a problem is uncertain."]},
            {"stage": "Harvest and post-harvest", "actions": ["Follow local maturity, handling, and food-safety guidance.", "Record harvest date, quality, and storage observations."]},
        ],
    },
}

_SOIL_SOURCES = [
    {"organization": "Ministry of Agriculture and Livestock Development, Kenya", "title": "Agricultural Soil Management Policy 2023", "url": "https://kilimo.go.ke/wp-content/uploads/2025/02/Agricultural-Soil-Management-Policy-2023.pdf", "checked_at": CHECKED_AT},
    {"organization": "Ministry of Agriculture and Livestock Development, Kenya", "title": "Training Manual: Soil Sampling and Testing", "url": "https://kilimo.go.ke/wp-content/uploads/2025/07/Training-Manual.pdf", "checked_at": CHECKED_AT},
]


class CropPlanningNotFound(Exception):
    """Crop or owned farm/crop relationship is missing, or no verified entry exists."""


def create_crop_calendar(*, crops, farms, farmer_id: str, crop_id: str):
    crop = crops.get(crop_id)
    if crop is None or crop["owner_id"] != farmer_id:
        raise CropPlanningNotFound
    farm = farms.get(crop["farm_id"])
    if farm is None or farm["owner_id"] != farmer_id:
        raise CropPlanningNotFound
    normalized_name = crop["name"].strip().casefold()
    normalized_name = {"tomatoes": "tomato", "potatoes": "potato", "corn": "maize", "maize/corn": "maize"}.get(normalized_name, normalized_name)
    entry = _CALENDARS.get(normalized_name)
    if entry is None:
        raise CropPlanningNotFound
    return {
        "crop_id": crop_id,
        "crop_name": entry["name"],
        "farm_id": crop["farm_id"],
        "county": farm["county"],
        "planting_date": str(crop["planting_date"]),
        "schedule_type": "STAGE_ORDER_ONLY",
        "message": "This source-linked checklist is organized by crop stage; it does not infer county planting dates or fixed day intervals. Confirm local timing and variety advice with county extension staff.",
        "stages": entry["stages"],
        "sources": entry["sources"],
    }


def create_soil_guidance(*, repository, crops, farms, farmer_id: str, farm_id: str, crop_id: str, soil_test_date=None, soil_test_reference=None):
    farm = farms.get(farm_id)
    crop = crops.get(crop_id)
    if farm is None or farm["owner_id"] != farmer_id or crop is None or crop["owner_id"] != farmer_id or crop["farm_id"] != farm_id:
        raise CropPlanningNotFound
    test_summary = (
        f"A soil test was recorded as dated {soil_test_date} ({soil_test_reference or 'reference not supplied'}). "
        "Use the laboratory report with a qualified extension professional; this service does not interpret nutrient values."
        if soil_test_date
        else "No soil test is recorded for this request. Consider a representative soil test and use its laboratory report with qualified extension advice."
    )
    message = (
        f"General soil education for {crop['name']} on your {farm['county']} farm: {test_summary} "
        "Do not select fertilizer type or quantity from soil type or crop name alone. Maintain soil cover and use suitable organic matter practices where locally appropriate. "
        "This system provides no nutrient rate, product, or application schedule."
    )
    return repository.create({
        "kind": AdvisoryKind.SOIL_EDUCATION.value,
        "title": f"Soil information for {crop['name']}",
        "message": message,
        "crop_name": crop["name"],
        "county": farm["county"],
        "farm_id": farm_id,
        "farmer_id": farmer_id,
        "author_id": None,
        "source_name": "Kenya Ministry of Agriculture soil-management references",
        "weather_data": {"soil_test_date": soil_test_date, "soil_test_reference": soil_test_reference},
        "rules_applied": ["SOIL_TEST_FIRST", "NO_UNSUPPORTED_NUTRIENT_RATES"],
        "is_active": True,
        "soil_test_recommended": True,
        "precise_rates_provided": False,
        "sources": _SOIL_SOURCES,
    })
