FROM python:3.10-slim

# Instalar dependencias esenciales del sistema y limpiar caché
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && pip install --no-cache-dir playwright google-genai pydantic \
    && playwright install chromium \
    && playwright install-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# 1. Cambiamos el directorio de trabajo a la ruta unificada
WORKDIR /home/node/.n8n-files
