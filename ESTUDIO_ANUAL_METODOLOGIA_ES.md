# Estudio anual 2025–2026: metodología operativa

## 1. Preguntas distintas

El proyecto conserva tres módulos independientes:

1. **Modelo anual actual** — rendimiento entre el 18 de julio de 2025 y el 17 de julio de 2026.
2. **Modelo pre-Mundial** — rendimiento entre el 11 de junio de 2025 y el 10 de junio de 2026, congelado antes del Mundial.
3. **Modelo Mundial** — rendimiento observado exclusivamente en la Copa de 2026.

El modelo pre-Mundial se utilizará para validación fuera de muestra. Ningún dato de la Copa podrá intervenir en su construcción.

## 2. Universo

El estudio principal incluye a los jugadores convocados por las 48 selecciones del Mundial de 2026. La afirmación válida será:

> Los mejores jugadores por función entre los participantes del Mundial, según el rendimiento observado en la ventana definida y dentro del universo de competiciones auditadas.

No se afirmará que el universo representa a todos los futbolistas profesionales del mundo.

## 3. Inclusión de partidos

Análisis principal:

- Partidos oficiales de clubes.
- Copas nacionales con estadísticas individuales disponibles.
- Competiciones continentales oficiales.
- Partidos oficiales de selecciones.
- Solo fixtures terminados (`FT`, `AET`, `PEN`).

Exclusiones principales:

- Amistosos.
- Competiciones juveniles.
- Partidos sin estadísticas individuales.
- Partidos fuera de las ventanas exactas.

Los amistosos podrán incorporarse únicamente como análisis de sensibilidad.

## 4. Cobertura y elegibilidad

### Entrada al ranking

- Al menos 900 minutos en la ventana exacta.
- Al menos 80% de los minutos observados cubiertos por estadísticas detalladas.
- Función estable o resoluble en al menos 60% de los minutos clasificables.

### Benchmark real principal

- Al menos 1.800 minutos.
- Al menos 15 partidos con participación.
- Al menos 80% de cobertura detallada.
- Incertidumbre suficientemente baja para estimar un límite inferior conservador.

Se repetirán los análisis con umbrales de 900, 1.500 y 2.000 minutos.

## 5. Tres conceptos separados

### Habilidad

Nivel estimado del jugador cuando participa, ajustado por función, competición, adversario, equipo, posesión e incertidumbre.

### Contribución acumulada

Valor total entregado durante la ventana, incorporando minutos y continuidad.

### Disponibilidad

Partidos, minutos, lesiones y periodos sin participación.

Una lesión puede reducir la contribución y la disponibilidad sin implicar que la habilidad técnica observada sea baja.

## 6. Funciones

El objetivo es resolver once funciones:

- GK
- RB
- RCB
- LCB
- LB
- DM
- CM
- AM
- RW
- LW
- ST

La asignación utilizará evidencia combinada de:

- posición general del proveedor;
- titularidad o suplencia;
- formación;
- `grid` de la alineación;
- posición modal del jugador;
- estabilidad de lado y línea a lo largo de la ventana.

Las reglas de lateralidad se validarán empíricamente antes de su uso final. Ningún jugador será forzado a una función específica cuando la evidencia sea ambigua.

## 7. Métricas

Las métricas se calcularán por partido, por 90 minutos y como tasas de éxito. Entre otras:

- finalización;
- creación;
- progresión;
- pases y pases clave;
- duelos;
- regate;
- recuperación e intercepción;
- disciplina;
- portería.

`passes.accuracy` se tratará como volumen de pases acertados cuando la auditoría de esquema lo confirme. La precisión será:

\[
\text{Precisión de pase}=\frac{\sum \text{pases acertados}}{\sum \text{pases intentados}}
\]

No se promediarán porcentajes partido a partido.

## 8. Ajustes

- Estandarización dentro de función.
- Winsorización de extremos.
- Ajuste por posesión para acciones defensivas.
- Efectos de competición y equipo.
- Fuerza del adversario.
- Decaimiento temporal con media vida principal de 180 días.
- Sensibilidad con 90 y 365 días.
- Retracción jerárquica para muestras pequeñas.

## 9. Selección de jugadores y avatares

Para cada función se producirán tres líderes:

1. mayor habilidad posterior;
2. mejor límite inferior conservador;
3. mayor contribución acumulada.

El benchmark del experimento será el segundo.

El avatar principal será el centroide robusto de los Top 20. Se repetirán los cálculos con Top 10 y Top 30. Cada jugador tendrá el mismo peso en la identidad del avatar; la minutación afectará la incertidumbre de su estimación, no su peso nominal dentro del centroide.

## 10. Validación

- Modelo pre-Mundial construido sin datos de la Copa.
- Copa de 2026 como prueba fuera de muestra.
- Validación cruzada por partido dentro del periodo de entrenamiento.
- Intervalos de incertidumbre y bootstrap.
- Análisis de sensibilidad por cobertura, competición y umbral de minutos.
- Análisis específico de Jordan y Uzbekistan por sus limitaciones de cobertura detectadas.

## 11. Bloqueos metodológicos

No se publicarán rankings mientras falte cualquiera de los siguientes elementos:

- extracción estabilizada;
- cobertura exacta por jugador;
- funciones posicionales validadas;
- definición de pesos y direcciones registrada;
- análisis de sensibilidad básico;
- separación comprobada entre entrenamiento pre-Mundial y prueba Mundial.

Los archivos parciales sirven para ingeniería y auditoría, no para conclusiones públicas.
