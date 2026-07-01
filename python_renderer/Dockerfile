FROM python:3.10-slim

# Instalar dependencias esenciales del sistema y limpiar caché
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && pip install --no-cache-dir playwright google-genai pydantic requests huggingface_hub pillow \
    && playwright install chromium \
    && playwright install-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# Directorio de trabajo interno del contenedor
WORKDIR /app