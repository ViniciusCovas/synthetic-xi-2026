/*
 * Tablero de Ventana.
 *
 * Consume exclusivamente el paquete `ventana_exhibits.json`. No recalcula
 * medias ni intervalos: si una cifra no está en el paquete, no se muestra.
 */

const DEFAULT_PACKAGE = '../../../data/ventana/exhibits/ventana_exhibits_synthetic.json';

const METRIC_LABELS = {
  crossings_per_minute: 'cruces por minuto',
  motion_energy: 'energía de movimiento',
  sky_luminance: 'luz de cielo',
  sky_blueness: 'azulidad',
  sky_texture: 'textura de nube',
  lit_windows: 'ventanas encendidas',
  large_share: 'proporción de porte grande',
  flow_asymmetry: 'asimetría de sentido',
};

const $ = (id) => document.getElementById(id);
const SVG_NS = 'http://www.w3.org/2000/svg';

let currentMetric = 'crossings_per_minute';
let data = null;

function el(tag, attrs = {}, text = null) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  if (text !== null) node.textContent = text;
  return node;
}

function fmt(value, digits = 2) {
  if (value === null || value === undefined) return '—';
  return Number(value).toFixed(digits);
}

/* ------------------------------------------------------------------ */
/* Tarjetas de cabecera                                                */
/* ------------------------------------------------------------------ */

function renderCards() {
  const cards = $('cards');
  cards.innerHTML = '';
  const busiest = busiestHour();
  const contrast = data.weekday_contrast;
  const rows = [
    ['minutos válidos', String(data.minutes_valid), `de ${data.minutes_observed} observados`],
    ['fechas cubiertas', String(data.coverage_by_date.length), 'días locales con observación'],
    [
      'hora más viva',
      busiest ? `${String(busiest.hour_local).padStart(2, '0')}:00` : '—',
      busiest ? `${fmt(busiest.mean)} cruces/min` : 'sin datos suficientes',
    ],
    [
      'índice de dispersión',
      fmt(data.dispersion.index),
      data.dispersion.index > 1.2 ? 'tráfico a ráfagas' : 'compatible con Poisson',
    ],
    [
      'laborable vs finde',
      contrast.comparable ? fmt(contrast.difference_weekday_minus_weekend) : '—',
      contrast.comparable ? 'diferencia en cruces/min' : 'aún sin fin de semana comparable',
    ],
  ];
  for (const [label, value, note] of rows) {
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = '<span></span><strong></strong><em></em>';
    card.querySelector('span').textContent = label;
    card.querySelector('strong').textContent = value;
    card.querySelector('em').textContent = note;
    cards.appendChild(card);
  }
  $('ceiling').textContent = `Techo de afirmación: ${data.claim_ceiling}`;
}

function busiestHour() {
  const hours = data.diurnal_profiles.crossings_per_minute.hours.filter((h) => h.mean !== null);
  if (!hours.length) return null;
  return hours.reduce((best, h) => (h.mean > best.mean ? h : best));
}

/* ------------------------------------------------------------------ */
/* Código de barras del cielo                                          */
/* ------------------------------------------------------------------ */

function renderBarcode() {
  const host = $('barcode');
  host.innerHTML = '';
  const byDate = new Map();
  for (const row of data.sky_barcode) {
    if (!byDate.has(row.date_local)) byDate.set(row.date_local, []);
    byDate.get(row.date_local).push(row);
  }
  if (!byDate.size) {
    host.innerHTML = '<p class="note">Todavía no hay minutos de cielo válidos.</p>';
    return;
  }

  for (const [date, rows] of [...byDate.entries()].sort()) {
    const wrap = document.createElement('div');
    wrap.className = 'barcode-row';
    const label = document.createElement('span');
    label.textContent = date;
    const canvas = document.createElement('canvas');
    canvas.width = 1440;
    canvas.height = 1;
    const ctx = canvas.getContext('2d');
    // Los minutos sin observación quedan transparentes a propósito: un hueco
    // en la franja es un hueco real de cobertura, no un color inventado.
    for (const row of rows) {
      ctx.fillStyle = row.hex;
      ctx.fillRect(row.minute_of_day, 0, 1, 1);
    }
    wrap.append(label, canvas);
    host.appendChild(wrap);
  }

  const axis = document.createElement('div');
  axis.className = 'axis';
  axis.innerHTML = '<span></span><div><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>24:00</span></div>';
  host.appendChild(axis);
}

/* ------------------------------------------------------------------ */
/* Perfil diurno                                                       */
/* ------------------------------------------------------------------ */

function renderMetricButtons() {
  const host = $('metric-buttons');
  host.innerHTML = '';
  for (const metric of Object.keys(data.diurnal_profiles)) {
    const button = document.createElement('button');
    button.textContent = METRIC_LABELS[metric] ?? metric;
    button.setAttribute('aria-pressed', String(metric === currentMetric));
    button.addEventListener('click', () => {
      currentMetric = metric;
      renderMetricButtons();
      renderProfile();
    });
    host.appendChild(button);
  }
}

function renderProfile() {
  const host = $('profile');
  host.innerHTML = '';
  const profile = data.diurnal_profiles[currentMetric];
  const hours = profile.hours;
  const present = hours.filter((h) => h.mean !== null);
  if (!present.length) {
    host.innerHTML = '<p class="note">Sin observaciones válidas para esta magnitud.</p>';
    return;
  }

  const W = 960;
  const H = 320;
  const pad = { top: 16, right: 16, bottom: 30, left: 52 };
  const innerW = W - pad.left - pad.right;
  const innerH = H - pad.top - pad.bottom;

  const values = present.flatMap((h) => [h.ci95_low ?? h.mean, h.ci95_high ?? h.mean, h.mean]);
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  if (hi === lo) {
    hi += 1;
    lo -= 1;
  }
  const span = hi - lo;
  lo -= span * 0.08;
  hi += span * 0.08;

  const x = (hour) => pad.left + (hour / 23) * innerW;
  const y = (value) => pad.top + innerH - ((value - lo) / (hi - lo)) * innerH;

  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img' });
  svg.appendChild(el('title', {}, `${METRIC_LABELS[currentMetric] ?? currentMetric} por hora local`));

  for (let i = 0; i <= 4; i += 1) {
    const value = lo + ((hi - lo) * i) / 4;
    const yy = y(value);
    svg.appendChild(el('line', { x1: pad.left, x2: W - pad.right, y1: yy, y2: yy, stroke: '#223041' }));
    svg.appendChild(
      el('text', { x: pad.left - 8, y: yy + 4, fill: '#8ba0b6', 'font-size': 11, 'text-anchor': 'end' }, fmt(value, 2)),
    );
  }
  for (const hour of [0, 6, 12, 18, 23]) {
    svg.appendChild(
      el(
        'text',
        { x: x(hour), y: H - 10, fill: '#8ba0b6', 'font-size': 11, 'text-anchor': 'middle' },
        `${String(hour).padStart(2, '0')}h`,
      ),
    );
  }

  /* La banda y la línea se dibujan por tramos contiguos: una hora sin datos
   * corta el trazo en lugar de interpolarse. */
  for (const run of contiguousRuns(hours)) {
    const withCi = run.filter((h) => h.ci95_low !== null && h.ci95_high !== null);
    if (withCi.length >= 2) {
      const top = withCi.map((h) => `${x(h.hour_local)},${y(h.ci95_high)}`);
      const bottom = withCi
        .slice()
        .reverse()
        .map((h) => `${x(h.hour_local)},${y(h.ci95_low)}`);
      svg.appendChild(
        el('polygon', { points: [...top, ...bottom].join(' '), fill: 'rgba(123,255,176,0.18)' }),
      );
    }
    if (run.length >= 2) {
      svg.appendChild(
        el('polyline', {
          points: run.map((h) => `${x(h.hour_local)},${y(h.mean)}`).join(' '),
          fill: 'none',
          stroke: '#7bffb0',
          'stroke-width': 2,
        }),
      );
    }
    for (const h of run) {
      svg.appendChild(el('circle', { cx: x(h.hour_local), cy: y(h.mean), r: 3, fill: '#7bffb0' }));
    }
  }

  host.appendChild(svg);
  const note = document.createElement('p');
  note.className = 'note';
  note.textContent = `${profile.minutes_used} minutos válidos · semilla ${profile.seed} · ${profile.bootstrap_iterations} remuestreos`;
  host.appendChild(note);
}

function contiguousRuns(hours) {
  const runs = [];
  let run = [];
  for (const hour of hours) {
    if (hour.mean === null) {
      if (run.length) runs.push(run);
      run = [];
    } else {
      run.push(hour);
    }
  }
  if (run.length) runs.push(run);
  return runs;
}

/* ------------------------------------------------------------------ */
/* Cobertura y compuertas                                              */
/* ------------------------------------------------------------------ */

function renderCoverage() {
  const host = $('coverage');
  host.innerHTML = '';
  const table = document.createElement('table');
  table.innerHTML =
    '<thead><tr><th>fecha local</th><th>observados</th><th>válidos</th><th>válidos %</th><th>del día</th></tr></thead>';
  const body = document.createElement('tbody');
  for (const row of data.coverage_by_date) {
    const tr = document.createElement('tr');
    for (const cell of [
      row.date_local,
      row.minutes_observed,
      row.minutes_valid,
      `${(row.valid_fraction * 100).toFixed(1)}%`,
      `${(row.day_coverage_fraction * 100).toFixed(1)}%`,
    ]) {
      const td = document.createElement('td');
      td.textContent = String(cell);
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }
  table.appendChild(body);
  host.appendChild(table);
}

function renderGates() {
  const host = $('gates');
  host.innerHTML = '';
  const table = document.createElement('table');
  table.innerHTML =
    '<thead><tr><th>sesión</th><th>válidos</th><th>total</th><th>compuerta</th><th>descartes principales</th></tr></thead>';
  const body = document.createElement('tbody');
  for (const report of data.gates) {
    const tr = document.createElement('tr');
    const failures = Object.entries(report.failures_by_gate)
      .filter(([, count]) => count > 0)
      .map(([gate, count]) => `${gate}: ${count}`)
      .join(', ');
    const cells = [
      report.session_id,
      report.valid_minutes,
      report.total_minutes,
      report.session_gate_passed ? 'PASS' : 'FAIL',
      failures || '—',
    ];
    cells.forEach((cell, index) => {
      const td = document.createElement('td');
      td.textContent = String(cell);
      if (index === 3) td.className = report.session_gate_passed ? 'pass' : 'fail';
      tr.appendChild(td);
    });
    body.appendChild(tr);
  }
  table.appendChild(body);
  host.appendChild(table);
}

/* ------------------------------------------------------------------ */
/* Carga                                                               */
/* ------------------------------------------------------------------ */

function render(payload) {
  if (payload.schema !== 'ventana.exhibits.v1') {
    throw new Error(`esquema inesperado: ${payload.schema}`);
  }
  data = payload;
  if (!Object.keys(data.diurnal_profiles).includes(currentMetric)) {
    currentMetric = Object.keys(data.diurnal_profiles)[0];
  }
  renderCards();
  renderBarcode();
  renderMetricButtons();
  renderProfile();
  renderCoverage();
  renderGates();
  const sites = data.sessions.map((s) => s.site_label).filter(Boolean);
  $('status').textContent = `${data.sessions.length} sesión(es)${sites.length ? ` · ${[...new Set(sites)].join(', ')}` : ''}`;
}

$('file').addEventListener('change', async (event) => {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    render(JSON.parse(await file.text()));
  } catch (err) {
    $('status').textContent = `No se pudo leer el paquete: ${err.message}`;
  }
});

fetch(DEFAULT_PACKAGE)
  .then((response) => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  })
  .then(render)
  .catch((err) => {
    $('status').textContent = `Carga el paquete a mano (${err.message}).`;
  });
