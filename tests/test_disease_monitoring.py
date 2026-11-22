from datetime import date, datetime, timezone

import numpy as np
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.core.dependencies import (
    get_current_user,
    get_disease_followup_repository,
    get_disease_report_repository,
    get_disease_treatment_repository,
    get_pesticide_repository,
)
from app.main import app
from app.ml.model_loader import DiseaseModelUnavailable
from app.models.pesticide import PesticideReviewStatus
from app.models.user import UserRole
from app.schemas.user import UserPublic
from app.services import disease_monitoring_service

FARMER_ID = "64b000000000000000000041"
OTHER_FARMER_ID = "64b000000000000000000042"
REPORT_ID = "64b000000000000000000043"
PESTICIDE_ID = "64b000000000000000000044"


def make_user(user_id=FARMER_ID, role=UserRole.FARMER):
    now = datetime.now(timezone.utc)
    return UserPublic(
        id=user_id,
        full_name="Test Farmer",
        email="farmer@example.test",
        phone="+254700000000",
        role=role,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


class MemoryReports:
    def __init__(self):
        self.report = {
            "id": REPORT_ID,
            "farmer_id": FARMER_ID,
            "filename": "leaf.png",
            "content_type": "image/png",
            "file_size_bytes": 20,
            "image_sha256": "a" * 64,
            "predicted_label": "Tomato___Early_blight",
            "confidence": 0.9,
            "disclaimer": "Screening only.",
            "created_at": datetime.now(timezone.utc),
        }

    def get_for_farmer(self, report_id, farmer_id):
        return self.report if report_id == REPORT_ID and farmer_id == FARMER_ID else None

    def request_review(self, report_id, farmer_id):
        report = self.get_for_farmer(report_id, farmer_id)
        if report and report.get("case_status", "OPEN") == "OPEN":
            report["case_status"] = "REVIEW_REQUESTED"
            report["review_requested_at"] = datetime.now(timezone.utc)
            return report
        return None

    def resolve(self, report_id, farmer_id):
        report = self.get_for_farmer(report_id, farmer_id)
        if report and report.get("case_status", "OPEN") in {"OPEN", "REVIEW_REQUESTED"}:
            report["case_status"] = "RESOLVED"
            report["resolved_at"] = datetime.now(timezone.utc)
            return report
        return None

    def list_review_requested(self, *, skip, limit):
        items = [self.report] if self.report.get("case_status") == "REVIEW_REQUESTED" else []
        return items[skip:skip + limit], len(items)

    def record_officer_review(self, report_id, officer_id, note):
        if report_id != REPORT_ID or self.report.get("case_status") != "REVIEW_REQUESTED":
            return None
        self.report.setdefault("officer_reviews", []).append({"officer_id": officer_id, "note": note, "at": datetime.now(timezone.utc)})
        self.report["case_status"] = "OPEN"
        return self.report


class MemoryIdempotentRecords:
    def __init__(self):
        self.records = {}

    def get_by_idempotency_key(self, key):
        return self.records.get(key)

    def create(self, values):
        from app.repositories.disease_followup_repository import FollowupIdempotencyConflict
        from app.repositories.disease_treatment_repository import TreatmentIdempotencyConflict

        key = values["idempotency_key"]
        if key in self.records:
            old = self.records[key]
            if old["disease_report_id"] == values["disease_report_id"] and old["farmer_id"] == values["farmer_id"]:
                return old, False
            conflict = FollowupIdempotencyConflict if "image_sha256" in values else TreatmentIdempotencyConflict
            raise conflict
        record = {
            **values,
            "id": str(ObjectId()),
            "created_at": datetime.now(timezone.utc),
        }
        record["disease_report_id"] = str(record["disease_report_id"])
        record["farmer_id"] = str(record["farmer_id"])
        if record.get("pesticide_record_id"):
            record["pesticide_record_id"] = str(record["pesticide_record_id"])
        self.records[key] = record
        return record, True

    def list_for_report(self, report_id, farmer_id):
        return [
            record for record in self.records.values()
            if record["disease_report_id"] == report_id and record["farmer_id"] == farmer_id
        ]


class MemoryPesticides:
    def __init__(self):
        self.product = {
            "id": PESTICIDE_ID,
            "registration_number": "PCPB(CR)0001",
            "review_status": PesticideReviewStatus.APPROVED.value,
            "registered_uses": ["Tomato Early blight"],
        }

    def get(self, product_id):
        return self.product if product_id == PESTICIDE_ID else None


@pytest.fixture
def disease_monitoring_client(monkeypatch):
    reports = MemoryReports()
    followups = MemoryIdempotentRecords()
    treatments = MemoryIdempotentRecords()
    pesticides = MemoryPesticides()
    current = {"user": make_user()}
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    app.dependency_overrides[get_disease_report_repository] = lambda: reports
    app.dependency_overrides[get_disease_followup_repository] = lambda: followups
    app.dependency_overrides[get_disease_treatment_repository] = lambda: treatments
    app.dependency_overrides[get_pesticide_repository] = lambda: pesticides
    monkeypatch.setattr(disease_monitoring_service, "predict_disease", lambda _: ("Tomato___Early_blight", 0.87))
    with TestClient(app) as client:
        yield client, current, reports, followups, treatments, pesticides
    app.dependency_overrides.clear()


def test_treatment_log_and_monitoring_are_farmer_owned(disease_monitoring_client):
    client, current, _, _, _, _ = disease_monitoring_client
    response = client.post(
        f"/disease-detection/{REPORT_ID}/treatments",
        headers={"Idempotency-Key": "treatment-001"},
        json={
            "treatment_type": "CULTURAL",
            "action_record": "Removed visibly affected leaves and cleaned tools.",
            "started_on": str(date.today()),
        },
    )
    assert response.status_code == 201
    assert response.json()["treatment_type"] == "CULTURAL"
    assert response.json()["pesticide_record_id"] is None
    assert client.get(f"/disease-detection/{REPORT_ID}/monitoring").json()["treatments"][0]["id"] == response.json()["id"]

    current["user"] = make_user(OTHER_FARMER_ID)
    assert client.get(f"/disease-detection/{REPORT_ID}/monitoring").status_code == 404
    assert client.post(
        f"/disease-detection/{REPORT_ID}/treatments",
        headers={"Idempotency-Key": "other-farmer-01"},
        json={"treatment_type": "OTHER", "action_record": "Observed the crop and contacted extension.", "started_on": str(date.today())},
    ).status_code == 404


def test_treatment_logs_require_approved_matching_pcpb_record(disease_monitoring_client):
    client, _, _, _, _, pesticides = disease_monitoring_client
    pesticides.product["review_status"] = "PENDING_REVIEW"
    response = client.post(
        f"/disease-detection/{REPORT_ID}/treatments",
        headers={"Idempotency-Key": "chemical-001"},
        json={"treatment_type": "CHEMICAL", "action_record": "Farmer recorded use according to current label.", "started_on": str(date.today()), "pesticide_record_id": PESTICIDE_ID},
    )
    assert response.status_code == 422
    pesticides.product["review_status"] = "APPROVED"
    pesticides.product["registered_uses"] = ["Maize leaf blight"]
    response = client.post(
        f"/disease-detection/{REPORT_ID}/treatments",
        headers={"Idempotency-Key": "chemical-002"},
        json={"treatment_type": "CHEMICAL", "action_record": "Farmer recorded use according to current label.", "started_on": str(date.today()), "pesticide_record_id": PESTICIDE_ID},
    )
    assert response.status_code == 422
    pesticides.product["registered_uses"] = ["Tomato Early blight"]
    response = client.post(
        f"/disease-detection/{REPORT_ID}/treatments",
        headers={"Idempotency-Key": "chemical-003"},
        json={"treatment_type": "CHEMICAL", "action_record": "Farmer recorded use according to current label.", "started_on": str(date.today()), "pesticide_record_id": PESTICIDE_ID},
    )
    assert response.status_code == 201
    assert response.json()["pesticide_registration_number"] == "PCPB(CR)0001"


def test_followup_upload_records_model_result_without_persisting_image(disease_monitoring_client):
    client, _, _, followups, _, _ = disease_monitoring_client
    response = client.post(
        f"/disease-detection/{REPORT_ID}/followups",
        headers={"Idempotency-Key": "followup-001"},
        data={"observation": "Leaves appear less affected."},
        files={"image": ("followup.png", b"test-image-bytes", "image/png")},
    )
    assert response.status_code == 201
    result = response.json()
    assert result["predicted_label"] == "Tomato___Early_blight"
    assert result["confidence"] == pytest.approx(0.87)
    assert result["comparison_to_initial"] == "SAME_LABEL"
    assert "does not confirm" in result["comparison_note"]
    assert result["image_sha256"]
    assert "not retained" in result["disclaimer"]
    assert all("image_bytes" not in record for record in followups.records.values())


def test_followup_replay_short_circuits_prediction_and_conflicts_are_rejected(disease_monitoring_client, monkeypatch):
    client, _, _, _, _, _ = disease_monitoring_client
    data = {"observation": "First observation."}
    files = {"image": ("followup.png", b"same-image", "image/png")}
    first = client.post(f"/disease-detection/{REPORT_ID}/followups", headers={"Idempotency-Key": "followup-002"}, data=data, files=files)
    assert first.status_code == 201
    monkeypatch.setattr(disease_monitoring_service, "predict_disease", lambda _: (_ for _ in ()).throw(AssertionError("must replay without inference")))
    second = client.post(f"/disease-detection/{REPORT_ID}/followups", headers={"Idempotency-Key": "followup-002"}, data=data, files=files)
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]


def test_followup_rejects_invalid_upload_missing_model_and_invalid_auth_role(disease_monitoring_client, monkeypatch):
    client, current, _, _, _, _ = disease_monitoring_client
    invalid = client.post(
        f"/disease-detection/{REPORT_ID}/followups",
        headers={"Idempotency-Key": "followup-003"},
        files={"image": ("bad.txt", b"text", "text/plain")},
    )
    assert invalid.status_code == 415
    monkeypatch.setattr(disease_monitoring_service, "predict_disease", lambda _: (_ for _ in ()).throw(DiseaseModelUnavailable("missing")))
    unavailable = client.post(
        f"/disease-detection/{REPORT_ID}/followups",
        headers={"Idempotency-Key": "followup-004"},
        files={"image": ("valid.png", b"valid", "image/png")},
    )
    assert unavailable.status_code == 503
    current["user"] = make_user(FARMER_ID, UserRole.BUYER)
    forbidden = client.get(f"/disease-detection/{REPORT_ID}/monitoring")
    assert forbidden.status_code == 403


def test_case_review_request_officer_response_and_resolution_lifecycle(disease_monitoring_client):
    client, current, _, _, _, _ = disease_monitoring_client
    requested = client.post(f"/disease-detection/{REPORT_ID}/review-request")
    assert requested.status_code == 200
    assert requested.json()["case_status"] == "REVIEW_REQUESTED"
    assert client.post(f"/disease-detection/{REPORT_ID}/review-request").status_code == 409

    current["user"] = make_user(OTHER_FARMER_ID, UserRole.AGRICULTURAL_OFFICER)
    queue = client.get("/disease-detection/review-queue")
    assert queue.status_code == 200 and queue.json()["total"] == 1
    reviewed = client.patch(f"/disease-detection/{REPORT_ID}/review", json={"note": "Reviewed the uploaded screening with the farmer; arrange an in-person crop check if symptoms persist."})
    assert reviewed.status_code == 200
    assert reviewed.json()["case_status"] == "OPEN"
    assert reviewed.json()["officer_reviews"][0]["officer_id"] == OTHER_FARMER_ID

    current["user"] = make_user()
    resolved = client.post(f"/disease-detection/{REPORT_ID}/resolve")
    assert resolved.status_code == 200
    assert resolved.json()["case_status"] == "RESOLVED"
    assert client.post(f"/disease-detection/{REPORT_ID}/review-request").status_code == 409
