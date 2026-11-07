from app.repositories.buyer_repository import BuyerRepository
from app.schemas.buyer import BuyerProfile, BuyerProfileUpsert


def save_profile(repository: BuyerRepository, user_id: str, payload: BuyerProfileUpsert) -> BuyerProfile:
    document = repository.upsert_profile(user_id, payload.model_dump())
    document["user_id"] = user_id
    return BuyerProfile.model_validate(document)


def get_profile(repository: BuyerRepository, user_id: str) -> BuyerProfile | None:
    document = repository.get_profile(user_id)
    if document:
        document["user_id"] = user_id
        return BuyerProfile.model_validate(document)
    return None
