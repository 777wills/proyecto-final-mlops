"""API de inferencia (FastAPI) que sirve el modelo ONNX y registra cada prediccion.

Endpoints:
    GET  /health    -> healthcheck (usado por Cloud Run y por los smoke tests)
    GET  /          -> UI HTML sencilla con ejemplos precargados para la demo
    GET  /examples  -> ejemplos benigno/maligno (JSON) para autocompletar el formulario
    POST /predict   -> recibe features, predice y agrega una linea al TXT del bucket
    GET  /logs      -> ultimas predicciones registradas en el TXT del bucket (monitoreo)
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app import examples
from app.gcs_logger import log_prediction, read_last_predictions
from app.model import OnnxModel

ENV = os.environ.get("ENV", "local")
# Version del modelo desplegado. La inyecta el pipeline en el deploy (vars.MODEL_VERSION o el
# SHA corto del commit). Permite VER en /health y en la UI que se despliega un modelo nuevo.
MODEL_VERSION = os.environ.get("MODEL_VERSION", "v1")

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
    features: list[float] = Field(
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
    return {"status": "ok", "env": ENV, "model_version": MODEL_VERSION, "model_loaded": model is not None}


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
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Registrar la prediccion en el TXT del bucket (read-modify-write).
    try:
        log_prediction(req.features, result)
    except Exception as exc:  # noqa: BLE001 - el logging no debe tumbar la prediccion
        print(f"[WARN] No se pudo registrar la prediccion: {exc}")

    return PredictResponse(env=ENV, **result)


@app.get("/logs")
def get_logs(n: int = 20) -> dict:
    """Devuelve las ultimas n predicciones registradas en el TXT del entorno (monitoreo)."""
    try:
        lines = read_last_predictions(n)
    except Exception as exc:  # noqa: BLE001 - no romper si el bucket no esta disponible
        raise HTTPException(status_code=503, detail=f"No se pudieron leer los logs: {exc}") from exc
    return {"env": ENV, "log_file": os.environ.get("LOG_FILE"), "count": len(lines), "predictions": lines}


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
    #logs pre {{ background:#0f172a; color:#e2e8f0; padding:1rem; border-radius:.5rem; overflow:auto; font-size:.8rem; }}
  </style>
</head>
<body>
  <h1>Clasificador Breast Cancer - Nuevo <span class="badge">entorno: {ENV}</span> <span class="badge">modelo: {MODEL_VERSION}</span></h1>
  <p>Carga un ejemplo o pega 30 valores separados por coma y predice.</p>
  <button onclick="loadExample('benigno')">Cargar ejemplo benigno</button>
  <button onclick="loadExample('maligno')">Cargar ejemplo maligno</button>
  <br/><br/>
  <textarea id="features" placeholder="30 valores separados por coma"></textarea>
  <br/>
  <button onclick="predict()">Predecir</button>
  <button onclick="loadLogs()">Ver predicciones recientes</button>
  <div id="result"></div>
  <div id="logs"></div>

  <script>
    let EXAMPLES = {{}};
    fetch('/examples').then(r => r.json()).then(d => {{ EXAMPLES = d.examples; }});
    function loadExample(k) {{
      document.getElementById('features').value = (EXAMPLES[k] || []).join(', ');
    }}
    async function loadLogs() {{
      const res = await fetch('/logs?n=20');
      const box = document.getElementById('logs');
      if (!res.ok) {{ box.textContent = 'No se pudieron cargar los logs.'; return; }}
      const d = await res.json();
      box.innerHTML = '<h3>Ultimas predicciones (' + d.log_file + ')</h3><pre>' +
        (d.predictions.length ? d.predictions.join('\\n') : 'Sin predicciones todavia.') + '</pre>';
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
