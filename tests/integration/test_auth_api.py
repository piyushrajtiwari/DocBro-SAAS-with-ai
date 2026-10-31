"""End-to-end auth tests: real FastAPI app + real PostgreSQL (see tests/conftest.py)."""
import pytest
from sqlalchemy import func, select

from app.auth.model import RefreshToken, User, UserRole
from app.auth.security import hash_token

pytestmark = pytest.mark.integration


def login_form(user: dict, password: str | None = None) -> dict:
    return {"username": user["email"], "password": password or user["password"]}


# --------------------------------------------------------------------- register
class TestRegister:
    async def test_success(self, client, valid_user):
        resp = await client.post("/auth/register", json=valid_user)
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == valid_user["email"]
        assert body["role"] == "patient"
        assert body["is_admin"] is True
        assert body["is_verified"] is False

    async def test_response_has_no_secrets(self, client, valid_user):
        body = (await client.post("/auth/register", json=valid_user)).json()
        assert "password" not in body and "password_hash" not in body

    async def test_password_is_stored_hashed(self, client, db_session, valid_user):
        await client.post("/auth/register", json=valid_user)
        user = (await db_session.scalars(select(User))).one()
        assert user.password_hash != valid_user["password"]
        assert user.password_hash.startswith("$argon2")

    @pytest.mark.parametrize("role", ["docbro", "doctor", "medical"])
    async def test_cannot_self_assign_privileged_role(self, client, db_session, valid_user, role):
        resp = await client.post("/auth/register", json={**valid_user, "role": role})
        assert resp.status_code == 201
        assert resp.json()["role"] == "patient"
        user = (await db_session.scalars(select(User))).one()
        assert user.role == UserRole.patient
        assert user.is_superuser is False

    async def test_email_is_normalised_to_lowercase(self, client, valid_user):
        resp = await client.post("/auth/register", json={**valid_user, "email": "Test.User@EXAMPLE.com"})
        assert resp.json()["email"] == "test.user@example.com"

    async def test_duplicate_email_is_409(self, client, registered_user):
        resp = await client.post(
            "/auth/register", json={**registered_user, "phone": "+919000000001"}
        )
        assert resp.status_code == 409

    async def test_duplicate_email_ignores_case(self, client, registered_user):
        resp = await client.post(
            "/auth/register",
            json={**registered_user, "email": registered_user["email"].upper(), "phone": None},
        )
        assert resp.status_code == 409

    async def test_duplicate_phone_is_409(self, client, registered_user):
        resp = await client.post(
            "/auth/register", json={**registered_user, "email": "other@example.com"}
        )
        assert resp.status_code == 409

    async def test_weak_password_is_422(self, client, valid_user):
        resp = await client.post("/auth/register", json={**valid_user, "password": "weak"})
        assert resp.status_code == 422

    async def test_invalid_email_is_422(self, client, valid_user):
        resp = await client.post("/auth/register", json={**valid_user, "email": "nope"})
        assert resp.status_code == 422

    async def test_missing_fields_is_422(self, client):
        assert (await client.post("/auth/register", json={})).status_code == 422


# ------------------------------------------------------------------------ login
class TestLogin:
    async def test_success_returns_token_and_sets_cookies(self, client, registered_user):
        resp = await client.post("/auth/login", data=login_form(registered_user))
        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "bearer" and body["access_token"]
        assert "refresh_token" not in body  # refresh token only travels as a cookie

        set_cookie = " ".join(resp.headers.get_list("set-cookie")).lower()
        assert "access_token=" in set_cookie and "refresh_token=" in set_cookie
        assert "httponly" in set_cookie and "samesite=lax" in set_cookie
        assert "path=/auth" in set_cookie  # refresh cookie is scoped to auth routes

    async def test_wrong_password_is_401(self, client, registered_user):
        resp = await client.post("/auth/login", data=login_form(registered_user, "Wr0ng!Password"))
        assert resp.status_code == 401
        assert not resp.cookies

    async def test_unknown_email_is_401(self, client):
        resp = await client.post(
            "/auth/login", data={"username": "ghost@example.com", "password": "Str0ng!Passw0rd"}
        )
        assert resp.status_code == 401

    async def test_unknown_email_and_wrong_password_look_identical(self, client, registered_user):
        wrong_pw = await client.post("/auth/login", data=login_form(registered_user, "Wr0ng!Password"))
        no_user = await client.post(
            "/auth/login", data={"username": "ghost@example.com", "password": "Wr0ng!Password"}
        )
        assert wrong_pw.status_code == no_user.status_code == 401
        assert wrong_pw.json() == no_user.json()

    async def test_email_is_case_insensitive(self, client, registered_user):
        resp = await client.post(
            "/auth/login", data=login_form({**registered_user, "email": registered_user["email"].upper()})
        )
        assert resp.status_code == 200

    async def test_refresh_token_is_stored_hashed(self, client, db_session, registered_user):
        await client.post("/auth/login", data=login_form(registered_user))
        raw = client.cookies.get("refresh_token")
        row = (await db_session.scalars(select(RefreshToken))).one()
        assert row.token == hash_token(raw)
        assert row.token != raw
        assert row.is_revoked is False

    async def test_two_logins_in_a_row_both_work(self, client, db_session, registered_user):
        for _ in range(2):
            assert (await client.post("/auth/login", data=login_form(registered_user))).status_code == 200
        count = await db_session.scalar(select(func.count()).select_from(RefreshToken))
        assert count == 2


# ---------------------------------------------------------------------------- me
class TestMe:
    async def test_with_bearer_header(self, client, logged_in, registered_user):
        client.cookies.clear()
        resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {logged_in['access_token']}"})
        assert resp.status_code == 200
        assert resp.json()["email"] == registered_user["email"]

    async def test_with_cookie_only(self, client, logged_in, registered_user):
        resp = await client.get("/auth/me")
        assert resp.status_code == 200
        assert resp.json()["email"] == registered_user["email"]

    async def test_never_leaks_password_hash(self, client, logged_in):
        body = (await client.get("/auth/me")).json()
        assert "password_hash" not in body and "password" not in body

    async def test_no_credentials_is_401(self, client):
        assert (await client.get("/auth/me")).status_code == 401

    async def test_garbage_token_is_401(self, client):
        resp = await client.get("/auth/me", headers={"Authorization": "Bearer garbage"})
        assert resp.status_code == 401

    async def test_refresh_token_cannot_be_used_as_access_token(self, client, logged_in):
        refresh = client.cookies.get("refresh_token")
        client.cookies.clear()
        resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {refresh}"})
        assert resp.status_code == 401

    async def test_deleted_user_is_401(self, client, db_session, logged_in):
        user = (await db_session.scalars(select(User))).one()
        await db_session.delete(user)
        await db_session.commit()
        assert (await client.get("/auth/me")).status_code == 401


# ------------------------------------------------------------------------ refresh
class TestRefresh:
    async def test_rotates_tokens(self, client, db_session, logged_in):
        old_refresh = client.cookies.get("refresh_token")
        resp = await client.post("/auth/refresh")
        assert resp.status_code == 200
        assert resp.json()["access_token"]
        new_refresh = client.cookies.get("refresh_token")
        assert new_refresh and new_refresh != old_refresh

        rows = {r.token: r for r in await db_session.scalars(select(RefreshToken))}
        old_row, new_row = rows[hash_token(old_refresh)], rows[hash_token(new_refresh)]
        assert old_row.is_revoked and old_row.revoked_at is not None
        assert old_row.replaced_by_token_id == new_row.id
        assert not new_row.is_revoked

    async def test_new_access_token_works(self, client, logged_in, registered_user):
        resp = await client.post("/auth/refresh")
        client.cookies.clear()
        me = await client.get(
            "/auth/me", headers={"Authorization": f"Bearer {resp.json()['access_token']}"}
        )
        assert me.status_code == 200

    async def test_chain_can_be_refreshed_repeatedly(self, client, logged_in):
        for _ in range(3):
            assert (await client.post("/auth/refresh")).status_code == 200

    async def test_missing_cookie_is_401_and_clears_cookies(self, client):
        resp = await client.post("/auth/refresh")
        assert resp.status_code == 401
        cleared = " ".join(resp.headers.get_list("set-cookie")).lower()
        assert "access_token=" in cleared and "refresh_token=" in cleared

    async def test_garbage_token_is_401(self, client):
        resp = await client.post("/auth/refresh", headers={"Cookie": "refresh_token=garbage"})
        assert resp.status_code == 401

    async def test_access_token_is_not_a_refresh_token(self, client, logged_in):
        resp = await client.post(
            "/auth/refresh", headers={"Cookie": f"refresh_token={logged_in['access_token']}"}
        )
        assert resp.status_code == 401

    async def test_replayed_token_is_rejected_and_revokes_all_sessions(self, client, db_session, logged_in):
        stolen = client.cookies.get("refresh_token")
        assert (await client.post("/auth/refresh")).status_code == 200
        legit_new = client.cookies.get("refresh_token")

        replay = await client.post("/auth/refresh", headers={"Cookie": f"refresh_token={stolen}"})
        assert replay.status_code == 401

        # the legitimately rotated token is now dead too (theft response)
        after = await client.post("/auth/refresh", headers={"Cookie": f"refresh_token={legit_new}"})
        assert after.status_code == 401
        db_session.expire_all()
        rows = (await db_session.scalars(select(RefreshToken))).all()
        assert rows and all(r.is_revoked for r in rows)

    async def test_expired_token_is_rejected(self, client, db_session, logged_in):
        from datetime import datetime, timedelta, timezone

        row = (await db_session.scalars(select(RefreshToken))).one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db_session.commit()
        assert (await client.post("/auth/refresh")).status_code == 401

    async def test_deleted_user_cannot_refresh(self, client, db_session, logged_in):
        user = (await db_session.scalars(select(User))).one()
        await db_session.delete(user)
        await db_session.commit()
        assert (await client.post("/auth/refresh")).status_code == 401


# ------------------------------------------------------------------------ logout
class TestLogout:
    async def test_revokes_refresh_token_and_clears_cookies(self, client, db_session, logged_in):
        refresh = client.cookies.get("refresh_token")
        resp = await client.post("/auth/logout")
        assert resp.status_code == 204

        row = (await db_session.scalars(select(RefreshToken).where(RefreshToken.token == hash_token(refresh)))).one()
        assert row.is_revoked

        # the revoked token no longer works
        again = await client.post("/auth/refresh", headers={"Cookie": f"refresh_token={refresh}"})
        assert again.status_code == 401

    async def test_logout_without_session_is_still_204(self, client):
        assert (await client.post("/auth/logout")).status_code == 204

    async def test_logout_only_ends_this_session(self, client, db_session, registered_user):
        await client.post("/auth/login", data=login_form(registered_user))
        other_device = client.cookies.get("refresh_token")
        client.cookies.clear()
        await client.post("/auth/login", data=login_form(registered_user))
        await client.post("/auth/logout")

        ok = await client.post("/auth/refresh", headers={"Cookie": f"refresh_token={other_device}"})
        assert ok.status_code == 200
