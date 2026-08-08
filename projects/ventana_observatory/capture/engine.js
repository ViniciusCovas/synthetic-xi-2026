/*
 * VENTANA — motor de visión por computadora en el dispositivo.
 *
 * Todo el procesamiento ocurre en el teléfono. Ningún fotograma sale del
 * aparato: la salida es exclusivamente un registro numérico por minuto.
 *
 * Tres capas de medición sobre la misma escena:
 *   calle   -> sustracción de fondo + componentes conexas + seguimiento + línea virtual
 *   cielo   -> estadísticas de color y textura sobre una región fija
 *   fachada -> fracción de píxeles luminosos y conteo de ventanas encendidas
 *
 * Sin dependencias externas. ES module puro.
 */

export const ENGINE_VERSION = 'ventana-engine-1.0.0';

/* Resolución de análisis. Fija por protocolo: cambiarla invalida la
 * comparabilidad entre sesiones porque las áreas se miden en píxeles. */
export const ANALYSIS_WIDTH = 320;
export const ANALYSIS_HEIGHT = 180;

export const DEFAULT_CONFIG = Object.freeze({
  target_fps: 10,
  /* Modelo de fondo: tasa de olvido para píxeles clasificados como fondo y,
   * mucho más lenta, para los clasificados como primer plano. La segunda evita
   * que un coche detenido en el semáforo se absorba en el fondo en segundos. */
  bg_alpha_background: 0.02,
  bg_alpha_foreground: 0.0015,
  /* Umbral de primer plano = max(tau_min, k * sigma_ruido). */
  fg_k_sigma: 3.5,
  fg_tau_min: 0.045,
  /* Área mínima de una componente conexa para considerarse objeto, en
   * fracción del fotograma de análisis. */
  blob_min_area_frac: 0.0006,
  /* Seguimiento. */
  track_max_match_dist: 26,
  track_max_missed: 6,
  track_min_age_to_count: 3,
  /* Clases de porte, en fracción de área del fotograma. Se declaran aquí pero
   * cada minuto exporta además el histograma de áreas crudas, de modo que los
   * umbrales puedan recalibrarse fuera de línea sin volver a filmar. */
  size_small_max_frac: 0.004,
  size_medium_max_frac: 0.02,
  /* Luminancia media por debajo de la cual la escena se marca como nocturna. */
  night_luminance: 0.16,
  /* Fachada: luminancia por encima de la cual un píxel cuenta como encendido. */
  facade_lit_luminance: 0.62,
  facade_min_window_area: 4,
  /* Detección de desplazamiento de cámara: si la fracción de primer plano
   * supera este valor durante tantos fotogramas seguidos, se asume que alguien
   * movió el teléfono. */
  scene_shift_fg_frac: 0.45,
  scene_shift_frames: 8,
  /* Bordes del histograma de áreas, en fracción de fotograma. */
  area_bins: [0.0006, 0.0012, 0.0025, 0.005, 0.01, 0.02, 0.04, 0.08],
});

/* ------------------------------------------------------------------ */
/* Utilidades geométricas                                              */
/* ------------------------------------------------------------------ */

/** Máscara binaria de un polígono en coordenadas normalizadas [0,1]. */
export function polygonMask(points, w, h) {
  const mask = new Uint8Array(w * h);
  if (!points || points.length < 3) {
    mask.fill(1);
    return mask;
  }
  const xs = points.map((p) => p.x * w);
  const ys = points.map((p) => p.y * h);
  for (let y = 0; y < h; y += 1) {
    const py = y + 0.5;
    for (let x = 0; x < w; x += 1) {
      const px = x + 0.5;
      let inside = false;
      for (let i = 0, j = points.length - 1; i < points.length; j = i, i += 1) {
        const yi = ys[i];
        const yj = ys[j];
        if (yi > py !== yj > py) {
          const cross = xs[i] + ((py - yi) / (yj - yi)) * (xs[j] - xs[i]);
          if (px < cross) inside = !inside;
        }
      }
      mask[y * w + x] = inside ? 1 : 0;
    }
  }
  return mask;
}

/** Máscara binaria de un rectángulo normalizado {x0,y0,x1,y1}. */
export function rectMask(rect, w, h) {
  const mask = new Uint8Array(w * h);
  if (!rect) return mask;
  const x0 = Math.max(0, Math.floor(Math.min(rect.x0, rect.x1) * w));
  const x1 = Math.min(w, Math.ceil(Math.max(rect.x0, rect.x1) * w));
  const y0 = Math.max(0, Math.floor(Math.min(rect.y0, rect.y1) * h));
  const y1 = Math.min(h, Math.ceil(Math.max(rect.y0, rect.y1) * h));
  for (let y = y0; y < y1; y += 1) {
    mask.fill(1, y * w + x0, y * w + x1);
  }
  return mask;
}

/** Lado de un punto respecto de la recta que pasa por a y b. */
function sideOfLine(a, b, px, py) {
  return (b.x - a.x) * (py - a.y) - (b.y - a.y) * (px - a.x);
}

/** Parámetro de la proyección de un punto sobre el segmento a-b. */
function projectionParam(a, b, px, py) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const den = dx * dx + dy * dy;
  if (den <= 1e-9) return -1;
  return ((px - a.x) * dx + (py - a.y) * dy) / den;
}

/* ------------------------------------------------------------------ */
/* Morfología binaria (elemento estructurante cuadrado 3x3, separable)  */
/* ------------------------------------------------------------------ */

function morphPass(src, dst, w, h, isDilate) {
  const tmp = new Uint8Array(w * h);
  const pick = isDilate ? 1 : 0;
  for (let y = 0; y < h; y += 1) {
    const row = y * w;
    for (let x = 0; x < w; x += 1) {
      let v = src[row + x];
      if (x > 0 && src[row + x - 1] === pick) v = pick;
      if (x < w - 1 && src[row + x + 1] === pick) v = pick;
      tmp[row + x] = v;
    }
  }
  for (let y = 0; y < h; y += 1) {
    const row = y * w;
    for (let x = 0; x < w; x += 1) {
      let v = tmp[row + x];
      if (y > 0 && tmp[row - w + x] === pick) v = pick;
      if (y < h - 1 && tmp[row + w + x] === pick) v = pick;
      dst[row + x] = v;
    }
  }
}

/** Apertura morfológica: erosión seguida de dilatación. Elimina ruido sal. */
export function openMask(mask, w, h) {
  const a = new Uint8Array(w * h);
  const b = new Uint8Array(w * h);
  morphPass(mask, a, w, h, false);
  morphPass(a, b, w, h, true);
  return b;
}

/* ------------------------------------------------------------------ */
/* Componentes conexas (dos pasadas con union-find)                     */
/* ------------------------------------------------------------------ */

/**
 * Etiqueta las componentes conexas de 8 vecinos de `mask`, restringida a `roi`.
 * Devuelve la lista de blobs con centroide, área y caja envolvente.
 */
export function connectedComponents(mask, roi, w, h, minArea) {
  const labels = new Int32Array(w * h);
  const parent = [0];
  const find = (x) => {
    let r = x;
    while (parent[r] !== r) r = parent[r];
    while (parent[x] !== r) {
      const next = parent[x];
      parent[x] = r;
      x = next;
    }
    return r;
  };
  const union = (a, b) => {
    const ra = find(a);
    const rb = find(b);
    if (ra !== rb) parent[Math.max(ra, rb)] = Math.min(ra, rb);
  };

  let next = 1;
  for (let y = 0; y < h; y += 1) {
    for (let x = 0; x < w; x += 1) {
      const i = y * w + x;
      if (!mask[i] || (roi && !roi[i])) continue;
      let best = 0;
      for (let dy = -1; dy <= 0; dy += 1) {
        for (let dx = -1; dx <= 1; dx += 1) {
          if (dy === 0 && dx >= 0) continue;
          const ny = y + dy;
          const nx = x + dx;
          if (ny < 0 || nx < 0 || nx >= w) continue;
          const l = labels[ny * w + nx];
          if (!l) continue;
          if (!best) best = l;
          else union(best, l);
        }
      }
      if (!best) {
        best = next;
        parent[next] = next;
        next += 1;
      }
      labels[i] = best;
    }
  }

  const stats = new Map();
  for (let y = 0; y < h; y += 1) {
    for (let x = 0; x < w; x += 1) {
      const l = labels[y * w + x];
      if (!l) continue;
      const root = find(l);
      let s = stats.get(root);
      if (!s) {
        s = { area: 0, sx: 0, sy: 0, x0: x, x1: x, y0: y, y1: y };
        stats.set(root, s);
      }
      s.area += 1;
      s.sx += x;
      s.sy += y;
      if (x < s.x0) s.x0 = x;
      if (x > s.x1) s.x1 = x;
      if (y < s.y0) s.y0 = y;
      if (y > s.y1) s.y1 = y;
    }
  }

  const blobs = [];
  for (const s of stats.values()) {
    if (s.area < minArea) continue;
    blobs.push({
      area: s.area,
      x: s.sx / s.area,
      y: s.sy / s.area,
      w: s.x1 - s.x0 + 1,
      h: s.y1 - s.y0 + 1,
    });
  }
  return blobs;
}

/* ------------------------------------------------------------------ */
/* Seguimiento por vecino más cercano                                   */
/* ------------------------------------------------------------------ */

export class Tracker {
  constructor(config) {
    this.config = config;
    this.tracks = [];
    this.nextId = 1;
  }

  /**
   * Asocia los blobs del fotograma actual a las trayectorias vivas.
   * Asociación voraz por distancia creciente: suficiente para una escena de
   * calle vista desde arriba, donde los objetos rara vez se cruzan a la misma
   * profundidad, y no introduce el coste de una asignación húngara.
   */
  update(blobs) {
    const maxDist = this.config.track_max_match_dist;
    const pairs = [];
    for (let t = 0; t < this.tracks.length; t += 1) {
      for (let b = 0; b < blobs.length; b += 1) {
        const dx = this.tracks[t].x - blobs[b].x;
        const dy = this.tracks[t].y - blobs[b].y;
        const d = Math.hypot(dx, dy);
        if (d <= maxDist) pairs.push({ d, t, b });
      }
    }
    pairs.sort((p, q) => p.d - q.d);

    const usedTrack = new Set();
    const usedBlob = new Set();
    const events = [];
    for (const pair of pairs) {
      if (usedTrack.has(pair.t) || usedBlob.has(pair.b)) continue;
      usedTrack.add(pair.t);
      usedBlob.add(pair.b);
      const track = this.tracks[pair.t];
      const blob = blobs[pair.b];
      track.px = track.x;
      track.py = track.y;
      track.vx = 0.6 * track.vx + 0.4 * (blob.x - track.x);
      track.vy = 0.6 * track.vy + 0.4 * (blob.y - track.y);
      track.x = blob.x;
      track.y = blob.y;
      track.area = blob.area;
      if (blob.area > track.maxArea) track.maxArea = blob.area;
      track.age += 1;
      track.missed = 0;
      track.moved = true;
    }

    for (let b = 0; b < blobs.length; b += 1) {
      if (usedBlob.has(b)) continue;
      const blob = blobs[b];
      this.tracks.push({
        id: this.nextId,
        x: blob.x,
        y: blob.y,
        px: blob.x,
        py: blob.y,
        vx: 0,
        vy: 0,
        area: blob.area,
        maxArea: blob.area,
        age: 1,
        missed: 0,
        counted: false,
        moved: false,
      });
      this.nextId += 1;
    }

    for (let t = 0; t < this.tracks.length; t += 1) {
      if (!usedTrack.has(t)) {
        const track = this.tracks[t];
        track.missed += 1;
        track.moved = false;
      }
    }
    this.tracks = this.tracks.filter((t) => t.missed <= this.config.track_max_missed);
    return events;
  }

  /**
   * Cuenta los cruces de la línea virtual producidos en este fotograma.
   * Una trayectoria sólo puede contarse una vez, debe tener edad suficiente y
   * el cruce debe caer dentro del segmento dibujado, no en su prolongación.
   */
  crossings(line) {
    if (!line) return [];
    const out = [];
    for (const track of this.tracks) {
      if (track.counted || !track.moved) continue;
      if (track.age < this.config.track_min_age_to_count) continue;
      const prev = sideOfLine(line.a, line.b, track.px, track.py);
      const cur = sideOfLine(line.a, line.b, track.x, track.y);
      if (prev === 0 || cur === 0) continue;
      if (prev > 0 === cur > 0) continue;
      const t = projectionParam(line.a, line.b, track.x, track.y);
      if (t < 0 || t > 1) continue;
      track.counted = true;
      out.push({ id: track.id, direction: cur > 0 ? 'b' : 'a', area: track.maxArea });
    }
    return out;
  }
}

/* ------------------------------------------------------------------ */
/* Acumulador de un minuto                                              */
/* ------------------------------------------------------------------ */

class MinuteAccumulator {
  constructor(config) {
    this.config = config;
    this.reset(new Date());
  }

  reset(now) {
    this.tStart = now;
    this.frames = 0;
    this.crossA = 0;
    this.crossB = 0;
    this.bySize = { small: 0, medium: 0, large: 0 };
    this.areaHist = new Array(this.config.area_bins.length + 1).fill(0);
    this.motion = [];
    this.tracksActive = [];
    this.sky = { lum: [], sat: [], blue: [], texture: [], r: 0, g: 0, b: 0, n: 0 };
    this.facadeLit = [];
    this.facadeWindows = [];
    this.clipHi = [];
    this.clipLo = [];
    this.nightFrames = 0;
    this.shiftFrames = 0;
    this.frameMs = [];
  }

  sizeClass(areaFrac) {
    if (areaFrac <= this.config.size_small_max_frac) return 'small';
    if (areaFrac <= this.config.size_medium_max_frac) return 'medium';
    return 'large';
  }

  addCrossing(cross, frameArea) {
    if (cross.direction === 'a') this.crossA += 1;
    else this.crossB += 1;
    const frac = cross.area / frameArea;
    this.bySize[this.sizeClass(frac)] += 1;
    const bins = this.config.area_bins;
    let idx = bins.length;
    for (let i = 0; i < bins.length; i += 1) {
      if (frac <= bins[i]) {
        idx = i;
        break;
      }
    }
    this.areaHist[idx] += 1;
  }
}

function mean(xs) {
  if (!xs.length) return null;
  let s = 0;
  for (const x of xs) s += x;
  return s / xs.length;
}

function stdev(xs) {
  if (xs.length < 2) return null;
  const m = mean(xs);
  let s = 0;
  for (const x of xs) s += (x - m) * (x - m);
  return Math.sqrt(s / (xs.length - 1));
}

function quantile(xs, q) {
  if (!xs.length) return null;
  const sorted = [...xs].sort((a, b) => a - b);
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  if (lo === hi) return sorted[lo];
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

function round(x, digits) {
  if (x === null || x === undefined || Number.isNaN(x)) return null;
  const f = 10 ** digits;
  return Math.round(x * f) / f;
}

function hex(r, g, b) {
  const c = (v) => Math.max(0, Math.min(255, Math.round(v * 255))).toString(16).padStart(2, '0');
  return `#${c(r)}${c(g)}${c(b)}`;
}

/* ------------------------------------------------------------------ */
/* Motor                                                                */
/* ------------------------------------------------------------------ */

export class VentanaEngine {
  /**
   * @param {object} options
   * @param {object} options.calibration  geometría normalizada de las regiones
   * @param {object} [options.config]     anulaciones del protocolo
   * @param {function} [options.onMinute] recibe cada registro de minuto
   * @param {function} [options.onFrame]  recibe el estado en vivo por fotograma
   */
  constructor({ calibration, config = {}, onMinute = null, onFrame = null }) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.calibration = calibration;
    this.onMinute = onMinute;
    this.onFrame = onFrame;

    this.w = ANALYSIS_WIDTH;
    this.h = ANALYSIS_HEIGHT;
    this.n = this.w * this.h;
    this.frameArea = this.n;

    this.gray = new Float32Array(this.n);
    this.bg = null;
    this.fg = new Uint8Array(this.n);
    this.sigma = 0.02;

    this.streetMask = polygonMask(calibration.street, this.w, this.h);
    this.skyMask = rectMask(calibration.sky, this.w, this.h);
    this.facadeMask = calibration.facade ? rectMask(calibration.facade, this.w, this.h) : null;
    this.line = calibration.line
      ? {
          a: { x: calibration.line.a.x * this.w, y: calibration.line.a.y * this.h },
          b: { x: calibration.line.b.x * this.w, y: calibration.line.b.y * this.h },
        }
      : null;

    this.streetArea = this.streetMask.reduce((a, b) => a + b, 0) || this.n;
    this.skyArea = this.skyMask.reduce((a, b) => a + b, 0);
    this.facadeArea = this.facadeMask ? this.facadeMask.reduce((a, b) => a + b, 0) : 0;

    this.tracker = new Tracker(this.config);
    this.acc = new MinuteAccumulator(this.config);
    /* El minuto en curso se ancla al primer fotograma procesado, no al momento
     * de construir el motor: entre ambos puede pasar un tiempo arbitrario
     * mientras el usuario concede permisos y la cámara arranca. */
    this.started = false;
    this.shiftRun = 0;
    this.pendingShift = false;
    this.warmupFrames = 0;
  }

  /**
   * Procesa un fotograma ya reducido a la resolución de análisis.
   * @param {ImageData} imageData  RGBA de ANALYSIS_WIDTH x ANALYSIS_HEIGHT
   * @param {Date} now
   * @param {number} frameMs  tiempo de cómputo del fotograma anterior
   */
  processFrame(imageData, now = new Date(), frameMs = 0) {
    if (!this.started) {
      this.acc.reset(now);
      this.started = true;
    }
    const data = imageData.data;
    const { gray } = this;

    /* Luminancia y estadísticas de color en una sola pasada. */
    let skyR = 0;
    let skyG = 0;
    let skyB = 0;
    let skySat = 0;
    let skyLum = 0;
    let clipHi = 0;
    let clipLo = 0;
    let facadeLit = 0;
    const facadeMaskOut = this.facadeMask ? new Uint8Array(this.n) : null;

    for (let i = 0, p = 0; i < this.n; i += 1, p += 4) {
      const r = data[p] / 255;
      const g = data[p + 1] / 255;
      const b = data[p + 2] / 255;
      const y = 0.2126 * r + 0.7152 * g + 0.0722 * b;
      gray[i] = y;
      if (y > 0.98) clipHi += 1;
      else if (y < 0.02) clipLo += 1;
      if (this.skyMask[i]) {
        skyR += r;
        skyG += g;
        skyB += b;
        skyLum += y;
        const mx = Math.max(r, g, b);
        const mn = Math.min(r, g, b);
        skySat += mx > 0 ? (mx - mn) / mx : 0;
      }
      if (facadeMaskOut && this.facadeMask[i] && y >= this.config.facade_lit_luminance) {
        facadeMaskOut[i] = 1;
        facadeLit += 1;
      }
    }

    const acc = this.acc;
    acc.frames += 1;
    acc.frameMs.push(frameMs);
    acc.clipHi.push(clipHi / this.n);
    acc.clipLo.push(clipLo / this.n);

    if (this.skyArea > 0) {
      const lum = skyLum / this.skyArea;
      const r = skyR / this.skyArea;
      const g = skyG / this.skyArea;
      const b = skyB / this.skyArea;
      acc.sky.lum.push(lum);
      acc.sky.sat.push(skySat / this.skyArea);
      /* Índice de azulidad normalizado: separa cielo despejado de cubierto sin
       * depender de la exposición absoluta de la cámara. */
      acc.sky.blue.push((b - r) / (b + r + 1e-6));
      acc.sky.texture.push(this.skyTexture());
      acc.sky.r += r;
      acc.sky.g += g;
      acc.sky.b += b;
      acc.sky.n += 1;
      if (lum < this.config.night_luminance) acc.nightFrames += 1;
    }

    if (facadeMaskOut) {
      acc.facadeLit.push(this.facadeArea ? facadeLit / this.facadeArea : 0);
      const windows = connectedComponents(
        facadeMaskOut,
        this.facadeMask,
        this.w,
        this.h,
        this.config.facade_min_window_area,
      );
      acc.facadeWindows.push(windows.length);
    }

    /* Modelo de fondo. El primer fotograma lo inicializa; los siguientes lo
     * actualizan con dos tasas según la clasificación del píxel. */
    if (!this.bg) {
      this.bg = Float32Array.from(gray);
      this.warmupFrames = 1;
      this.emitFrameState(0, 0);
      return this.maybeCloseMinute(now);
    }

    const tau = Math.max(this.config.fg_tau_min, this.config.fg_k_sigma * this.sigma);
    let fgCount = 0;
    let residualSum = 0;
    let residualCount = 0;
    for (let i = 0; i < this.n; i += 1) {
      const d = Math.abs(gray[i] - this.bg[i]);
      const isFg = d > tau;
      this.fg[i] = isFg ? 1 : 0;
      if (isFg) fgCount += 1;
      else {
        residualSum += d;
        residualCount += 1;
      }
    }
    const fgFrac = fgCount / this.n;

    /* Estimación robusta del ruido a partir de los píxeles de fondo. */
    if (residualCount > 0) {
      const meanAbs = residualSum / residualCount;
      this.sigma = 0.95 * this.sigma + 0.05 * (meanAbs * 1.2533);
    }

    /* Desplazamiento de cámara: casi toda la escena cambia a la vez. */
    if (fgFrac > this.config.scene_shift_fg_frac) this.shiftRun += 1;
    else this.shiftRun = 0;
    if (this.shiftRun >= this.config.scene_shift_frames) {
      this.bg = Float32Array.from(gray);
      this.shiftRun = 0;
      this.warmupFrames = 1;
      this.pendingShift = true;
      acc.shiftFrames += 1;
      this.tracker.tracks = [];
      this.emitFrameState(fgFrac, 0);
      return this.maybeCloseMinute(now);
    }

    for (let i = 0; i < this.n; i += 1) {
      const alpha = this.fg[i] ? this.config.bg_alpha_foreground : this.config.bg_alpha_background;
      this.bg[i] += alpha * (gray[i] - this.bg[i]);
    }

    /* Los primeros fotogramas tras un reinicio del fondo no son medibles. */
    this.warmupFrames += 1;
    if (this.warmupFrames < 15) {
      this.emitFrameState(fgFrac, 0);
      return this.maybeCloseMinute(now);
    }

    const opened = openMask(this.fg, this.w, this.h);
    let streetFg = 0;
    for (let i = 0; i < this.n; i += 1) {
      if (opened[i] && this.streetMask[i]) streetFg += 1;
    }
    acc.motion.push(streetFg / this.streetArea);

    const minArea = Math.max(2, Math.round(this.config.blob_min_area_frac * this.n));
    const blobs = connectedComponents(opened, this.streetMask, this.w, this.h, minArea);
    this.tracker.update(blobs);
    acc.tracksActive.push(this.tracker.tracks.length);

    for (const cross of this.tracker.crossings(this.line)) {
      acc.addCrossing(cross, this.frameArea);
    }

    this.emitFrameState(fgFrac, blobs.length);
    return this.maybeCloseMinute(now);
  }

  /** Desviación típica de las medias de bloques 8x8 dentro de la región de cielo. */
  skyTexture() {
    const step = 8;
    const means = [];
    for (let by = 0; by < this.h; by += step) {
      for (let bx = 0; bx < this.w; bx += step) {
        let sum = 0;
        let count = 0;
        for (let y = by; y < Math.min(by + step, this.h); y += 1) {
          for (let x = bx; x < Math.min(bx + step, this.w); x += 1) {
            const i = y * this.w + x;
            if (!this.skyMask[i]) continue;
            sum += this.gray[i];
            count += 1;
          }
        }
        if (count >= (step * step) / 2) means.push(sum / count);
      }
    }
    return stdev(means) ?? 0;
  }

  emitFrameState(fgFrac, blobCount) {
    if (!this.onFrame) return;
    this.onFrame({
      tracks: this.tracker.tracks,
      blobs: blobCount,
      fg_frac: fgFrac,
      warming: this.warmupFrames < 15,
      crossings_minute: this.acc.crossA + this.acc.crossB,
    });
  }

  /** Cierra el minuto en curso si ya pasaron 60 segundos. */
  maybeCloseMinute(now) {
    if (now - this.acc.tStart < 60000) return null;
    const record = this.buildRecord(now);
    this.acc.reset(now);
    this.pendingShift = false;
    if (this.onMinute) this.onMinute(record);
    return record;
  }

  /** Fuerza el cierre del minuto en curso, por ejemplo al detener la sesión. */
  flush(now = new Date()) {
    if (this.acc.frames === 0) return null;
    const record = this.buildRecord(now, true);
    this.acc.reset(now);
    this.pendingShift = false;
    if (this.onMinute) this.onMinute(record);
    return record;
  }

  buildRecord(now, partial = false) {
    const acc = this.acc;
    const seconds = Math.max(0.001, (now - acc.tStart) / 1000);
    const sky = acc.sky.n
      ? {
          luminance_mean: round(mean(acc.sky.lum), 4),
          luminance_sd: round(stdev(acc.sky.lum), 4),
          saturation_mean: round(mean(acc.sky.sat), 4),
          blueness_mean: round(mean(acc.sky.blue), 4),
          texture_mean: round(mean(acc.sky.texture), 4),
          rgb_mean: [
            round(acc.sky.r / acc.sky.n, 4),
            round(acc.sky.g / acc.sky.n, 4),
            round(acc.sky.b / acc.sky.n, 4),
          ],
          hex: hex(acc.sky.r / acc.sky.n, acc.sky.g / acc.sky.n, acc.sky.b / acc.sky.n),
        }
      : null;

    return {
      schema: 'ventana.minute.v1',
      engine: ENGINE_VERSION,
      t_start: acc.tStart.toISOString(),
      t_end: now.toISOString(),
      duration_s: round(seconds, 2),
      partial,
      frames: acc.frames,
      fps_mean: round(acc.frames / seconds, 2),
      street: {
        crossings_a: acc.crossA,
        crossings_b: acc.crossB,
        crossings_total: acc.crossA + acc.crossB,
        by_size: { ...acc.bySize },
        area_histogram: [...acc.areaHist],
        motion_energy_mean: round(mean(acc.motion), 5),
        motion_energy_p95: round(quantile(acc.motion, 0.95), 5),
        tracks_active_mean: round(mean(acc.tracksActive), 2),
      },
      sky,
      facade: acc.facadeLit.length
        ? {
            lit_fraction_mean: round(mean(acc.facadeLit), 5),
            lit_windows_mean: round(mean(acc.facadeWindows), 2),
            lit_windows_p95: round(quantile(acc.facadeWindows, 0.95), 2),
          }
        : null,
      exposure: {
        clipped_high_frac: round(mean(acc.clipHi), 5),
        clipped_low_frac: round(mean(acc.clipLo), 5),
      },
      quality: {
        night: acc.frames > 0 && acc.nightFrames / acc.frames > 0.5,
        camera_shift: this.pendingShift || acc.shiftFrames > 0,
        frame_ms_p95: round(quantile(acc.frameMs, 0.95), 1),
        measurable_frames: acc.motion.length,
      },
    };
  }
}
