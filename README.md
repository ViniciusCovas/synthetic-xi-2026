# Synthetic XI 2026 Lab

Laboratorio científico reproducible para construir avatares sintéticos por posición y compararlos con futbolistas y equipos reales bajo datos, supuestos y límites de afirmación explícitos.

## Estudios

### Estudio 1 — Avatares posicionales vs élite individual

Compara ocho arquetipos (`GK`, `CB`, `FB`, `DM`, `CM`, `AM`, `W`, `ST`) con benchmarks reales de la misma función. El análisis principal utiliza un centro robusto Top 20; Top 10 y Top 30 son sensibilidades y siempre se informa el N real disponible.

### Estudio 2 — Synthetic XI vs Real Best XI

Compara distribuciones de finales eliminatorias entre:

- **Synthetic XI:** instancias independientes de arquetipos posicionales congelados;
- **Real Best XI:** once futbolistas reales distintos seleccionados para `GK, RB, RCB, LCB, LB, DM, CM, AM, RW, LW, ST`.

El motor es un simulador probabilístico por eventos y estados. No equivale a un partido físico ni permite afirmar que un equipo “ganaría realmente”.

## Estado científico actual

El experimento oficial v1 y su replicación independiente están **completos, validados e integrados**.

### Corrida confirmatoria principal

- 10.000 finales, seed `2026073001`.
- Synthetic XI campeón: **44,590%** (IC 95%: 43,618%–45,566%).
- Real Best XI campeón: **55,410%** (IC 95%: 54,434%–56,382%).

### Replicación pre-registrada de precisión

- 50.000 finales, seed independiente `2026073102`.
- Synthetic XI campeón: **44,696%** (IC 95%: 44,261%–45,132%).
- Real Best XI campeón: **55,304%** (IC 95%: 54,868%–55,739%).
- Diferencia frente a la corrida confirmatoria: **0,106 punto porcentual**.
- Consistencia de Monte Carlo, precisión y dirección: **PASS**.

La corrida de 10.000 permanece como resultado confirmatorio principal. La corrida de 50.000 se reporta separadamente como replicación de precisión. La síntesis ponderada de 60.000 —Synthetic XI **44,678%**, IC 95% 44,281%–45,076%— es únicamente secundaria.

El release científico consolidado está documentado en `SCIENTIFIC_RELEASE_OFFICIAL_V1.md`.

La ejecución histórica de 10.000 finales del 22 de julio de 2026 permanece conservada, sin modificación, como **piloto final / release candidate** y no se confunde con la corrida confirmatoria oficial.

## Decisiones del experimento oficial v1

- Top 20 como análisis principal; Top 10 y Top 30 como sensibilidad.
- Mínimo principal de 900 minutos exactos; 450 y 180 como sensibilidades.
- Media recortada al 10% para cada arquetipo.
- La calificación opaca del proveedor no entra directamente en probabilidades de éxito.
- Si no existen 20 o 30 elegibles, se informa y utiliza el N real.
- Planteles de 26 integrantes y once inicial congelados.
- Sustituciones exclusivamente desde el banquillo congelado.
- Condiciones, árbitro y ambiente pareados cuando el diseño lo permite.
- Sensibilidad e incertidumbre anidada ejecutadas sobre el mismo motor oficial.
- H5, H6 y H7 operacionalizadas antes de la ejecución confirmatoria.
- Ausencia de evidencia afirmativa = gate fallido.
- Ningún ajuste de parámetros, jugadores o código después de observar resultados.

## Arquitectura

```text
Datos y cachés auditables
          ↓
Construcción de perfiles y roster canónico
          ↓
Preflight estructural fail-closed
          ↓
Smoke → validación aislada → autorización con hashes
          ↓
Corrida confirmatoria de 10.000 finales
          ↓
H5–H7, sensibilidad e incertidumbre anidada
          ↓
Replicación independiente de 50.000 finales
          ↓
Release científico congelado
```

## Reproducibilidad

La guía completa está en `EXPERIMENT_DEPLOYMENT.md`.

### Smoke local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

PYTHONPATH=. python scripts/scientific/validate_official_release.py \
  --mode structural \
  --status-output /tmp/official_structural_preflight.json

PYTHONPATH=. pytest -q \
  tests/test_official_experiment.py \
  tests/test_official_orientation.py

PYTHONPATH=. python scripts/run_official_experiment_v1_1.py \
  --mode smoke \
  --simulations 200
```

### Validación aislada

```bash
PYTHONPATH=. python scripts/run_official_experiment_v1_1.py \
  --mode validation \
  --simulations 2000

PYTHONPATH=. python scripts/scientific/run_official_robustness.py \
  --output data/experiments/official_v1/robustness

PYTHONPATH=. python scripts/scientific/validate_official_release.py \
  --mode release \
  --validation data/experiments/official_v1/validation \
  --robustness data/experiments/official_v1/robustness
```

### Corrida confirmatoria

```bash
PYTHONPATH=. python scripts/run_official_experiment_v1_1.py \
  --mode official \
  --simulations 10000 \
  --seed 2026073001 \
  --output data/experiments/official_v1
```

El modo `official` falla si falta autorización o si cualquier fuente crítica, protocolo, configuración, roster o hash difiere de la validación autorizada.

## GitHub Actions permanentes

- `Official v1 PR Smoke`: compilación, preflight, pruebas y smoke observable.
- `Official Experiment v1`: despliegues controlados de smoke, validación y ejecución oficial.
- Los paquetes completos se conservan como artifacts con manifest SHA-256 y ledger de seeds.

Los workflows one-shot utilizados para validar, autorizar, ejecutar e integrar las corridas se eliminan después del congelamiento.

## Documentación científica

- `SCIENTIFIC_RELEASE_OFFICIAL_V1.md`: registro consolidado del resultado congelado.
- `METHODS_OFFICIAL_V1.md`: método del experimento oficial.
- `PROTOCOL_AMENDMENT_OFFICIAL_V1.md`: enmienda previa al experimento oficial.
- `PROTOCOL_AMENDMENT_OFFICIAL_V1_ADDENDUM_01.md`: política de sustituciones de emergencia.
- `protocol/official_v1_precision_replication_50000_preregistration.json`: pre-registro de la replicación.
- `PRERREGISTRO.md`: pre-registro histórico.
- `METHODS.md`: metodología consolidada histórica.
- `PROTOCOLO_FINAL_COMPLETA.md`: arquitectura general de la final.
- `EXPERIMENT_DEPLOYMENT.md`: operación y gates de despliegue.
- `ESTUDIO_1_POSICIONES.md`: manuscrito del estudio posicional.
- `ESTUDIO_2_ONCE.md`: protocolo/manuscrito del estudio de equipos.

## Estudio 3 — Ventana (observatorio de ventana)

Estudio de observación real, independiente de los estudios de fútbol, que aplica
la misma disciplina de pre-registro, compuertas y techo de afirmación a un punto
fijo del mundo: una ventana.

Un teléfono inmóvil ejecuta visión por computadora **en el propio dispositivo** y
produce un registro numérico por minuto con tres capas —flujo de calle, estado de
cielo y ocupación aparente de fachada—. No se graba ni se transmite vídeo.

- Guía de operación: `projects/ventana_observatory/README.md`
- Pre-registro: `projects/ventana_observatory/PROTOCOLO_VENTANA_V1.md`
- Esquema de datos: `projects/ventana_observatory/SCHEMA_VENTANA_V1.md`

```bash
python scripts/ventana/validate_session.py data/ventana/raw/*.jsonl
python scripts/ventana/build_ventana_exhibits.py
```

## Aplicación web

La interfaz Vite permanece separada de la autorización científica del experimento:

```bash
cd web
npm install
npm run dev
```

Un deploy visual nunca transforma por sí mismo una corrida exploratoria en resultado confirmatorio.
