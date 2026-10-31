import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from jose import JWTError, jwt
from fastapi.concurrency import run_in_threadpool
from pwdlib import PasswordHash
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.model import RefreshToken, User
from app.core.settings import settings

TokenType = Literal["access", "refresh"]

password_hash = PasswordHash.recommended()

# Verified against when the account does not exist, so login takes the same
# time whether or not the email is registered.
_DUMMY_HASH = password_hash.hash("dummy-password-for-timing")


# PASSWORD HASHING USING ARGON2
async def get_password_hash(password: str) -> str:
    """Hash a plain-text password without blocking the event loop."""
    return await run_in_threadpool(password_hash.hash, password)


async def verify_password(plain_password: str, hashed_password: str | None) -> bool:
    """Verify a password against an Argon2 hash without blocking the event loop."""
    matches = await run_in_threadpool(
        password_hash.verify, plain_password, hashed_password or _DUMMY_HASH
    )
    return matches and hashed_password is not None


def hash_token(raw_token: str) -> str:
    """SHA-256 of a token; only the hash is stored in the database."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _encode(user_id: uuid.UUID, token_type: TokenType, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(raw_token: str, expected_type: TokenType) -> dict | None:
    """Return the payload if the token is valid and of the expected type, else None."""
    try:
        payload = jwt.decode(
            raw_token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require_exp": True, "require_sub": True, "require_jti": True},
        )
    except JWTError:
        return None
    # jose has no generic "require claim" option, so the custom claim is checked here
    if payload.get("type") != expected_type:
        return None
    return payload


async def issue_tokens(
    session: AsyncSession,
    user: User,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[dict, RefreshToken]:
    """Create an access/refresh pair and stage the hashed refresh token.

    The caller owns the transaction and must commit.
    """
    access_token = _encode(
        user.id, "access", timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    refresh_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_token = _encode(user.id, "refresh", refresh_delta)

    db_token = RefreshToken(
        user_id=user.id,
        token=hash_token(refresh_token),
        expires_at=datetime.now(timezone.utc) + refresh_delta,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:500] or None,
    )
    session.add(db_token)
    await session.flush()

    return (
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        },
        db_token,
    )
