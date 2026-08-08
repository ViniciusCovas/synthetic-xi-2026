# Protocolo Ventana v1 — pre-registro

Documento congelado antes de observar el primer minuto. Cualquier cambio en los
umbrales, en las magnitudes o en el techo de afirmación exige una enmienda
fechada y numerada, no una edición silenciosa de este fichero.

## 1. Objeto

Caracterizar el ritmo diario de un punto fijo de observación urbana —una
ventana— mediante tres magnitudes medidas por visión por computadora en el
propio dispositivo:

1. **Flujo de calle**: objetos que atraviesan una línea virtual, con sentido y
   con clase de porte derivada del área en píxeles.
2. **Estado de cielo**: luminancia, saturación, índice de azulidad y textura
   sobre una región fija de cielo.
3. **Ocupación aparente de fachada**: fracción de píxeles luminosos y número de
   ventanas encendidas sobre una región fija de edificio.

## 2. Instrumento

- Un teléfono fijo, alimentado a la red, con la cámara trasera contra el vidrio.
- Resolución de análisis congelada en **320 × 180**. Las áreas se miden en
  píxeles de esa retícula: cambiarla rompe la comparabilidad entre sesiones y
  obliga a declarar una versión nueva de motor.
- Frecuencia de análisis objetivo: **10 fotogramas por segundo**, degradable por
  temperatura del aparato.
- Motor: `projects/ventana_observatory/capture/engine.js`, versión declarada en
  cada registro bajo la clave `engine`.

## 3. Unidad de observación

El **minuto de reloj**. Cada minuto produce exactamente un registro
`ventana.minute.v1`. No existe unidad menor: los fotogramas individuales no se
conservan ni se pueden reconstruir.

## 4. Definiciones operativas

- **Cruce**: una trayectoria seguida durante al menos 3 fotogramas cuyo centroide
  cambia de lado respecto del segmento calibrado, con la proyección del punto
  dentro del segmento y no de su prolongación. Cada trayectoria se cuenta **una
  sola vez**; un objeto que va y vuelve aporta un cruce, no dos.
- **Sentido**: etiqueta `a` o `b` según el lado de llegada. La correspondencia
  entre `a`/`b` y las direcciones del mundo depende del trazado de la línea y se
  documenta en la etiqueta del sitio, no se infiere.
- **Porte**: clase derivada del área máxima de la trayectoria, en fracción de
  fotograma: `small` ≤ 0,004, `medium` ≤ 0,02, `large` por encima. Es un proxy
  de tamaño aparente, **no** una clasificación de vehículo ni de persona. Cada
  minuto exporta además el histograma de áreas crudas para permitir recalibrar
  los umbrales sin volver a observar.
- **Noche**: más de la mitad de los fotogramas del minuto con luminancia media
  de cielo por debajo de 0,16.
- **Desplazamiento de cámara**: fracción de primer plano superior a 0,45 durante
  8 fotogramas consecutivos. Dispara el reinicio del modelo de fondo y marca el
  minuto.

## 5. Compuertas de calidad

Se aplican a cada minuto antes de cualquier análisis. Un minuto que falla
cualquiera queda fuera del análisis principal y **se cuenta e informa**; no se
borra.

| Compuerta | Condición para pasar |
| --- | --- |
| `complete_minute` | registro no parcial y duración entre 55 y 65 s |
| `frame_rate` | fotogramas por segundo medios ≥ 4,0 |
| `measurable_coverage` | fotogramas medibles / fotogramas ≥ 0,50 |
| `camera_stable` | sin desplazamiento de cámara en el minuto |
| `exposure` | fracción de píxeles saturados en alto ≤ 0,25 |

Compuerta de sesión: al menos **60 minutos válidos** y una fracción de minutos
válidos ≥ **0,80**. Una sesión que no la supera se conserva y se informa, pero no
entra en los perfiles publicados.

Los umbrales viven en `ventana/gates.py::GATE_THRESHOLDS` y son la única fuente
de verdad; este documento los transcribe.

## 6. Análisis principal

- Perfil diurno por **hora local** de cada magnitud, sobre minutos válidos.
- Media por hora con intervalo de confianza del 95% mediante **bootstrap de
  percentiles**, 10 000 remuestreos, semilla base `20260808` y semilla derivada
  `base + hora` para cada celda. Añadir horas nuevas no altera los intervalos ya
  publicados de las demás.
- Contraste laborable frente a fin de semana, declarado **comparable** sólo si
  ambos grupos alcanzan 30 minutos válidos.
- Índice de dispersión de los cruces por minuto (varianza sobre media) como
  descriptor del régimen de llegadas.

Una hora sin observación válida se informa **vacía**, nunca como cero. Un cero
significa «se observó y no pasó nada»; un vacío significa «no se observó».

## 7. Techo de afirmación

Sube únicamente con la cobertura acumulada y se publica junto a cada resultado:

| Cobertura | Afirmación permitida |
| --- | --- |
| < 600 minutos válidos | exploratorio; ninguna afirmación sobre el ritmo del sitio |
| < 7 fechas locales | descriptivo de las fechas observadas; sin afirmación semanal |
| < 28 fechas locales | perfil diurno con contraste laborable/fin de semana declarado |
| ≥ 28 fechas locales | perfil diurno y semanal estable; estacionalidad aún no evaluable |

Ninguna cobertura autoriza afirmaciones sobre **identidad** de los objetos
contados, sobre causas del comportamiento observado, ni sobre otros sitios
distintos del observado.

## 8. Reproducibilidad

- Todo intervalo procede de una semilla declarada en el propio paquete de
  resultados; dos ejecuciones con los mismos datos y la misma semilla producen
  cifras idénticas.
- El tablero no recalcula nada: sólo dibuja lo que el paquete contiene.
- El generador sintético `scripts/ventana/simulate_session.py` reproduce la
  forma exacta del export para ejercitar el análisis sin observación. Sus
  ficheros llevan la etiqueta `SINTÉTICO — no es observación` y no pueden
  mezclarse con datos reales.

## 9. Límites declarados

1. El sistema detecta **movimiento sobre fondo estable**, no objetos. Sombras en
   marcha, lluvia intensa, limpiaparabrisas y ramas al viento producen
   trayectorias legítimas para el motor y espurias para la interpretación.
2. Un objeto detenido sobre la línea acaba absorbido por el modelo de fondo y
   deja de contarse. El sistema mide **tránsito**, no ocupación.
3. La oclusión mutua funde dos objetos en una trayectoria: en horas de máximo
   flujo el recuento subestima por construcción, y esa subestimación crece con
   el propio flujo.
4. De noche el objeto medido son los faros, no el vehículo; las áreas nocturnas
   y diurnas no son comparables entre sí y por eso el indicador `night` viaja en
   cada minuto.
5. La cámara aplica exposición y balance de blancos automáticos que el navegador
   no siempre permite fijar. La luminancia de cielo es una magnitud **relativa
   dentro de una sesión**, no una medida fotométrica absoluta.
6. El desfase horario se toma del declarado por el aparato al abrir la sesión.
   Una sesión que atraviesa un cambio de horario de verano conserva el desfase
   inicial; el hecho se declara aquí en vez de corregirse en silencio.
7. La región de fachada mide **píxeles luminosos**, no viviendas: una farola
   dentro del rectángulo cuenta como ventana encendida durante toda la noche.

## 10. Ética y privacidad

La observación se dirige a la vía pública desde una ventana privada. A 320 × 180
no hay identificación posible de personas, matrículas ni rostros, y el motor no
implementa ningún reconocimiento. No se graba ni se transmite vídeo: la única
salida es una fila numérica por minuto, y sale del dispositivo únicamente por
acción explícita de la persona que observa.
