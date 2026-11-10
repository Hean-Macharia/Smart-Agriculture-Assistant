from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FarmerProfileUpsert(BaseModel):
    county: str = Field(min_length=2, max_length=80)
    sub_county: str = Field(min_length=2, max_length=80)
    location: str = Field(min_length=2, max_length=160)
    farm_size_acres: float = Field(gt=0, le=100000)
    soil_type: str = Field(min_length=2, max_length=80)
    irrigation_available: bool
    crops_grown: list[str] = Field(default_factory=list, max_length=50)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FarmerProfile(FarmerProfileUpsert):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
