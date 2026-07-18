# Plan v0.5: modelo anual y validación pre-Mundial

## Objetivo

Construir dos modelos independientes:

1. **Modelo anual actual**: 18/07/2025 a 17/07/2026.
2. **Modelo pre-Mundial**: 11/06/2025 a 10/06/2026, congelado antes de la apertura de la Copa el 11/06/2026.

El snapshot exclusivo de la Copa permanece preservado en la rama `snapshot/world-cup-v0.4-2026-07-18`.

## Universo principal

Jugadores de las 48 selecciones participantes en la Copa de 2026. El rendimiento anual se calculará con sus partidos oficiales de clubes y selecciones.

Un universo global más amplio será una extensión secundaria y solo se presentará con una declaración explícita de las competiciones cubiertas.

## Once funciones

GK, RB, RCB, LCB, LB, DM, CM, AM, RW, LW y ST.

## Variables separadas

- Habilidad estimada cuando juega.
- Contribución acumulada durante la ventana.
- Disponibilidad.
- Incertidumbre.

## Elegibilidad principal

- 900 minutos para entrar al ranking.
- 1.800 minutos y 15 partidos para ser benchmark real principal.
- Función principal en al menos 60% de los minutos clasificables.
- Cobertura mínima de 80% de los minutos conocidos.

Sensibilidad: 900, 1.500 y 2.000 minutos; Top 10, Top 20 y Top 30; semivida temporal de 90, 180 y 365 días.

## Fases

### 1. Auditoría de cobertura

- Obtener la lista completa de jugadores del Mundial.
- Identificar equipos, ligas y temporadas relevantes.
- Verificar cobertura de estadísticas por jugador y por partido.
- Estimar el número de llamadas y dividir la extracción en lotes seguros.
- Generar `annual_coverage_audit.json` y un informe en español.

No se construirá ningún ranking anual antes de aprobar esta auditoría.

### 2. Data lake anual

- Recoger partidos oficiales dentro de la ventana exacta.
- Deduplicar partidos y jugadores.
- Registrar hashes, timestamps y procedencia.
- Guardar respuestas brutas como artefactos privados.
- Excluir amistosos del análisis principal.

### 3. Funciones y métricas

- Inferir once funciones específicas.
- Ajustar por competición, adversario, posesión y recencia.
- Separar habilidad, contribución y disponibilidad.
- Aplicar retracción por muestra e intervalos de incertidumbre.

### 4. Avatares y benchmarks

- Crear Top 20 por función.
- Identificar mejor habilidad media, benchmark conservador y mayor contribución anual.
- Optimizar el Real Best XI sin duplicar jugadores.
- Crear Synthetic XI con once avatares funcionales.

### 5. Validación en la Copa

- Comparar el modelo pre-Mundial con el rendimiento observado en la Copa.
- Medir correlación, error, calibración y estabilidad.
- Analizar lesiones, cambios de posición y disponibilidad.
- Identificar jugadores por encima y por debajo de la expectativa.

### 6. Simulación

- Construir escenarios pareados por función.
- Ejecutar Monte Carlo con semillas registradas.
- Comparar nivel, piso, techo, consistencia y fragilidad.
- Simular Synthetic XI contra Real Best XI.

### 7. Productos

- Paper 1: avatar anual contra mejor jugador real.
- Paper 2: generalización pre-Mundial hacia la Copa.
- Dashboard público.
- Contenido viral en español con resultados derivados.

## Regla científica

Nunca se afirmará “mejor del mundo” sin declarar el universo observado, las competiciones cubiertas, la ventana temporal y los criterios de elegibilidad.
