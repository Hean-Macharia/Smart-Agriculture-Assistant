"""Farmer-owned disease follow-up and retrospective treatment records."""

import hashlib
from pathlib import Path

from app.core.config import settings
from app.ml.disease_model import predict_disease
from app.models.disease import TreatmentRecordType
from app.models.pesticide import PesticideReviewStatus
from app.repositories.disease_followup_repository import DiseaseFollowupRepository
from app.repositories.disease_report_repository import DiseaseReportRepository
from app.repositories.disease_treatment_repository import DiseaseTreatmentRepository
from app.repositories.pesticide_repository import PesticideRepository
from app.services.disease_knowledge_service import get_disease_knowledge

MONITORING_DISCLAIMER = (
    "This is a farmer-entered activity record, not a treatment instruction or endorsement. "
    "For chemicals, follow the current approved PCPB label and seek extension advice."
)
FOLLOWUP_DISCLAIMER = (
    "Follow-up model screening is preliminary and may be wrong. Compare field conditions "
    "and ask an agricultural extension officer if symptoms worsen or remain uncertain. "
    "The original image is not retained; only its hash and screening metadata are stored."
)


class DiseaseReportNotFound(Exception):
    """The requested report is missing or does not belong to this farmer."""


class ApprovedPesticideRecordRequired(Exception):
    """Chemical history requires a reviewed PCPB record with a matching crop and use."""


class DiseaseCaseTransitionConflict(Exception):
    """A disease case cannot make the requested status transition."""


def _crop_name_for_label(model_label: str) -> str | None:
    prefix = model_label.partition("___")[0].casefold()
    return {"corn_(maize)": "maize", "potato": "potato", "tomato": "tomato"}.get(prefix)


def create_treatment_record(
    *,
    reports: DiseaseReportRepository,
    treatments: DiseaseTreatmentRepository,
    pesticides: PesticideRepository,
    farmer_id: str,
    report_id: str,
    idempotency_key: str,
    values: dict,
):
    report = reports.get_for_farmer(report_id, farmer_id)
    if report is None:
        raise DiseaseReportNotFound
    prior = treatments.get_by_idempotency_key(idempotency_key)
    if prior:
        if prior["disease_report_id"] == report_id and prior["farmer_id"] == farmer_id:
            return prior, False
        from app.repositories.disease_treatment_repository import TreatmentIdempotencyConflict

        raise TreatmentIdempotencyConflict

    pesticide_number = None
    product_id = values.get("pesticide_record_id")
    if values["treatment_type"] == TreatmentRecordType.CHEMICAL or values["treatment_type"] == TreatmentRecordType.CHEMICAL.value:
        product = pesticides.get(product_id) if product_id else None
        crop_name = _crop_name_for_label(report["predicted_label"])
        knowledge = get_disease_knowledge(report["predicted_label"])
        disease_name = knowledge["display_name"].partition("–")[2].strip().casefold() if knowledge else ""
        registered_uses = product.get("registered_uses", []) if product else []
        matching_use = any(
            crop_name
            and crop_name in use.casefold()
            and disease_name
            and disease_name in use.casefold()
            for use in registered_uses
        )
        if (
            not product
            or product.get("review_status") != PesticideReviewStatus.APPROVED.value
            or not matching_use
        ):
            raise ApprovedPesticideRecordRequired
        pesticide_number = product["registration_number"]

    record, created = treatments.create({
        "disease_report_id": report_id,
        "farmer_id": farmer_id,
        "treatment_type": values["treatment_type"].value if hasattr(values["treatment_type"], "value") else values["treatment_type"],
        "action_record": values["action_record"],
        "started_on": values["started_on"],
        "pesticide_record_id": product_id,
        "pesticide_registration_number": pesticide_number,
        "idempotency_key": idempotency_key,
        "disclaimer": MONITORING_DISCLAIMER,
    })
    return record, created


def create_followup_screening(
    *,
    reports: DiseaseReportRepository,
    followups: DiseaseFollowupRepository,
    farmer_id: str,
    report_id: str,
    idempotency_key: str,
    filename: str,
    content_type: str,
    image_bytes: bytes,
    observation: str | None,
):
    report = reports.get_for_farmer(report_id, farmer_id)
    if report is None:
        raise DiseaseReportNotFound
    prior = followups.get_by_idempotency_key(idempotency_key)
    if prior:
        if prior["disease_report_id"] == report_id and prior["farmer_id"] == farmer_id:
            return prior, False
        from app.repositories.disease_followup_repository import FollowupIdempotencyConflict

        raise FollowupIdempotencyConflict
    label, confidence = predict_disease(image_bytes)
    same_label = label == report["predicted_label"]
    threshold = settings.disease_confidence_threshold
    safe_filename = Path(filename or "followup-crop-image").name[:160]
    return followups.create({
        "disease_report_id": report_id,
        "farmer_id": farmer_id,
        "filename": safe_filename,
        "content_type": content_type,
        "file_size_bytes": len(image_bytes),
        "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
        "predicted_label": label,
        "confidence": confidence,
        "confidence_threshold": threshold,
        "is_uncertain": confidence < threshold,
        "comparison_to_initial": "SAME_LABEL" if same_label else "DIFFERENT_LABEL",
        "comparison_note": (
            "The follow-up and initial screening returned the same model class. This does not confirm disease status or progression."
            if same_label
            else "The follow-up and initial screening returned different model classes. This alone does not show improvement or worsening."
        ),
        "observation": observation.strip()[:500] if observation else None,
        "idempotency_key": idempotency_key,
        "disclaimer": FOLLOWUP_DISCLAIMER,
    })


def get_disease_monitoring(*, reports, followups, treatments, farmer_id: str, report_id: str):
    report = reports.get_for_farmer(report_id, farmer_id)
    if report is None:
        raise DiseaseReportNotFound
    return {
        "disease_report": report,
        "followups": followups.list_for_report(report_id, farmer_id),
        "treatments": treatments.list_for_report(report_id, farmer_id),
    }


def request_officer_review(*, reports, farmer_id: str, report_id: str):
    report = reports.request_review(report_id, farmer_id)
    if report is None:
        raise DiseaseCaseTransitionConflict
    return report


def resolve_disease_case(*, reports, farmer_id: str, report_id: str):
    report = reports.resolve(report_id, farmer_id)
    if report is None:
        raise DiseaseCaseTransitionConflict
    return report


def review_disease_case(*, reports, officer_id: str, report_id: str, note: str):
    report = reports.record_officer_review(report_id, officer_id, note)
    if report is None:
        raise DiseaseCaseTransitionConflict
    return report
