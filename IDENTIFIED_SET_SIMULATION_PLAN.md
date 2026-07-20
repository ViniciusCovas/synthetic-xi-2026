# Plan preanalítico — Synthetic XI vs. conjunto identificado de Real XI

Fecha de fijación: 2026-07-20  
Semilla maestra: `20260720`

## Pregunta

¿El Synthetic XI construido mediante una media recortada de los mejores jugadores por función produce una ventaja simulada robusta frente a todas las alineaciones del Real XI compatibles con la evidencia disponible?

## Estimando principal

El resultado principal no será una comparación contra un único Real XI. Será el **envolvente de probabilidades de resultado** entre las ocho alineaciones completas del conjunto identificado.

Se reportarán por alineación:

- probabilidad de victoria del Synthetic XI;
- probabilidad de empate;
- probabilidad de victoria del Real XI;
- diferencia media de goles;
- diferencia media de xG;
- participación media de posesiones del Synthetic XI.

## Equipos

### Synthetic XI principal

- Once funciones exactas: GK, RB, RCB, LCB, LB, DM, CM, AM, RW, LW y ST.
- Top 20 por función, ordenado por puntuación conservadora.
- Media recortada al 10% en cada dimensión.
- Solo perfiles puntuables, con rol estable, cobertura aprobada, elegibilidad científica y al menos 900 minutos.
- Cuando una función tenga menos de 20 elegibles, se conservará y reportará el N real.

### Real XI

Se simularán las ocho combinaciones cartesianas ya publicadas en `data/releases/v1_0_identified_set/plausible_real_xi_combinations.csv`. Ninguna recibirá probabilidad subjetiva ni se elegirá después de observar resultados.

## Incertidumbre

1. Incertidumbre de perfil individual ya incorporada en el motor.
2. Mundos de calibración que incluyen el mundo observado y remuestreos bootstrap de los 94 partidos FT.
3. Corrientes comunes de semillas entre las ocho alineaciones.
4. Simulación espejo con Synthetic XI y Real XI alternando la etiqueta de local, con ventaja local igual a cero.

## Escenario principal

- Top 20.
- Incertidumbre del avatar agrupada según el tamaño real del Top-N, con piso de 0.025.
- Parámetros calibrados base del motor.
- 40 mundos de calibración.
- 40 partidos por orientación y mundo para cada uno de los ocho Real XI.
- 3,200 partidos por Real XI; 25,600 en el escenario principal.

## Sensibilidades preespecificadas

- Top 10.
- Top 30.
- Top 20 sin reducción de incertidumbre por agregación; se usa la mediana de incertidumbre de los miembros.
- Respuesta baja de habilidad en posesión, disparo y conversión.
- Respuesta alta de habilidad en posesión, disparo y conversión.
- Cada sensibilidad utiliza 20 mundos, 25 partidos por orientación y 1,000 partidos por Real XI.

## Regla de decisión

La dirección será declarada robusta únicamente cuando, para las ocho alineaciones, el intervalo bootstrap del margen `P(Synthetic gana) − P(Real gana)` quede completamente:

- por encima de cero, o
- por debajo de cero.

Un titular fuerte solo será autorizado si la dirección también permanece igual en todas las sensibilidades y el gate de calibración de ingeniería está aprobado.

## Restricciones de interpretación

- No se declarará un Real XI único.
- No se presentará la simulación como predicción cierta de un partido real.
- El motor representa eventos probabilísticos, no tracking ni física continua.
- El partido narrado será elegido mediante una regla determinista de representatividad, no por dramatismo.
- Todos los archivos de entrada serán registrados mediante SHA-256.

## Salidas

- ledger comprimido de partidos;
- resultados por mundo de calibración;
- resultados por cada Real XI;
- envolvente identificado;
- distribución de marcadores;
- miembros de cada avatar;
- perfiles de equipos;
- decisión de robustez;
- manifiesto reproducible;
- partido representativo;
- métodos y paquete narrativo con guardrails.

## Enmienda computacional ciega a resultados

La primera ejecución integral comenzó con un presupuesto de 396,800 partidos. Antes de que existiera cualquier salida de resultados, se sustituyó por un presupuesto de precisión de **65,600 partidos** para evitar computación redundante del motor secuencial. La enmienda no altera la pregunta, el estimando, los equipos, la semilla, las sensibilidades, los parámetros ni la regla de decisión.

El escenario principal conserva 3,200 partidos por cada Real XI. En el caso de máxima varianza binomial (`p = 0.5`), el error estándar Monte Carlo de una probabilidad agregada por alineación es aproximadamente `0.0088`. Cada sensibilidad conserva 1,000 partidos por alineación, con error estándar máximo aproximado de `0.0158`; estas corridas se utilizan únicamente para verificar dirección y no para reemplazar la estimación principal.
