"""Entrena un clasificador sobre el dataset Breast Cancer, lo exporta a ONNX y
genera el CSV de datos de prueba.
"""

import argparse
import os

import numpy as np
import pandas as pd
from skl2onnx import to_onnx
from sklearn.datasets import load_breast_cancer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def main() -> None:
    parser = argparse.ArgumentParser(description="Entrena y exporta el modelo Breast Cancer a ONNX")
    parser.add_argument("--out-dir", default=".", help="Carpeta de salida para model.onnx y test_data.csv")
    parser.add_argument(
        "--bad",
        action="store_true",
        help="Entrena un modelo deliberadamente malo (para demostrar que el pipeline lo rechaza)",
    )
    parser.add_argument(
        "--variant",
        choices=["v1", "v2"],
        default="v1",
        help=(
            "Variante del modelo BUENO. v1 = LogisticRegression base (C=1.0); "
            "v2 = LogisticRegression mas regularizada (C=0.05, solver=liblinear). "
            "Sirve para demostrar el despliegue de un MODELO NUEVO y distinto que igual pasa el umbral."
        ),
    )
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    data = load_breast_cancer()
    X = data.data.astype(np.float32)
    y = data.target.astype(np.int64)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)

    # Pipeline: estandarizacion + regresion logistica. Exporta a ONNX de forma
    # estable (clasificador lineal) y alcanza ~0.97 de accuracy en este dataset.
    # La variante v2 usa una regularizacion mas fuerte: es un MODELO DISTINTO (otros
    # coeficientes y probabilidades) que igualmente supera el umbral de metrica.
    if args.variant == "v2":
        clf = LogisticRegression(C=0.05, penalty="l2", solver="liblinear", max_iter=10000, random_state=42)
    else:
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
        print(f">> Entrenando modelo BUENO (variante {args.variant})")

    acc = (model.predict(X_test) == y_test).mean()
    print(f">> Accuracy sobre el set de prueba: {acc:.4f}")

    # Exportar a ONNX. 'zipmap=False' hace que las probabilidades salgan como tensor,
    # mas facil de consumir con onnxruntime.
    onnx_model = to_onnx(
        model,
        X_train[:1],
        options={"zipmap": False},
        target_opset=15,
    )
    model_path = os.path.join(args.out_dir, "model.onnx")
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


if __name__ == "__main__":
    main()
