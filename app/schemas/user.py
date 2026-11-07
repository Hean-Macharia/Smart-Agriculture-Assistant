from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.user import UserRole


class UserPublic(BaseModel):
    id: str
    full_name: str
    email: str
    phone: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid")


class UserListResponse(BaseModel):
    items: list[UserPublic]
    total: int
    limit: int
    offset: int


def to_public_user(document: dict) -> UserPublic:
    """Build an allow-listed response; credential fields never enter the schema."""
    return UserPublic(
        id=str(document["_id"]),
        full_name=document["full_name"],
        email=document["email"],
        phone=document["phone"],
        role=document["role"],
        is_active=document["is_active"],
        created_at=document["created_at"],
        updated_at=document["updated_at"],
    )
