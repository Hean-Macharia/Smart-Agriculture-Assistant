from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.marketplace import ProductAvailability


class ProductCreate(BaseModel):
    product_name: str = Field(min_length=2, max_length=120)
    category: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=5, max_length=2000)
    quantity_available: int = Field(gt=0, le=2_000_000_000)
    unit: str = Field(min_length=1, max_length=30)
    price_per_unit_kes: int = Field(gt=0, le=2_000_000_000)
    county: str = Field(min_length=2, max_length=80)
    sub_county: str = Field(min_length=2, max_length=80)
    product_images: list[str] = Field(default_factory=list, max_length=10)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProductUpdate(BaseModel):
    product_name: str | None = Field(default=None, min_length=2, max_length=120)
    category: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, min_length=5, max_length=2000)
    quantity_available: int | None = Field(default=None, ge=0, le=2_000_000_000)
    unit: str | None = Field(default=None, min_length=1, max_length=30)
    price_per_unit_kes: int | None = Field(default=None, gt=0, le=2_000_000_000)
    county: str | None = Field(default=None, min_length=2, max_length=80)
    sub_county: str | None = Field(default=None, min_length=2, max_length=80)
    product_images: list[str] | None = Field(default=None, max_length=10)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        nullable = set()
        if any(getattr(self, name) is None for name in self.model_fields_set - nullable):
            raise ValueError("Product fields cannot be set to null")
        return self


class ProductPublic(BaseModel):
    id: str
    farmer_id: str
    product_name: str
    category: str
    description: str
    quantity_available: int = Field(ge=0)
    unit: str
    price_per_unit_kes: int
    county: str
    sub_county: str
    product_images: list[str]
    availability_status: ProductAvailability
    created_at: datetime
    updated_at: datetime


class ProductListResponse(BaseModel):
    items: list[ProductPublic]
    total: int
    limit: int
    offset: int
