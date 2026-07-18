# Simulador de partido Synthetic XI — metodología exploratoria v0.1

## Objetivo

Construir un partido casi real en el sentido estadístico y narrativo: 90 minutos,
posesiones, progresión territorial, actores por función, pérdidas, disparos, xG,
paradas y goles. No se pretende reconstruir la física continua ni el tracking de
los veintidós jugadores.

## Estado científico

La versión v0.1 es exploratoria. Sirve para validar el motor mientras continúa la
extracción anual. No autoriza una afirmación final sobre qué equipo o jugador es
mejor.

## Equipos

El partido utiliza una estructura simétrica de once plazas:

- GK
- CB1 y CB2
- FB1 y FB2
- DM
- CM
- AM
- W1 y W2
- ST

Se mantienen plazas laterales neutrales porque la orientación izquierda/derecha
del grid del proveedor aún debe validarse empíricamente.

### Real Best XI exploratorio

Se selecciona un jugador único para cada plaza mediante el mayor score
conservador disponible dentro del grupo funcional. El score conservador resta una
penalización de incertidumbre dependiente de los minutos.

### Synthetic XI exploratorio

Cada avatar es una media robusta de los Top 20 provisionales de su grupo. Se
recorta el 10% de cada cola cuando la muestra lo permite. La incertidumbre del
avatar disminuye con el tamaño de la muestra, pero nunca llega a cero.

## Dimensiones latentes

Los perfiles contienen ocho dimensiones normalizadas dentro del universo parcial:

1. construcción;
2. progresión;
3. creación;
4. finalización;
5. defensa;
6. duelos;
7. retención;
8. portería.

Las métricas por 90 y las tasas de éxito se transforman con una escala robusta
basada en mediana e IQR. La precisión de pase se calcula como pases acertados
divididos entre pases intentados.

## Resolución provisional de funciones

- GK: posición de plantilla o proveedor de portero.
- CB/FB: defensa central o exterior según grid y evidencia de alineación.
- DM/CM/AM: balance entre señal defensiva y señal creativa/progresiva.
- W/ST: balance entre progresión/creación y finalización.

La resolución definitiva exigirá al menos 60% de estabilidad funcional y la
validación de la orientación lateral.

## Motor de partido

Cada simulación genera aproximadamente 103 posesiones. Cada posesión:

1. selecciona al equipo con balón según construcción, retención, duelos y tempo;
2. selecciona un actor compatible con la zona;
3. elige una acción: pase seguro, pase vertical, conducción, regate o disparo;
4. compara la capacidad del actor con defensa, duelos y presión del rival;
5. avanza entre construcción, medio, último tercio y área;
6. produce un disparo o termina en pérdida.

La probabilidad de gol depende de zona, finalización, creación y capacidad del
portero. La habilidad de cada jugador se vuelve a muestrear por partido para
representar forma e incertidumbre.

## Monte Carlo

La ejecución automática produce 10.000 partidos y reporta:

- victoria, empate y derrota;
- goles medios;
- xG medio del modelo;
- marcadores más frecuentes;
- un partido representativo con línea temporal.

## Próximas calibraciones

1. Ajustar posesiones, disparos y goles contra distribuciones empíricas del Mundial.
2. Validar la orientación izquierda/derecha del grid.
3. Resolver las once funciones definitivas.
4. Incorporar fuerza del rival, competición y recencia.
5. Añadir sustituciones, fatiga, tarjetas y cambios tácticos.
6. Backtesting fuera de muestra con partidos reales.
