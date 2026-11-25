from app.repositories.crop_repository import CropRepository
from app.schemas.crop import CropCreate, CropPublic, CropUpdate


def create_crop(repository: CropRepository, owner_id: str, payload: CropCreate, *, idempotency_key: str | None = None) -> CropPublic:
    values = payload.model_dump(mode="json")
    document = repository.create(owner_id, values, **({"idempotency_key": idempotency_key} if idempotency_key else {}))
    return CropPublic.model_validate(document)


def update_crop(repository: CropRepository, crop_id: str, owner_id: str, payload: CropUpdate, *, expected_updated_at=None) -> CropPublic | None:
    changes = payload.model_dump(exclude_unset=True, mode="json")
    document = repository.update(crop_id, owner_id, changes, **({"expected_updated_at": expected_updated_at} if expected_updated_at else {}))
    return CropPublic.model_validate(document) if document else None
