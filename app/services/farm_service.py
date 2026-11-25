from app.repositories.farm_repository import FarmRepository
from app.schemas.farm import FarmCreate, FarmPublic, FarmUpdate


def create_farm(repository: FarmRepository, owner_id: str, payload: FarmCreate, *, idempotency_key: str | None = None) -> FarmPublic:
    values = payload.model_dump()
    document = repository.create(owner_id, values, **({"idempotency_key": idempotency_key} if idempotency_key else {}))
    return FarmPublic.model_validate(document)


def update_farm(repository: FarmRepository, farm_id: str, owner_id: str, payload: FarmUpdate, *, expected_updated_at=None) -> FarmPublic | None:
    changes = payload.model_dump(exclude_unset=True)
    document = repository.update(farm_id, owner_id, changes, **({"expected_updated_at": expected_updated_at} if expected_updated_at else {}))
    return FarmPublic.model_validate(document) if document else None
