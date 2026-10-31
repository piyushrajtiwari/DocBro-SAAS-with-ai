# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased] - 2026-10-31

### Added
- `POST /auth/logout`, which revokes the refresh token and clears the auth cookies.
- `require_roles(...)` dependency for role-based route protection.
- Models for `Staff`, `Invitation` and `Addresses`.
- `Invitation.token_hash`, `status` and `expires_at`.
- Test suite: 68 unit tests and 39 integration tests (`tests/`), `pytest.ini`; `pytest` and `pytest-asyncio` added to `requirements.txt`.
- Settings `REFRESH_TOKEN_EXPIRE_DAYS` and `TokenOUT` response schema.
- README and this changelog.

### Changed
- Public registration always creates a `patient`; the `role` field was removed from the request.
- Emails are lowercased on register and login; phone numbers are validated.
- Password rules: 8-128 characters, any special character allowed (was max 23 with a fixed set).
- Login returns `200`, register returns `201`.
- Tokens carry `type` and `jti` claims, and expiry comes from settings.
- Refresh tokens are stored as SHA-256 hashes, not raw values.
- The refresh cookie is scoped to the `/auth` path.
- `get_current_user` accepts the bearer header or the `access_token` cookie.
- `User.is_admin` stays `True` by default for every account (product decision); the server default is now set too. `User.password_hash` is `String(255)`.
- `User` collections are lazy-loaded instead of `selectin`.
- `Staff` now links a staff member (`user_id`) to a doctor (`doctor_id`); `User.staff` is replaced by `staff_profile` and `staff_members`.
- `Addresses`: `Text` columns fixed, `address_line1` required and `address_line2` optional, `pincode` is `String(10)`, enum renamed `address_type`.
- Settings use `SettingsConfigDict`; `SECRET_KEY` must be 32+ characters when `PRODUCTION=true`.
- Alembic `env.py` imports all models and no longer sets `render_as_batch`.

### Fixed
- **Security:** login accepted any password for an existing email (the async `verify_password` was not awaited).
- **Security:** `/auth/me` returned the password hash.
- **Security:** anyone could register as `docbro` or `doctor`.
- **Security:** a refresh token could be used as an access token.
- Wrong keyword arguments (`details=`, `status=`) that caused 500 errors on bad login and bad tokens.
- Circular imports between the auth, staff, invitation and addresses models.
- Duplicate refresh tokens when two logins happened in the same second.
- Failed refreshes did not clear cookies, and rotation crashed for deleted users.
- Concurrent duplicate registrations returned a 500 instead of 409.
- Login timing no longer reveals whether an email is registered.

### Notes
- Existing migrations predate these model changes. Generate and review a new migration before deploying.
- Existing refresh-token rows hold raw tokens and are no longer accepted; users must log in again.

## [0.1.0] - 2026-10-17

### Added
- Initial FastAPI project with CORS and the `/auth` router.
- `User` and `RefreshToken` models.
- Async SQLAlchemy session setup and Alembic configuration with the first migrations.
- Async Redis client wrapper.
- Initial documentation (`docs/`).
