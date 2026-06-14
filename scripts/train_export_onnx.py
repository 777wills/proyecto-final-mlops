"""Entrena un clasificador sobre el dataset Breast Cancer, lo exporta a ONNX con nombre
versionado, actualiza model_version.txt y, opcionalmente, sube los artefactos al bucket de GCS.

Uso típico:
    # Solo local (sin subida a GCS):
    python scripts/train_export_onnx.py --version v3

    # Con subida automática al bucket (entorno dev):
    python scripts/train_export_onnx.py --version v3 --bucket <bucket>
    # o bien con la variable de entorno: GCS_BUCKET=<bucket> python scripts/train_export_onnx.py --version v3

    # Demo negativa (modelo malo):
    python scripts/train_export_onnx.py --version vbad --bad
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd
from skl2onnx import to_onnx
from sklearn.datasets import load_breast_cancer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Entrena y exporta el modelo Breast Cancer a ONNX, actualiza model_version.txt"
    )
    parser.add_argument(
        "--version",
        required=True,
        help="Versión del modelo (ej: v3). Nombra el archivo model-v3.onnx y actualiza model_version.txt.",
    )
    parser.add_argument(
        "--bad",
        action="store_true",
        help="Entrena un modelo deliberadamente malo (para demostrar que el pipeline lo rechaza).",
    )
    parser.add_argument(
        "--out-dir",
        default=".",
        help="Carpeta de salida local para model-<version>.onnx y test_data.csv.",
    )
    parser.add_argument(
        "--bucket",
        default=os.environ.get("GCS_BUCKET"),
        help=(
            "Nombre del bucket de GCS (sin gs://). Si se indica (o existe GCS_BUCKET), "
            "sube automáticamente el modelo y los datos al entorno dev del bucket."
        ),
    )
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    data = load_breast_cancer()
    X = data.data.astype(np.float32)
    y = data.target.astype(np.int64)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)

    # Pipeline: estandarizacion + regresion logistica.
    clf = LogisticRegression(max_iter=10000, random_state=42)
    model = make_pipeline(StandardScaler(), clf)

    if args.bad:
        # Modelo intencionalmente malo: se entrena con las etiquetas BARAJADAS,
        # por lo que aprende ruido -> accuracy ~0.5, el test de metrica debe FALLAR.
        rng = np.random.RandomState(0)
        y_corrupted = y_train.copy()
        rng.shuffle(y_corrupted)
        model.fit(X_train, y_corrupted)
        print(">> Entrenando modelo MALO (demo negativa)")
    else:
        model.fit(X_train, y_train)
        print(f">> Entrenando modelo BUENO (versión {args.version})")

    acc = (model.predict(X_test) == y_test).mean()
    print(f">> Accuracy sobre el set de prueba: {acc:.4f}")

    # Exportar a ONNX con nombre versionado. 'zipmap=False' hace que las probabilidades
    # salgan como tensor, mas facil de consumir con onnxruntime.
    model_filename = f"model-{args.version}.onnx"
    model_path = os.path.join(args.out_dir, model_filename)
    onnx_model = to_onnx(
        model,
        X_train[:1],
        options={"zipmap": False},
        target_opset=15,
    )
    with open(model_path, "wb") as f:
        f.write(onnx_model.SerializeToString())
    print(f">> Modelo ONNX guardado en: {model_path}")

    # CSV de datos de prueba: 30 features + columna 'target'
    feature_names = list(data.feature_names)
    df = pd.DataFrame(X_test, columns=feature_names)
    df["target"] = y_test
    csv_path = os.path.join(args.out_dir, "test_data.csv")
    df.to_csv(csv_path, index=False)
    print(f">> Datos de prueba guardados en: {csv_path} ({len(df)} filas)")

    # Actualizar model_version.txt en la raíz del repositorio.
    version_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "model_version.txt")
    with open(version_file, "w", encoding="utf-8") as f:
        f.write(args.version + "\n")
    print(f">> model_version.txt actualizado a: {args.version}")

    # Subir al bucket de GCS si está configurado.
    if args.bucket:
        try:
            from google.cloud import storage as gcs
        except ImportError:
            print("AVISO: google-cloud-storage no instalado; omitiendo subida a GCS.", file=sys.stderr)
            return

        try:
            client = gcs.Client()
        except Exception as exc:
            print(
                f"ERROR: no se pudo autenticar en GCS: {exc}\n"
                "Ejecuta: gcloud auth application-default login",
                file=sys.stderr,
            )
            sys.exit(1)
        bucket_obj = client.bucket(args.bucket)

        gcs_model_blob = f"models/dev/{model_filename}"
        bucket_obj.blob(gcs_model_blob).upload_from_filename(model_path)
        print(f">> Subido a gs://{args.bucket}/{gcs_model_blob}")

        gcs_data_blob = "data/test_data.csv"
        bucket_obj.blob(gcs_data_blob).upload_from_filename(csv_path)
        print(f">> Subido a gs://{args.bucket}/{gcs_data_blob}")
    else:
        print(
            f"AVISO: bucket no configurado. Sube manualmente:\n"
            f"  gcloud storage cp {model_path} gs://<bucket>/models/dev/{model_filename}\n"
            f"  gcloud storage cp {csv_path} gs://<bucket>/data/test_data.csv"
        )


if __name__ == "__main__":
    main()
