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
