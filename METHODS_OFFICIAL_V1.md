# Métodos — Official Experiment v1

## Diseño

Estudio computacional preregistrado de comparación entre dos equipos contrafactuales construidos a partir del mismo corte de datos: `Synthetic XI` y `Real Best XI`. La unidad científica principal es una distribución de finales eliminatorias simuladas, no una narración individual.

La ejecución histórica de julio de 2026 se trata como piloto final. La nueva ruta confirmatoria se rige por `PROTOCOL_AMENDMENT_OFFICIAL_V1.md` y `config/official_experiment_v1.json`.

## Datos y corte temporal

Los perfiles se construyen únicamente con información disponible en el snapshot congelado. Cada artefacto conserva hashes SHA-256, configuración y ledger de semillas. La ausencia de evidencia afirmativa bloquea la ejecución confirmatoria.

## Elegibilidad

El análisis principal requiere 900 minutos exactos en las ventanas declaradas. Los umbrales de 450 y 180 minutos se analizan como sensibilidades. Los futbolistas sin evidencia suficiente no se imputan para completar un Top-N.

## Roles

Los arquetipos amplios son `GK`, `CB`, `FB`, `DM`, `CM`, `AM`, `W` y `ST`. Para el once se utilizan los slots canónicos:

`GK, RB, RCB, LCB, LB, DM, CM, AM, RW, LW, ST`.

El motor traduce determinísticamente esos roles a sus slots internos. La ontología principal es cohort-relative; una regla transparente basada en posición y grid del proveedor constituye sensibilidad estructural.

## Construcción del Synthetic XI

Para cada slot se seleccionan los Top 20 elegibles del arquetipo correspondiente mediante el índice estabilizado ya congelado. El perfil sintético es una media recortada al 10% por dimensión. Cuando el universo contiene menos de N jugadores, se usa el N real y se registra explícitamente.

Las instancias duplicadas de CB, FB y W comparten el centro estadístico del arquetipo, pero tienen identificadores, estados, fatiga, disciplina y decisiones independientes.

## Construcción del Real Best XI

Los once titulares reales y el plantel de 26 jugadores se cargan directamente desde `complete_final_rosters_v1.json`. Los futbolistas son distintos y los desempates son determinísticos. El runtime aborta si cualquier ID, rol o tamaño del plantel difiere del roster congelado.

## Banquillos

Las sustituciones se realizan exclusivamente desde los planteles congelados. No se generan reservas funcionales a partir del futbolista sustituido. Un suplente puede ingresar una sola vez y debe ser compatible con el slot reemplazado.

## Motor de partido

El motor `complete_final_official_v1` representa:

- posesiones y progresión territorial;
- tiros, xG y goles;
- estado del marcador;
- fatiga y coordinación;
- decisiones tácticas dependientes del estado;
- faltas, amarillas, segundas amarillas y rojas directas;
- lesiones y sustituciones;
- VAR, penaltis y tiempo añadido;
- prórroga y tanda;
- igualdad, superioridad e inferioridad numérica.

No modela física continua ni reproduce toda la táctica sin balón.

## Disciplina

Los objetivos congelados del benchmark son 23.192 faltas, 2.872 amarillas comparables y 0.144 rojas por partido. El motor incluye adaptación conductual: un jugador amonestado reduce su propensión posterior a cometer una nueva falta.

El release exige:

- error absoluto de faltas ≤ 3.00;
- error absoluto de amarillas ≤ 0.75;
- error absoluto de rojas ≤ 0.20;
- razón de rojas simuladas/observadas entre 0.50 y 2.00.

## Semántica de eventos

Cada evento registra equipo actor, afectado, en posesión y beneficiado, actor, pertenencia del actor, periodo, minuto, marcador y estado numérico. Cualquier actor no perteneciente al plantel activo genera un fallo de integridad.

## Condiciones pareadas

Las orientaciones utilizan números aleatorios comunes. El contexto arbitral y ambiental se empareja entre equipos. El ambiente se registra y se usa como etiqueta de sensibilidad; no se introduce un modificador de habilidad no validado.

## Monte Carlo

La validación aislada usa 2.000 finales. La ejecución confirmatoria utiliza 10.000 finales. Las probabilidades binarias se acompañan de intervalos de Wilson. La ejecución oficial se bloquea si falta convergencia operacional, estabilidad entre semillas o equivalencia de orientación.

## Sensibilidad

Se repite el mismo motor oficial variando:

- Top 10, 20 y 30;
- 180, 450 y 900 minutos;
- ontología posicional;
- coordinación de cada equipo;
- parámetros del motor;
- disciplina y arbitraje.

La dirección consistente se reporta, pero no es una condición de validez.

## Incertidumbre anidada

El Monte Carlo anidado separa mundos de parámetros de la aleatoriedad del partido. Incluye perfiles, roles, Top-N, minutos, coordinación, parámetros del motor, árbitro, ambiente pareado y aleatoriedad de trayectoria.

## H5 — Consistencia

Se estiman diferencias Synthetic–Real en:

- varianza de goles;
- varianza de xG;
- varianza de tiros;
- probabilidad de cero goles;
- cola ofensiva inferior.

Menor variabilidad no equivale automáticamente a superioridad.

## H6 — Impacto extremo

Se estiman diferencias en:

- probabilidad de al menos tres goles;
- probabilidad de xG ≥ 2.0;
- probabilidad de al menos 15 tiros;
- probabilidad de ganar por al menos dos goles;
- cuantiles 0.90 y 0.95 de goles, xG y tiros.

## H7 — Dependencia contextual

Se estiman tiros, goles y xG por posesión según:

- empatando, ganando o perdiendo;
- primera parte, segunda parte o prórroga;
- igualdad, superioridad o inferioridad numérica.

La unidad de incertidumbre es la simulación completa. Los eventos de un mismo partido no se tratan como observaciones independientes.

## Replay representativo

El replay se selecciona automáticamente mediante distancia estandarizada a medianas preregistradas y etapa modal. No se elige por dramaticidad.

## Gates de release

La ejecución oficial requiere simultáneamente:

- roster canónico idéntico al runtime;
- perfiles no provisionales y sin etiquetas exploratorias;
- suficiencia de selección y rankings autorizados;
- holdout externo aprobado;
- cordura de eventos;
- calibración disciplinaria;
- equivalencia de orientación;
- estabilidad entre semillas;
- sensibilidad e incertidumbre oficiales completas;
- estimandos H5–H7 presentes;
- comparación final autorizada;
- ausencia de tuning posterior a resultados.

## Límite de inferencia

La afirmación permitida es una distribución comparativa condicionada al modelo, los datos y los supuestos preregistrados. El estudio no demuestra que un equipo sintético pueda existir corporalmente ni predice con certeza el resultado de un partido físico.
