from datetime import date, datetime
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.pesticide import PesticideReviewDecision, PesticideReviewStatus


def _validate_pcpb_url(value: str) -> str:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host == "pcpb.go.ke" or host.endswith(".pcpb.go.ke")):
        raise ValueError("URL must be an HTTPS page on the official PCPB domain")
    return value


class PesticideRecordCreate(BaseModel):
    registration_number: str = Field(min_length=3, max_length=80)
    trade_name: str = Field(min_length=2, max_length=160)
    formulation: str = Field(min_length=2, max_length=120)
    active_ingredients: list[str] = Field(min_length=1, max_length=10)
    registered_uses: list[str] = Field(min_length=1, max_length=30)
    pcpb_record_url: str = Field(min_length=12, max_length=500)
    approved_label_url: str = Field(min_length=12, max_length=500)
    source_checked_on: date
    source_reference: str = Field(min_length=3, max_length=300)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("pcpb_record_url", "approved_label_url")
    @classmethod
    def official_pcpb_sources_only(cls, value: str) -> str:
        return _validate_pcpb_url(value)


class PesticideReviewRequest(BaseModel):
    decision: PesticideReviewDecision
    review_note: str = Field(min_length=10, max_length=1000)
    registration_and_label_verified: bool = False
    source_checked_on: date

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def require_verified_sources_for_approval(self):
        if self.decision == PesticideReviewDecision.APPROVE and not self.registration_and_label_verified:
            raise ValueError("Approval requires explicit confirmation of the current PCPB registration and approved label")
        return self


class PesticideReviewEventPublic(BaseModel):
    reviewer_id: str
    decision: PesticideReviewDecision
    note: str
    registration_and_label_verified: bool
    source_checked_on: date
    at: datetime

    model_config = ConfigDict(extra="forbid")


class PesticideRecordPublic(BaseModel):
    id: str
    registration_number: str
    trade_name: str
    formulation: str
    active_ingredients: list[str]
    registered_uses: list[str]
    pcpb_record_url: str
    approved_label_url: str
    source_checked_on: date
    source_reference: str
    review_status: PesticideReviewStatus
    submitted_by: str
    review_events: list[PesticideReviewEventPublic]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid")


class PesticideRecordList(BaseModel):
    items: list[PesticideRecordPublic]
    total: int
    limit: int
    offset: int
