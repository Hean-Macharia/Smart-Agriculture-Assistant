from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

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
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    model_config = ConfigDict(extra="forbid")


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
