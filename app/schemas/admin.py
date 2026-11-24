from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AdminListResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")


class AdminOverview(BaseModel):
    counts: dict[str, Any]
    trends: dict[str, list[dict[str, Any]]]
    disease_by_condition: list[dict[str, Any]]
    disease_by_crop: list[dict[str, Any]]
    marketplace_by_county: list[dict[str, Any]]
    payment_statuses: list[dict[str, Any]] = Field(default_factory=list)
    order_statuses: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
