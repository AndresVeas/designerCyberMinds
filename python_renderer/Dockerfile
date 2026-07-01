FROM python:3.10-slim

# Instalar dependencias esenciales del sistema y limpiar caché
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium \
    && playwright install-deps chromium

# Directorio de trabajo interno del contenedor
WORKDIR /app