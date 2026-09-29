# ¿Puede un once sintético igualar al mejor once humano?

## Un experimento reproducible con ajuste por fuerza competitiva, ontología posicional y simulación de 100.000 partidos

**Borrador de artículo — versión 2, 21 de julio de 2026**

## Resumen

Este estudio compara un único once de futbolistas reales con un único once de agentes sintéticos, construidos a partir de perfiles estadísticos de jugadores observados durante una ventana congelada de 2025–2026. La versión inicial del experimento reveló dos problemas de validez externa: una dimensión de portería sin capacidad discriminativa y la ausencia de ajuste explícito por fuerza de competición y de oponentes. La versión 2 corrige ambos problemas antes de volver a seleccionar los equipos.

La base final contiene 541 combinaciones jugador–posición elegibles, 4.794 partidos con contexto completo y 25.624 observaciones jugador–partido. La fuerza competitiva se estimó mediante redes Elo separadas para clubes y selecciones, combinando 70% de fuerza media de los rivales y 30% de fuerza mediana de la competición. El modelo de porteros integra tasa de paradas con regularización bayesiana, residuo de goles recibidos ajustado por Elo, porterías a cero, distribución y penaltis. El modelo produjo 50 valores distintos entre 50 porteros elegibles.

El Real XI se seleccionó mediante asignación global uno-a-uno. El AI XI se generó mediante combinaciones convexas de vectores completos de jugadores elegibles de la misma posición, sin acceso al rival ni al motor de simulación. Tras validación temporal, pruebas de sensibilidad, congelamiento de hashes y una validación direccional independiente, se simularon 100.000 partidos neutrales en 50.000 pares de semillas comunes.

El Real XI ganó el 39,879% de los partidos, el AI XI el 37,652% y el 22,469% terminó en empate. La diferencia Real menos AI en probabilidad de victoria fue de 2,227 puntos porcentuales, con intervalo de confianza del 95% por clusters de pares entre 2,061 y 2,393 puntos. La diferencia media de goles fue de +0,05574 para el Real XI. Los resultados indican que los agentes sintéticos se aproximan estrechamente al rendimiento del once real óptimo bajo el modelo, aunque conservan una desventaja pequeña y consistente.

**Palabras clave:** inteligencia artificial; simulación; fútbol; agentes sintéticos; Elo; validez externa; ciencia abierta.

## 1. Introducción

La construcción de futbolistas sintéticos suele adoptar uno de dos enfoques: personajes ficticios sin anclaje empírico o agregados estadísticos que combinan máximos incompatibles entre sí. Ambos enfoques dificultan una comparación científicamente defendible con jugadores reales. Este trabajo plantea una alternativa: generar agentes sintéticos únicamente mediante combinaciones de perfiles completos de jugadores reales elegibles para la misma función táctica.

La pregunta central es:

> ¿Puede un once formado por agentes sintéticos plausibles igualar o superar a un once real seleccionado globalmente bajo una misma ontología posicional y un mismo corte temporal?

El estudio no pretende predecir un partido físico real. Estima resultados condicionales a los datos, la ontología, las funciones de puntuación, el modelo de fuerza competitiva, el generador sintético y el motor de eventos congelados.

## 2. Diseño del estudio

### 2.1 Estimando

El estimando final compara exactamente:

- un Real XI determinista;
- un AI XI determinista;
- once posiciones: `GK, RB, RCB, LCB, LB, DM, CM, AM, RW, LW, ST`;
- condiciones neutrales;
- 100.000 partidos;
- 50.000 pares con las dos orientaciones nominales;
- semilla maestra `20260721`.

No se permite identificación parcial ni selección posterior a la simulación.

### 2.2 Ventana y elegibilidad

Cada candidato debe cumplir:

- al menos 1.800 minutos en la ventana anual congelada;
- al menos 900 minutos y tres observaciones en su familia posicional;
- posición exacta resuelta por dos clasificadores independientes basados en IA o por adjudicación explícita;
- cobertura mínima del 90% en las ventanas congeladas;
- perfil estadístico completo;
- identidad canónica única.

La auditoría posicional reunió 664 jugadores. La concordancia inicial entre los dos clasificadores fue 66,7%, con Cohen’s κ = 0,634. Las 221 divergencias fueron adjudicadas de forma ciega a puntuaciones, rankings, equipos y simulaciones. El κ original se conserva como diagnóstico y no se sustituye por el consenso posterior.

## 3. Corrección de validez externa

### 3.1 Razón para reconstruir el experimento

La primera versión del modelo asignó el mismo valor de portería a todos los guardametas elegibles y no incorporó explícitamente club, competición ni fuerza del rival. Por tanto, su simulación se preserva únicamente como diagnóstico y no sostiene una afirmación de mejor once global.

La versión 2 se ejecutó desde cero antes de observar el nuevo resultado.

### 3.2 Contexto competitivo

Se recuperó contexto completo para 4.794 partidos vinculados a candidatos elegibles. Se construyeron dos redes Elo separadas:

- clubes;
- selecciones nacionales.

Parámetros principales:

- ventaja local Elo: 45 puntos para clubes y 25 para selecciones;
- actualización K: 22 para clubes y 26 para selecciones;
- ajuste por margen de goles;
- fuerza contextual individual: 70% fuerza media de rivales + 30% fuerza mediana de competición;
- transformación de métricas en espacio logit con γ = 0,18;
- confiabilidad dependiente de cobertura, número de partidos y conectividad entre competiciones.

En un holdout temporal del 20%, el modelo Elo obtuvo Brier 0,15966 frente a 0,18142 del baseline, equivalente a una mejora relativa de 11,99%. El holdout incluyó 960 partidos.

### 3.3 Modelo específico de porteros

La dimensión de portería v2 combina:

- 50% tasa de paradas regularizada;
- 20% goles evitados mediante residuo de goles recibidos ajustado por Elo;
- 15% tasa de porterías a cero regularizada;
- 10% precisión de distribución regularizada;
- 5% penaltis detenidos regularizados.

La confiabilidad se retrae hacia 0,5 según los minutos del portero. Entre 50 guardametas elegibles, el modelo produjo 50 valores únicos y desviación estándar de 0,17756.

La principal limitación es que los tiros a puerta enfrentados se aproximan como paradas más goles recibidos; no se dispone de xG enfrentado a nivel de evento para toda la muestra.

## 4. Selección de los equipos

### 4.1 Real XI

La selección usa una asignación global de peso máximo con una persona por posición y una posición por persona. Los desempates priorizan puntuación conservadora, minutos, experiencia posicional y menor vector ordenado de identificadores.

| Posición | Jugador | Club dominante |
|---|---|---|
| GK | Diogo Costa | FC Porto |
| RB | Alexis Saelemaekers | AC Milan |
| RCB | Cristian Romero | Tottenham |
| LCB | Brandon Mechele | Club Brugge |
| LB | Nuno Mendes | Paris Saint-Germain |
| DM | Elliot Anderson | Nottingham Forest |
| CM | Pedri | Barcelona |
| AM | Rayan Cherki | Manchester City |
| RW | Lamine Yamal | Barcelona |
| LW | Jérémy Doku | Manchester City |
| ST | Lionel Messi | Inter Miami |

La selección no equivale a un once de consenso periodístico. Es el óptimo bajo las reglas congeladas. La auditoría publica las diez primeras alternativas de cada posición y la diferencia exacta de puntuación.

### 4.2 AI XI

Cada agente sintético se genera mediante una combinación convexa de vectores completos de jugadores reales elegibles para la misma posición. El procedimiento:

- no mezcla columnas de jugadores diferentes de forma independiente;
- preserva relaciones multivariadas;
- aplica límites percentiles y Mahalanobis;
- rechaza copias exactas;
- no conoce al rival;
- no conoce el motor de partidos;
- evalúa 50.000 candidatos por posición.

Los equipos fueron congelados antes de simular:

- Real XI SHA-256: `cb5fce1cc56b7f5dbf22b41c76a59848fa9d1f5b61a25c3eacec2fba9a0cd585`;
- AI XI SHA-256: `badd74b15a7bd601241dea8f8e97d89e9d9f63aa78433336ede28f2328c655fb`.

## 5. Validación previa a la simulación

Se aplicaron cuatro pruebas adicionales:

1. **Holdout predictivo Elo:** aprobado, con skill de 11,99% frente al baseline.
2. **Sensibilidad de γ:** valores `0,00; 0,09; 0,18; 0,27; 0,36`; solapamiento medio de 9,4 jugadores y mínimo de 8 entre 11; 96,36% de las selecciones congeladas permanecieron en el Top 3 de su posición.
3. **Sensibilidad del modelo de porteros:** Diogo Costa ocupó las posiciones `1, 1, 2 y 3` bajo cuatro ponderaciones alternativas.
4. **Plausibilidad individual:** los once seleccionados superaron cobertura, experiencia posicional y trazabilidad.

Un modelo Poisson independiente del motor de eventos estimó 1,5578 goles para el Real XI y 1,5192 para el AI XI. La dirección favorable al Real XI se mantuvo en el 100% de las exclusiones jackknife por posición y en el 100% de las combinaciones de parámetros evaluadas.

## 6. Simulación final

El motor calibrado se ejecutó con:

- 100.000 partidos;
- 50.000 pares de semillas comunes;
- dos orientaciones nominales por par;
- ventaja local igual a cero;
- semilla maestra `20260721`;
- equipos, código y parámetros congelados.

La inferencia utiliza los 50.000 pares como clusters para no tratar como independientes las dos orientaciones que comparten semilla.

## 7. Resultados

| Resultado | Probabilidad | IC95% por clusters |
|---|---:|---:|
| Victoria Real XI | 39,879% | 39,692%–40,066% |
| Empate | 22,469% | 22,128%–22,810% |
| Victoria AI XI | 37,652% | 37,459%–37,845% |

La diferencia Real menos AI en probabilidad de victoria fue:

- **2,227 puntos porcentuales**;
- IC95%: **2,061 a 2,393 puntos**.

Producción media por partido:

| Indicador | Real XI | AI XI | Diferencia Real − AI |
|---|---:|---:|---:|
| Goles | 1,75693 | 1,70119 | +0,05574 |
| xG | 1,75022 | 1,69653 | +0,05369 |
| Tiros | 9,46295 | 9,27478 | +0,18817 |
| Tiros a puerta | 4,78186 | 4,68897 | +0,09289 |

El marcador más frecuente fue 1–1, observado en 9,382% de las simulaciones. La dirección final coincidió con el modelo independiente previo.

## 8. Discusión

El AI XI no superó al Real XI, pero se aproximó de forma estrecha: la diferencia de victoria fue inferior a 2,3 puntos porcentuales. Esto sugiere que combinaciones multivariadas plausibles de habilidades humanas pueden generar agentes colectivos cercanos al óptimo observado, sin recurrir a jugadores ficticios con máximos incompatibles.

La reconstrucción v2 modificó sustancialmente la interpretación. En la versión sin validez externa, la ventaja del Real XI era de apenas 0,483 puntos. Tras introducir un modelo de porteros discriminativo y ajustar el contexto competitivo, la ventaja aumentó a 2,227 puntos. La versión anterior no debe usarse como resultado principal.

Algunos nombres permanecen contraintuitivos. Saelemaekers y Mechele ganan por márgenes pequeños bajo γ = 0,18 y son sensibles a ajustes contextuales más intensos. Por ello, el artículo debe presentar rankings completos, sensibilidad y alternativas, en lugar de vender el once como una verdad universal.

## 9. Limitaciones

1. El Elo se construye con los partidos disponibles de la muestra y no constituye un ranking comercial exhaustivo de todas las ligas del mundo.
2. La portería utiliza proxies agregados; no existe xG enfrentado uniforme a nivel de evento.
3. La ontología posicional fue clasificada por sistemas de IA y adjudicada con evidencia pública, no por un panel humano de scouts.
4. Las estadísticas no capturan completamente movimiento sin balón, liderazgo, coordinación táctica ni adaptación interpersonal.
5. El motor de eventos simplifica decisiones y relaciones de un partido físico.
6. El resultado es condicional a una ventana concreta y debe actualizarse cuando cambien los datos.

## 10. Conclusión

Bajo un protocolo congelado, ajuste explícito de fuerza competitiva, modelo de portería discriminativo y simulación pareada, el Real XI superó al AI XI por una diferencia pequeña pero consistente. El resultado principal no es que la IA haya creado un equipo invencible, sino que un once sintético empíricamente plausible puede acercarse notablemente al mejor once real definido por el mismo modelo.

La contribución metodológica es una arquitectura abierta para distinguir entre perfiles sintéticos plausibles y combinaciones irreales de máximos, incorporando validez externa, trazabilidad posicional y publicación integral de hashes, semillas, candidatos, exclusiones y partidos simulados.
