# Estudio 2 — Synthetic XI vs Real Best XI

## Pregunta

¿Qué ocurre cuando ocho arquetipos posicionales sintéticos ocupan las once plazas de un equipo y compiten, en escenarios simulados equivalentes, contra el mejor once real disponible en el mismo corte temporal?

## Formación

| Plaza | Perfil |
|---|---|
| GK | Portero 1 |
| RB | Lateral 1 |
| RCB | Central 1 |
| LCB | Central 2 |
| LB | Lateral 2 |
| DM | Mediocentro defensivo 1 |
| CM | Mediocentro 1 |
| AM | Mediapunta 1 |
| RW | Extremo 1 |
| LW | Extremo 2 |
| ST | Delantero centro 1 |

## Equipos

- Synthetic XI replica el avatar CB, FB y W en dos plazas, pero cada instancia realiza decisiones independientes, conserva estado propio y ocupa un rol lateral específico.
- Real Best XI selecciona a los dos mejores CB, FB y W, y al número 1 en las demás funciones.
- La coordinación del equipo se estima separadamente de la habilidad individual y se somete a análisis de sensibilidad.

## Diseño de la simulación

El partido se modela mediante un motor por eventos y estados. Incluye circulación, progresión, duelos, pérdidas, tiros, goles, balón parado, faltas, tarjetas, VAR, lesiones, sustituciones, cambios tácticos, tiempo añadido, prórroga y tanda de penaltis.

La unidad principal de análisis es una distribución Monte Carlo de partidos posibles. Una transmisión minuto a minuto representa solamente una realización seleccionada mediante una regla preregistrada y nunca sustituye los resultados agregados.

El protocolo integral está definido en `PROTOCOLO_FINAL_COMPLETA.md`.

## Condición de activación

La comparación confirmatoria entre equipos permanece bloqueada hasta que se aprueben simultáneamente los gates de suficiencia de selección, calibración, holdout externo, cordura de eventos e incertidumbre completa.

Mientras exista cualquier gate fallido, las ejecuciones deben etiquetarse como **exploratorias** y no pueden utilizarse para afirmar que Synthetic XI o Real Best XI sería superior en un partido físico real.
