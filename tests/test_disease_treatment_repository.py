from copy import deepcopy
from datetime import date

from bson import BSON, ObjectId

from app.repositories.disease_treatment_repository import DiseaseTreatmentRepository
from app.schemas.disease import DiseaseTreatmentPublic


class InsertCollection:
    def __init__(self):
        self.document = None

    def create_index(self, *_args, **_kwargs):
        return None

    def find_one(self, _query):
        return None

    def insert_one(self, document):
        # Exercise the BSON encoder so Python-only values fail in this test as
        # they would against MongoDB.
        BSON.encode(document)
        self.document = deepcopy(document)

        class InsertResult:
            inserted_id = ObjectId()

        return InsertResult()


def test_treatment_started_on_date_is_bson_safe_and_public_date_round_trips():
    collection = InsertCollection()
    repository = DiseaseTreatmentRepository(collection)
    report_id = str(ObjectId())
    farmer_id = str(ObjectId())
    started_on = date(2026, 11, 22)

    record, created = repository.create({
        "disease_report_id": report_id,
        "farmer_id": farmer_id,
        "treatment_type": "OTHER",
        "action_record": "QA-only record; no real treatment was applied.",
        "started_on": started_on,
        "pesticide_record_id": None,
        "pesticide_registration_number": None,
        "idempotency_key": "date-bson-check",
        "disclaimer": "History only.",
    })

    assert created is True
    assert collection.document["started_on"] == "2026-11-22"
    assert record["started_on"] == "2026-11-22"
    assert DiseaseTreatmentPublic.model_validate(record).started_on == started_on
