"""Authentication business rules, separate from HTTP routing."""

from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import UserRole
from app.repositories.user_repository import UserConflictError, UserRepository
from app.schemas.auth import LoginRequest, RegistrationRequest, TokenResponse
from app.schemas.user import UserPublic, to_public_user


class InvalidCredentialsError(Exception):
    """Raised for missing users, bad passwords, and disabled accounts."""


def register_user(
    users: UserRepository,
    payload: RegistrationRequest,
    role: UserRole,
    *,
    bootstrap_admin: bool = False,
) -> UserPublic:
    values = payload.model_dump(exclude={"password"})
    values.update(
        password_hash=hash_password(payload.password),
        role=role.value,
    )
    document = users.create_user(values, bootstrap_admin=bootstrap_admin)
    return to_public_user(document)


def login_user(users: UserRepository, payload: LoginRequest) -> TokenResponse:
    user = users.get_by_email(payload.email)
    if (
        user is None
        or not user.get("is_active", False)
        or not verify_password(payload.password, user.get("password_hash", ""))
    ):
        raise InvalidCredentialsError

    token = create_access_token(str(user["_id"]), user["role"])
    return TokenResponse(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=to_public_user(user),
    )
