# Imagen del servicio de inferencia (FastAPI + ONNX Runtime).
# IMPORTANTE: el modelo NO esta en el repo. El job de CI descarga model.onnx del bucket
# (scripts/download_artifacts.py) y lo deja en el contexto de build ANTES de "docker build".
# Aqui simplemente lo horneamos dentro de la imagen con COPY.
FROM python:3.11-slim

# Evita prompts y bytecode innecesario; logs en tiempo real
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

# Instalar dependencias de runtime primero (mejor cacheo de capas)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Codigo de la aplicacion
COPY app/ ./app/

# Modelo descargado del bucket por CI (queda dentro de la imagen)
COPY model.onnx ./model.onnx

EXPOSE 8080

# Cloud Run inyecta $PORT (8080). Usamos shell form para expandir la variable.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
