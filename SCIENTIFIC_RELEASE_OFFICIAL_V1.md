# Scientific Release — Official Experiment v1

## Estado

- Experimento confirmatorio: **completo**.
- Replicación independiente de precisión: **completa**.
- Motor congelado: `complete_final_official_v1`.
- Ajuste posterior a resultados: **no realizado**.
- Revisión fuente autorizada: `06c750cfef3246d3c6112f6bd86d25a83287308f`.
- Evidencia confirmatoria publicada: `0461ed7b5cf796cd4ab484eeca4ceb5a8075e41b`.
- Evidencia de replicación publicada: `7c55141d9a597deaf25058a2eec28f1d945af093`.

## Resultado confirmatorio principal

- Simulaciones: **10.000**.
- Seed maestra: `2026073001`.
- Synthetic XI campeón: **44,590%**.
- IC 95%: **43,618%–45,566%**.
- Real Best XI campeón: **55,410%**.
- IC 95%: **54,434%–56,382%**.

Esta corrida permanece como resultado confirmatorio principal.

## Replicación independiente de precisión

- Simulaciones: **50.000**.
- Seed maestra: `2026073102`.
- Synthetic XI campeón: **44,696%**.
- IC 95%: **44,261%–45,132%**.
- Real Best XI campeón: **55,304%**.
- IC 95%: **54,868%–55,739%**.
- Diferença absoluta frente al resultado confirmatorio: **0,106 punto porcentual**.
- Umbral máximo de consistencia Monte Carlo pre-registrado: **1,067 puntos porcentuales**.
- Consistencia Monte Carlo: **PASS**.
- Dirección del resultado replicada: **PASS**.
- Objetivo de precisión: **PASS**.

## Síntesis secundaria de precisión

La combinación ponderada se reporta únicamente como resumen secundario; no sustituye el resultado confirmatorio.

- Simulaciones totales: **60.000**.
- Synthetic XI campeón: **44,678%**.
- IC 95% de Wilson: **44,281%–45,076%**.
- Real Best XI campeón: **55,322%**.

## Gates científicos

- Planteles canónicos congelados: **PASS**.
- Perfiles congelados coincidentes con runtime: **PASS**.
- Ausencia de perfiles provisionales: **PASS**.
- Suficiencia de selección: **PASS**.
- Holdout externo: **PASS**.
- Integridad de eventos: **PASS**.
- Calibración disciplinaria: **PASS**.
- Equivalencia de orientación: **PASS**.
- Estabilidad entre seeds: **PASS**.
- Sensibilidad oficial completa: **PASS**.
- Incertidumbre anidada completa: **PASS**.
- Estimandos H5, H6 y H7 presentes: **PASS**.
- Hashes críticos idénticos entre autorización, corrida confirmatoria y replicación: **PASS**.
- Ajuste posterior a resultados: **FALSE**.

## Integridad criptográfica

### Corrida confirmatoria

- Summary SHA-256: `e870f3e4e4b871bc8e06a1a07942427b3a54b32005c01c77c6927e73618566be`.
- Manifest SHA-256: `cf81e04eadd82a0067a50cbbc0a1bb6725e2528528e0c129674d64644034aa42`.
- Ledger de seeds SHA-256: `8634ca05a94b3c031746058c894279428af818fcff91d5cffaf86cf84b4b0a20`.

### Replicación de precisión

- Summary SHA-256: `70f87a197c4ae484aa7e280f24a12e0f3e6960b26c1451b9b09d38e3809a0bef`.
- Manifest SHA-256: `7260b5e112ce5d5d6bde0f0d7b9a6d4181a899a47dafe9685877d698d367c53e`.
- Comparación SHA-256: `79d4c77813cc99c6ed3609bba8878ffd7250d2b676dffdb7988bb72eb207459a`.
- Ledger de seeds SHA-256: `2f13e6e61cbe55beb0931614dd444c7117469c1f3519cbf1c6d34d8b1aadd2d0`.

## Política de interpretación

El experimento estima resultados dentro de un modelo probabilístico congelado. No establece verdad causal del mundo real ni permite afirmar que una alineación sintética derrotaría físicamente a una selección real. La menor variabilidad del Synthetic XI no equivale automáticamente a superioridad. Los resultados deben interpretarse junto con la calibración, las sensibilidades, la incertidumbre estructural y las limitaciones de construcción de perfiles.

Ningún parámetro, jugador, regla, seed o componente del motor puede modificarse retroactivamente para mejorar el resultado observado.

## Archivos de evidencia

- `data/model_readiness/official_release_authorization_v1.json`
- `data/model_readiness/official_experiment_v1_completion.json`
- `data/model_readiness/official_v1_precision_replication_50000_completion.json`
- `data/model_readiness/official_v1_precision_replication_50000_comparison.json`
- `data/experiments/official_v1/official/`
- `data/experiments/official_v1/validation/`
- `data/experiments/official_v1/robustness/`
- `data/experiments/official_v1_precision_replication_50000/official/`
- `protocol/official_v1_precision_replication_50000_preregistration.json`
