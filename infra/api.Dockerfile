FROM python:3.14-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (preserving structure)
COPY api/app ./app
COPY api/alembic ./alembic
COPY api/alembic.ini ./alembic.ini
COPY api/main.py ./main.py
COPY infra/api-entrypoint.sh /usr/local/bin/api-entrypoint

# Verify the module structure is correct
RUN python -c "from main import app; print('Import OK')"
RUN chmod +x /usr/local/bin/api-entrypoint

EXPOSE 8000

# main.py is at root, not inside app/
ENTRYPOINT ["api-entrypoint"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
