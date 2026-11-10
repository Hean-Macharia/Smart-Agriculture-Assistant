import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.payment import PaymentRecordStatus


class PaymentInitiateRequest(BaseModel):
    order_id: str = Field(pattern=r"^[0-9a-fA-F]{24}$")
    phone_number: str = Field(min_length=10, max_length=20)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("phone_number")
    @classmethod
    def normalize_ke_phone(cls, value: str) -> str:
        value = re.sub(r"[\s()-]", "", value)
        if re.fullmatch(r"0[17]\d{8}", value):
            value = "254" + value[1:]
        elif value.startswith("+254"):
            value = value[1:]
        if not re.fullmatch(r"254[17]\d{8}", value):
            raise ValueError("Use a valid Kenyan mobile number")
        return value


class PaymentPublic(BaseModel):
    id: str
    order_id: str
    buyer_id: str
    provider: str
    status: PaymentRecordStatus
    amount_kes: int
    currency: str
    phone_number: str
    merchant_reference: str
    checkout_request_id: str | None = None
    provider_receipt: str | None = None
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid")


class PaymentListResponse(BaseModel):
    items: list[PaymentPublic]
    total: int
    limit: int
    offset: int


class MockCallbackSimulation(BaseModel):
    success: bool = True
    amount_kes: int | None = Field(default=None, ge=1)

    model_config = ConfigDict(extra="forbid")


class CallbackAcknowledgement(BaseModel):
    accepted: bool
    result_code: int
    result_description: str
