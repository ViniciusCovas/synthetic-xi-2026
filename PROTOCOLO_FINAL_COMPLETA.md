# Protocolo científico — Simulación completa de una final

## 1. Propósito

Este documento pre-registra la arquitectura de una simulación completa de una final entre **Synthetic XI** y **Real Best XI**. El objetivo no es producir una narración espectacular aislada, sino generar trayectorias de partido reproducibles, auditables y estadísticamente calibradas, con todos los acontecimientos relevantes y con incertidumbre explícita.

La unidad científica principal no será “un partido”, sino una **distribución de partidos posibles** bajo condiciones iniciales equivalentes. El replay audiovisual o textual será una realización seleccionada después del análisis agregado y nunca sustituirá los resultados inferenciales.

## 2. Principios de validez

1. **Separación entre modelo y relato.** El motor genera estados y eventos; la capa de transmisión únicamente verbaliza la salida.
2. **Condiciones pareadas.** Synthetic XI y Real Best XI se comparan con las mismas semillas ambientales, arbitrales y contextuales siempre que el diseño lo permita.
3. **Sin información futura.** Cada snapshot utiliza únicamente datos disponibles hasta su fecha de corte.
4. **Calibración antes de exhibición.** No se publican probabilidades de victoria ni comparaciones finales mientras fallen los gates científicos.
5. **Incertidumbre total.** Se propaga incertidumbre de selección, estimación de habilidades, parámetros del motor y aleatoriedad del partido.
6. **Auditabilidad.** Cada final conserva versión de datos, versión del modelo, configuración, semilla y registro completo de eventos.
7. **No equivalencia ontológica.** Un avatar sintético representa un perfil estadístico posicional, no un cuerpo humano ni una identidad deportiva real.

## 3. Gates obligatorios

La simulación final pública solo se habilita cuando todos los gates son verdaderos:

- `selection_sufficiency = true`
- `scientific_ready = true`
- `external_holdout_passed = true`
- `calibration_passed = true`
- `event_sanity_passed = true`
- `uncertainty_complete = true`
- `rankings_allowed = true`
- `final_team_comparison_allowed = true`

Si cualquiera falla, el sistema puede ejecutar simulaciones diagnósticas, pero debe etiquetarlas como **exploratorias**.

## 4. Estado del partido

El estado mínimo en el instante `t` incluye:

- marcador;
- minuto, periodo y tiempo añadido;
- posesión y ubicación del balón;
- equipo y jugador en control;
- forma táctica efectiva de ambos equipos;
- orientación de ataque;
- fatiga y carga acumulada por jugador;
- disponibilidad, lesión y riesgo de lesión;
- tarjetas y riesgo disciplinario;
- sustituciones restantes y ventanas disponibles;
- intensidad de presión, altura del bloque y riesgo asumido;
- contexto del marcador;
- ventaja arbitral activa;
- condiciones ambientales y del césped;
- historial reciente de eventos para efectos de dependencia temporal.

El motor debe ser **stateful**: la probabilidad de cada evento depende del estado actual y los eventos modifican el estado posterior.

## 5. Reloj y periodos

La final contempla:

- primer tiempo;
- tiempo añadido del primer tiempo;
- segundo tiempo;
- tiempo añadido del segundo tiempo;
- prórroga en dos periodos cuando corresponda;
- tiempo añadido en cada periodo de prórroga;
- tanda de penaltis cuando corresponda.

La duración añadida se estima a partir de sustituciones, lesiones, revisiones VAR, celebraciones, pérdidas deliberadas de tiempo y otras interrupciones. No se fija como un número arbitrario previo.

## 6. Taxonomía de eventos

### 6.1 Reinicios

- saque inicial;
- saque de banda;
- saque de meta;
- córner;
- falta directa o indirecta;
- penalti;
- balón a tierra.

### 6.2 Circulación y progresión

- pase corto, medio y largo;
- conducción;
- cambio de orientación;
- pase progresivo;
- pase al último tercio;
- entrada al área;
- centro;
- cutback;
- pase filtrado;
- recepción entre líneas;
- progresión fallida.

### 6.3 Duelos y recuperación

- presión;
- contra-presión;
- intercepción;
- entrada;
- duelo aéreo;
- bloqueo;
- despeje;
- segunda jugada;
- recuperación alta, media o baja;
- pérdida no forzada;
- pérdida forzada.

### 6.4 Ataque y finalización

- tiro;
- tiro bloqueado;
- tiro fuera;
- tiro al poste;
- tiro a puerta;
- parada;
- rebote;
- gran ocasión;
- gol;
- autogol;
- gol anulado.

Cada tiro registra, cuando la cobertura lo permita: ubicación, ángulo, distancia, parte del cuerpo, tipo de asistencia, presión defensiva, transición o ataque organizado, situación a balón parado y valor de `xG`.

### 6.5 Disciplina y arbitraje

- falta sin tarjeta;
- amarilla;
- segunda amarilla;
- roja directa;
- ley de la ventaja;
- penalti señalado;
- revisión VAR;
- cambio de decisión;
- decisión confirmada.

La capa arbitral utiliza un perfil latente muestreado por partido: frecuencia de faltas, severidad disciplinaria, tolerancia al contacto y propensión a añadir tiempo. Ese perfil nunca favorece deliberadamente a un equipo.

### 6.6 Lesiones y atención médica

- golpe sin salida;
- lesión leve con reducción temporal;
- lesión limitante;
- sustitución obligada;
- retirada sin sustitución disponible.

La lesión depende de exposición, fatiga, contacto y riesgo basal. No debe utilizarse como recurso narrativo libre.

### 6.7 Sustituciones y decisiones tácticas

- sustitución planificada;
- sustitución por lesión;
- cambio de formación;
- cambio de altura defensiva;
- variación de presión;
- cambio de amplitud;
- cambio de ritmo;
- protección del resultado;
- búsqueda del empate;
- riesgo máximo al final.

Las decisiones tácticas se activan mediante políticas predefinidas dependientes del minuto, marcador, fatiga, tarjetas, disponibilidad y métricas recientes. No se ajustan después de conocer el resultado.

## 7. Modelo de posesiones y eventos

El partido se modela como un proceso jerárquico:

1. inicio o reinicio;
2. estado de posesión;
3. elección de acción;
4. selección del actor y oponente relevante;
5. resolución probabilística de la acción;
6. actualización espacial y contextual;
7. posible interrupción;
8. actualización de fatiga, táctica y disciplina;
9. avance del reloj.

Las probabilidades deben combinar:

- habilidades estabilizadas por posición y jugador;
- interacción atacante-defensor;
- coordinación del equipo;
- zona del campo;
- presión y densidad local;
- fatiga;
- estado del marcador;
- fase del partido;
- superioridad o inferioridad numérica;
- incertidumbre estimada del perfil.

No se permite convertir directamente una calificación global del proveedor en probabilidad de éxito.

## 8. Dependencia y memoria

El motor debe evitar eventos independientes irreales. Incorporará como mínimo:

- posesiones encadenadas;
- secuencias de presión y salida;
- rebotes y segundas jugadas;
- periodos de dominio territorial;
- deterioro por fatiga;
- adaptación al marcador;
- impacto de tarjetas;
- impacto de expulsiones;
- sustituciones que cambian roles y parámetros;
- transiciones producidas por pérdidas en zonas específicas.

El llamado “momentum” solo se utilizará si mejora predicción fuera de muestra. No se introducirá como fuerza narrativa no identificada.

## 9. Coordinación del Synthetic XI

Los avatares replicados en CB, FB y W comparten el perfil posicional, pero cada instancia posee:

- semilla de decisiones independiente;
- estado de fatiga independiente;
- historial disciplinario independiente;
- ubicación y rol lateral independiente;
- interacciones distintas con compañeros y rivales.

La coordinación sintética se modela por separado de la habilidad individual. El análisis principal debe reportarse con un parámetro de coordinación preregistrado y análisis de sensibilidad en, al menos, tres niveles plausibles.

## 10. Prórroga y tanda de penaltis

### 10.1 Prórroga

La prórroga reutiliza el motor principal, con parámetros de fatiga, riesgo y sustituciones actualizados. No se simula como una lotería separada.

### 10.2 Penaltis durante el partido

Cada penalti combina:

- habilidad estabilizada del lanzador;
- habilidad del portero;
- pie dominante y dirección latente;
- fatiga;
- presión contextual;
- incertidumbre de los parámetros.

### 10.3 Tanda

La tanda incluye:

- orden de lanzadores definido por una política previa;
- elegibilidad de quienes terminan el partido;
- selección de lado del lanzador;
- decisión del portero;
- muerte súbita;
- actualización del estado psicológico solo si existe un parámetro validado externamente.

No se añadirá un efecto psicológico ad hoc para producir dramatismo.

## 11. Calibración

La calibración se realiza con partidos históricos comparables y ventanas temporales anteriores al holdout. Debe cubrir, como mínimo:

- goles por partido;
- tiros y tiros a puerta;
- `xG` agregado;
- posesiones;
- pérdidas;
- progresiones;
- córners;
- faltas;
- amarillas y rojas;
- sustituciones;
- lesiones observables;
- tiempo añadido;
- frecuencia de prórroga y penaltis en eliminatorias;
- distribución temporal de goles;
- resultados condicionados por expulsiones y estado del marcador.

Se compararán distribuciones completas, no solo medias.

## 12. Validación

### 12.1 Validación interna

- rolling-origin temporal;
- calibración por competición y fase;
- posterior predictive checks;
- análisis de residuos;
- pruebas de invariancia lateral;
- pruebas de conservación del estado;
- pruebas de imposibilidad lógica.

### 12.2 Holdout externo

El conjunto externo permanece bloqueado hasta finalizar calibración y selección de hiperparámetros. Métricas mínimas:

- log loss para resultados discretos;
- Brier score para victoria/empate/derrota;
- error y calibración de goles;
- cobertura de intervalos predictivos;
- distancia entre distribuciones de eventos;
- calibration slope e intercept;
- error por minuto y estado del marcador.

### 12.3 Pruebas de cordura

El motor debe rechazar o marcar realizaciones con:

- eventos después del final del partido;
- jugadores sustituidos que vuelven a participar;
- más sustituciones o ventanas de las permitidas;
- dos poseedores simultáneos;
- goles sin secuencia válida;
- marcador inconsistente;
- tarjetas o penaltis sin actor elegible;
- tanda con jugadores no elegibles;
- coordenadas fuera del campo;
- orientación espacial invertida.

## 13. Diseño Monte Carlo

El resultado principal se estima mediante múltiples capas:

1. remuestreo de jugadores elegibles;
2. muestreo de parámetros de habilidad;
3. muestreo de coordinación;
4. muestreo de parámetros del motor;
5. muestreo ambiental y arbitral pareado;
6. simulación de la trayectoria completa.

La cantidad final de simulaciones se determina por convergencia, no por una cifra estética. El criterio mínimo es estabilidad de las probabilidades principales y de sus intervalos bajo lotes adicionales.

## 14. Resultados que deben publicarse

### 14.1 Resultados agregados

- probabilidad de victoria en 90 minutos;
- probabilidad de prórroga;
- probabilidad de tanda;
- probabilidad de levantar el título;
- distribución de marcadores;
- goles, `xG`, tiros y posesión esperados;
- tarjetas, lesiones y sustituciones esperadas;
- contribución por fase y posición;
- intervalos de incertidumbre;
- sensibilidad a Top-N, minutos mínimos y coordinación.

### 14.2 Una final narrada

La transmisión mostrará una trayectoria elegida mediante una regla preregistrada, por ejemplo:

- mediana representativa;
- resultado modal;
- realización más cercana a los estadísticos agregados.

Nunca se elegirá manualmente “la más emocionante”. Debe publicarse su semilla y explicar que es una realización, no el resultado científico completo.

## 15. Auditoría de cada ejecución

Cada final genera:

- `run_id`;
- fecha de corte;
- hash de datos;
- commit del código;
- versión del modelo;
- configuración completa;
- semillas;
- alineaciones y banquillos;
- parámetros muestreados;
- event log inmutable;
- estados periódicos;
- resultado final;
- checks de integridad;
- etiqueta `exploratory` o `confirmatory`.

## 16. Criterio de afirmación científica

Hasta completar los gates, la formulación permitida es:

> “El sistema produce simulaciones exploratorias, calibradas y auditables bajo supuestos explícitos.”

Después de completar calibración, holdout y sensibilidad, podrá afirmarse:

> “Bajo el modelo, los datos y los supuestos preregistrados, se estima una distribución comparativa de resultados entre Synthetic XI y Real Best XI.”

No se afirmará que un equipo sintético “ganaría realmente” un partido físico.

## 17. Orden de implementación

1. cerrar suficiencia y calidad de selección;
2. congelar snapshot y perfiles;
3. completar taxonomía y state machine;
4. implementar reglas de competición;
5. implementar políticas tácticas y sustituciones;
6. integrar arbitraje, VAR, lesiones y tiempo añadido;
7. implementar prórroga y tanda;
8. calibrar distribuciones agregadas y condicionales;
9. ejecutar rolling-origin y holdout externo;
10. propagar incertidumbre anidada;
11. ejecutar sensibilidad y ablations;
12. habilitar comparación final;
13. generar replay representativo y paquete de auditoría.
