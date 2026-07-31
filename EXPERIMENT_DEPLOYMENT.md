# Despliegue de experimentos — Official Experiment v1

Esta ruta sustituye la etiqueta confirmatoria del piloto `complete_final_v1_1` sin borrar ni modificar sus artefactos históricos.

## Rama de preparación

`science/official-experiment-v1`

## Motor

`complete_final_official_v1`

El código oficial está separado del motor histórico:

- `simulator/official_profiles.py`
- `simulator/official_profile_sensitivity.py`
- `simulator/official_complete_final.py`
- `simulator/official_monte_carlo.py`
- `simulator/official_orientation.py`
- `scripts/run_official_experiment.py`
- `scripts/run_official_experiment_v1_1.py`
- `scripts/scientific/run_official_robustness.py`
- `scripts/scientific/analyze_official_hypotheses.py`
- `scripts/scientific/validate_official_release.py`

El lanzador canónico es `scripts/run_official_experiment_v1_1.py`. Conserva el runner auditado y sustituye únicamente la prueba de orientación por la implementación de equivalencia pareada congelada en `config/official_orientation_equivalence_v1.json`.

## Principio fail-closed

Ningún despliegue `official` puede comenzar si falta una autorización generada por la validación oficial o si cualquier hash de código, protocolo, roster, contrato estadístico o configuración difiere del autorizado.

La ausencia de evidencia afirmativa equivale a fallo.

## Despliegue 1 — Smoke

Se ejecuta automáticamente en cada cambio relevante de la rama y también puede iniciarse manualmente.

```bash
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

Objetivo:

- compilar;
- verificar 26 jugadores únicos por plantel;
- verificar once inicial y roles;
- comprobar que no existen etiquetas provisionales o exploratorias;
- comprobar sustituciones desde el banquillo congelado;
- comprobar semántica y pertenencia de actores;
- detectar errores lógicos antes de consumir cómputo;
- detectar asimetrías gruesas mediante 200 pares neutrales.

El smoke nunca autoriza resultados confirmatorios. Sus 200 pares se etiquetan como `diagnostic_only_insufficient_sample`, aunque la diferencia puntual quede dentro del margen.

## Despliegue 2 — Validación aislada

Desde GitHub Actions:

1. abrir **Actions**;
2. elegir **Official Experiment v1**;
3. ejecutar `workflow_dispatch`;
4. seleccionar `validation`;
5. dejar vacío el número de simulaciones para utilizar las 2.000 congeladas;
6. activar `promote_validation_evidence` solo cuando se quiera guardar la autorización aprobada.

Equivalente local:

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

La validación incluye:

- 2.000 finales aisladas;
- 2.000 pares neutrales de orientación con números aleatorios comunes;
- prueba de equivalencia: todo el intervalo de confianza del 95% debe quedar dentro de ±0,04;
- calibración disciplinaria estricta;
- invariantes de eventos y actores;
- estabilidad entre semillas;
- sensibilidad Top 10/20/30;
- sensibilidad 180/450/900 minutos;
- ontología posicional alternativa;
- coordinación;
- Monte Carlo anidado sobre el mismo motor oficial;
- estimandos H5, H6 y H7.

Cuando todos los gates pasan se crea:

`data/model_readiness/official_release_authorization_v1.json`

## Despliegue 3 — Experimento oficial

Solo se habilita después de que la autorización de validación esté comprometida en la misma rama y sus hashes coincidan con el runtime.

Desde GitHub Actions seleccionar `official`, sin sobrescribir las 10.000 simulaciones congeladas.

Equivalente local:

```bash
PYTHONPATH=. python scripts/run_official_experiment_v1_1.py --mode official
```

La ejecución aborta cuando:

- falta autorización;
- cambió el motor;
- cambió el constructor de perfiles;
- cambió el roster;
- cambió el protocolo;
- cambió el contrato estadístico;
- cambió la configuración;
- se registró tuning posterior a resultados.

## Artefactos principales

Cada despliegue produce:

- `simulation_summary.json`;
- `official_matches.csv`;
- `official_state_conditions.csv`;
- `official_hypotheses_summary.json`;
- `official_h7_state_rates.csv`;
- `official_h7_interactions.csv`;
- alineaciones y banquillos exactos;
- membresía de arquetipos;
- replay representativo;
- audit sample;
- manifest con SHA-256;
- ledger reproducible de semillas.

Los artefactos completos se conservan como GitHub Actions artifacts durante 90 días. La evidencia compacta necesaria para autorizar el release puede comprometerse en el repositorio.

## Qué no debe hacerse

- No editar parámetros después de observar el resultado oficial.
- No promover manualmente un smoke a resultado confirmatorio.
- No interpretar el intervalo del smoke como prueba de equivalencia.
- No reemplazar el roster congelado mediante CSV provisional.
- No ejecutar directamente el motor histórico para el paper confirmatorio.
- No elegir manualmente el replay más dramático.
- No interpretar una simulación como predicción ontológica de un partido físico.
