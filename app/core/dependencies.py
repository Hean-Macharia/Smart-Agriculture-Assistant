from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.database import get_database
from app.core.security import TokenConfigurationError, decode_access_token
from app.models.user import UserRole
from app.repositories.user_repository import UserRepository
from app.repositories.buyer_repository import BuyerRepository
from app.repositories.crop_repository import CropRepository
from app.repositories.farm_repository import FarmRepository
from app.repositories.farmer_repository import FarmerRepository
from app.repositories.marketplace_repository import MarketplaceRepository
from app.repositories.order_repository import OrderRepository
from app.schemas.user import UserPublic, to_public_user

_bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def get_user_repository() -> UserRepository:
    return UserRepository(get_database()["users"])


@lru_cache(maxsize=1)
def get_farmer_repository() -> FarmerRepository:
    return FarmerRepository(get_database()["farmers"])


@lru_cache(maxsize=1)
def get_buyer_repository() -> BuyerRepository:
    return BuyerRepository(get_database()["buyers"])


@lru_cache(maxsize=1)
def get_farm_repository() -> FarmRepository:
    return FarmRepository(get_database()["farms"])


@lru_cache(maxsize=1)
def get_crop_repository() -> CropRepository:
    return CropRepository(get_database()["crops"])


@lru_cache(maxsize=1)
def get_marketplace_repository() -> MarketplaceRepository:
    return MarketplaceRepository(get_database()["marketplace_products"])


@lru_cache(maxsize=1)
def get_order_repository() -> OrderRepository:
    return OrderRepository(get_database()["orders"])


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    users: UserRepository = Depends(get_user_repository),
) -> UserPublic:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        claims = decode_access_token(credentials.credentials)
    except TokenConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured on this server",
        ) from None
    if not claims or not isinstance(claims.get("sub"), str):
        raise unauthorized

    user = users.get_by_id(claims["sub"])
    if user is None or not user.get("is_active", False):
        raise unauthorized
    return to_public_user(user)


def require_roles(*roles: UserRole):
    allowed = {role.value for role in roles}

    def role_guard(current_user: UserPublic = Depends(get_current_user)) -> UserPublic:
        if current_user.role.value not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user

    return role_guard
