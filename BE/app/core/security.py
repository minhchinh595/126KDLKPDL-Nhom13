from datetime import datetime, timedelta, timezone
import os

import jwt
from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()
TOKEN_COOKIE = "electricity_access_token"
TOKEN_ALGORITHM = "HS256"
TOKEN_TTL_MINUTES = int(os.getenv("ACCESS_TOKEN_TTL_MINUTES", "60"))


def _secret() -> str:
    secret = os.getenv("JWT_SECRET_KEY", "")
    if len(secret.encode("utf-8")) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be configured with at least 32 bytes")
    return secret


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return password_hash.verify(password, encoded)
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=TOKEN_TTL_MINUTES)},
        _secret(),
        algorithm=TOKEN_ALGORITHM,
    )


def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, _secret(), algorithms=[TOKEN_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        return None


def cookie_secure() -> bool:
    return os.getenv("APP_ENV", "development").lower() == "production"
