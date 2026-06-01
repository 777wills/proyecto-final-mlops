"""Registro de predicciones en un archivo TXT dentro del bucket de GCS.

Cada peticion agrega una nueva linea al archivo del entorno correspondiente
(logs/predicciones_dev.txt o logs/predicciones_prod.txt).

GCS no soporta 'append' nativo, asi que usamos read-modify-write:
descargar el contenido actual, agregar la linea y volver a subir. Es suficiente
para el volumen de la demo (la limitacion de concurrencia se documenta en el README).

Si no hay bucket configurado (desarrollo local), cae a un archivo local para no romper.
"""

from __future__ import annotations

import datetime
import os
import threading

# Evita condiciones de carrera entre hilos del mismo proceso (uvicorn workers async).
_lock = threading.Lock()

GCS_BUCKET = os.environ.get("GCS_BUCKET")
LOG_FILE = os.environ.get("LOG_FILE", "logs/predicciones_dev.txt")
ENV = os.environ.get("ENV", "local")


def _build_line(features, result: dict) -> str:
    ts = datetime.datetime.now(datetime.UTC).isoformat()
    return (
        f"{ts} | env={ENV} | entrada={features} | "
        f"label={result.get('label')} | clase={result.get('class_name')} | "
        f"prob={result.get('probability')}\n"
    )


def log_prediction(features, result: dict) -> None:
    """Agrega una linea con la prediccion al TXT del bucket (o a un archivo local)."""
    line = _build_line(features, result)

    if not GCS_BUCKET:
        # Modo local sin bucket: escribir a archivo local para no fallar.
        with _lock:
            local_path = os.path.basename(LOG_FILE)
            with open(local_path, "a", encoding="utf-8") as f:
                f.write(line)
        return

    # Import perezoso para que el modo local no requiera la libreria/credenciales.
    from google.cloud import storage

    with _lock:
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(LOG_FILE)

        current = blob.download_as_text() if blob.exists() else ""
        blob.upload_from_string(current + line, content_type="text/plain")


def read_last_predictions(n: int = 50) -> list[str]:
    """Devuelve las ultimas n predicciones registradas (para el endpoint /logs).

    Lee el TXT del bucket (o el archivo local en modo desarrollo) y devuelve las
    ultimas n lineas no vacias. Permite DEMOSTRAR en vivo que cada llamada a
    /predict queda registrada para futuros monitoreos/analisis.
    """
    if not GCS_BUCKET:
        local_path = os.path.basename(LOG_FILE)
        if not os.path.exists(local_path):
            return []
        with _lock, open(local_path, encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        return lines[-n:]

    from google.cloud import storage

    with _lock:
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(LOG_FILE)
        if not blob.exists():
            return []
        content = blob.download_as_text()

    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    return lines[-n:]
