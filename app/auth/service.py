from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.model import RefreshToken, User, UserRole
from app.auth.schema import UserIN
from app.auth.security import (
    get_password_hash,
    hash_token,
    issue_tokens,
    verify_password,
)


async def user_registration(session: AsyncSession, user: UserIN) -> User:
    conditions = []
    if user.email:
        conditions.append(User.email == user.email)
    if user.phone:
        conditions.append(User.phone == user.phone)

    if conditions:
        existing = (await session.scalars(select(User).where(or_(*conditions)))).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email or phone already registered",
            )

    new_user = User(
        name=user.name,
        email=user.email,
        password_hash=await get_password_hash(user.password),
        phone=user.phone,
        role=UserRole.patient,  # privileged roles are granted via invitation/admin, never self-service
        is_verified=False,
    )
    session.add(new_user)
    try:
        await session.commit()
    except IntegrityError:
        # lost a race with a concurrent registration
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or phone already registered",
        )
    await session.refresh(new_user)
    return new_user


async def user_login(session: AsyncSession, email: str, password: str) -> User:
    user = (
        await session.scalars(select(User).where(User.email == email.strip().lower()))
    ).first()

    # always verify (against a dummy hash when the user is missing) to keep timing uniform
    password_ok = await verify_password(password, user.password_hash if user else None)
    if not user or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def create_session_tokens(
    session: AsyncSession,
    user: User,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    tokens, _ = await issue_tokens(session, user, ip_address, user_agent)
    await session.commit()
    return tokens


async def _revoke_all_for_user(session: AsyncSession, user_id) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.is_revoked.is_(False))
        .values(is_revoked=True, revoked_at=datetime.now(timezone.utc))
    )


async def verify_and_rotate_refresh_token(
    session: AsyncSession,
    plain_token: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict | None:
    """Exchange a valid refresh token for a new pair. Returns None if it is not acceptable."""
    db_token = (
        await session.scalars(
            select(RefreshToken)
            .where(RefreshToken.token == hash_token(plain_token))
            .with_for_update()  # serialise concurrent refreshes of the same token
        )
    ).first()
    if not db_token:
        return None

    if db_token.is_revoked:
        # a rotated/revoked token was replayed: assume theft and kill every session
        await _revoke_all_for_user(session, db_token.user_id)
        await session.commit()
        return None

    if db_token.expires_at < datetime.now(timezone.utc):
        return None

    user = await session.get(User, db_token.user_id)
    if not user:
        return None

    tokens, new_db_token = await issue_tokens(session, user, ip_address, user_agent)
    db_token.is_revoked = True
    db_token.revoked_at = datetime.now(timezone.utc)
    db_token.replaced_by_token_id = new_db_token.id
    await session.commit()
    return tokens


async def revoke_refresh_token(session: AsyncSession, plain_token: str) -> None:
    db_token = (
        await session.scalars(
            select(RefreshToken).where(RefreshToken.token == hash_token(plain_token))
        )
    ).first()
    if db_token and not db_token.is_revoked:
        db_token.is_revoked = True
        db_token.revoked_at = datetime.now(timezone.utc)
        await session.commit()
