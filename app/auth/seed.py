"""Create the first DocBro admin from ADMIN_EMAIL / ADMIN_PASSWORD in .env.

Run from the project root:  python -m app.auth.seed
Safe to run repeatedly: an existing account with that email is left untouched.
"""
import asyncio
import sys

from sqlalchemy import select

from app.auth.model import User, UserRole
from app.auth.schema import UserIN
from app.auth.security import get_password_hash
from app.core.settings import settings
from db.config import async_session, engine


async def seed_admin() -> str:
    if not settings.ADMIN_EMAIL or not settings.ADMIN_PASSWORD:
        raise SystemExit("Set ADMIN_EMAIL and ADMIN_PASSWORD in .env before seeding.")

    # reuse the registration rules so the seeded password/email are valid and normalised
    admin = UserIN(
        name=settings.ADMIN_NAME,
        email=settings.ADMIN_EMAIL,
        password=settings.ADMIN_PASSWORD,
    )

    async with async_session() as session:
        existing = (await session.scalars(select(User).where(User.email == admin.email))).first()
        if existing:
            return f"Admin {admin.email} already exists - nothing changed."

        session.add(
            User(
                name=admin.name,
                email=admin.email,
                password_hash=await get_password_hash(admin.password),
                role=UserRole.docbro,
                is_verified=True,
                is_admin=True,
                is_superuser=True,
            )
        )
        await session.commit()
        return f"Created admin {admin.email}."


async def main() -> None:
    try:
        print(await seed_admin())
    finally:
        await engine.dispose()


if __name__ == "__main__":
    # asyncpg needs the selector loop on Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
