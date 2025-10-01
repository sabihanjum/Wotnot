# ---------------------------
# Stage 1: Build frontend
# ---------------------------
FROM node:18 AS frontend-builder

WORKDIR /frontend

# Install frontend dependencies
COPY frontend/package*.json ./
RUN npm install

# Copy frontend source and build
COPY frontend/ .
RUN npm run build


# ---------------------------
# Stage 2: Backend with Python
# ---------------------------
FROM python:3.10-slim

WORKDIR /app

# Install backend dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source code
COPY backend/ .

# Copy built frontend into backend's static directory
COPY --from=frontend-builder /frontend/dist ./static

# Expose port
EXPOSE 8000

# Run FastAPI with Uvicorn
CMD ["uvicorn", "wati.main:app", "--host", "0.0.0.0", "--port", "8000"]
