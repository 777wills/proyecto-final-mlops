"""API de inferencia (FastAPI) que sirve el modelo ONNX y registra cada prediccion.

Endpoints:
    GET  /health    -> healthcheck (usado por Cloud Run y por los smoke tests)
    GET  /          -> UI HTML sencilla con ejemplos precargados para la demo
    GET  /examples  -> ejemplos benigno/maligno (JSON) para autocompletar el formulario
    POST /predict   -> recibe features, predice y agrega una linea al TXT del bucket
"""
from __future__ import annotations

import os
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app import examples
from app.gcs_logger import log_prediction
from app.model import OnnxModel

ENV = os.environ.get("ENV", "local")

app = FastAPI(
    title="Despliegue automatico de modelos ONNX",
    description="Servicio de inferencia (Breast Cancer) desplegado via CI/CD en Cloud Run.",
    version="1.0.0",
)

# El modelo se carga una vez al arrancar (esta horneado en la imagen).
model: OnnxModel | None = None


@app.on_event("startup")
def _load_model() -> None:
    global model
    model = OnnxModel()


class PredictRequest(BaseModel):
    features: List[float] = Field(
        ...,
        description="Lista de 30 features del dataset Breast Cancer",
        min_length=30,
        max_length=30,
    )


class PredictResponse(BaseModel):
    label: int
    class_name: str
    probability: float | None
    env: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "env": ENV, "model_loaded": model is not None}


@app.get("/examples")
def get_examples() -> dict:
    return {"feature_names": examples.FEATURE_NAMES, "examples": examples.EXAMPLES}


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest) -> PredictResponse:
    if model is None:
        raise HTTPException(status_code=503, detail="Modelo no cargado")
    try:
        result = model.predict(req.features)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Registrar la prediccion en el TXT del bucket (read-modify-write).
    try:
        log_prediction(req.features, result)
    except Exception as exc:  # noqa: BLE001 - el logging no debe tumbar la prediccion
        print(f"[WARN] No se pudo registrar la prediccion: {exc}")

    return PredictResponse(env=ENV, **result)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return f"""
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <title>Modelo ONNX - {ENV}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 760px; margin: 2rem auto; padding: 0 1rem; }}
    .badge {{ background:#2563eb; color:#fff; padding:.2rem .6rem; border-radius:.4rem; font-size:.8rem; }}
    textarea {{ width:100%; height:120px; font-family:monospace; }}
    button {{ margin:.2rem; padding:.5rem .9rem; cursor:pointer; }}
    #result {{ margin-top:1rem; padding:1rem; background:#f1f5f9; border-radius:.5rem; white-space:pre-wrap; }}
  </style>
</head>
<body>
  <h1>Clasificador Breast Cancer <span class="badge">entorno: {ENV}</span></h1>
  <p>Carga un ejemplo o pega 30 valores separados por coma y predice.</p>
  <button onclick="loadExample('benigno')">Cargar ejemplo benigno</button>
  <button onclick="loadExample('maligno')">Cargar ejemplo maligno</button>
  <br/><br/>
  <textarea id="features" placeholder="30 valores separados por coma"></textarea>
  <br/>
  <button onclick="predict()">Predecir</button>
  <div id="result"></div>

  <script>
    let EXAMPLES = {{}};
    fetch('/examples').then(r => r.json()).then(d => {{ EXAMPLES = d.examples; }});
    function loadExample(k) {{
      document.getElementById('features').value = (EXAMPLES[k] || []).join(', ');
    }}
    async function predict() {{
      const raw = document.getElementById('features').value.split(',').map(s => parseFloat(s.trim()));
      const res = await fetch('/predict', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ features: raw }})
      }});
      const out = document.getElementById('result');
      if (!res.ok) {{ out.textContent = 'Error: ' + (await res.text()); return; }}
      const d = await res.json();
      out.textContent = 'Prediccion: ' + d.class_name + ' (label=' + d.label +
        ', probabilidad=' + (d.probability !== null ? d.probability.toFixed(4) : 'N/A') + ')';
    }}
  </script>
</body>
</html>
"""
