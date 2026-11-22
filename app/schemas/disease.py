from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.disease import DiseaseCaseStatus, TreatmentRecordType


class DiseaseKnowledgeSource(BaseModel):
    organization: str
    title: str
    url: str
    reference: str

    model_config = ConfigDict(extra="forbid")


class DiseaseKnowledgePublic(BaseModel):
    model_label: str
    crop_name: str
    display_name: str
    scientific_name: str | None
    summary: str
    symptoms: list[str]
    general_guidance: list[str]
    sources: list[DiseaseKnowledgeSource]
    source_checked_at: str
    review_state: str
    guidance_status: str
    chemical_guidance_available: bool
    disclaimer: str

    model_config = ConfigDict(extra="forbid")


class DiseaseKnowledgeList(BaseModel):
    items: list[DiseaseKnowledgePublic]
    total: int


class DiseaseOfficerReviewPublic(BaseModel):
    officer_id: str
    note: str
    at: datetime

    model_config = ConfigDict(extra="forbid")


class DiseasePredictionPublic(BaseModel):
    id: str
    farmer_id: str
    filename: str
    content_type: str
    file_size_bytes: int
    image_sha256: str
    predicted_label: str
    confidence: float = Field(ge=0, le=1)
    confidence_threshold: float = Field(default=0.60, ge=0, le=1)
    is_uncertain: bool | None = None
    uncertainty_message: str | None = None
    disclaimer: str
    created_at: datetime
    case_status: DiseaseCaseStatus = DiseaseCaseStatus.OPEN
    review_requested_at: datetime | None = None
    resolved_at: datetime | None = None
    officer_reviews: list[DiseaseOfficerReviewPublic] = Field(default_factory=list)

    # The repository explicitly maps and removes internal MongoDB fields.
    # Reject unexpected output keys so schema drift is visible during testing.
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def explain_low_confidence(self):
        uncertain = self.confidence < self.confidence_threshold
        if self.is_uncertain is None:
            self.is_uncertain = uncertain
        if uncertain and not self.uncertainty_message:
            self.uncertainty_message = "The model confidence is below this system's screening threshold. Take a clearer photo and ask an agricultural officer to review the crop; do not treat this as a confirmed diagnosis."
        return self


class DiseasePredictionList(BaseModel):
    items: list[DiseasePredictionPublic]
    total: int
    limit: int
    offset: int


class DiseaseTreatmentCreate(BaseModel):
    treatment_type: TreatmentRecordType
    action_record: str = Field(min_length=5, max_length=1000)
    started_on: date
    pesticide_record_id: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{24}$")

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def chemical_requires_reviewed_record(self):
        if self.treatment_type == TreatmentRecordType.CHEMICAL and not self.pesticide_record_id:
            raise ValueError("A chemical treatment log must reference an approved PCPB evidence record")
        if self.treatment_type != TreatmentRecordType.CHEMICAL and self.pesticide_record_id:
            raise ValueError("A PCPB product record may only be attached to a chemical treatment log")
        return self


class DiseaseTreatmentPublic(BaseModel):
    id: str
    disease_report_id: str
    farmer_id: str
    treatment_type: TreatmentRecordType
    action_record: str
    started_on: date
    pesticide_record_id: str | None
    pesticide_registration_number: str | None
    idempotency_key: str
    disclaimer: str
    created_at: datetime

    model_config = ConfigDict(extra="forbid")


class DiseaseFollowupPublic(BaseModel):
    id: str
    disease_report_id: str
    farmer_id: str
    filename: str
    content_type: str
    file_size_bytes: int
    image_sha256: str
    predicted_label: str
    confidence: float = Field(ge=0, le=1)
    confidence_threshold: float = Field(default=0.60, ge=0, le=1)
    is_uncertain: bool | None = None
    uncertainty_message: str | None = None
    comparison_to_initial: str = "NOT_AVAILABLE"
    comparison_note: str = "Comparison was not recorded for this screening."
    observation: str | None
    idempotency_key: str
    created_at: datetime
    disclaimer: str

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def explain_low_confidence(self):
        uncertain = self.confidence < self.confidence_threshold
        if self.is_uncertain is None:
            self.is_uncertain = uncertain
        if uncertain and not self.uncertainty_message:
            self.uncertainty_message = "This follow-up result is uncertain. Use a clearer image and request an agricultural officer review if the crop concern remains."
        return self


class DiseaseMonitoringResponse(BaseModel):
    disease_report: DiseasePredictionPublic
    treatments: list[DiseaseTreatmentPublic]
    followups: list[DiseaseFollowupPublic]


class DiseaseOfficerReviewRequest(BaseModel):
    note: str = Field(min_length=10, max_length=1000)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
