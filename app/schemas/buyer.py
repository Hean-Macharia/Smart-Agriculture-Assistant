from pydantic import BaseModel, ConfigDict, Field


class BuyerProfileUpsert(BaseModel):
    county: str = Field(min_length=2, max_length=80)
    sub_county: str = Field(min_length=2, max_length=80)
    delivery_location: str = Field(min_length=2, max_length=200)
    organization_name: str | None = Field(default=None, max_length=160)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BuyerProfile(BuyerProfileUpsert):
    id: str
    user_id: str
