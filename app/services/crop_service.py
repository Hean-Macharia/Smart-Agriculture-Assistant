from app.repositories.crop_repository import CropRepository
from app.schemas.crop import CropCreate, CropPublic, CropUpdate


def create_crop(repository: CropRepository, owner_id: str, payload: CropCreate) -> CropPublic:
    values = payload.model_dump(mode="json")
    return CropPublic.model_validate(repository.create(owner_id, values))


def update_crop(repository: CropRepository, crop_id: str, owner_id: str, payload: CropUpdate) -> CropPublic | None:
    changes = payload.model_dump(exclude_unset=True, mode="json")
    document = repository.update(crop_id, owner_id, changes)
    return CropPublic.model_validate(document) if document else None
