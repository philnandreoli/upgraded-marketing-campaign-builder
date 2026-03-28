# ---------- Worker ----------
FROM python:3.12-slim AS base

WORKDIR /app

# Install dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/

# Run as non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup --no-create-home appuser
USER appuser

CMD ["python", "-m", "backend.worker"]
