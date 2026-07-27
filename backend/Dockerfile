# ResQNet-SAGE Backend — Python 3.11 + FastAPI
# GDAL system packages required for the `gdal` and `rasterio` Python packages.

FROM python:3.11-slim-bookworm

# System packages: GDAL + build tools + curl (for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gdal-bin \
        libgdal-dev \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

# GDAL Python bindings must match the system GDAL version exactly.
ENV GDAL_CONFIG=/usr/bin/gdal-config \
    CPLUS_INCLUDE_PATH=/usr/include/gdal \
    C_INCLUDE_PATH=/usr/include/gdal

WORKDIR /app

# Install GDAL Python package matching system version first (avoids pip build failures).
RUN pip install --no-cache-dir "gdal==$(gdal-config --version)"

# Install torch CPU-only (smaller image, no CUDA needed for local-hardware-first).
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install remaining requirements from the pinned lock file.
# --no-deps: the lock file already contains every transitive dependency;
# torch and gdal are installed separately above.
COPY requirements.lock .
RUN pip install --no-cache-dir --no-deps -r requirements.lock

# Copy application code.
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
