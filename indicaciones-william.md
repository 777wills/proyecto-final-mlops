# Indicaciones para William (ARCHIVO TEMPORAL — borrar al finalizar)

Este documento lista **todo lo que debes hacer fuera del workspace** para dejar el sistema 100%
funcional. No reemplaza al `README.md`. Bórralo cuando termines la entrega.

> Ya tienes cuenta de GCP. Donde veas `<...>` reemplaza por tus valores.

Valores definidos para este proyecto:

| Variable                      | Valor                         |
| ----------------------------- | ----------------------------- |
| `PROJECT_ID`                  | `proyecto-final-mlops`        |
| `BUCKET` (único global)       | `proyecto-final-mlops-bucket` |
| `REGION`                      | `us-central1`                 |
| `AR_REPO` (Artifact Registry) | `mlops-models`                |

> Si `PROJECT_ID` o `BUCKET` resultan no estar disponibles (son únicos a nivel global), elige otro
> sufijo y actualiza **todos** los comandos, las variables/secrets de GitHub y este documento.

---

## 0. Herramientas en tu máquina  ✅ (hecho)

- `gcloud` instalado en `~/google-cloud-sdk` (Google Cloud CLI, incluye `gsutil`). Abre una
  **terminal nueva** para tenerlo en el PATH y verifica con `gcloud --version`.
- Docker y Python ya están instalados.
- (Opcional) instala `gh` (GitHub CLI) para configurar secrets desde la terminal.

> ⚠️ Si alguna vez reinstalas gcloud, hazlo en una ruta **sin espacios ni acentos** (p. ej. `$HOME`),
> nunca dentro de la carpeta del proyecto.

---

## 1. Autenticación, proyecto y APIs

```bash
gcloud auth login

# Verifica si el proyecto ya existe; si no, créalo
gcloud projects list
# gcloud projects create proyecto-final-mlops   # solo si no existe

gcloud config set project proyecto-final-mlops

gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  storage.googleapis.com \
  iam.googleapis.com
```

> Asegúrate de tener **billing activado** en el proyecto (requisito de GCP aunque uses free tier).
> Console → Billing → vincular cuenta de facturación.

---

## 2. Crear el bucket de GCS y su estructura

```bash
gcloud storage buckets create gs://proyecto-final-mlops-bucket --location=us-central1 --uniform-bucket-level-access

# Crea las "carpetas" subiendo placeholders (GCS no tiene carpetas reales)
echo "" | gcloud storage cp - gs://proyecto-final-mlops-bucket/logs/predicciones_dev.txt
echo "" | gcloud storage cp - gs://proyecto-final-mlops-bucket/logs/predicciones_prod.txt
```

---

## 3. Crear el repositorio de Artifact Registry (imágenes Docker)

```bash
gcloud artifacts repositories create mlops-models \
  --repository-format=docker \
  --location=us-central1 \
  --description="Imágenes del servicio de inferencia ONNX"
```

---

## 4. Crear las dos Service Accounts

### 4.1 Service Account de CI/Deploy (la usa GitHub Actions)

```bash
gcloud iam service-accounts create gh-deployer \
  --display-name="GitHub Actions deployer"

CI_SA="gh-deployer@proyecto-final-mlops.iam.gserviceaccount.com"

for ROLE in roles/run.admin roles/artifactregistry.writer roles/storage.admin roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding proyecto-final-mlops \
    --member="serviceAccount:${CI_SA}" --role="${ROLE}"
done

# Descarga la clave JSON (este archivo va SOLO como GitHub Secret, NUNCA al repo)
gcloud iam service-accounts keys create gcp-sa-key.json --iam-account="${CI_SA}"
```

> 🔐 `gcp-sa-key.json` ya está en `.gitignore`. NO lo subas a git, NO lo pegues en chats. Tras
> configurar el secret en GitHub, bórralo en local (sección 8). Si en algún momento se expuso,
> regenérala: `gcloud iam service-accounts keys create ... && gcloud iam service-accounts keys delete <KEY_ID>`.

### 4.2 Service Account de runtime (la usa el contenedor en Cloud Run para escribir logs)

```bash
gcloud iam service-accounts create run-runtime \
  --display-name="Cloud Run runtime"

RUNTIME_SA="run-runtime@proyecto-final-mlops.iam.gserviceaccount.com"

# Permiso para leer/escribir el TXT de predicciones en el bucket
gcloud storage buckets add-iam-policy-binding gs://proyecto-final-mlops-bucket \
  --member="serviceAccount:${RUNTIME_SA}" --role="roles/storage.objectAdmin"

# La SA de CI necesita poder "actuar como" la SA de runtime al desplegar
gcloud iam service-accounts add-iam-policy-binding "${RUNTIME_SA}" \
  --member="serviceAccount:${CI_SA}" --role="roles/iam.serviceAccountUser"
```

---

## 5. Generar el modelo inicial y los datos de prueba, y subirlos al bucket

Esto materializa el **"modelo ya existente en producción"** y los datos de prueba.

```bash
pip install -r requirements-dev.txt
python scripts/train_export_onnx.py      # genera model.onnx y test_data.csv

gcloud storage cp model.onnx     gs://proyecto-final-mlops-bucket/models/dev/model.onnx
gcloud storage cp model.onnx     gs://proyecto-final-mlops-bucket/models/prod/model.onnx
gcloud storage cp test_data.csv  gs://proyecto-final-mlops-bucket/data/test_data.csv
```

> `model.onnx` y `test_data.csv` quedan ignorados por git (`.gitignore`), no se suben al repo.

---

## 6. Subir el código y crear las ramas `dev` y `prod`

```bash
# Sube el código a main
git add .
git commit -m "feat: sistema de despliegue automatico de modelos ONNX"
git push origin main

# Crea las ramas de entorno a partir de main (este primer push DISPARA el pipeline
# y hace que el check 'test' quede registrado en GitHub para usarlo en la branch protection)
git checkout -b dev  && git push -u origin dev
git checkout -b prod && git push -u origin prod
git checkout main
```

---

## 7. Configurar GitHub Environments (variables y secrets)

En GitHub: **Settings → Environments → New environment**. Crea **`dev`** y **`prod`**.

### 7.1 Variables por entorno (Settings → Environments → [dev|prod] → Environment variables)

| Variable           | Valor en `dev`                                           | Valor en `prod`                                           |
| ------------------ | -------------------------------------------------------- | --------------------------------------------------------- |
| `SERVICE_NAME`     | `model-api-dev`                                          | `model-api-prod`                                          |
| `MODEL_GCS_URI`    | `gs://proyecto-final-mlops-bucket/models/dev/model.onnx` | `gs://proyecto-final-mlops-bucket/models/prod/model.onnx` |
| `LOG_FILE`         | `logs/predicciones_dev.txt`                              | `logs/predicciones_prod.txt`                              |
| `APP_ENV`          | `dev`                                                    | `prod`                                                    |
| `METRIC_THRESHOLD` | `0.90`                                                   | `0.90`                                                    |

### 7.2 Secrets (a nivel de cada Environment, o como Repository secrets compartidos)

| Secret        | Valor                                                      |
| ------------- | ---------------------------------------------------------- |
| `GCP_SA_KEY`  | **contenido completo** del archivo `gcp-sa-key.json`       |
| `GCP_PROJECT` | `proyecto-final-mlops`                                     |
| `GCS_BUCKET`  | `proyecto-final-mlops-bucket`                              |
| `GCP_REGION`  | `us-central1`                                              |
| `RUNTIME_SA`  | `run-runtime@proyecto-final-mlops.iam.gserviceaccount.com` |

Vía `gh` CLI (ejemplo):

```bash
gh secret set GCP_SA_KEY < gcp-sa-key.json
gh secret set GCP_PROJECT --body "proyecto-final-mlops"
gh secret set GCS_BUCKET  --body "proyecto-final-mlops-bucket"
gh secret set GCP_REGION  --body "us-central1"
gh secret set RUNTIME_SA  --body "run-runtime@proyecto-final-mlops.iam.gserviceaccount.com"
```

> ⚠️ Aunque pongas los secrets a nivel de repositorio, debes crear los **Environments** `dev` y
> `prod` para que el workflow (`environment: ...`) y las **variables** funcionen.

---

## 8. Borrar la clave local por seguridad

```bash
rm gcp-sa-key.json
```

---

## 9. Configurar Branch Protection Rules (flujo por Pull Requests)

> Hazlo **después** del primer push a `dev`/`prod` (sección 6), para que GitHub ya conozca el check `test`.

En GitHub: **Settings → Branches → Add branch ruleset** (o *Add classic branch protection rule*).
Crea una regla para **`dev`** y otra para **`prod`** (o un ruleset que aplique a ambas) con:

- ✅ **Require a pull request before merging** (bloquea el push directo).
  - Required approvals: **0** (proyecto individual; no te bloqueas a ti mismo).
- ✅ **Require status checks to pass before merging** → selecciona el check **`test`**.
  - ✅ *Require branches to be up to date before merging* (recomendado).
- (Opcional) ✅ *Do not allow bypassing the above settings*.

Con esto, **ningún cambio entra a `dev`/`prod` sin que pasen las pruebas**.

> Nota: en repos **privados** con plan Free, las *branch protection rules* clásicas pueden requerir
> plan de pago; los **rulesets** y/o los repos **públicos** sí las permiten gratis. Si tu repo es
> privado y no te deja, hazlo **público** o usa *rulesets*.

---

## 10. Operar el sistema (lo que mostrarás en la demo)

Flujo normal de despliegue de un modelo nuevo:

```bash
# 1) (si cambia el modelo) sube el nuevo modelo a dev
gcloud storage cp model.onnx gs://proyecto-final-mlops-bucket/models/dev/model.onnx

# 2) crea una rama de trabajo, haz tus cambios y abre un PR hacia dev
git checkout -b cambio-modelo
git commit --allow-empty -m "deploy: nuevo modelo a dev"
git push -u origin cambio-modelo
#   -> abre el PR (cambio-modelo -> dev) en GitHub. Se ejecuta SOLO 'test'.
#   -> si pasa, haz MERGE. El push a dev dispara test + build/promote (deploy a dev).

# 3) promover a prod: abre un PR de dev -> prod
#   -> se ejecuta 'test'; al hacer MERGE, el pipeline promueve el modelo y despliega en prod.
```

Probar los endpoints:

```bash
# Obtener las URLs (o cópialas del Summary de Actions)
gcloud run services describe model-api-dev  --region us-central1 --format='value(status.url)'
gcloud run services describe model-api-prod --region us-central1 --format='value(status.url)'

curl $URL/health
curl -X POST "$URL/predict" -H "Content-Type: application/json" \
  -d '{"features": [13.54,14.36,87.46,566.3,0.09779,0.08129,0.06664,0.04781,0.1885,0.05766,0.2699,0.7886,2.058,23.56,0.008462,0.0146,0.02387,0.01315,0.0198,0.0023,15.11,19.26,99.7,711.2,0.144,0.1773,0.239,0.1288,0.2977,0.07259]}'

# Ver que se registró la predicción en el bucket
gcloud storage cat gs://proyecto-final-mlops-bucket/logs/predicciones_dev.txt
```

---

## 11. (Recomendado) Demo de la prueba que RECHAZA un modelo malo

Demuestra que el test de métrica + branch protection protegen producción:

```bash
python scripts/train_export_onnx.py --bad     # genera un model.onnx con accuracy < 0.90
gcloud storage cp model.onnx gs://proyecto-final-mlops-bucket/models/dev/model.onnx

git checkout -b modelo-malo
git commit --allow-empty -m "test: modelo malo"
git push -u origin modelo-malo
#   -> abre PR (modelo-malo -> dev). El check 'test' FALLA -> GitHub NO permite el merge -> NO se despliega.

# Restaura el modelo bueno
python scripts/train_export_onnx.py
gcloud storage cp model.onnx gs://proyecto-final-mlops-bucket/models/dev/model.onnx
```

---

## 12. Limpieza al terminar (evitar costos)

```bash
gcloud run services delete model-api-dev  --region us-central1 --quiet
gcloud run services delete model-api-prod --region us-central1 --quiet
# (opcional) borrar bucket, imágenes y la service account key
```

Antes de la entrega final: **regenera/borra `gcp-sa-key.json` si se expuso** y borra este archivo
`indicaciones-william.md`.
