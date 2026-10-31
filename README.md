# DocBro Backend

REST API for DocBro, built with **FastAPI**, **SQLAlchemy 2 (async)** and **PostgreSQL**.

## Features

- User registration and login with Argon2 password hashing
- JWT access tokens plus rotating refresh tokens, delivered as httpOnly cookies
- Refresh-token reuse detection (a replayed token revokes all of that user's sessions)
- Role-based access (`patient`, `doctor`, `medical`, `docbro`) via the `require_roles` dependency
- Data models for staff, invitations and addresses (API endpoints are not built yet)
- Alembic migrations, async Redis client, unit and integration tests

## Tech stack

| Area        | Library                         |
|-------------|---------------------------------|
| Web         | FastAPI, Uvicorn                |
| Database    | PostgreSQL, SQLAlchemy 2, asyncpg, Alembic |
| Auth        | python-jose, pwdlib (Argon2)          |
| Validation  | Pydantic v2, pydantic-settings  |
| Cache       | Redis (`redis/redis.py`)        |
| Tests       | pytest, pytest-asyncio, httpx   |

## Project layout

```
app/
├── main.py            # FastAPI app, CORS, router registration
├── core/settings.py   # environment-based configuration
├── auth/              # model, schema, security (JWT/hashing), service, router, dependency
├── staff/             # Staff model
├── invitation/        # Invitation model
└── addresses/         # Addresses model
db/                    # async engine/session (config.py) and declarative Base
alembic/               # migrations
redis/redis.py         # async Redis client wrapper
tests/                 # unit/ and integration/
docs/                  # design notes
```

## Getting started

### 1. Install

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows   (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
```

### 2. Configure

Create a `.env` file in the project root (it is git-ignored):

```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/docbro
DIRECT_URL=postgresql+asyncpg://user:password@localhost:5432/docbro

SECRET_KEY=<at least 32 random characters>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

PRODUCTION=false

# Redis
HOST=localhost
PORT=6379
DB=0
PASSWORD=
```

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | yes | Runtime connection string (asyncpg). Use the pooled URL if you have one. |
| `DIRECT_URL` | yes | Direct connection used by Alembic migrations. |
| `SECRET_KEY` | yes | JWT signing key. Must be 32+ characters when `PRODUCTION=true`. |
| `ALGORITHM` | no | `HS256` (default), `HS384` or `HS512`. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | no | Access token lifetime, default `15`. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | no | Refresh token lifetime, default `7`. |
| `PRODUCTION` | no | When `true`, auth cookies are marked `Secure`. Default `false`. |
| `HOST`, `PORT`, `DB`, `PASSWORD` | `HOST`/`PORT` yes | Redis connection. |

Generate a key with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

### 3. Migrate the database

```bash
alembic upgrade head
```

> The existing migrations predate the current models (staff, invitation, addresses,
> invitation tokens, address and enum changes). Generate a fresh migration and review it
> before applying: `alembic revision --autogenerate -m "describe change"`.

### 4. Run

```bash
uvicorn app.main:app --reload
```

Interactive docs: <http://localhost:8000/docs>

## API

All routes are under `/auth`.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Create a patient account. Body: `name`, `password`, optional `email`, `phone`. Returns `201`. |
| POST | `/auth/login` | Form fields `username` (email) and `password`. Returns an access token and sets `access_token` and `refresh_token` cookies. |
| POST | `/auth/refresh` | Rotate the refresh-token cookie and issue a new pair. `401` if invalid, expired or reused. |
| POST | `/auth/logout` | Revoke the current refresh token and clear the cookies. |
| GET | `/auth/me` | The current user. Accepts `Authorization: Bearer <token>` or the `access_token` cookie. |

### Authentication notes

- Passwords need 8-128 characters with an uppercase letter, a lowercase letter, a digit and a special character.
- Emails are stored lowercase. A phone number is 10-15 digits with an optional leading `+`.
- Public registration always creates a `patient`. Other roles must be granted by an admin or invitation.
- Only a SHA-256 hash of each refresh token is stored in the database.
- The refresh cookie is scoped to `/auth`. Cookies use `HttpOnly` and `SameSite=Lax`, and `Secure` when `PRODUCTION=true`.
- Cookie authentication relies on `SameSite=Lax`. If the frontend runs on a different site than the API, add CSRF protection.

Protect a route by role:

```python
from app.auth.dependency import require_roles
from app.auth.model import UserRole

@router.get("/patients")
async def patients(user=Depends(require_roles(UserRole.doctor, UserRole.docbro))): ...
```

## Database models

| Table | Purpose |
|-------|---------|
| `users` | Accounts, with `role`, `is_verified`, `is_admin`, `is_superuser` (`is_admin` defaults to on for every account; `is_superuser` and `is_verified` default to off). |
| `refresh_tokens` | Hashed refresh tokens with expiry, revocation and a rotation chain. |
| `staff` | A staff member (`user_id`) working for a doctor (`doctor_id`), with a designation. |
| `invitation` | Role invitations with a hashed token, status and expiry. |
| `addresses` | Per-user addresses (`clinic`, `store`, `home`, `permanent`). |

## Running tests

```bash
pip install -r requirements.txt
pytest -m "not integration"          # unit tests, no services needed
```

Integration tests need a PostgreSQL database whose name contains `test`
(its tables are created and **dropped** by the run):

```bash
docker run -d --name docbro-test-db -e POSTGRES_PASSWORD=pass -e POSTGRES_DB=docbro_test -p 5433:5432 postgres:16
export TEST_DATABASE_URL=postgresql+asyncpg://postgres:pass@localhost:5433/docbro_test   # PowerShell: $env:TEST_DATABASE_URL="..."
pytest
```

Without `TEST_DATABASE_URL` the integration tests are skipped.

## Roadmap

- Rate limiting on login and registration (Redis)
- Email verification and password reset
- Seed script for the first `docbro` admin
- Endpoints for staff, invitations and addresses
- Periodic cleanup of expired and revoked refresh tokens

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
