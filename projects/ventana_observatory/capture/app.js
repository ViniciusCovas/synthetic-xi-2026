/*
 * VENTANA — aplicación de captura.
 *
 * Abre la cámara trasera, permite calibrar las tres regiones de la escena y
 * ejecuta el motor de visión en bucle. Sólo salen del teléfono los registros
 * numéricos por minuto, y únicamente cuando el usuario pulsa exportar.
 */

import { VentanaEngine, ANALYSIS_WIDTH, ANALYSIS_HEIGHT, ENGINE_VERSION } from './engine.js';

const $ = (id) => document.getElementById(id);

const state = {
  stream: null,
  engine: null,
  running: false,
  wakeLock: null,
  sessionId: null,
  sessionStart: null,
  minutes: 0,
  lastRecord: null,
  calibration: loadCalibration(),
  mode: null,
  draft: null,
  lastFrameMs: 0,
  nextAnalysisAt: 0,
};

/* ------------------------------------------------------------------ */
/* Persistencia                                                        */
/* ------------------------------------------------------------------ */

const CAL_KEY = 'ventana.calibration.v1';
const DB_NAME = 'ventana';
const DB_VERSION = 1;

function loadCalibration() {
  try {
    const raw = localStorage.getItem(CAL_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function saveCalibration(cal) {
  localStorage.setItem(CAL_KEY, JSON.stringify(cal));
}

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains('records')) {
        db.createObjectStore('records', { keyPath: 'seq', autoIncrement: true });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function putRecord(record) {
  const db = await openDb();
  await new Promise((resolve, reject) => {
    const tx = db.transaction('records', 'readwrite');
    tx.objectStore('records').add(record);
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

async function allRecords() {
  const db = await openDb();
  const rows = await new Promise((resolve, reject) => {
    const req = db.transaction('records', 'readonly').objectStore('records').getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  db.close();
  return rows;
}

async function clearRecords() {
  const db = await openDb();
  await new Promise((resolve, reject) => {
    const tx = db.transaction('records', 'readwrite');
    tx.objectStore('records').clear();
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

/* ------------------------------------------------------------------ */
/* Cámara                                                              */
/* ------------------------------------------------------------------ */

const video = $('video');
const overlay = $('overlay');
const octx = overlay.getContext('2d');
const work = document.createElement('canvas');
work.width = ANALYSIS_WIDTH;
work.height = ANALYSIS_HEIGHT;
const wctx = work.getContext('2d', { willReadFrequently: true });

async function startCamera() {
  state.stream = await navigator.mediaDevices.getUserMedia({
    video: {
      facingMode: { ideal: 'environment' },
      width: { ideal: 1280 },
      height: { ideal: 720 },
      frameRate: { ideal: 30 },
    },
    audio: false,
  });
  video.srcObject = state.stream;
  await video.play();
  resizeOverlay();
  setStatus('Cámara activa. Calibra las regiones o inicia la sesión.');
  $('btn-camera').disabled = true;
  $('btn-start').disabled = !state.calibration;
  document.querySelectorAll('.cal-btn').forEach((b) => {
    b.disabled = false;
  });
}

function resizeOverlay() {
  const rect = video.getBoundingClientRect();
  overlay.width = Math.max(1, Math.round(rect.width));
  overlay.height = Math.max(1, Math.round(rect.height));
}

window.addEventListener('resize', resizeOverlay);

/* ------------------------------------------------------------------ */
/* Calibración                                                         */
/* ------------------------------------------------------------------ */

const MODES = {
  sky: { label: 'cielo', kind: 'rect', help: 'Arrastra un rectángulo sobre una zona que sea sólo cielo.' },
  street: { label: 'calle', kind: 'poly', help: 'Toca los vértices del área de calle y pulsa Cerrar.' },
  line: { label: 'línea', kind: 'line', help: 'Toca dos puntos: los objetos se cuentan al cruzar esa recta.' },
  facade: { label: 'fachada', kind: 'rect', help: 'Opcional: arrastra un rectángulo sobre las ventanas de un edificio.' },
};

function beginMode(mode) {
  state.mode = mode;
  state.draft = MODES[mode].kind === 'poly' ? [] : null;
  $('cal-help').textContent = MODES[mode].help;
  $('btn-cal-close').hidden = MODES[mode].kind !== 'poly';
  $('btn-cal-cancel').hidden = false;
  drawOverlay();
}

function endMode() {
  state.mode = null;
  state.draft = null;
  $('cal-help').textContent = '';
  $('btn-cal-close').hidden = true;
  $('btn-cal-cancel').hidden = true;
  $('btn-start').disabled = !isCalibrationComplete();
  drawOverlay();
}

function isCalibrationComplete() {
  const c = state.calibration;
  return Boolean(c && c.sky && c.street && c.street.length >= 3 && c.line);
}

function normPoint(evt) {
  const rect = overlay.getBoundingClientRect();
  const src = evt.touches ? evt.touches[0] : evt;
  return {
    x: Math.min(1, Math.max(0, (src.clientX - rect.left) / rect.width)),
    y: Math.min(1, Math.max(0, (src.clientY - rect.top) / rect.height)),
  };
}

function ensureCalibration() {
  if (!state.calibration) state.calibration = { sky: null, street: null, line: null, facade: null };
  return state.calibration;
}

overlay.addEventListener('pointerdown', (evt) => {
  if (!state.mode) return;
  evt.preventDefault();
  const p = normPoint(evt);
  const kind = MODES[state.mode].kind;
  if (kind === 'rect') {
    state.draft = { x0: p.x, y0: p.y, x1: p.x, y1: p.y };
  } else if (kind === 'poly') {
    state.draft.push(p);
  } else if (kind === 'line') {
    if (!state.draft) state.draft = { a: p, b: p };
    else {
      state.draft.b = p;
      ensureCalibration().line = state.draft;
      saveCalibration(state.calibration);
      endMode();
      return;
    }
  }
  drawOverlay();
});

overlay.addEventListener('pointermove', (evt) => {
  if (!state.mode || !state.draft) return;
  const kind = MODES[state.mode].kind;
  if (kind !== 'rect' || evt.buttons === 0) return;
  const p = normPoint(evt);
  state.draft.x1 = p.x;
  state.draft.y1 = p.y;
  drawOverlay();
});

overlay.addEventListener('pointerup', () => {
  if (!state.mode || !state.draft) return;
  if (MODES[state.mode].kind !== 'rect') return;
  const r = state.draft;
  if (Math.abs(r.x1 - r.x0) < 0.03 || Math.abs(r.y1 - r.y0) < 0.03) return;
  ensureCalibration()[state.mode] = r;
  saveCalibration(state.calibration);
  endMode();
});

$('btn-cal-close').addEventListener('click', () => {
  if (state.mode !== 'street' || !state.draft || state.draft.length < 3) return;
  ensureCalibration().street = state.draft;
  saveCalibration(state.calibration);
  endMode();
});

$('btn-cal-cancel').addEventListener('click', endMode);

document.querySelectorAll('.cal-btn').forEach((btn) => {
  btn.addEventListener('click', () => beginMode(btn.dataset.mode));
});

$('btn-cal-reset').addEventListener('click', () => {
  if (state.running) return;
  localStorage.removeItem(CAL_KEY);
  state.calibration = null;
  $('btn-start').disabled = true;
  drawOverlay();
  setStatus('Calibración borrada.');
});

/* ------------------------------------------------------------------ */
/* Dibujo del overlay                                                  */
/* ------------------------------------------------------------------ */

let liveFrame = null;

function drawOverlay() {
  const w = overlay.width;
  const h = overlay.height;
  octx.clearRect(0, 0, w, h);
  const cal = state.calibration;

  const rect = (r, color, label) => {
    if (!r) return;
    const x = Math.min(r.x0, r.x1) * w;
    const y = Math.min(r.y0, r.y1) * h;
    const rw = Math.abs(r.x1 - r.x0) * w;
    const rh = Math.abs(r.y1 - r.y0) * h;
    octx.strokeStyle = color;
    octx.lineWidth = 2;
    octx.strokeRect(x, y, rw, rh);
    octx.fillStyle = color;
    octx.font = '12px system-ui, sans-serif';
    octx.fillText(label, x + 4, y + 14);
  };

  if (cal) {
    rect(cal.sky, '#5eb8ff', 'cielo');
    rect(cal.facade, '#ffd166', 'fachada');
    if (cal.street && cal.street.length >= 3) {
      octx.beginPath();
      octx.moveTo(cal.street[0].x * w, cal.street[0].y * h);
      for (const p of cal.street.slice(1)) octx.lineTo(p.x * w, p.y * h);
      octx.closePath();
      octx.strokeStyle = '#7bffb0';
      octx.lineWidth = 2;
      octx.stroke();
      octx.fillStyle = 'rgba(123,255,176,0.10)';
      octx.fill();
    }
    if (cal.line) {
      octx.beginPath();
      octx.moveTo(cal.line.a.x * w, cal.line.a.y * h);
      octx.lineTo(cal.line.b.x * w, cal.line.b.y * h);
      octx.strokeStyle = '#ff6b6b';
      octx.lineWidth = 3;
      octx.stroke();
    }
  }

  if (state.draft) {
    if (Array.isArray(state.draft)) {
      octx.strokeStyle = '#ffffff';
      octx.lineWidth = 2;
      octx.beginPath();
      state.draft.forEach((p, i) => {
        const x = p.x * w;
        const y = p.y * h;
        if (i === 0) octx.moveTo(x, y);
        else octx.lineTo(x, y);
        octx.fillStyle = '#ffffff';
        octx.fillRect(x - 3, y - 3, 6, 6);
      });
      octx.stroke();
    } else if ('a' in state.draft) {
      octx.fillStyle = '#ffffff';
      octx.fillRect(state.draft.a.x * w - 4, state.draft.a.y * h - 4, 8, 8);
    } else {
      rect(state.draft, '#ffffff', '');
    }
  }

  if (liveFrame && state.running) {
    const sx = w / ANALYSIS_WIDTH;
    const sy = h / ANALYSIS_HEIGHT;
    for (const t of liveFrame.tracks) {
      const r = Math.max(6, Math.sqrt(t.area) * sx);
      octx.beginPath();
      octx.arc(t.x * sx, t.y * sy, r, 0, Math.PI * 2);
      octx.strokeStyle = t.counted ? '#ff6b6b' : '#7bffb0';
      octx.lineWidth = 2;
      octx.stroke();
    }
  }
}

/* ------------------------------------------------------------------ */
/* Bucle de análisis                                                   */
/* ------------------------------------------------------------------ */

function grabFrame() {
  wctx.drawImage(video, 0, 0, ANALYSIS_WIDTH, ANALYSIS_HEIGHT);
  return wctx.getImageData(0, 0, ANALYSIS_WIDTH, ANALYSIS_HEIGHT);
}

function loop() {
  if (!state.running) return;
  const now = performance.now();
  if (now >= state.nextAnalysisAt) {
    const t0 = performance.now();
    try {
      state.engine.processFrame(grabFrame(), new Date(), state.lastFrameMs);
    } catch (err) {
      setStatus(`Error de análisis: ${err.message}`);
      stopSession();
      return;
    }
    state.lastFrameMs = performance.now() - t0;
    /* Si el teléfono se calienta y el fotograma cuesta más que el presupuesto,
     * el intervalo se estira solo en lugar de acumular retraso. */
    const budget = 1000 / state.engine.config.target_fps;
    state.nextAnalysisAt = now + Math.max(budget, state.lastFrameMs * 1.5);
    drawOverlay();
  }
  requestAnimationFrame(loop);
}

/* ------------------------------------------------------------------ */
/* Sesión                                                              */
/* ------------------------------------------------------------------ */

function newSessionId() {
  const bytes = new Uint8Array(8);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

function sessionHeader() {
  const track = state.stream?.getVideoTracks?.()[0];
  const settings = track?.getSettings?.() ?? {};
  return {
    schema: 'ventana.session.v1',
    engine: ENGINE_VERSION,
    session_id: state.sessionId,
    t_start: state.sessionStart.toISOString(),
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    utc_offset_minutes: -new Date().getTimezoneOffset(),
    device: {
      user_agent: navigator.userAgent,
      capture_width: settings.width ?? null,
      capture_height: settings.height ?? null,
      capture_fps: settings.frameRate ?? null,
    },
    analysis: { width: ANALYSIS_WIDTH, height: ANALYSIS_HEIGHT },
    config: state.engine.config,
    calibration: state.calibration,
    site_label: $('site-label').value.trim() || null,
  };
}

async function startSession() {
  if (!isCalibrationComplete()) {
    setStatus('Falta calibrar cielo, calle y línea.');
    return;
  }
  state.sessionId = newSessionId();
  state.sessionStart = new Date();
  state.minutes = 0;
  state.engine = new VentanaEngine({
    calibration: state.calibration,
    onMinute: onMinute,
    onFrame: (f) => {
      liveFrame = f;
    },
  });
  await putRecord(sessionHeader());
  state.running = true;
  state.nextAnalysisAt = 0;
  $('btn-start').disabled = true;
  $('btn-stop').disabled = false;
  document.querySelectorAll('.cal-btn').forEach((b) => {
    b.disabled = true;
  });
  await requestWakeLock();
  setStatus(`Sesión ${state.sessionId} en curso.`);
  loop();
}

async function stopSession() {
  if (!state.running) return;
  state.running = false;
  state.engine.flush(new Date());
  releaseWakeLock();
  $('btn-start').disabled = false;
  $('btn-stop').disabled = true;
  document.querySelectorAll('.cal-btn').forEach((b) => {
    b.disabled = false;
  });
  setStatus(`Sesión detenida. ${state.minutes} minutos registrados.`);
}

async function onMinute(record) {
  record.session_id = state.sessionId;
  state.minutes += 1;
  state.lastRecord = record;
  try {
    await putRecord(record);
  } catch (err) {
    setStatus(`No se pudo guardar el minuto: ${err.message}`);
  }
  renderLive(record);
  const url = $('ingest-url').value.trim();
  if (url) {
    fetch(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(record),
    }).catch(() => {
      /* La ingesta remota es opcional: el registro local ya está a salvo. */
    });
  }
}

async function requestWakeLock() {
  try {
    state.wakeLock = await navigator.wakeLock.request('screen');
    state.wakeLock.addEventListener('release', () => {
      state.wakeLock = null;
    });
  } catch {
    setStatus('Aviso: no se pudo bloquear la pantalla. Desactiva el apagado automático.');
  }
}

function releaseWakeLock() {
  state.wakeLock?.release?.();
  state.wakeLock = null;
}

document.addEventListener('visibilitychange', async () => {
  if (document.visibilityState === 'visible' && state.running && !state.wakeLock) {
    await requestWakeLock();
  }
});

/* ------------------------------------------------------------------ */
/* Panel en vivo y exportación                                         */
/* ------------------------------------------------------------------ */

function renderLive(r) {
  $('m-minutes').textContent = String(state.minutes);
  $('m-cross').textContent = String(r.street.crossings_total);
  $('m-dir').textContent = `${r.street.crossings_a} / ${r.street.crossings_b}`;
  $('m-sizes').textContent = `${r.street.by_size.small} · ${r.street.by_size.medium} · ${r.street.by_size.large}`;
  $('m-fps').textContent = r.fps_mean === null ? '—' : r.fps_mean.toFixed(1);
  if (r.sky) {
    $('m-sky').textContent = r.sky.luminance_mean.toFixed(3);
    $('m-blue').textContent = r.sky.blueness_mean.toFixed(3);
    $('sky-swatch').style.background = r.sky.hex;
  }
  $('m-facade').textContent = r.facade ? r.facade.lit_windows_mean.toFixed(1) : '—';
  const flags = [];
  if (r.quality.night) flags.push('noche');
  if (r.quality.camera_shift) flags.push('cámara movida');
  $('m-flags').textContent = flags.length ? flags.join(', ') : 'ok';
}

$('btn-export').addEventListener('click', async () => {
  const rows = await allRecords();
  if (!rows.length) {
    setStatus('No hay registros que exportar.');
    return;
  }
  const body = rows
    .map((row) => {
      const { seq, ...rest } = row;
      return JSON.stringify(rest);
    })
    .join('\n');
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const blob = new Blob([`${body}\n`], { type: 'application/x-ndjson' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `ventana_${stamp}.jsonl`;
  a.click();
  URL.revokeObjectURL(a.href);
  setStatus(`Exportados ${rows.length} registros.`);
});

$('btn-clear').addEventListener('click', async () => {
  if (state.running) return;
  if (!confirm('Borrar todos los registros guardados en este teléfono?')) return;
  await clearRecords();
  setStatus('Almacenamiento local vacío.');
});

$('btn-camera').addEventListener('click', () => {
  startCamera().catch((err) => setStatus(`No se pudo abrir la cámara: ${err.message}`));
});
$('btn-start').addEventListener('click', () => startSession());
$('btn-stop').addEventListener('click', () => stopSession());

function setStatus(text) {
  $('status').textContent = text;
}

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('./sw.js').catch(() => {
    /* Sin service worker la aplicación sigue funcionando, sólo pierde el modo
     * fuera de línea. */
  });
}

allRecords().then((rows) => {
  const minutes = rows.filter((r) => r.schema === 'ventana.minute.v1').length;
  if (minutes) setStatus(`${minutes} minutos ya guardados en este teléfono.`);
});

drawOverlay();
