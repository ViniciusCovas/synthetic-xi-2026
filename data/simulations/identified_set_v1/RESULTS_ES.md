# Resultados científicos — Synthetic XI vs. conjunto identificado de Real XI

Generado: 2026-07-20T02:44:29.002309+00:00

## Resultado principal

Se ejecutaron **65,600 partidos** con semilla fija, campo neutral,
ocho alineaciones reales plausibles, incertidumbre de perfil, bootstrap de calibración y cinco
sensibilidades preespecificadas.

Frente a las ocho alineaciones posibles:

- **Synthetic XI gana:** 23.4%–26.7%.
- **Empate:** 23.2%–25.3%.
- **Real XI gana:** 49.3%–52.1%.
- **Diferencia media de goles (Synthetic − Real):** -0.657 a -0.521.
- **Diferencia media de xG (Synthetic − Real):** -0.681 a -0.537.
- **Intervalo identificado-bootstrap del margen de victoria:** -0.401 a -0.124.

Todo el intervalo permanece por debajo de cero. Por tanto, la dirección está identificada dentro
del modelo: el Real XI conserva ventaja en las ocho alineaciones, no únicamente en una selección
conveniente.

## Robustez

Las cinco sensibilidades —Top 10, Top 30, incertidumbre no agrupada y respuesta de habilidad
baja/alta— conservaron la misma dirección. El rango más favorable para el Synthetic XI apareció
en Top 10, pero incluso allí su probabilidad de victoria quedó entre
26.4%
y 29.4%,
frente a 48.4%–51.2%
del Real XI.

## Qué hacen las tres posiciones ambiguas

- **GK — J. Garcia → L. Hornicek:** victoria Synthetic +0.1 pp; victoria Real -0.1 pp; diferencia de goles +0.004.
- **RB — D. Raum → J. Hadjam:** victoria Synthetic -2.4 pp; victoria Real +1.1 pp; diferencia de goles -0.074.
- **AM — J. Quintero → W. Semedo:** victoria Synthetic -0.8 pp; victoria Real +1.5 pp; diferencia de goles -0.057.

La portería apenas cambia el resultado. Las mayores variaciones proceden de RB y AM, pero ninguna
combinación revierte la conclusión.

## Por qué gana el Real XI

El Synthetic XI no es un “superjugador” que toma el máximo de cada métrica: es una media recortada
de los mejores candidatos. Esa regla reduce dependencia de outliers y mejora estabilidad, pero
también suaviza las cimas individuales. Los mayores gaps de perfil fueron:

- **FB2**: ventaja media Real − Synthetic de +0.154 en overall.
- **CB1**: ventaja media Real − Synthetic de +0.144 en overall.
- **CM**: ventaja media Real − Synthetic de +0.121 en overall.
- **CB2**: ventaja media Real − Synthetic de +0.110 en overall.
- **W1**: ventaja media Real − Synthetic de +0.088 en overall.

La diferencia aparece más en calidad de ocasión y conversión que en control territorial: en el
escenario principal el Synthetic XI mantuvo aproximadamente 48% de los estados de posesión, pero
cedió entre 0.537 y 0.681 xG medios por partido.

## Validación disponible

El gate de calibración de ingeniería está aprobado. Además, una prueba externa separada, con
perfiles congelados antes del torneo, evaluó 91 partidos FT y obtuvo log loss
**0.883** frente a **1.099**
del baseline uniforme, con accuracy top-1 de **62.6%**.
Esta prueba confirma señal predictiva en la agregación de perfiles; no equivale a validar cada
micro-mecanismo del motor de eventos.

## Claim autorizado

> En 65,600 simulaciones calibradas, las ocho versiones científicamente plausibles del mejor XI
> real conservaron una probabilidad de victoria superior a la del Synthetic XI; la dirección se
> mantuvo en todas las sensibilidades preespecificadas.

## Lo que no debe afirmarse

No se demostró que el Real XI ganaría con certeza un partido real, no se identificó un único Real
Best XI y el 2-1 representativo no es un marcador pronosticado. El resultado es una inferencia
condicional a un motor transparente y a una familia explícita de supuestos.
