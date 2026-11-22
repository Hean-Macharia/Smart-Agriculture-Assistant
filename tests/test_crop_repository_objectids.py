from datetime import date
from copy import deepcopy

from bson import ObjectId

from app.repositories.crop_repository import CropRepository
from app.schemas.crop import CropCreate, CropPublic
from app.services.crop_service import create_crop


class InsertOnlyCollection:
    def __init__(self):
        self.document = None

    def create_index(self, *_args, **_kwargs):
        return None

    def insert_one(self, document):
        self.document = deepcopy(document)

        class InsertResult:
            inserted_id = ObjectId()

        return InsertResult()


def test_create_crop_serializes_farm_object_id_for_public_schema():
    collection = InsertOnlyCollection()
    repository = CropRepository(collection)
    farm_id = str(ObjectId())
    owner_id = str(ObjectId())
    payload = CropCreate(
        farm_id=farm_id,
        name="Tomatoes",
        planting_date=date(2026, 11, 1),
    )

    crop = create_crop(repository, owner_id, payload)

    assert isinstance(collection.document["farm_id"], ObjectId)
    assert crop.farm_id == farm_id
    assert CropPublic.model_validate(crop).farm_id == farm_id
