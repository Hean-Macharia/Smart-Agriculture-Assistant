from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DiseasePredictionPublic(BaseModel):
    id: str
    farmer_id: str
    filename: str
    content_type: str
    file_size_bytes: int
    image_sha256: str
    predicted_label: str
    confidence: float = Field(ge=0, le=1)
    disclaimer: str
    created_at: datetime

    model_config = ConfigDict(extra="ignore")


class DiseasePredictionList(BaseModel):
    items: list[DiseasePredictionPublic]
    total: int
    limit: int
    offset: int
