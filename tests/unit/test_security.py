import base64
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from jose import jwt
import pytest

pytest.importorskip("pwdlib", reason="pwdlib[argon2] not installed")

from app.auth import security
from app.auth.model import RefreshToken, User, UserRole
from app.core.settings import settings


def _forge(payload: dict, key: str | None = None) -> str:
    return jwt.encode(payload, key or settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _claims(**overrides) -> dict:
    claims = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "jti": uuid.uuid4().hex,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    claims.update(overrides)
    return claims


class TestPasswordHashing:
    async def test_hash_is_not_plaintext_and_is_salted(self):
        h1 = await security.get_password_hash("Str0ng!Passw0rd")
        h2 = await security.get_password_hash("Str0ng!Passw0rd")
        assert h1 != "Str0ng!Passw0rd"
        assert h1 != h2

    async def test_correct_password_verifies(self):
        h = await security.get_password_hash("Str0ng!Passw0rd")
        assert await security.verify_password("Str0ng!Passw0rd", h) is True

    async def test_wrong_password_fails(self):
        h = await security.get_password_hash("Str0ng!Passw0rd")
        assert await security.verify_password("wrong", h) is False

    async def test_missing_hash_never_verifies(self):
        # used for unknown emails; must be False even for the dummy's own password
        assert await security.verify_password("dummy-password-for-timing", None) is False


class TestHashToken:
    def test_deterministic_and_hex(self):
        assert security.hash_token("abc") == security.hash_token("abc")
        assert len(security.hash_token("abc")) == 64

    def test_different_tokens_differ(self):
        assert security.hash_token("a") != security.hash_token("b")

    def test_does_not_contain_raw_token(self):
        assert "secret-token" not in security.hash_token("secret-token")


class TestDecodeToken:
    def test_valid_access_token(self):
        token = _forge(_claims())
        assert security.decode_token(token, "access")["type"] == "access"

    def test_wrong_type_is_rejected(self):
        refresh = _forge(_claims(type="refresh"))
        assert security.decode_token(refresh, "access") is None
        access = _forge(_claims(type="access"))
        assert security.decode_token(access, "refresh") is None

    def test_expired_is_rejected(self):
        token = _forge(_claims(exp=datetime.now(timezone.utc) - timedelta(seconds=1)))
        assert security.decode_token(token, "access") is None

    def test_wrong_signature_is_rejected(self):
        token = _forge(_claims(), key="another-key-that-is-long-enough-for-hs256!!")
        assert security.decode_token(token, "access") is None

    def test_tampered_token_is_rejected(self):
        header, payload, signature = _forge(_claims()).split(".")
        # flip a character in the middle of the signature; the final characters of a
        # base64url string can carry unused bits, so changing them may not alter the bytes
        flipped = "A" if signature[5] != "A" else "B"
        tampered = ".".join([header, payload, signature[:5] + flipped + signature[6:]])
        assert security.decode_token(tampered, "access") is None

    def test_alg_none_is_rejected(self):
        def b64(data: dict) -> str:
            raw = json.dumps(data, default=lambda d: int(d.timestamp())).encode()
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

        token = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(_claims())}."
        assert security.decode_token(token, "access") is None

    @pytest.mark.parametrize("missing", ["exp", "sub", "type", "jti"])
    def test_required_claims(self, missing):
        claims = _claims()
        claims.pop(missing)
        assert security.decode_token(_forge(claims), "access") is None

    def test_garbage_is_rejected(self):
        assert security.decode_token("not.a.jwt", "access") is None
        assert security.decode_token("", "access") is None


class TestIssueTokens:
    @pytest.fixture
    def session(self):
        s = MagicMock()
        s.add = MagicMock()
        s.flush = AsyncMock()
        return s

    @pytest.fixture
    def user(self):
        return User(id=uuid.uuid4(), name="x", password_hash="h", role=UserRole.patient)

    async def test_returns_both_tokens_of_correct_type(self, session, user):
        tokens, _ = await security.issue_tokens(session, user)
        access = security.decode_token(tokens["access_token"], "access")
        refresh = security.decode_token(tokens["refresh_token"], "refresh")
        assert access["sub"] == refresh["sub"] == str(user.id)
        assert security.decode_token(tokens["access_token"], "refresh") is None
        assert tokens["token_type"] == "bearer"

    async def test_stores_only_the_hash(self, session, user):
        tokens, db_token = await security.issue_tokens(session, user, "1.2.3.4", "pytest")
        assert isinstance(db_token, RefreshToken)
        assert db_token.token == security.hash_token(tokens["refresh_token"])
        assert db_token.token != tokens["refresh_token"]
        assert db_token.ip_address == "1.2.3.4"
        assert db_token.user_agent == "pytest"
        session.add.assert_called_once_with(db_token)
        session.flush.assert_awaited_once()

    async def test_tokens_are_unique_even_in_the_same_second(self, session, user):
        a, _ = await security.issue_tokens(session, user)
        b, _ = await security.issue_tokens(session, user)
        assert a["refresh_token"] != b["refresh_token"]
        assert a["access_token"] != b["access_token"]

    async def test_refresh_expiry_follows_settings(self, session, user):
        _, db_token = await security.issue_tokens(session, user)
        expected = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        assert abs((db_token.expires_at - expected).total_seconds()) < 5

    async def test_long_user_agent_is_truncated(self, session, user):
        _, db_token = await security.issue_tokens(session, user, user_agent="a" * 900)
        assert len(db_token.user_agent) == 500
