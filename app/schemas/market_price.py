from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.market_price import MarketPriceSource


class MarketPriceCreate(BaseModel):
    crop_name: str = Field(min_length=2, max_length=100)
    market_location: str = Field(min_length=2, max_length=120)
    county: str = Field(min_length=2, max_length=80)
    price_kes: int = Field(gt=0, le=2_000_000_000)
    unit: str = Field(min_length=1, max_length=30)
    date_collected: date
    data_source: MarketPriceSource = MarketPriceSource.MANUAL
    source_name: str = Field(min_length=2, max_length=160)
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MarketPriceUpdate(BaseModel):
    price_kes: int = Field(gt=0, le=2_000_000_000)
    date_collected: date
    source_name: str = Field(min_length=2, max_length=160)
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MarketPricePublic(BaseModel):
    id: str
    crop_name: str
    market_location: str
    county: str
    price_kes: int
    unit: str
    date_collected: date
    data_source: MarketPriceSource
    source_name: str
    recorded_by: str
    supersedes_id: str | None = None
    created_at: datetime

    model_config = ConfigDict(extra="forbid")


class MarketPriceListResponse(BaseModel):
    items: list[MarketPricePublic]
    total: int
    limit: int
    offset: int


class MarketPriceComparison(BaseModel):
    crop_name: str
    county: str | None
    items: list[MarketPricePublic]
