"""pytest configuration and fixtures."""

import os

# Set required environment variables for testing before any imports
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")
