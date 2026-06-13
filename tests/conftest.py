"""Fixtures compartidas por los tests.

Los tests asumen que el modelo y los datos de prueba YA fueron descargados del bucket
por scripts/download_artifacts.py (en CI) o manualmente (en local), y estan en:
    ./model.onnx
    ./test_data.csv
"""

import os

import onnxruntime as ort
import pandas as pd
import pytest

MODEL_PATH = os.environ.get("MODEL_PATH", "model.onnx")
TEST_DATA_PATH = os.environ.get("TEST_DATA_PATH", "test_data.csv")


@pytest.fixture(scope="session")
def onnx_session() -> ort.InferenceSession:
    if not os.path.exists(MODEL_PATH):
        pytest.fail(
            f"No se encontro el modelo en '{MODEL_PATH}'. "
            "Ejecuta scripts/download_artifacts.py antes de los tests."
        )
    return ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])


@pytest.fixture(scope="session")
def test_dataframe() -> pd.DataFrame:
    if not os.path.exists(TEST_DATA_PATH):
        pytest.fail(
            f"No se encontraron los datos en '{TEST_DATA_PATH}'. "
            "Ejecuta scripts/download_artifacts.py antes de los tests."
        )
    return pd.read_csv(TEST_DATA_PATH)


@pytest.fixture(scope="session")
def n_features(onnx_session: ort.InferenceSession) -> int:
    shape = onnx_session.get_inputs()[0].shape
    return shape[1] if len(shape) > 1 and isinstance(shape[1], int) else 30
