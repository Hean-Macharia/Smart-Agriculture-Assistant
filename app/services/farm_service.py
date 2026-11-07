from app.repositories.farm_repository import FarmRepository
from app.schemas.farm import FarmCreate, FarmPublic, FarmUpdate


def create_farm(repository: FarmRepository, owner_id: str, payload: FarmCreate) -> FarmPublic:
    return FarmPublic.model_validate(repository.create(owner_id, payload.model_dump()))


def update_farm(repository: FarmRepository, farm_id: str, owner_id: str, payload: FarmUpdate) -> FarmPublic | None:
    document = repository.update(farm_id, owner_id, payload.model_dump(exclude_unset=True))
    return FarmPublic.model_validate(document) if document else None
