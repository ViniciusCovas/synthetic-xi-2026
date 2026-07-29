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

La ejecución histórica de 10.000 finales del 22 de julio de 2026 se conserva sin modificación como **piloto final / release candidate**. No es la ejecución confirmatoria oficial.

La nueva ruta confirmatoria es `official_experiment_v1`, preparada en la rama:

```text
science/official-experiment-v1
```

Sus decisiones previas a resultados están congeladas en:

- `PROTOCOL_AMENDMENT_OFFICIAL_V1.md`;
- `config/official_experiment_v1.json`;
- `data/model_readiness/official_rankings_authorization_v1.json`.

El modo `official` permanece bloqueado hasta que una validación aislada del mismo motor, roster y configuración produzca una autorización con hashes coincidentes.

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
- H5, H6 y H7 operacionalizadas antes de la nueva ejecución.
- Ausencia de evidencia afirmativa = gate fallido.

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
Distribución oficial de 10.000 finales
          ↓
H5–H7, sensibilidad, incertidumbre y replay representativo
```

## Despliegues

La guía completa está en `EXPERIMENT_DEPLOYMENT.md`.

### Smoke local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

PYTHONPATH=. python scripts/scientific/validate_official_release.py \
  --mode structural \
  --status-output /tmp/official_structural_preflight.json

PYTHONPATH=. pytest -q tests/test_official_experiment.py

PYTHONPATH=. python scripts/run_official_experiment.py --mode smoke
```

### Validación aislada

```bash
PYTHONPATH=. python scripts/run_official_experiment.py --mode validation

PYTHONPATH=. python scripts/scientific/run_official_robustness.py \
  --output data/experiments/official_v1/robustness

PYTHONPATH=. python scripts/scientific/validate_official_release.py \
  --mode release \
  --validation data/experiments/official_v1/validation \
  --robustness data/experiments/official_v1/robustness
```

### Ejecución oficial

```bash
PYTHONPATH=. python scripts/run_official_experiment.py --mode official
```

El comando anterior falla cuando falta autorización o cambió cualquier fuente crítica, protocolo, configuración o roster respecto de la validación.

## GitHub Actions

- `Official v1 PR Smoke`: compilación, preflight, pruebas y smoke observable en cada PR.
- `Official Experiment v1`: despliegues manuales `smoke`, `validation` y `official`.
- Los paquetes completos se conservan como artifacts con manifest SHA-256 y ledger de semillas.

## Documentación científica

- `PRERREGISTRO.md`: preregistro histórico.
- `PROTOCOL_AMENDMENT_OFFICIAL_V1.md`: enmienda previa al nuevo experimento oficial.
- `METHODS.md`: metodología consolidada histórica.
- `PROTOCOLO_FINAL_COMPLETA.md`: arquitectura general de la final.
- `EXPERIMENT_DEPLOYMENT.md`: operación y gates de despliegue.
- `ESTUDIO_1_POSICIONES.md`: manuscrito del estudio posicional.
- `ESTUDIO_2_ONCE.md`: protocolo/manuscrito del estudio de equipos.

## Aplicación web

La interfaz Vite permanece separada de la autorización científica del experimento:

```bash
cd web
npm install
npm run dev
```

Un deploy visual nunca transforma por sí mismo una corrida exploratoria en resultado confirmatorio.
