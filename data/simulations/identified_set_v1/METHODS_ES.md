# Métodos — simulación Synthetic XI vs. conjunto identificado de Real XI

## Estimando principal

No se selecciona retrospectivamente un único Real XI. La comparación principal es el
**envolvente de resultados** frente a las ocho alineaciones completas compatibles con la
evidencia disponible. Este tratamiento sigue la lógica de identificación parcial ante datos
faltantes: se reporta lo que queda identificado sin imponer supuestos suficientes para fabricar
un punto único.

## Diseño preespecificado antes de observar los resultados

- Synthetic XI principal: media recortada al 10% del Top 20 por cada una de las once funciones.
- Si una función contiene menos de 20 candidatos elegibles, se utiliza y declara el N real.
- Elegibilidad: perfil puntuable, rol estable, cobertura aprobada y al menos 900 minutos.
- Campo neutral: ventaja local igual a cero.
- Ocho Real XI plausibles; ninguna combinación recibe probabilidad subjetiva.
- Incertidumbre de calibración: remuestreo bootstrap de los 94 partidos FT.
- Comparaciones pareadas: mismas corrientes de semillas para todas las alineaciones y espejo
  Synthetic-local/Real-local.
- Simulaciones ejecutadas: **65,600**.
- Semilla maestra: **20260720**.

## Sensibilidades

1. Top 10 y Top 30 por función.
2. Incertidumbre sintética agrupada (principal) frente a no reducirla por el tamaño del Top-N.
3. Respuesta baja y alta de la ventaja de habilidad en posesión, disparo y conversión.

## Interpretación

El motor es una simulación probabilística de eventos —posesiones, tiros y goles— calibrada con
el Mundial observado. No es tracking, física continua ni reconstrucción causal de un partido.
Una conclusión solo se considera robusta cuando mantiene dirección en las ocho alineaciones y
en todas las sensibilidades preespecificadas.

## Bases metodológicas

- Dixon y Coles (1997), modelación probabilística de marcadores de fútbol. DOI: 10.1111/1467-9876.00065.
- Gneiting, Balabdaoui y Raftery (2007), calibración y nitidez de pronósticos probabilísticos. DOI: 10.1111/j.1467-9868.2007.00587.x.
- Manski (2005), identificación parcial con datos faltantes. DOI: 10.1016/j.ijar.2004.10.006.
- Nelson y Hsu (1993), números aleatorios comunes para reducir varianza en comparaciones de simulación. DOI: 10.1287/mnsc.39.8.989.
