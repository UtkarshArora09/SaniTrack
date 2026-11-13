# Use a slim Python base image for deployment
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System packages needed for OpenCV and model inference
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

# Ensure runtime directories exist even when ignored by git
RUN mkdir -p backend/data/uploads backend/data/inspections backend/data/face_dataset

EXPOSE 5050

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5050} wsgi:app --workers 1 --threads 4 --timeout 180"]
