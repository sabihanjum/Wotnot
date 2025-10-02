# Stage 1: Build frontend
FROM node:18 AS frontend-builder
WORKDIR /app/frontend/app

# Install frontend dependencies
COPY frontend/app/package*.json ./
RUN npm install --legacy-peer-deps

# Copy all frontend source, then build
COPY frontend/app/ ./
RUN npm run build

# Stage 2: Backend
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

ENV CARGO_NET_GIT_FETCH_WITH_CLI=true

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/

# Copy built frontend to backend/static
COPY --from=frontend-builder /app/frontend/app/dist ./backend/static

EXPOSE 8000
CMD ["uvicorn", "backend.wati.main:app", "--host", "0.0.0.0", "--port", "8000"]
