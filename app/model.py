"""Carga del modelo ONNX e inferencia con ONNX Runtime."""

from __future__ import annotations

import os

import numpy as np
import onnxruntime as ort

# Ruta donde el Dockerfile horneo el modelo descargado del bucket en CI.
MODEL_PATH = os.environ.get("MODEL_PATH", "model.onnx")

# Etiquetas legibles para el dataset Breast Cancer (0 = maligno, 1 = benigno).
CLASS_NAMES = {0: "maligno", 1: "benigno"}


class OnnxModel:
    """Envuelve una sesion de ONNX Runtime y expone una prediccion sencilla."""

    def __init__(self, model_path: str = MODEL_PATH):
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"No se encontro el modelo en '{model_path}'. "
                "En produccion lo hornea el Dockerfile; en local descargalo del bucket."
            )
        self.session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]
        # Numero de features esperado (segunda dimension del input).
        shape = self.session.get_inputs()[0].shape
        self.n_features = shape[1] if len(shape) > 1 and isinstance(shape[1], int) else None

    def predict(self, features: list[float]) -> dict:
        """Recibe una lista de features y devuelve label, nombre de clase y probabilidad."""
        x = np.asarray(features, dtype=np.float32).reshape(1, -1)
        if self.n_features is not None and x.shape[1] != self.n_features:
            raise ValueError(f"Se esperaban {self.n_features} features y llegaron {x.shape[1]}.")
        outputs = self.session.run(self.output_names, {self.input_name: x})

        label = int(np.asarray(outputs[0]).ravel()[0])
        probability = None
        if len(outputs) > 1:
            probs = np.asarray(outputs[1]).reshape(1, -1)[0]
            probability = float(probs[label]) if label < len(probs) else float(np.max(probs))

        return {
            "label": label,
            "class_name": CLASS_NAMES.get(label, str(label)),
            "probability": probability,
        }


def predict_batch(session: ort.InferenceSession, X: np.ndarray) -> np.ndarray:
    """Predice etiquetas para un lote (usado en los tests de metrica)."""
    input_name = session.get_inputs()[0].name
    output_names = [o.name for o in session.get_outputs()]
    outputs = session.run(output_names, {input_name: X.astype(np.float32)})
    return np.asarray(outputs[0]).ravel().astype(int)
