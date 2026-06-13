# Imagen del servicio de inferencia (FastAPI + ONNX Runtime).
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
