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

    # The repository explicitly maps and removes internal MongoDB fields.
    # Reject unexpected output keys so schema drift is visible during testing.
    model_config = ConfigDict(extra="forbid")


class DiseasePredictionList(BaseModel):
    items: list[DiseasePredictionPublic]
    total: int
    limit: int
    offset: int
