FROM node:22-alpine AS dashboard

WORKDIR /dashboard
COPY dashboard/package.json dashboard/vite.config.js dashboard/index.html ./
COPY dashboard/src src
RUN npm install && npm run build

FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app app
COPY models models
COPY --from=dashboard /dashboard/dist dashboard/dist

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
