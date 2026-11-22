from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.advisory import AdvisoryKind


class AdvisoryCreate(BaseModel):
    title: str = Field(min_length=4, max_length=160)
    message: str = Field(min_length=10, max_length=3000)
    crop_name: str | None = Field(default=None, max_length=100)
    county: str | None = Field(default=None, max_length=80)
    source_name: str = Field(min_length=2, max_length=160)
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AdvisoryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=4, max_length=160)
    message: str | None = Field(default=None, min_length=10, max_length=3000)
    is_active: bool | None = None
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WeatherRecommendationRequest(BaseModel):
    farm_id: str = Field(pattern=r"^[0-9a-fA-F]{24}$")
    crop_id: str = Field(pattern=r"^[0-9a-fA-F]{24}$")
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def coordinates_must_be_paired(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must be provided together")
        return self


class AdvisoryPublic(BaseModel):
    id: str
    kind: AdvisoryKind
    title: str
    message: str
    crop_name: str | None = None
    county: str | None = None
    farm_id: str | None = None
    farmer_id: str | None = None
    author_id: str | None = None
    source_name: str
    weather_data: dict | None = None
    rules_applied: list[str] = Field(default_factory=list)
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid")


class AdvisoryListResponse(BaseModel):
    items: list[AdvisoryPublic]
    total: int
    limit: int
    offset: int


class CropCalendarStage(BaseModel):
    stage: str
    actions: list[str]


class CropCalendarReference(BaseModel):
    organization: str
    title: str
    url: str
    checked_at: str


class CropCalendarResponse(BaseModel):
    crop_id: str
    crop_name: str
    farm_id: str
    county: str
    planting_date: str
    schedule_type: str
    message: str
    stages: list[CropCalendarStage]
    sources: list[CropCalendarReference]


class SoilGuidanceRequest(BaseModel):
    farm_id: str = Field(pattern=r"^[0-9a-fA-F]{24}$")
    crop_id: str = Field(pattern=r"^[0-9a-fA-F]{24}$")
    soil_test_date: date | None = None
    soil_test_reference: str | None = Field(default=None, max_length=160)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SoilGuidanceResponse(AdvisoryPublic):
    soil_test_recommended: bool
    precise_rates_provided: bool
    sources: list[CropCalendarReference]


class PestKnowledgeSource(BaseModel):
    organization: str
    title: str
    url: str


class PestKnowledgePublic(BaseModel):
    slug: str
    common_name: str
    scientific_name: str | None
    crops_affected: list[str]
    identification: list[str]
    damage_signs: list[str]
    prevention_and_nonchemical_management: list[str]
    sources: list[PestKnowledgeSource]
    chemical_guidance_available: bool
    review_state: str
    source_checked_at: str

    model_config = ConfigDict(extra="forbid")


class PestKnowledgeList(BaseModel):
    items: list[PestKnowledgePublic]
    total: int
