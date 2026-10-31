from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from app.auth.model import User, UserRole
from app.auth.security import decode_token
from db.config import sessiondb

# auto_error=False so the access_token cookie can be used when there is no Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

_credentials_error = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or missing credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    session: sessiondb,
    request: Request,
    bearer_token: Annotated[str | None, Depends(oauth2_scheme)],
) -> User:
    raw_token = bearer_token or request.cookies.get("access_token")
    if not raw_token:
        raise _credentials_error

    payload = decode_token(raw_token, "access")
    if not payload:
        raise _credentials_error

    try:
        user_id = UUID(payload["sub"])
    except ValueError:
        raise _credentials_error

    user = await session.get(User, user_id)
    if not user:
        raise _credentials_error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole):
    """Dependency factory: allow only users whose role is in `roles`."""

    async def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
        return user

    return checker
