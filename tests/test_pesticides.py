from datetime import date, datetime, timezone

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.dependencies import get_current_user, get_pesticide_repository
from app.main import app
from app.models.pesticide import PesticideReviewDecision, PesticideReviewStatus
from app.models.user import UserRole
from app.schemas.pesticide import PesticideRecordCreate, PesticideReviewRequest
from app.schemas.user import UserPublic


OFFICER_ID = "64b000000000000000000011"
ADMIN_ID = "64b000000000000000000012"
FARMER_ID = "64b000000000000000000013"


def user(user_id, role):
    now = datetime.now(timezone.utc)
    return UserPublic(
        id=user_id,
        full_name="Test User",
        email="test@example.test",
        phone="+254700000001",
        role=role,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


class MemoryPesticideRepository:
    def __init__(self):
        self.records = {}

    def create_draft(self, submitted_by, values):
        record_id = str(ObjectId())
        now = datetime.now(timezone.utc)
        record = {
            **values,
            "id": record_id,
            "registration_number": values["registration_number"].upper(),
            "review_status": PesticideReviewStatus.PENDING_REVIEW.value,
            "submitted_by": submitted_by,
            "review_events": [],
            "created_at": now,
            "updated_at": now,
        }
        self.records[record_id] = record
        return record

    def list_records(self, *, skip, limit, review_status=None):
        records = list(self.records.values())
        if review_status:
            records = [x for x in records if x["review_status"] == review_status]
        return records[skip:skip + limit], len(records)

    def get(self, record_id):
        return self.records.get(record_id)

    def review(self, record_id, reviewer_id, values):
        record = self.records.get(record_id)
        if not record or record["review_status"] != "PENDING_REVIEW":
            return None
        decision = PesticideReviewDecision(values["decision"])
        record["review_status"] = "APPROVED" if decision == PesticideReviewDecision.APPROVE else "REJECTED"
        record["review_events"].append({
            "reviewer_id": reviewer_id,
            "decision": decision.value,
            "note": values["review_note"],
            "registration_and_label_verified": values["registration_and_label_verified"],
            "source_checked_on": values["source_checked_on"],
            "at": datetime.now(timezone.utc),
        })
        record["updated_at"] = datetime.now(timezone.utc)
        return record

    def list_approved(self, *, crop_name, skip, limit):
        records = [x for x in self.records.values() if x["review_status"] == "APPROVED"]
        if crop_name:
            records = [x for x in records if any(crop_name.casefold() in use.casefold() for use in x["registered_uses"])]
        return records[skip:skip + limit], len(records)


@pytest.fixture
def pesticide_client():
    current = {"user": user(OFFICER_ID, UserRole.AGRICULTURAL_OFFICER)}
    repository = MemoryPesticideRepository()
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    app.dependency_overrides[get_pesticide_repository] = lambda: repository
    with TestClient(app) as client:
        yield client, current, repository
    app.dependency_overrides.clear()


def record_payload():
    return {
        "registration_number": "PCPB(CR)0001",
        "trade_name": "Verified Label Example",
        "formulation": "Example formulation",
        "active_ingredients": ["Example active ingredient"],
        "registered_uses": ["Tomato disease use exactly as confirmed on the label"],
        "pcpb_record_url": "https://www.pcpb.go.ke/crops/",
        "approved_label_url": "https://www.pcpb.go.ke/crops/",
        "source_checked_on": str(date.today()),
        "source_reference": "PCPB crop registration table and approved label PDF",
    }


def test_pesticide_record_urls_must_be_official_pcpb_https_urls():
    payload = record_payload()
    payload["approved_label_url"] = "https://example.com/fake-label.pdf"
    with pytest.raises(ValidationError):
        PesticideRecordCreate.model_validate(payload)


def test_pesticide_record_approval_requires_confirmation_of_both_sources():
    with pytest.raises(ValidationError):
        PesticideReviewRequest.model_validate({
            "decision": "APPROVE",
            "review_note": "Reviewed the available information carefully.",
            "registration_and_label_verified": False,
            "source_checked_on": str(date.today()),
        })


def test_officer_can_submit_pending_record_but_it_is_not_farmer_visible(pesticide_client):
    client, current, repository = pesticide_client
    created = client.post("/pesticide-records", json=record_payload())
    assert created.status_code == 201
    assert created.json()["review_status"] == "PENDING_REVIEW"
    assert len(created.json()["review_events"]) == 0
    current["user"] = user(FARMER_ID, UserRole.FARMER)
    approved = client.get("/pesticide-records/approved")
    assert approved.status_code == 200
    assert approved.json()["items"] == []
    assert len(repository.records) == 1


def test_admin_approval_is_audited_and_duplicate_review_is_blocked(pesticide_client):
    client, current, _ = pesticide_client
    draft = client.post("/pesticide-records", json=record_payload()).json()
    current["user"] = user(ADMIN_ID, UserRole.ADMIN)
    review = client.patch(f"/pesticide-records/{draft['id']}/review", json={
        "decision": "APPROVE",
        "review_note": "Checked current PCPB registration and its approved product label.",
        "registration_and_label_verified": True,
        "source_checked_on": str(date.today()),
    })
    assert review.status_code == 200
    assert review.json()["review_status"] == "APPROVED"
    assert review.json()["review_events"][0]["reviewer_id"] == ADMIN_ID
    duplicate = client.patch(f"/pesticide-records/{draft['id']}/review", json={
        "decision": "APPROVE",
        "review_note": "Checked current PCPB registration and its approved product label.",
        "registration_and_label_verified": True,
        "source_checked_on": str(date.today()),
    })
    assert duplicate.status_code == 409


def test_farmer_cannot_submit_or_review_pesticide_evidence(pesticide_client):
    client, current, _ = pesticide_client
    current["user"] = user(FARMER_ID, UserRole.FARMER)
    assert client.post("/pesticide-records", json=record_payload()).status_code == 403
    assert client.patch("/pesticide-records/64b000000000000000000099/review", json={
        "decision": "REJECT",
        "review_note": "Evidence was not sufficient to approve this record.",
        "registration_and_label_verified": False,
        "source_checked_on": str(date.today()),
    }).status_code == 403
