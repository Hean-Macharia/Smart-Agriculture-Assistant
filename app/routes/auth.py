"""Registration, login, profile, and role-protected account endpoints."""

import hmac

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, status

from app.core.config import settings
from app.core.dependencies import get_current_user, get_user_repository, require_roles
from app.core.security import TokenConfigurationError
from app.models.user import UserRole
from app.repositories.user_repository import UserConflictError, UserRepository
from app.schemas.auth import (
    AdminUserCreateRequest,
    LoginRequest,
    ProfileUpdateRequest,
    RegistrationRequest,
    TokenResponse,
)
from app.schemas.user import UserListResponse, UserPublic, to_public_user
from app.services.auth_service import InvalidCredentialsError, login_user, register_user
from app.services.notification_service import dispatch_sms_event

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="An account with that email or phone number already exists",
    )


@router.post(
    "/register/farmer",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Register a farmer account",
    responses={409: {"description": "Email or phone number is already registered."}},
)
def register_farmer(
    payload: RegistrationRequest,
    background_tasks: BackgroundTasks,
    users: UserRepository = Depends(get_user_repository),
) -> UserPublic:
    try:
        registered = register_user(users, payload, UserRole.FARMER)
        background_tasks.add_task(dispatch_sms_event, recipient_user_id=registered.id, event="REGISTRATION", event_id=registered.id, message="Your Smart Agriculture farmer account is registered.")
        return registered
    except UserConflictError:
        raise _conflict() from None


@router.post(
    "/register/buyer",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Register a buyer account",
    responses={409: {"description": "Email or phone number is already registered."}},
)
def register_buyer(
    payload: RegistrationRequest,
    background_tasks: BackgroundTasks,
    users: UserRepository = Depends(get_user_repository),
) -> UserPublic:
    try:
        registered = register_user(users, payload, UserRole.BUYER)
        background_tasks.add_task(dispatch_sms_event, recipient_user_id=registered.id, event="REGISTRATION", event_id=registered.id, message="Your Smart Agriculture buyer account is registered.")
        return registered
    except UserConflictError:
        raise _conflict() from None


@router.post(
    "/bootstrap-admin",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create the first administrator",
    description=(
        "One-time setup endpoint. Requires the ADMIN_BOOTSTRAP_TOKEN header configured on the server. "
        "The database unique index prevents concurrent bootstrap requests from creating multiple bootstrap admins."
    ),
    responses={
        403: {"description": "Bootstrap token is missing or invalid."},
        409: {"description": "An administrator already exists or the account conflicts."},
        503: {"description": "Admin bootstrap is not configured on this server."},
    },
)
def bootstrap_admin(
    payload: RegistrationRequest,
    x_admin_bootstrap_token: str | None = Header(default=None, alias="X-Admin-Bootstrap-Token"),
    users: UserRepository = Depends(get_user_repository),
) -> UserPublic:
    configured_token = settings.admin_bootstrap_token.strip()
    if len(configured_token) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin bootstrap is not configured on this server",
        )
    if x_admin_bootstrap_token is None or not hmac.compare_digest(x_admin_bootstrap_token, configured_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin bootstrap token",
        )
    if users.count_admins() > 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An administrator already exists")
    try:
        return register_user(users, payload, UserRole.ADMIN, bootstrap_admin=True)
    except UserConflictError:
        raise _conflict() from None


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in and receive a JWT access token",
    responses={
        401: {"description": "Email/password invalid or account disabled."},
        503: {"description": "JWT signing key is missing or invalid."},
    },
)
def login(
    payload: LoginRequest,
    users: UserRepository = Depends(get_user_repository),
) -> TokenResponse:
    try:
        return login_user(users, payload)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except TokenConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured on this server",
        ) from None


@router.get("/me", response_model=UserPublic, summary="Get the authenticated user")
def get_me(current_user: UserPublic = Depends(get_current_user)) -> UserPublic:
    return current_user


@router.patch("/me", response_model=UserPublic, summary="Update the authenticated user's profile")
def update_me(
    payload: ProfileUpdateRequest,
    current_user: UserPublic = Depends(get_current_user),
    users: UserRepository = Depends(get_user_repository),
) -> UserPublic:
    try:
        updated = users.update_profile(current_user.id, payload.model_dump(exclude_unset=True))
    except UserConflictError:
        raise _conflict() from None
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return to_public_user(updated)


@router.post(
    "/admin/users",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create an administrator or agricultural officer account",
    responses={403: {"description": "Administrator role required."}},
)
def create_managed_user(
    payload: AdminUserCreateRequest,
    _: UserPublic = Depends(require_roles(UserRole.ADMIN)),
    users: UserRepository = Depends(get_user_repository),
) -> UserPublic:
    try:
        return register_user(users, payload, payload.role)
    except UserConflictError:
        raise _conflict() from None


@router.get(
    "/admin/users",
    response_model=UserListResponse,
    summary="List user accounts (administrator only)",
    responses={403: {"description": "Administrator role required."}},
)
def list_managed_users(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    role: UserRole | None = Query(default=None),
    _: UserPublic = Depends(require_roles(UserRole.ADMIN)),
    users: UserRepository = Depends(get_user_repository),
) -> UserListResponse:
    documents, total = users.list_users(
        skip=offset,
        limit=limit,
        role=role.value if role else None,
    )
    return UserListResponse(
        items=[to_public_user(document) for document in documents],
        total=total,
        limit=limit,
        offset=offset,
    )
