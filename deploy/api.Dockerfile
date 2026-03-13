# ---------- API ----------
FROM python:3.12-slim AS base

WORKDIR /app

# Install dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/

EXPOSE 8000

CMD ["uvicorn", "backend.apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
