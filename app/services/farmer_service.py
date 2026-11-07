from app.repositories.farmer_repository import FarmerRepository
from app.schemas.farmer import FarmerProfile, FarmerProfileUpsert


def save_profile(repository: FarmerRepository, user_id: str, payload: FarmerProfileUpsert) -> FarmerProfile:
    document = repository.upsert_profile(user_id, payload.model_dump())
    document["user_id"] = user_id
    return FarmerProfile.model_validate(document)


def get_profile(repository: FarmerRepository, user_id: str) -> FarmerProfile | None:
    document = repository.get_profile(user_id)
    if document:
        document["user_id"] = user_id
        return FarmerProfile.model_validate(document)
    return None
