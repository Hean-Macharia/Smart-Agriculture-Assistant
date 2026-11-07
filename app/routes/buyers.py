from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_buyer_repository, require_roles
from app.models.user import UserRole
from app.repositories.buyer_repository import BuyerRepository
from app.schemas.buyer import BuyerProfile, BuyerProfileUpsert
from app.schemas.user import UserPublic
from app.services.buyer_service import get_profile, save_profile

router = APIRouter(prefix="/buyers", tags=["Buyers"])


@router.get("/me", response_model=BuyerProfile, summary="Get my buyer profile")
def get_my_profile(
    user: UserPublic = Depends(require_roles(UserRole.BUYER)),
    repository: BuyerRepository = Depends(get_buyer_repository),
) -> BuyerProfile:
    profile = get_profile(repository, user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Buyer profile not found")
    return profile


@router.put("/me", response_model=BuyerProfile, summary="Create or update my buyer profile")
def put_my_profile(
    payload: BuyerProfileUpsert,
    user: UserPublic = Depends(require_roles(UserRole.BUYER)),
    repository: BuyerRepository = Depends(get_buyer_repository),
) -> BuyerProfile:
    return save_profile(repository, user.id, payload)
