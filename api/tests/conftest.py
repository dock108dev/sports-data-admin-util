"""pytest configuration and fixtures."""

import os

# Set required environment variables for testing before any imports
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")

# Register all SQLAlchemy models so mapper relationships resolve correctly.
# Without this, running a subset of tests may fail if a model referenced by a
# relationship (e.g., SportsScrapeRun from SportsLeague) hasn't been imported.
import app.db.flow  # noqa: F401, E402
import app.db.scraper  # noqa: F401, E402
import app.db.social  # noqa: F401, E402
