# ---------------------------
# Stage 1: Build frontend
# ---------------------------
FROM node:18 AS frontend-builder

WORKDIR /app/frontend

# Install frontend dependencies
COPY frontend/package*.json ./
RUN npm install --legacy-peer-deps

# Copy frontend source and build
COPY frontend/ .
RUN npm run build


# ---------------------------
# Stage 2: Backend
# ---------------------------
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Set environment for Rust-based builds (pydantic-core, orjson, etc.)
ENV CARGO_NET_GIT_FETCH_WITH_CLI=true

# Install backend dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ .

# Copy built frontend to backend/static
COPY --from=frontend-builder /app/frontend/dist ./static

# Expose FastAPI port
EXPOSE 8000

# Start FastAPI app
CMD ["uvicorn", "wati.main:app", "--host", "0.0.0.0", "--port", "8000"]
