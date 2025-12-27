FROM python:3.14-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (preserving structure)
COPY api/app ./app
COPY api/main.py ./main.py

# Verify the module structure is correct
RUN python -c "from main import app; print('Import OK')"

EXPOSE 8000

# main.py is at root, not inside app/
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
