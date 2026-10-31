import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from jose import jwt
import pytest
from fastapi import HTTPException

pytest.importorskip("pwdlib", reason="pwdlib[argon2] not installed")

from app.auth.dependency import get_current_user, require_roles
from app.auth.model import User, UserRole
from app.core.settings import settings


def _token(token_type="access", sub=None, **extra) -> str:
    claims = {
        "sub": sub or str(uuid.uuid4()),
        "type": token_type,
        "jti": uuid.uuid4().hex,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        **extra,
    }
    return jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _request(cookie: str | None = None) -> MagicMock:
    request = MagicMock()
    request.cookies = {"access_token": cookie} if cookie else {}
    return request


def _session(user: User | None) -> MagicMock:
    session = MagicMock()
    session.get = AsyncMock(return_value=user)
    return session


class TestGetCurrentUser:
    async def test_no_token_is_401(self):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(_session(None), _request(), None)
        assert exc.value.status_code == 401

    async def test_bearer_token_returns_user(self):
        user = User(id=uuid.uuid4(), name="a", password_hash="h")
        result = await get_current_user(_session(user), _request(), _token(sub=str(user.id)))
        assert result is user

    async def test_cookie_is_used_when_no_header(self):
        user = User(id=uuid.uuid4(), name="a", password_hash="h")
        cookie = _token(sub=str(user.id))
        assert await get_current_user(_session(user), _request(cookie), None) is user

    async def test_refresh_token_is_not_accepted(self):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(_session(None), _request(), _token("refresh"))
        assert exc.value.status_code == 401

    async def test_garbage_token_is_401(self):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(_session(None), _request(), "garbage")
        assert exc.value.status_code == 401

    async def test_malformed_subject_is_401_not_500(self):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(_session(None), _request(), _token(sub="not-a-uuid"))
        assert exc.value.status_code == 401

    async def test_deleted_user_is_401(self):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(_session(None), _request(), _token())
        assert exc.value.status_code == 401


class TestRequireRoles:
    async def test_allowed_role_passes(self):
        user = User(id=uuid.uuid4(), name="a", password_hash="h", role=UserRole.doctor)
        checker = require_roles(UserRole.doctor, UserRole.docbro)
        assert await checker(user) is user

    async def test_other_role_is_403(self):
        user = User(id=uuid.uuid4(), name="a", password_hash="h", role=UserRole.patient)
        with pytest.raises(HTTPException) as exc:
            await require_roles(UserRole.doctor)(user)
        assert exc.value.status_code == 403
