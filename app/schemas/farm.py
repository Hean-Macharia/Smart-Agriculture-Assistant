from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FarmCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    county: str = Field(min_length=2, max_length=80)
    sub_county: str = Field(min_length=2, max_length=80)
    location: str = Field(min_length=2, max_length=160)
    size_acres: float = Field(gt=0, le=100000)
    soil_type: str = Field(min_length=2, max_length=80)
    irrigation_available: bool = False
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def coordinates_must_be_paired(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must be saved together")
        return self


class FarmUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    county: str | None = Field(default=None, min_length=2, max_length=80)
    sub_county: str | None = Field(default=None, min_length=2, max_length=80)
    location: str | None = Field(default=None, min_length=2, max_length=160)
    size_acres: float | None = Field(default=None, gt=0, le=100000)
    soil_type: str | None = Field(default=None, min_length=2, max_length=80)
    irrigation_available: bool | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def require_non_null_update(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Farm fields cannot be set to null")
        return self

    @model_validator(mode="after")
    def coordinates_must_be_paired(self):
        if ("latitude" in self.model_fields_set) != ("longitude" in self.model_fields_set):
            raise ValueError("Latitude and longitude must be updated together")
        return self


class FarmPublic(FarmCreate):
    id: str
    owner_id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class FarmListResponse(BaseModel):
    items: list[FarmPublic]
    total: int
    limit: int
    offset: int
