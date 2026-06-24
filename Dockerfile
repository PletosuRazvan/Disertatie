# ---- Stage 1: build the React frontend ----
FROM node:20-slim AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python backend + built frontend ----
FROM python:3.12-slim AS app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FRONTEND_DIST=/app/frontend_dist \
    FLASK_DEBUG=false

WORKDIR /app

# CPU-only PyTorch first (keeps the image small — no CUDA).
RUN pip install --no-cache-dir torch==2.3.1 --index-url https://download.pytorch.org/whl/cpu

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Backend source (includes trained model artifacts + data CSV).
COPY backend/ ./

# Built frontend from stage 1.
COPY --from=frontend /frontend/dist ./frontend_dist

EXPOSE 5000

# Streaming-friendly: gthread worker keeps NDJSON forecast progress flowing.
CMD ["sh", "-c", "gunicorn wsgi:app --bind 0.0.0.0:${PORT:-5000} --workers 1 --threads 8 --worker-class gthread --timeout 120"]
