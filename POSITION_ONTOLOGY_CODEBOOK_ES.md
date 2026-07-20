# Código de clasificación ciega de posiciones

Versión: 1.0 · Semilla de muestreo: `20260720`

## Objetivo

Clasificar la función futbolística primaria de cada jugador sin consultar su puntuación, ranking, resultado de la simulación, clasificación anterior ni clasificación automática auditada.

Los revisores deben trabajar de forma independiente. No deben discutir casos antes de entregar sus formularios.

## Unidad de clasificación

La unidad es el **jugador durante la ventana analizada**, no su posición histórica de carrera ni una aparición aislada. Se debe elegir la función que mejor describa la mayor parte de sus minutos relevantes.

## Roles permitidos

| Código | Definición operativa |
|---|---|
| GK | Portero. |
| RB | Lateral o carrilero derecho. |
| RCB | Central derecho o central del lado derecho en línea de tres. |
| LCB | Central izquierdo o central del lado izquierdo en línea de tres. |
| LB | Lateral o carrilero izquierdo. |
| DM | Pivote, mediocentro defensivo o centrocampista más retrasado. |
| CM | Interior o mediocampista central de ida y vuelta, sin ser claramente el pivote ni el mediapunta. |
| AM | Mediapunta, número 10 o interior claramente adelantado entre mediocampo y ataque. |
| RW | Extremo derecho o atacante exterior derecho. |
| LW | Extremo izquierdo o atacante exterior izquierdo. |
| ST | Delantero centro, falso nueve o uno de los dos delanteros centrales. |
| UNRESOLVED | Evidencia insuficiente o función verdaderamente ambigua. |

## Reglas

1. Seleccionar un solo rol primario.
2. Registrar un rol secundario solo cuando represente una fracción sustancial de minutos.
3. No convertir automáticamente a un jugador en extremo por comenzar a un lado en un 4-4-2; los dos atacantes de la última línea son ST.
4. En líneas de tres centrales, el defensor central puro puede quedar sin lateralidad; cuando no sea posible distinguir RCB/LCB, usar `UNRESOLVED` y explicarlo.
5. Los carrileros de 3-5-2, 3-4-2-1 y sistemas equivalentes se clasifican como RB o LB, no como CM.
6. El número de camiseta, reputación, premios y rendimiento no determinan la posición.
7. No consultar los archivos de rankings, simulaciones ni el `answer_key.csv`.

## Confianza

- `3`: evidencia clara y consistente.
- `2`: función probable, con uso secundario relevante.
- `1`: evidencia limitada o contradictoria.

## Criterio de aprobación

La revisión se considerará suficientemente fiable cuando:

- Cohen’s κ entre revisores sea al menos 0.80;
- el acuerdo en jugadores de alto impacto sea al menos 90%;
- no queden desacuerdos sin adjudicar entre los jugadores que pueden entrar al Real XI o al Top 20 sintético;
- la compatibilidad con fuentes públicas independientes sea al menos 90% en los casos con ancla disponible.
