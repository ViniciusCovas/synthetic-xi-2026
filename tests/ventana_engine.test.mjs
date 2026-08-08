/*
 * Pruebas del motor de visión de Ventana sobre escenas sintéticas.
 *
 * Ejecutar con:  node --test tests/ventana_engine.test.mjs
 */

import assert from 'node:assert/strict';
import test from 'node:test';

import {
  ANALYSIS_HEIGHT,
  ANALYSIS_WIDTH,
  VentanaEngine,
  connectedComponents,
  openMask,
  polygonMask,
  rectMask,
} from '../projects/ventana_observatory/capture/engine.js';

const W = ANALYSIS_WIDTH;
const H = ANALYSIS_HEIGHT;

const CALIBRATION = {
  sky: { x0: 0.0, y0: 0.0, x1: 1.0, y1: 0.25 },
  street: [
    { x: 0.0, y: 0.45 },
    { x: 1.0, y: 0.45 },
    { x: 1.0, y: 1.0 },
    { x: 0.0, y: 1.0 },
  ],
  line: { a: { x: 0.5, y: 0.45 }, b: { x: 0.5, y: 1.0 } },
  facade: null,
};

/** Fotograma gris uniforme con un cuadrado claro opcional. */
function frame({ square = null, skyValue = 150, groundValue = 90 } = {}) {
  const data = new Uint8ClampedArray(W * H * 4);
  for (let y = 0; y < H; y += 1) {
    for (let x = 0; x < W; x += 1) {
      const p = (y * W + x) * 4;
      const base = y < H * 0.25 ? skyValue : groundValue;
      data[p] = base;
      data[p + 1] = base;
      data[p + 2] = base;
      data[p + 3] = 255;
    }
  }
  if (square) {
    const half = square.size / 2;
    for (let y = Math.round(square.y - half); y < Math.round(square.y + half); y += 1) {
      for (let x = Math.round(square.x - half); x < Math.round(square.x + half); x += 1) {
        if (x < 0 || y < 0 || x >= W || y >= H) continue;
        const p = (y * W + x) * 4;
        data[p] = 245;
        data[p + 1] = 245;
        data[p + 2] = 245;
      }
    }
  }
  return { data, width: W, height: H };
}

function makeEngine(overrides = {}) {
  return new VentanaEngine({
    calibration: CALIBRATION,
    config: { target_fps: 10, ...overrides },
  });
}

/** Alimenta n fotogramas estáticos para inicializar y estabilizar el fondo. */
function warmUp(engine, startMs, frames = 40) {
  let t = startMs;
  for (let i = 0; i < frames; i += 1) {
    engine.processFrame(frame(), new Date(t), 5);
    t += 100;
  }
  return t;
}

test('polygonMask cubre sólo el interior del polígono', () => {
  const mask = polygonMask(CALIBRATION.street, W, H);
  assert.equal(mask[Math.round(H * 0.8) * W + 10], 1);
  assert.equal(mask[Math.round(H * 0.1) * W + 10], 0);
});

test('rectMask respeta los límites normalizados', () => {
  const mask = rectMask({ x0: 0.25, y0: 0.0, x1: 0.75, y1: 0.5 }, W, H);
  assert.equal(mask[10 * W + Math.round(W * 0.5)], 1);
  assert.equal(mask[10 * W + 5], 0);
  assert.equal(mask[Math.round(H * 0.9) * W + Math.round(W * 0.5)], 0);
});

test('openMask elimina el ruido aislado y conserva los bloques', () => {
  const mask = new Uint8Array(W * H);
  mask[50 * W + 50] = 1; // píxel suelto
  for (let y = 100; y < 110; y += 1) {
    for (let x = 100; x < 110; x += 1) mask[y * W + x] = 1;
  }
  const opened = openMask(mask, W, H);
  assert.equal(opened[50 * W + 50], 0);
  assert.equal(opened[105 * W + 105], 1);
});

test('connectedComponents separa dos objetos y descarta los pequeños', () => {
  const mask = new Uint8Array(W * H);
  const draw = (cx, cy, size) => {
    for (let y = cy; y < cy + size; y += 1) {
      for (let x = cx; x < cx + size; x += 1) mask[y * W + x] = 1;
    }
  };
  draw(40, 120, 10);
  draw(200, 120, 10);
  draw(280, 120, 2); // por debajo del área mínima

  const blobs = connectedComponents(mask, null, W, H, 20);
  assert.equal(blobs.length, 2);
  assert.equal(blobs[0].area, 100);
  const centres = blobs.map((b) => b.x).sort((a, b) => a - b);
  assert.deepEqual(centres, [44.5, 204.5]);
});

test('connectedComponents ignora lo que cae fuera de la región de interés', () => {
  const mask = new Uint8Array(W * H);
  for (let y = 20; y < 30; y += 1) {
    for (let x = 20; x < 30; x += 1) mask[y * W + x] = 1; // en el cielo
  }
  const street = polygonMask(CALIBRATION.street, W, H);
  assert.equal(connectedComponents(mask, street, W, H, 20).length, 0);
  assert.equal(connectedComponents(mask, null, W, H, 20).length, 1);
});

test('un objeto que cruza la línea se cuenta una sola vez y con sentido', () => {
  const engine = makeEngine();
  let t = warmUp(engine, Date.UTC(2026, 7, 8, 12, 0, 0));

  for (let x = 60; x <= 260; x += 8) {
    engine.processFrame(frame({ square: { x, y: 130, size: 14 } }), new Date(t), 5);
    t += 100;
  }
  const record = engine.flush(new Date(t));

  assert.equal(record.street.crossings_total, 1);
  assert.equal(record.street.crossings_a + record.street.crossings_b, 1);
  assert.equal(record.quality.camera_shift, false);
  assert.ok(record.street.motion_energy_mean > 0);
});

test('el sentido inverso se registra en el contador opuesto', () => {
  const forward = makeEngine();
  let t = warmUp(forward, Date.UTC(2026, 7, 8, 12, 0, 0));
  for (let x = 60; x <= 260; x += 8) {
    forward.processFrame(frame({ square: { x, y: 130, size: 14 } }), new Date(t), 5);
    t += 100;
  }
  const forwardRecord = forward.flush(new Date(t));

  const backward = makeEngine();
  let u = warmUp(backward, Date.UTC(2026, 7, 8, 12, 0, 0));
  for (let x = 260; x >= 60; x -= 8) {
    backward.processFrame(frame({ square: { x, y: 130, size: 14 } }), new Date(u), 5);
    u += 100;
  }
  const backwardRecord = backward.flush(new Date(u));

  assert.equal(forwardRecord.street.crossings_total, 1);
  assert.equal(backwardRecord.street.crossings_total, 1);
  assert.notEqual(forwardRecord.street.crossings_a, backwardRecord.street.crossings_a);
});

test('un objeto que se queda en el cielo no se cuenta', () => {
  const engine = makeEngine();
  let t = warmUp(engine, Date.UTC(2026, 7, 8, 12, 0, 0));
  for (let x = 60; x <= 260; x += 8) {
    engine.processFrame(frame({ square: { x, y: 20, size: 14 } }), new Date(t), 5);
    t += 100;
  }
  const record = engine.flush(new Date(t));
  assert.equal(record.street.crossings_total, 0);
});

test('un objeto que se detiene antes de la línea no se cuenta', () => {
  const engine = makeEngine();
  let t = warmUp(engine, Date.UTC(2026, 7, 8, 12, 0, 0));
  for (let x = 60; x <= 140; x += 8) {
    engine.processFrame(frame({ square: { x, y: 130, size: 14 } }), new Date(t), 5);
    t += 100;
  }
  const record = engine.flush(new Date(t));
  assert.equal(record.street.crossings_total, 0);
});

test('el desglose por porte suma siempre el total de cruces', () => {
  const engine = makeEngine();
  let t = warmUp(engine, Date.UTC(2026, 7, 8, 12, 0, 0));
  for (let x = 60; x <= 260; x += 8) {
    engine.processFrame(frame({ square: { x, y: 130, size: 14 } }), new Date(t), 5);
    t += 100;
  }
  const record = engine.flush(new Date(t));
  const { small, medium, large } = record.street.by_size;
  assert.equal(small + medium + large, record.street.crossings_total);
  assert.equal(
    record.street.area_histogram.reduce((a, b) => a + b, 0),
    record.street.crossings_total,
  );
});

test('el cielo se mide sobre su propia región y distingue azul de gris', () => {
  const engine = makeEngine();
  let t = warmUp(engine, Date.UTC(2026, 7, 8, 12, 0, 0));
  // El calentamiento se midió con cielo gris: se descarta para que el minuto
  // siguiente contenga únicamente los fotogramas azules.
  engine.flush(new Date(t));

  const blueSky = frame();
  for (let y = 0; y < Math.round(H * 0.25); y += 1) {
    for (let x = 0; x < W; x += 1) {
      const p = (y * W + x) * 4;
      blueSky.data[p] = 90;
      blueSky.data[p + 1] = 150;
      blueSky.data[p + 2] = 235;
    }
  }
  for (let i = 0; i < 10; i += 1) {
    engine.processFrame(blueSky, new Date(t), 5);
    t += 100;
  }
  const record = engine.flush(new Date(t));

  assert.ok(record.sky.blueness_mean > 0.2, `azulidad inesperada: ${record.sky.blueness_mean}`);
  assert.ok(record.sky.luminance_mean > 0.4 && record.sky.luminance_mean < 0.8);
  assert.match(record.sky.hex, /^#[0-9a-f]{6}$/);
});

test('mover la cámara marca el minuto y reinicia el fondo', () => {
  const engine = makeEngine();
  let t = warmUp(engine, Date.UTC(2026, 7, 8, 12, 0, 0));

  // Escena completamente distinta durante varios fotogramas seguidos.
  const shifted = frame({ skyValue: 20, groundValue: 240 });
  for (let i = 0; i < 12; i += 1) {
    engine.processFrame(shifted, new Date(t), 5);
    t += 100;
  }
  const record = engine.flush(new Date(t));
  assert.equal(record.quality.camera_shift, true);
});

test('la fachada cuenta ventanas encendidas dentro de su región', () => {
  const engine = new VentanaEngine({
    calibration: { ...CALIBRATION, facade: { x0: 0.0, y0: 0.25, x1: 1.0, y1: 0.45 } },
  });
  let t = Date.UTC(2026, 7, 8, 22, 0, 0);

  const night = frame({ skyValue: 12, groundValue: 25 });
  const lightUp = (cx, cy) => {
    for (let y = cy; y < cy + 5; y += 1) {
      for (let x = cx; x < cx + 5; x += 1) {
        const p = (y * W + x) * 4;
        night.data[p] = 240;
        night.data[p + 1] = 230;
        night.data[p + 2] = 200;
      }
    }
  };
  lightUp(40, 60);
  lightUp(120, 60);
  lightUp(200, 70);

  for (let i = 0; i < 20; i += 1) {
    engine.processFrame(night, new Date(t), 5);
    t += 100;
  }
  const record = engine.flush(new Date(t));

  assert.equal(record.facade.lit_windows_mean, 3);
  assert.ok(record.facade.lit_fraction_mean > 0);
  assert.equal(record.quality.night, true);
});

test('los registros de minuto se emiten al cumplirse sesenta segundos', () => {
  const emitted = [];
  const engine = new VentanaEngine({
    calibration: CALIBRATION,
    onMinute: (record) => emitted.push(record),
  });

  let t = Date.UTC(2026, 7, 8, 12, 0, 0);
  for (let i = 0; i < 700; i += 1) {
    engine.processFrame(frame(), new Date(t), 5);
    t += 100; // 10 fps -> 70 segundos de reloj
  }

  assert.equal(emitted.length, 1);
  assert.equal(emitted[0].schema, 'ventana.minute.v1');
  assert.ok(emitted[0].duration_s >= 60);
  assert.ok(emitted[0].fps_mean > 8 && emitted[0].fps_mean < 12);
  assert.equal(emitted[0].partial, false);
});
