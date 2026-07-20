import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

_MAX_BCRYPT_BYTES = 72
_JWT_ALGORITHM = "HS256"


def hash_password(plain: str) -> str:
    encoded = plain.encode("utf-8")
    if len(encoded) > _MAX_BCRYPT_BYTES:
        raise ValueError(f"password exceeds bcrypt's {_MAX_BCRYPT_BYTES}-byte limit")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


class InvalidTokenError(Exception):
    pass


def create_access_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID:
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(token, settings.secret_key, algorithms=[_JWT_ALGORITHM])
    except JWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError("token missing a valid subject") from exc
