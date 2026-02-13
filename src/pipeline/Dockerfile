# Geo Change Risk Pipeline - Docker build
FROM python:3.11-slim AS base

# Install GDAL native libraries and build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Set GDAL environment
ENV GDAL_CONFIG=/usr/bin/gdal-config

WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY georisk/ georisk/

# Install base dependencies (no ML for initial deployment)
RUN pip install --no-cache-dir -e .

ENTRYPOINT ["python", "-m", "georisk.cli"]
