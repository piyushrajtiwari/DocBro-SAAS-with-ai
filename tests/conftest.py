"""Shared test setup.

Unit tests need no external services. Integration tests need a PostgreSQL
database whose name contains "test", given as TEST_DATABASE_URL, e.g.

    TEST_DATABASE_URL=postgresql+asyncpg://postgres:pass@localhost:5432/docbro_test

Its tables are created before the run and DROPPED afterwards.
"""
import os

# Settings() is built at import time, so these must be set before any `app` import.
# Real environment variables take precedence over .env, which keeps tests off real data.
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost:5432/unused_test"
os.environ["DIRECT_URL"] = "postgresql+asyncpg://test:test@localhost:5432/unused_test"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-at-least-32-characters-long"
os.environ["ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "15"
os.environ["REFRESH_TOKEN_EXPIRE_DAYS"] = "7"
os.environ["PRODUCTION"] = "false"
os.environ["HOST"] = "localhost"
os.environ["PORT"] = "6379"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def pytest_collection_modifyitems(config, items):
    if TEST_DATABASE_URL:
        return
    skip = pytest.mark.skip(reason="set TEST_DATABASE_URL to run integration tests")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest_asyncio.fixture(scope="session")
async def engine():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set")
    db_name = make_url(TEST_DATABASE_URL).database or ""
    if "test" not in db_name:
        pytest.exit(
            f"Refusing to run: database '{db_name}' does not look like a test database "
            "(its name must contain 'test'). Tables are dropped after the run.",
            returncode=2,
        )

    from app.auth import model as _auth  # noqa: F401  (registers every table)
    from db.base import Base

    test_engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
        connect_args={"statement_cache_size": 0},
    )
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield test_engine
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture(autouse=False)
async def clean_db(engine):
    """Empty every table before a test so tests stay independent."""
    from db.base import Base

    async with engine.begin() as conn:
        tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture
async def db_session(engine, clean_db):
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session


@pytest_asyncio.fixture
async def client(engine, clean_db):
    from app.main import app
    from db.config import get_session

    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_session():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ---- helpers shared by integration tests ----

VALID_USER = {
    "name": "Test User",
    "email": "test.user@example.com",
    "password": "Str0ng!Passw0rd",
    "phone": "+919876543210",
}


@pytest.fixture
def valid_user() -> dict:
    return dict(VALID_USER)


@pytest_asyncio.fixture
async def registered_user(client, valid_user):
    resp = await client.post("/auth/register", json=valid_user)
    assert resp.status_code == 201, resp.text
    return valid_user


@pytest_asyncio.fixture
async def logged_in(client, registered_user):
    """Register + log in; the client's cookie jar now holds both cookies."""
    resp = await client.post(
        "/auth/login",
        data={"username": registered_user["email"], "password": registered_user["password"]},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()
