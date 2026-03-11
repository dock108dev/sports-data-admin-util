#!/usr/bin/env python3
"""Seed the initial admin user.

Usage:
    DATABASE_URL=postgresql+asyncpg://... python scripts/seed_admin_user.py

Idempotent — skips if the email already exists.
"""

from __future__ import annotations

import asyncio
import os
import sys

from passlib.context import CryptContext
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Ensure app modules are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.users import User  # noqa: E402

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

ADMIN_EMAIL = "mike.fuscoletti@gmail.com"
ADMIN_PASSWORD = "4815162342bogey"
ADMIN_ROLE = "admin"


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is required.")
        sys.exit(1)

    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Check if user already exists
        result = await session.execute(
            select(User).where(User.email == ADMIN_EMAIL)
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            print(f"User {ADMIN_EMAIL} already exists (id={existing.id}, role={existing.role})")
            if existing.role != ADMIN_ROLE:
                existing.role = ADMIN_ROLE
                await session.commit()
                print(f"  -> Updated role to '{ADMIN_ROLE}'")
            else:
                print("  -> Already admin, nothing to do.")
            await engine.dispose()
            return

        user = User(
            email=ADMIN_EMAIL,
            password_hash=_pwd_ctx.hash(ADMIN_PASSWORD),
            role=ADMIN_ROLE,
            is_active=True,
        )
        session.add(user)
        await session.commit()

        print(f"Created admin user: {ADMIN_EMAIL} (id={user.id})")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
