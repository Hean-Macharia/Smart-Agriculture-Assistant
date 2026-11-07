import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.user import UserRole
from app.schemas.user import UserPublic

_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PHONE_PATTERN = re.compile(r"^\+254[17]\d{8}$")


def _normalize_email(value: str) -> str:
    value = value.strip().lower()
    if not _EMAIL_PATTERN.fullmatch(value):
        raise ValueError("A valid email address is required")
    return value


def _normalize_kenyan_phone(value: str) -> str:
    value = re.sub(r"[\s()-]", "", value)
    if re.fullmatch(r"0[17]\d{8}", value):
        value = "+254" + value[1:]
    if not _PHONE_PATTERN.fullmatch(value):
        raise ValueError("Use a Kenyan mobile number such as +254712345678 or 0712345678")
    return value


class RequestSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegistrationRequest(RequestSchema):
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=254)
    phone: str = Field(min_length=10, max_length=20)
    password: str = Field(min_length=8, max_length=128, repr=False)

    @field_validator("full_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("Full name must contain at least two characters")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _normalize_email(value)

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        return _normalize_kenyan_phone(value)


class LoginRequest(RequestSchema):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128, repr=False)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _normalize_email(value)


class AdminUserCreateRequest(RegistrationRequest):
    role: UserRole

    @field_validator("role")
    @classmethod
    def restrict_managed_roles(cls, value: UserRole) -> UserRole:
        if value not in {UserRole.ADMIN, UserRole.AGRICULTURAL_OFFICER}:
            raise ValueError("Admins may create only admin or agricultural officer accounts")
        return value


class ProfileUpdateRequest(RequestSchema):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    phone: str | None = Field(default=None, min_length=10, max_length=20)

    @field_validator("full_name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Full name cannot be null")
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("Full name must contain at least two characters")
        return value

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Phone cannot be null")
        return _normalize_kenyan_phone(value)

    @model_validator(mode="after")
    def require_an_update(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one profile field to update")
        return self


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic
