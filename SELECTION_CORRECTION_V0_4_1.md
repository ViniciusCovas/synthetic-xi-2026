# Corrección de selección v0.4.1 — identidades y lados

Corrección de la capa de selección pública (rankings → avatares → onces →
web), reconstruida íntegramente desde la caché versionada de la API
(`data/processed/player_matches.csv`, `data/lake/batches/`), sin red y sin
tocar los artefactos congelados del experimento oficial v1.

## Defectos corregidos

### 1. Identidades de jugador duplicadas

La agregación de features agrupaba por `player_name` además de `player_id`.
El proveedor alterna grafías del mismo jugador entre partidos, por lo que
cuatro jugadores quedaban partidos en dos filas cada uno, diluyendo sus
minutos y ocupando dos puestos del pool posicional:

| player_id | Variantes | Minutos fusionados | Efecto de la fusión |
|---|---|---|---|
| 2701 | Bono / Yassine Bounou | 570 | Entra al Top-20 del avatar GK (rank 18) |
| 44362 | Hassan Altambakti / Hassan Tambakti | 213 | Pasa a ser elegible (≥180′) en CB |
| 158433 | Siphephelo / Sphephelo Sithole | 236 | Consolida sus estadísticas en DM |
| 575283 | Ali Al Azaizah / Al Azaizeh | 60 | Sigue no elegible (declarado) |

Regla nueva (`canonicalize_player_identity` en `features_v04.py` y
`features.py`): una sola identidad por `player_id`; el nombre canónico es el
del partido con más minutos.

### 2. Slots laterales asignados solo por ranking

RB/LB, RCB/LCB y RW/LW se repartían por orden de ranking, ignorando el lado
real de cada jugador (p. ej. Vinícius Júnior aparecía como RW y Rubén Vargas
como LW). Ahora, dentro de cada par:

- la **elegibilidad no cambia**: entran los dos mejores del ranking, como
  antes;
- el **lado** se decide con la evidencia observada: orientación de grid del
  proveedor validada contra anclas humanas (`lateral_grid_validation.json`,
  mapeo `low_is_left`, 96% de acuerdo) más las anclas públicas de rol
  (`public_role_anchors_2026.csv`), que tienen prioridad;
- sin evidencia concluyente (o con ambos jugadores del mismo lado), se
  conserva el orden de ranking y la regla queda registrada en la columna
  `side_assignment_rule` de `real_best_xi.csv`.

Implementación: `build_experimental_lineups` (`ranking.py`) +
`synthetic_xi_2026/sides.py`. Evidencia auditable en
`data/processed/xi_side_evidence.csv`.

## Real Best XI v0.4.1

GK Gregor Kobel · RB Achraf Hakimi · RCB Alexander Freeman ·
LCB Ramy Bensebaini · LB Marcos Llorente · DM Rodri · CM Lucas Paquetá ·
AM Michael Olise · RW Rubén Vargas · LW Vinícius Júnior · ST Lionel Messi

Cambios frente a v0.4.0: Freeman↔Bensebaini intercambian RCB/LCB y
Vargas↔Vinícius intercambian RW/LW, por evidencia de lado. Hakimi conserva RB
(ancla oficial). Llorente permanece en LB por orden de ranking con evidencia
en conflicto (ambos laterales seleccionados son diestros); el conflicto queda
declarado en la fila.

El Synthetic XI mantiene los 8 arquetipos publicados (`SYN-GK20` …
`SYN-ST20`); la membresía del avatar GK cambia al entrar Bounou fusionado al
Top-20. El avatar AM sigue declarando `actual_n=19 < 20` porque el pool AM
completo del torneo es 19 (limitación de datos, no defecto).

## Coherencia del paquete web

La web publicaba un replay generado con la corrida exploratoria
`calibrated_v0_2`, cuyos actores (Mbappé, Pedri, Doué…) no pertenecían al
once mostrado y usaban IDs de avatar inexistentes (`SYN-W120`). Ahora:

- `simulator/profiles_wc.py` construye ambos equipos desde la selección
  corregida (rol primario del torneo, avatares como media recortada al 10% de
  sus miembros publicados, **incertidumbre de muestreo pareada entre
  equipos** — el avatar hereda la σ media de sus miembros en lugar del error
  estándar del centroide, eliminando el sesgo direccional detectado en
  auditoría);
- `scripts/run_calibrated_selection_simulation.py` corre el motor calibrado
  (10.000 partidos, seed 20260718) sobre esos equipos:
  **Real Best XI 52,82% · empate 21,08% · Synthetic XI 26,10%**, gate de
  calibración de ingeniería PASS
  (`data/simulations/calibrated_v0_4_selection/`);
- `scripts/build_replay_broadcast.py` regenera `replay_package.json` desde esa
  corrida; todos los actores del replay pertenecen a los onces publicados.

Estas probabilidades son de **partido único a 90 minutos** (permite empate) y
no sustituyen al experimento oficial v1 de finales eliminatorias
(44,59%/55,41%), que permanece congelado e intacto.

## Reproducción

```bash
pip install -r requirements.txt
python scripts/rebuild_selection_from_cache.py
PYTHONPATH=. python scripts/run_calibrated_selection_simulation.py
python scripts/build_replay_broadcast.py
PYTHONPATH=. pytest tests/test_selection_correction.py -q
```
