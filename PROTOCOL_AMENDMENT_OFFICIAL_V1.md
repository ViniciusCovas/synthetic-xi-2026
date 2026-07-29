# Enmienda preregistrada — Experimento oficial v1

**Estado:** congelación previa a la nueva ejecución confirmatoria  
**Fecha:** 2026-07-29  
**Rama:** `science/official-experiment-v1`  
**Objeto:** Synthetic XI vs Real Best XI, final eliminatoria simulada  

## 1. Motivo y transparencia

La ejecución de 10.000 partidos publicada el 22 de julio de 2026 se conserva íntegra como **piloto final / release candidate**. Sus resultados no se utilizan para escoger jugadores, alterar pesos de habilidad, ampliar tolerancias ni favorecer una dirección de resultado.

Esta enmienda corrige problemas de trazabilidad detectados después del piloto:

1. el runner podía construir perfiles amplios y provisionales distintos del roster canónico congelado;
2. el gate de publicación no exigía literalmente `rankings_allowed`;
3. la sensibilidad y la incertidumbre anidada correspondían a un motor anterior;
4. la semántica del event log no distinguía equipo actor, equipo afectado y equipo en posesión;
5. la disciplina, especialmente las expulsiones, requería una calibración más estricta;
6. las hipótesis H5–H7 necesitaban estimandos explícitos.

Todo cambio descrito aquí ocurre **antes** de observar resultados producidos por la nueva ruta `official_v1`.

## 2. Datos, elegibilidad y sensibilidades

- El análisis principal utiliza cobertura exacta y un mínimo de **900 minutos** en las ventanas declaradas.
- Los umbrales de **450** y **180 minutos** se conservan como análisis de sensibilidad y no sustituyen el análisis principal.
- El avatar principal sigue siendo el centro robusto Top 20 por arquetipo posicional.
- Top 10 y Top 30 son sensibilidades.
- Ninguna calificación opaca del proveedor entra directamente en probabilidades de éxito.
- Ningún jugador real puede ocupar dos plazas del once o del plantel.

## 3. Estimando y equipos canónicos

El estimando principal es la distribución comparativa de una final eliminatoria entre un único `Synthetic XI` y un único `Real Best XI`, bajo condiciones iniciales pareadas.

Los roles canónicos son:

`GK, RB, RCB, LCB, LB, DM, CM, AM, RW, LW, ST`.

El motor conserva internamente los slots:

`GK, FB1, CB1, CB2, FB2, DM, CM, AM, W1, W2, ST`.

La traducción es determinística:

- `RB → FB1`
- `RCB → CB1`
- `LCB → CB2`
- `LB → FB2`
- `RW → W1`
- `LW → W2`

Los titulares, suplentes, órdenes de penaltis y porteros de emergencia se cargan exclusivamente desde `data/model_readiness/complete_final_rosters_v1.json`. Una discrepancia de ID, rol, tamaño del plantel o hash bloquea la ejecución.

## 4. Banquillos

La ruta oficial no genera reservas funcionales a partir del titular sustituido. Utiliza exclusivamente futbolistas o instancias sintéticas del plantel congelado de 26 integrantes. Cada suplente puede ingresar una sola vez y debe ser compatible con el slot reemplazado.

## 5. Disciplina

La calibración disciplinaria oficial usa como objetivos congelados del benchmark 2026:

- amarillas comparables por partido: `2.87234`;
- rojas por partido: `0.144231`;
- faltas por partido: `23.192308`.

Los criterios de release son más estrictos que los del piloto:

- error absoluto de amarillas ≤ `0.75`;
- error absoluto de rojas ≤ `0.20`;
- razón motor/benchmark de rojas entre `0.50` y `2.00`;
- error absoluto de faltas ≤ `3.00`.

Los jugadores amonestados reducen su propensión posterior a cometer faltas mediante un parámetro congelado de adaptación conductual. Las segundas amarillas continúan produciendo expulsión; no se eliminan de forma ad hoc.

## 6. Semántica del registro de eventos

Cada evento oficial registra como mínimo:

- `acting_team`;
- `affected_team`;
- `possession_team`;
- `benefiting_team` cuando corresponda;
- `actor`;
- `actor_team`;
- `actor_membership_valid`;
- estado del marcador anterior a la acción;
- estado numérico;
- periodo y minuto.

El campo heredado `team` se conserva temporalmente, pero representa al equipo actor y no se utiliza como única fuente analítica.

## 7. Hipótesis y estimandos

### H5 — Consistencia del Synthetic XI

Estimandos principales:

- diferencia de varianza de goles;
- diferencia de varianza de xG;
- diferencia de varianza de tiros;
- probabilidad de cero goles;
- probabilidad de producción ofensiva en la cola inferior.

Una menor varianza no se interpreta automáticamente como superioridad.

### H6 — Acciones extremas del Real Best XI

Estimandos principales:

- probabilidad de marcar al menos tres goles;
- probabilidad de superar 2.0 xG;
- probabilidad de realizar al menos 15 tiros;
- probabilidad de ganar por al menos dos goles;
- diferencias en cuantiles 0.90 y 0.95 de goles, xG y tiros.

### H7 — Dependencia del estado del partido

Estimandos descriptivos e interacciones preregistradas:

- tasas de tiro y gol por posesión estando empatado, ganando o perdiendo;
- tasas por periodo;
- tasas bajo igualdad, superioridad o inferioridad numérica;
- interacción `equipo × estado del marcador`;
- interacción `equipo × fase del partido`.

Los eventos dentro de un mismo partido no se tratarán como observaciones independientes. La incertidumbre se estima por simulación y por mundos de parámetros.

## 8. Capas de incertidumbre

La validación oficial debe corresponder al mismo motor, roster y configuración de la ejecución oficial e incluir:

1. incertidumbre de perfiles;
2. sensibilidad de clasificación posicional;
3. Top-N y minutos mínimos;
4. coordinación;
5. parámetros del motor;
6. contexto arbitral y ambiental pareado;
7. aleatoriedad del partido.

Cualquier componente no estimado se declara como sensibilidad, no como posterior aprendido.

## 9. Gates literales

La ejecución confirmatoria se bloquea salvo que todos sean verdaderos:

- `canonical_rosters_match_runtime = true`
- `no_provisional_profiles = true`
- `no_exploratory_labels = true`
- `selection_sufficiency = true`
- `rankings_allowed = true`
- `external_holdout_passed = true`
- `event_sanity_passed = true`
- `discipline_calibration_passed = true`
- `orientation_equivalence_passed = true`
- `seed_stability_passed = true`
- `official_sensitivity_complete = true`
- `official_nested_uncertainty_complete = true`
- `h5_h6_h7_estimands_present = true`
- `final_team_comparison_allowed = true`
- `post_result_tuning_performed = false`

La ausencia de evidencia afirmativa equivale a fallo.

## 10. Orden de ejecución

1. construir inputs canónicos;
2. ejecutar pruebas unitarias e invariantes;
3. ejecutar smoke test;
4. ejecutar validación aislada de 2.000 finales;
5. ejecutar sensibilidad y Monte Carlo anidado sobre `official_v1`;
6. generar autorización de release con hashes;
7. congelar tag y contenedor;
8. ejecutar 10.000 finales confirmatorias;
9. analizar H5–H7;
10. publicar distribución, sensibilidad, ablations y replay representativo.

## 11. Límite de afirmación

La formulación autorizada después de todos los gates es:

> Bajo los datos, el modelo y los supuestos preregistrados, se estima una distribución comparativa de resultados entre Synthetic XI y Real Best XI.

No se afirmará que un equipo sintético ganaría realmente un partido físico ni que el motor reproduce toda la complejidad táctica, corporal o social del fútbol.
