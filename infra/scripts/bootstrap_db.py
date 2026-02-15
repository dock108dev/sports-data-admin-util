#!/usr/bin/env python3
"""Bootstrap the database with schema and stamp alembic at heads.

This script:
1. Creates all tables from SQLAlchemy models
2. Stamps alembic at all heads to skip incremental migrations

Use this for development instead of running migrations.
"""

import asyncio
import os
import sys

# Add API to path
sys.path.insert(0, "/app")

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.db import Base
# Import all model modules so their tables register with Base.metadata
import app.db.sports  # noqa: F401
import app.db.flow  # noqa: F401
import app.db.pipeline  # noqa: F401
import app.db.social  # noqa: F401
import app.db.scraper  # noqa: F401
import app.db.odds  # noqa: F401
import app.db.resolution  # noqa: F401
import app.db.config  # noqa: F401
import app.db.cache  # noqa: F401


async def bootstrap():
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://sports:sports@postgres:5432/sports"
    )

    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        # Create all tables from models
        await conn.run_sync(Base.metadata.create_all)
        print("Created all tables from SQLAlchemy models")

        # Create alembic_version table if it doesn't exist
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num VARCHAR(32) NOT NULL,
                CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
            )
        """))

        # Clear existing version stamps
        await conn.execute(text("DELETE FROM alembic_version"))

        # Stamp at the merged head
        # This is the merged head from the alembic merge we did earlier
        await conn.execute(text("""
            INSERT INTO alembic_version (version_num) VALUES
            ('2a6236c3c8c4')
        """))
        print("Stamped alembic at head: 2a6236c3c8c4")

    await engine.dispose()
    print("Database bootstrap complete!")


if __name__ == "__main__":
    asyncio.run(bootstrap())
