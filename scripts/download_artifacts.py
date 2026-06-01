"""Descarga el modelo ONNX y los datos de prueba desde GCS al runner de CI (o a local).

Cumple el requisito del enunciado: ni el modelo ni los datos de prueba existen en el
repositorio; se obtienen en tiempo de ejecucion del pipeline desde el bucket.

Variables de entorno usadas:
    GCS_BUCKET     -> nombre del bucket (ej: mi-bucket-mlops)
    MODEL_GCS_URI  -> uri completa del modelo (ej: gs://mi-bucket-mlops/models/dev/model.onnx)
    TEST_DATA_URI  -> (opcional) uri del CSV; por defecto gs://<GCS_BUCKET>/data/test_data.csv

USO:
    python scripts/download_artifacts.py                 # descarga modelo + datos
    python scripts/download_artifacts.py --model-only     # solo el modelo (para el build)
"""

import argparse
import os
import sys

from google.cloud import storage


def parse_gcs_uri(uri: str):
    """gs://bucket/path/objeto -> (bucket, path/objeto)"""
    if not uri.startswith("gs://"):
        raise ValueError(f"URI invalida (esperaba gs://...): {uri}")
    without_scheme = uri[len("gs://") :]
    bucket, _, blob = without_scheme.partition("/")
    if not bucket or not blob:
        raise ValueError(f"URI invalida (esperaba gs://bucket/objeto): {uri}")
    return bucket, blob


def download(client: storage.Client, uri: str, dest: str) -> None:
    bucket_name, blob_name = parse_gcs_uri(uri)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    if not blob.exists():
        raise FileNotFoundError(f"No existe el objeto en GCS: {uri}")
    blob.download_to_filename(dest)
    print(f">> Descargado {uri} -> {dest}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Descarga artefactos (modelo/datos) desde GCS")
    parser.add_argument("--model-only", action="store_true", help="Descargar solo el modelo")
    parser.add_argument("--model-dest", default="model.onnx", help="Ruta local del modelo")
    parser.add_argument("--data-dest", default="test_data.csv", help="Ruta local del CSV de prueba")
    args = parser.parse_args()

    bucket = os.environ.get("GCS_BUCKET")
    model_uri = os.environ.get("MODEL_GCS_URI")
    if not model_uri:
        print("ERROR: falta la variable de entorno MODEL_GCS_URI", file=sys.stderr)
        sys.exit(1)

    data_uri = os.environ.get("TEST_DATA_URI")
    if not data_uri and bucket:
        data_uri = f"gs://{bucket}/data/test_data.csv"

    client = storage.Client()

    download(client, model_uri, args.model_dest)

    if not args.model_only:
        if not data_uri:
            print("ERROR: define TEST_DATA_URI o GCS_BUCKET para los datos de prueba", file=sys.stderr)
            sys.exit(1)
        download(client, data_uri, args.data_dest)


if __name__ == "__main__":
    main()
