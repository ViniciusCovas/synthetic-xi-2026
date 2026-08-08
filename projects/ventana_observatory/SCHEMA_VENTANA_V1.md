# Esquema de registros — Ventana v1

El export del teléfono es **JSONL**: un objeto por línea. Cada sesión aporta una
cabecera y tantos registros de minuto como minutos observados. Un minuto sin su
cabecera es un error de validación: sin la calibración no hay forma de
interpretar ninguna de sus magnitudes.

## `ventana.session.v1` — cabecera

```json
{
  "schema": "ventana.session.v1",
  "engine": "ventana-engine-1.0.0",
  "session_id": "9f3a1c4b22d70e15",
  "t_start": "2026-08-08T09:12:44.031Z",
  "timezone": "America/Sao_Paulo",
  "utc_offset_minutes": -180,
  "device": {
    "user_agent": "...",
    "capture_width": 1280,
    "capture_height": 720,
    "capture_fps": 30
  },
  "analysis": { "width": 320, "height": 180 },
  "config": { "target_fps": 10, "fg_k_sigma": 3.5, "...": "..." },
  "calibration": {
    "sky":    { "x0": 0.05, "y0": 0.02, "x1": 0.95, "y1": 0.30 },
    "street": [ { "x": 0.02, "y": 0.62 }, { "x": 0.98, "y": 0.58 }, "..." ],
    "line":   { "a": { "x": 0.5, "y": 0.58 }, "b": { "x": 0.5, "y": 0.97 } },
    "facade": { "x0": 0.06, "y0": 0.30, "x1": 0.62, "y1": 0.56 }
  },
  "site_label": "ventana norte, 4º piso"
}
```

Toda la geometría está en **coordenadas normalizadas [0, 1]** sobre el fotograma,
de modo que sigue siendo válida aunque cambie la resolución de captura. El
polígono `street` necesita al menos tres vértices; `facade` puede ser `null`.

`config` guarda la configuración completa del motor tal como corrió, incluidos
los umbrales. Es lo que permite reinterpretar una sesión antigua sabiendo
exactamente con qué parámetros se midió.

## `ventana.minute.v1` — un minuto

```json
{
  "schema": "ventana.minute.v1",
  "engine": "ventana-engine-1.0.0",
  "session_id": "9f3a1c4b22d70e15",
  "t_start": "2026-08-08T09:13:00.104Z",
  "t_end":   "2026-08-08T09:14:00.219Z",
  "duration_s": 60.12,
  "partial": false,
  "frames": 597,
  "fps_mean": 9.93,

  "street": {
    "crossings_a": 7,
    "crossings_b": 5,
    "crossings_total": 12,
    "by_size": { "small": 3, "medium": 8, "large": 1 },
    "area_histogram": [3, 2, 4, 2, 1, 0, 0, 0, 0],
    "motion_energy_mean": 0.0142,
    "motion_energy_p95": 0.0910,
    "tracks_active_mean": 1.84
  },

  "sky": {
    "luminance_mean": 0.6213,
    "luminance_sd": 0.0104,
    "saturation_mean": 0.1877,
    "blueness_mean": 0.2140,
    "texture_mean": 0.0231,
    "rgb_mean": [0.5012, 0.6188, 0.7402],
    "hex": "#809ebc"
  },

  "facade": {
    "lit_fraction_mean": 0.0121,
    "lit_windows_mean": 4.30,
    "lit_windows_p95": 7.00
  },

  "exposure": { "clipped_high_frac": 0.0182, "clipped_low_frac": 0.0009 },

  "quality": {
    "night": false,
    "camera_shift": false,
    "frame_ms_p95": 47.2,
    "measurable_frames": 588
  }
}
```

### Campos y unidades

| Campo | Unidad | Notas |
| --- | --- | --- |
| `duration_s` | segundos | tiempo de reloj real del minuto, rara vez exactamente 60 |
| `frames` | recuento | fotogramas procesados |
| `fps_mean` | Hz | `frames / duration_s` |
| `crossings_a`, `crossings_b` | recuento | suman siempre `crossings_total` |
| `by_size` | recuento | suma siempre `crossings_total` |
| `area_histogram` | recuento | bordes en `DEFAULT_CONFIG.area_bins`, fracción de fotograma; suma `crossings_total` |
| `motion_energy_*` | fracción | píxeles en movimiento sobre el área de calle |
| `tracks_active_mean` | recuento | trayectorias vivas por fotograma |
| `luminance_mean` | 0–1 | luminancia relativa, Rec. 709 |
| `saturation_mean` | 0–1 | saturación HSV media |
| `blueness_mean` | −1…1 | `(B − R) / (B + R)`, robusto a la exposición |
| `texture_mean` | 0–1 | desviación típica de medias de bloques 8×8 en el cielo |
| `hex` | color | color medio del cielo; base del código de barras del día |
| `lit_fraction_mean` | fracción | píxeles de fachada por encima del umbral de encendido |
| `lit_windows_mean` | recuento | componentes conexas luminosas dentro de la fachada |
| `clipped_*_frac` | fracción | píxeles saturados en alto y en bajo del fotograma completo |
| `measurable_frames` | recuento | fotogramas fuera de calentamiento y de reinicio de fondo |

`sky` y `facade` pueden ser `null` cuando la región correspondiente no está
calibrada o no aportó ningún fotograma medible.

### Invariantes verificadas

`ventana/records.py` rechaza el registro si:

- `t_end` no es posterior a `t_start`;
- `crossings_a + crossings_b ≠ crossings_total`;
- el desglose por porte no suma `crossings_total`;
- falta alguna clase de porte;
- `luminance_mean` cae fuera de `[0, 1]`;
- un minuto declara un `session_id` sin cabecera correspondiente.

## `ventana.exhibits.v1` — paquete de resultados

Producido por `scripts/ventana/build_ventana_exhibits.py`, es lo único que el
tablero lee y lo único que una figura o un informe pueden citar. Contiene las
sesiones, los informes de compuertas, la cobertura por fecha, los perfiles
diurnos con sus intervalos, el contraste laborable/fin de semana, el índice de
dispersión, el código de barras del cielo y el techo de afirmación vigente —
junto a la semilla y el número de remuestreos con que se calculó todo.
