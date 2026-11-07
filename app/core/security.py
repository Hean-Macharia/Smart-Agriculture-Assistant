"""Password hashing and signed access-token helpers."""

from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import PwdlibError

from app.core.config import settings

_TOKEN_ISSUER = "smart-agriculture-api"
_password_hash = PasswordHash.recommended()


class TokenConfigurationError(RuntimeError):
    """Raised when the deployment has no sufficiently strong signing key."""


def _signing_key() -> str:
    key = settings.jwt_secret_key.strip()
    if len(key) < 32:
        raise TokenConfigurationError("JWT_SECRET_KEY must contain at least 32 characters")
    return key


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hash.verify(password, password_hash)
    except (PwdlibError, ValueError):
        return False


def create_access_token(user_id: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    claims = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": expires_at,
        "iss": _TOKEN_ISSUER,
    }
    return jwt.encode(claims, _signing_key(), algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(
            token,
            _signing_key(),
            algorithms=[settings.jwt_algorithm],
            issuer=_TOKEN_ISSUER,
            options={"require": ["sub", "iat", "exp", "iss"]},
        )
    except jwt.InvalidTokenError:
        return None
