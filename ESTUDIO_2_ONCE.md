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

- Synthetic XI replica el avatar CB, FB y W en dos plazas, pero cada instancia realiza decisiones independientes.
- Real Best XI selecciona a los dos mejores CB, FB y W, y al número 1 en las demás funciones.

## Primera simulación

La primera versión será un motor por eventos, no una recreación física. Se modelarán posesiones, progresiones, duelos, pases, pérdidas, tiros y goles bajo condiciones pareadas. El protocolo completo se activa después de validar la cobertura del Estudio 1.
