# Metodología v0.3 — Synthetic XI 2026

## Pregunta general

¿Puede un avatar construido a partir del perfil agregado de los mejores futbolistas elegibles de cada posición mostrar mayor equilibrio y consistencia que el mejor jugador real de esa misma función y, al combinar once avatares, competir con el mejor once real del torneo?

## Diseño temporal

La unidad de análisis es un **snapshot acumulado y fechado**. Ningún corte se sobrescribe silenciosamente. Toda tabla o figura debe informar la fecha y hora de corte, el número de partidos concluidos y el número de jugadores elegibles por posición.

## Fuente y auditabilidad

El adaptador inicial utiliza API-FOOTBALL para Copa Mundial, temporada 2026. La clave permanece en GitHub Secrets. Las respuestas se almacenan en caché privada y reciben hash SHA-256. Los resultados públicos solo contienen estadísticas procesadas y metadatos metodológicos.

## Posiciones

- GK: portero.
- CB: defensa central.
- FB: lateral o carrilero.
- DM: mediocentro defensivo.
- CM: mediocentro.
- AM: mediapunta.
- W: extremo.
- ST: delantero centro.

La clasificación se realiza para titulares usando posición, formación y grid. Los suplentes sin rol preciso se excluyen en esta versión.

## Elegibilidad

- 180 minutos acumulados como umbral principal.
- La posición principal debe ser inferible de forma consistente.
- No se imputa ni duplica ningún jugador para completar el Top 20.

## Ajuste por confiabilidad

Cada métrica se retrae hacia la media de su posición:

```text
confiabilidad = minutos / (minutos + 180)
ajustada = media_posición + confiabilidad × (observada − media_posición)
```

## Ranking posicional

1. Selección de elegibles.
2. Winsorización al percentil 5–95.
3. Estandarización intraposición.
4. Inversión de métricas perjudiciales.
5. Promedio de z-scores con pesos iguales pre-registrados.

La nota compuesta del proveedor no entra en el índice.

## Avatar Top 20

El avatar principal es una **media recortada al 10%** de los Top 20. Para N=20 se retiran los dos valores más altos y los dos más bajos de cada atributo antes de calcular el centro. También se reportan media aritmética, mediana, desviación estándar e intervalo bootstrap de 95%.

## Mejor jugador real

El benchmark real es el número 1 del índice posicional después de la retracción por minutos. La selección es independiente para cada una de las ocho posiciones.

## Estudio 1

Se comparan avatar y benchmark real en cada atributo de su posición. Las diferencias se orientan para que valores positivos siempre favorezcan al avatar. El resultado principal distingue:

- superioridad descriptiva;
- equilibrio multidimensional;
- peor atributo relativo;
- dispersión e incertidumbre;
- estabilidad en Top 10, Top 20 y Top 30.

No se proclamará superioridad inferencial hasta completar la validación leave-one-match-out.

## Estudio 2

Formación funcional 4-3-3:

```text
1 GK + 2 CB + 2 FB + 1 DM + 1 CM + 1 AM + 2 W + 1 ST = 11
```

El Real Best XI usa los puestos 1 y 2 cuando una función ocupa dos plazas. El Synthetic XI usa dos instancias independientes del mismo avatar en esas plazas. La independencia se aplicará a las realizaciones probabilísticas, no a la identidad estadística del avatar.

## Validación prevista

- leave-one-match-out;
- correlación con rating externo como validez convergente;
- sensibilidad Top 10/20/30;
- sensibilidad del prior de minutos;
- media recortada vs mediana;
- auditoría de cobertura;
- simulación pareada con las mismas condiciones para ambos agentes.

## Límites de afirmación

No se afirmará que el avatar es uno de los mejores jugadores del mundo fuera de la muestra, que el motor reproduce toda la táctica sin balón ni que una simulación por eventos equivale a un partido físico real.
