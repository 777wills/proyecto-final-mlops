# Despliegue automático de modelos ONNX (MLOps)

Sistema de **CI/CD para el despliegue automático de modelos de Machine Learning** en formato
ONNX. Partiendo del supuesto de que ya existe un modelo en producción, este repositorio permite
que **cada nuevo modelo se pruebe y se despliegue de forma automática** para que los usuarios
finales lo consuman a través de una API.

El caso de uso de ejemplo es un **clasificador de cáncer de mama** (dataset *Breast Cancer* de
scikit-learn): dado un vector de 30 mediciones, predice si un tumor es **benigno** o **maligno**.

---

## Arquitectura

```
   PR ──► (test gate)         merge ──► push
                                          │
              ▼                           ▼
   ┌─────────────────────────────────────────────┐
   │            GitHub Actions (CI/CD)            │
   │                                             │
   │  PR:   [test]                               │
   │  push: [test] ──► [build/promote] ──► Cloud Run
   │     │              │                        │
   │     │ descarga     │ descarga modelo,       │
   │     │ modelo+datos │ construye imagen,      │
   │     ▼              ▼ despliega endpoint     │
   └─────┼──────────────┼────────────────────────┘
         │              │
         ▼              ▼
   ┌──────────────────────────────┐      ┌──────────────────────────┐
   │       Google Cloud Storage    │      │        Cloud Run          │
   │  models/dev/model.onnx        │      │  model-api-dev   (dev)    │
   │  models/prod/model.onnx       │◄─────┤  model-api-prod  (prod)   │
   │  data/test_data.csv           │ logs │  cada /predict agrega     │
   │  logs/predicciones_dev.txt    │◄─────┤  una linea al TXT         │
   │  logs/predicciones_prod.txt   │      └──────────────────────────┘
   └──────────────────────────────┘
```

- **Nube:** Google Cloud Platform (Cloud Run + Cloud Storage + Artifact Registry).
- **App:** FastAPI + ONNX Runtime, empaquetada en un contenedor Docker.
- **Dos entornos = dos endpoints:** la rama `dev` despliega el servicio `model-api-dev` y la rama
  `prod` despliega `model-api-prod`. Cada uno tiene su propia URL HTTPS estable.

---

## Flujo de trabajo con Pull Requests (branch protection)

Las ramas `dev` y `prod` están **protegidas**: no se permite `push` directo. Todo cambio entra por
**Pull Request**, y para poder hacer *merge* el check **`test`** debe pasar (regla de *required
status check*). Esto garantiza que **ningún modelo o código llegue a un entorno sin pasar las
pruebas**.

- **Al abrir/actualizar un PR** hacia `dev` o `prod` → se ejecuta **solo la etapa `test`** (gate de
  calidad). No se despliega nada.
- **Al hacer *merge*** (que produce un `push` a la rama) → se ejecuta **`test` + `build/promote`** y
  se actualiza el endpoint del entorno.

> La configuración exacta de las *branch protection rules* está documentada en `indicaciones-william.md`.

---

## El modelo NO vive en el repositorio

El archivo `.onnx` **nunca** se versiona (está en `.gitignore`). El repositorio solo guarda una
**referencia** al modelo mediante la variable `MODEL_GCS_URI` (configurada por entorno). El modelo
se descarga del bucket de GCS durante el pipeline:

- En la etapa **test** para correr las pruebas.
- En la etapa **build/promote** para hornearlo dentro de la imagen Docker.

---

## Pipeline de CI/CD (`.github/workflows/deploy.yml`)

Se dispara con `pull_request` y con `push` a `dev`/`prod`. Mediante GitHub Environments selecciona
las variables/secrets del entorno correspondiente (en PR se toma de la rama destino, `base_ref`).

### Etapa `test` (corre en PR y en push)
1. Autentica en GCP.
2. Descarga `model.onnx` y `test_data.csv` desde el bucket (`scripts/download_artifacts.py`).
3. Corre las pruebas unitarias con `pytest`:
   - **`test_model_response`**: el modelo responde con una salida válida ante una entrada definida.
   - **`test_model_metric`**: el *accuracy* sobre los datos de prueba **no cae por debajo del
     umbral** (`0.90` por defecto). Si cae, el pipeline falla y **no se permite el merge ni el deploy**.

### Etapa `build/promote` (corre solo en push, tras el merge)
1. (Solo `prod`) **Promueve** el modelo validado: copia `models/dev/model.onnx` → `models/prod/model.onnx`.
2. Descarga el modelo del bucket (según `MODEL_GCS_URI` del entorno).
3. Construye la imagen Docker (con el modelo horneado) y la publica en Artifact Registry.
4. **Despliega en Cloud Run**, actualizando el endpoint del entorno.

---

## La aplicación (FastAPI)

| Endpoint | Descripción |
|----------|-------------|
| `GET /health` | Healthcheck (usado por Cloud Run y smoke tests). |
| `GET /` | UI HTML sencilla con ejemplos precargados (benigno/maligno) para la demo. |
| `GET /examples` | Devuelve los ejemplos y nombres de features (JSON). |
| `POST /predict` | Recibe `{"features": [30 valores]}`, predice y **registra la predicción**. |
| `GET /docs` | Documentación interactiva automática (Swagger). |

### Registro de predicciones (monitoreo)
Cada llamada a `/predict` agrega una línea al archivo TXT del entorno en el bucket
(`logs/predicciones_dev.txt` o `logs/predicciones_prod.txt`), con timestamp, entrada y predicción.
Como GCS no soporta *append* nativo, se usa **read-modify-write** (suficiente para el volumen de la
demo; ver *Limitaciones*).

Ejemplo de petición:
```bash
curl -X POST "$URL/predict" \
  -H "Content-Type: application/json" \
  -d '{"features": [13.54,14.36,87.46,566.3,0.09779,0.08129,0.06664,0.04781,0.1885,0.05766,0.2699,0.7886,2.058,23.56,0.008462,0.0146,0.02387,0.01315,0.0198,0.0023,15.11,19.26,99.7,711.2,0.144,0.1773,0.239,0.1288,0.2977,0.07259]}'
```

---

## Estructura del repositorio

```
.
├── .github/workflows/deploy.yml   # pipeline CI/CD (test en PR; test + build/promote en push)
├── app/                           # aplicación FastAPI + inferencia ONNX
│   ├── main.py                    # endpoints (/, /health, /examples, /predict)
│   ├── model.py                   # carga e inferencia del modelo ONNX
│   ├── gcs_logger.py              # registro de predicciones en GCS (read-modify-write)
│   └── examples.py                # ejemplos precargados para la UI/demo
├── tests/                         # pruebas unitarias (corren en CI)
│   ├── conftest.py
│   ├── test_model_response.py     # PRUEBA 1: el modelo responde
│   └── test_model_metric.py       # PRUEBA 2: umbral de métrica
├── scripts/
│   ├── train_export_onnx.py       # entrena + exporta a ONNX + genera datos de prueba
│   └── download_artifacts.py      # descarga modelo/datos desde GCS (en CI)
├── Dockerfile                     # imagen del servicio (hornea el modelo descargado en CI)
├── requirements.txt               # dependencias de runtime
├── requirements-dev.txt           # dependencias de CI/local (test + entrenamiento)
├── .gitignore                     # excluye *.onnx, *.csv y credenciales
└── README.md
```

## Ramas

- **`dev`**: entorno de desarrollo. Protegida (PR + check `test`). Al hacer merge despliega a `model-api-dev`.
- **`prod`**: entorno de producción. Protegida (PR + check `test`). Al hacer merge promueve el modelo
  validado y despliega a `model-api-prod`.

---

## Cómo desplegar un modelo nuevo (flujo MLOps)

1. Entrena/obtén el nuevo modelo y súbelo a `gs://<bucket>/models/dev/model.onnx`.
2. Crea una rama de trabajo y abre un **Pull Request hacia `dev`** → se ejecuta `test`. Si pasa,
   haz *merge*; el `push` resultante despliega en el endpoint `dev`.
3. Valida el endpoint `dev`. Si todo está bien, abre un **Pull Request de `dev` hacia `prod`** →
   se ejecuta `test`; al hacer *merge*, el pipeline **promueve** el modelo (dev→prod) y despliega
   en el endpoint `prod`.

---

## Ejecución local (opcional)

```bash
pip install -r requirements-dev.txt
python scripts/train_export_onnx.py      # genera model.onnx y test_data.csv
pytest -v                                # corre las pruebas
docker build -t modelo-onnx .
docker run -p 8080:8080 -e ENV=local modelo-onnx
# abrir http://localhost:8080
```

---

## Limitaciones conocidas

- El registro de predicciones (read-modify-write a GCS) **no es atómico** bajo alta concurrencia;
  es suficiente para la demo. Para producción real se usaría una cola/log estructurado o BigQuery.
- Los endpoints se despliegan con `--allow-unauthenticated` para facilitar la demo. En un entorno
  real se restringiría el acceso (IAM / API Gateway).
