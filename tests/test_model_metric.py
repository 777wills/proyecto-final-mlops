"""PRUEBA 2 (obligatoria): la metrica del modelo no cae por debajo del umbral definido.

Si el accuracy del modelo nuevo sobre los datos de prueba es menor al umbral,
el test falla y el pipeline NO despliega el modelo. Esto evita degradar produccion.
"""

import os

import numpy as np

# Umbral configurable por variable de entorno; por defecto 0.90.
METRIC_THRESHOLD = float(os.environ.get("METRIC_THRESHOLD", "0.90"))


def test_accuracy_no_cae_bajo_umbral(onnx_session, test_dataframe):
    feature_cols = [c for c in test_dataframe.columns if c != "target"]
    X = test_dataframe[feature_cols].to_numpy(dtype=np.float32)
    y_true = test_dataframe["target"].to_numpy(dtype=int)

    input_name = onnx_session.get_inputs()[0].name
    output_names = [o.name for o in onnx_session.get_outputs()]
    outputs = onnx_session.run(output_names, {input_name: X})
    y_pred = np.asarray(outputs[0]).ravel().astype(int)

    accuracy = float((y_pred == y_true).mean())
    print(f"\nAccuracy del modelo: {accuracy:.4f} (umbral minimo: {METRIC_THRESHOLD})")

    assert accuracy >= METRIC_THRESHOLD, (
        f"El accuracy {accuracy:.4f} cayo por debajo del umbral {METRIC_THRESHOLD}. "
        "El modelo NO debe desplegarse."
    )
