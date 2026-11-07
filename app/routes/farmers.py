from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import get_current_user, get_farmer_repository, require_roles
from app.models.user import UserRole
from app.repositories.farmer_repository import FarmerRepository
from app.schemas.farmer import FarmerProfile, FarmerProfileUpsert
from app.schemas.user import UserPublic
from app.services.farmer_service import get_profile, save_profile

router = APIRouter(prefix="/farmers", tags=["Farmers"])


@router.get("/me", response_model=FarmerProfile, summary="Get my farmer profile")
def get_my_profile(
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    repository: FarmerRepository = Depends(get_farmer_repository),
) -> FarmerProfile:
    profile = get_profile(repository, user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Farmer profile not found")
    return profile


@router.put("/me", response_model=FarmerProfile, summary="Create or update my farmer profile")
def put_my_profile(
    payload: FarmerProfileUpsert,
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    repository: FarmerRepository = Depends(get_farmer_repository),
) -> FarmerProfile:
    return save_profile(repository, user.id, payload)
