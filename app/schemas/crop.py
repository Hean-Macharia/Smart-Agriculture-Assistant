from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CropCreate(BaseModel):
    farm_id: str = Field(pattern=r"^[0-9a-fA-F]{24}$")
    name: str = Field(min_length=2, max_length=100)
    variety: str | None = Field(default=None, max_length=100)
    planting_date: date
    expected_harvest_date: date | None = None
    quantity: float | None = Field(default=None, ge=0)
    quantity_unit: str = Field(default="kg", min_length=1, max_length=30)
    growth_information: str | None = Field(default=None, max_length=2000)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def harvest_after_planting(self):
        if self.expected_harvest_date and self.expected_harvest_date < self.planting_date:
            raise ValueError("Expected harvest date cannot be before planting date")
        return self


class CropUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    variety: str | None = Field(default=None, max_length=100)
    planting_date: date | None = None
    expected_harvest_date: date | None = None
    quantity: float | None = Field(default=None, ge=0)
    quantity_unit: str | None = Field(default=None, min_length=1, max_length=30)
    growth_information: str | None = Field(default=None, max_length=2000)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def require_update(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        required_when_set = {"name", "planting_date", "quantity_unit"}
        if any(getattr(self, field) is None for field in required_when_set & self.model_fields_set):
            raise ValueError("Name, planting date, and quantity unit cannot be null")
        return self


class CropPublic(CropCreate):
    id: str
    owner_id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CropListResponse(BaseModel):
    items: list[CropPublic]
    total: int
    limit: int
    offset: int
