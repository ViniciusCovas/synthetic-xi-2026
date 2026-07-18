import Chart from 'chart.js/auto';
import './style.css';

const app = document.querySelector('#app');

async function loadJson(name, fallback) {
  try {
    const response = await fetch(`/data/${name}.json`, { cache: 'no-store' });
    if (!response.ok) return fallback;
    return await response.json();
  } catch {
    return fallback;
  }
}

const [manifest, methods, avatars, metrics, members, fixtures, benchmarks, comparisons, syntheticXI, realXI] = await Promise.all([
  loadJson('manifest', { status: 'awaiting_api_key', competition: 'Copa Mundial de la FIFA 2026' }),
  loadJson('methods', {}),
  loadJson('avatars', []),
  loadJson('avatar_metrics', []),
  loadJson('avatar_members', []),
  loadJson('fixtures', []),
  loadJson('real_benchmarks', []),
  loadJson('positional_comparisons', []),
  loadJson('synthetic_xi', []),
  loadJson('real_best_xi', []),
]);

const metricLabel = (value) => value
  .replaceAll('_p90', ' /90')
  .replaceAll('_rate', ' — tasa')
  .replaceAll('_', ' ')
  .replace(/\b\w/g, (char) => char.toUpperCase());

const fmt = (value) => Number(value ?? 0).toLocaleString('es-MX', { maximumFractionDigits: 2 });
const snapshot = manifest.data_cutoff_utc
  ? new Date(manifest.data_cutoff_utc).toLocaleString('es-MX')
  : 'pendiente de la primera extracción';

app.innerHTML = `
  <header class="topbar">
    <div class="brandmark">XI</div>
    <div><p class="eyebrow">COPA 2026 · PROTOTIPO CIENTÍFICO</p><h1>Synthetic XI Lab</h1></div>
    <div class="live-badge"><span></span> corte ${snapshot}</div>
  </header>

  <main>
    <section class="hero">
      <div>
        <p class="eyebrow">DOS ESTUDIOS · UN MISMO SISTEMA</p>
        <h2>La élite colectiva contra la excepcionalidad individual.</h2>
        <p class="lede">Avatares separados por posición, benchmark real y dos onces completos. Todo resultado declara su muestra, su fecha y su incertidumbre.</p>
      </div>
      <div class="scope-card"><span>PARTIDOS INCLUIDOS</span><strong>${manifest.completed_matches_included ?? 0}</strong><small>concluidos hasta el corte</small></div>
    </section>

    <section class="study-grid">
      <article><span>ESTUDIO 1</span><h3>Avatar vs mejor real</h3><p>Ocho comparaciones intraposición: Top 20 sintético frente al número 1 real.</p></article>
      <article><span>ESTUDIO 2</span><h3>Once vs once</h3><p>Synthetic XI y Real Best XI, ambos con exactamente once integrantes.</p></article>
    </section>

    <section id="status-panel"></section>

    <section class="lab-grid ${avatars.length ? '' : 'hidden'}">
      <aside class="avatar-nav"><div class="section-heading"><p class="eyebrow">AVATARES</p><h3>Posición</h3></div><div id="avatar-buttons"></div></aside>
      <article class="profile-card">
        <div class="profile-head">
          <div><p class="eyebrow">AVATAR POSICIONAL SINTÉTICO</p><h3 id="avatar-title"></h3><p id="avatar-subtitle"></p><p id="benchmark-line" class="benchmark-line"></p></div>
          <div class="sample-seal" id="sample-seal"></div>
        </div>
        <div class="profile-body"><div class="chart-wrap"><canvas id="radar"></canvas></div><div class="metric-table" id="metric-table"></div></div>
      </article>
    </section>

    <section class="members-section ${avatars.length ? '' : 'hidden'}">
      <div class="section-heading"><p class="eyebrow">TRANSPARENCIA</p><h3>Quién forma el avatar</h3></div>
      <div class="table-shell"><table><thead><tr><th>#</th><th>Jugador</th><th>Selección</th><th>Minutos</th><th>Índice</th><th>Confiabilidad</th></tr></thead><tbody id="members-body"></tbody></table></div>
    </section>

    <section class="teams-section ${syntheticXI.length ? '' : 'hidden'}">
      <div class="section-heading"><p class="eyebrow">ESTUDIO 2 · 11 CONTRA 11</p><h3>Composición experimental</h3></div>
      <div class="team-grid"><article><h4>Synthetic XI</h4><div id="synthetic-team"></div></article><article><h4>Real Best XI</h4><div id="real-team"></div></article></div>
    </section>

    <section class="method-section">
      <div class="section-heading"><p class="eyebrow">MÉTODO PRE-REGISTRADO</p><h3>Decisiones fijadas antes de observar resultados</h3></div>
      <div class="method-grid">
        <article><span>01</span><h4>Top 20</h4><p>Análisis principal, con Top 10 y Top 30 como sensibilidad.</p></article>
        <article><span>02</span><h4>180 minutos</h4><p>Umbral mínimo y retracción por confiabilidad.</p></article>
        <article><span>03</span><h4>Media robusta</h4><p>Centroide con recorte del 10% e intervalo bootstrap.</p></article>
        <article><span>04</span><h4>Once completo</h4><p>1 GK, 2 CB, 2 FB, 1 DM, 1 CM, 1 AM, 2 W y 1 ST.</p></article>
      </div>
      <details><summary>Ver especificación metodológica</summary><pre>${JSON.stringify(methods, null, 2)}</pre></details>
    </section>
  </main>
  <footer>Versión ${manifest.project_version ?? '0.3.0'} · ${fixtures.length} partidos archivados · Estudio redactado en español</footer>
`;

const statusPanel = document.querySelector('#status-panel');
if (!avatars.length) {
  statusPanel.innerHTML = `<div class="setup-panel"><div class="pulse-ring"></div><div><p class="eyebrow">PIPELINE LISTO · SIN DATOS INVENTADOS</p><h3>Falta ejecutar el primer snapshot real.</h3><p>El código ya genera avatares, benchmarks, comparaciones y dos onces. La clave debe guardarse como secret de GitHub, nunca en el navegador.</p><code>API_FOOTBALL_KEY → GitHub → Settings → Secrets and variables → Actions</code></div></div>`;
} else {
  statusPanel.innerHTML = `<div class="data-strip"><div><span>FUENTE</span><strong>${manifest.source}</strong></div><div><span>CORTE</span><strong>${snapshot}</strong></div><div><span>JUGADORES-PARTIDO</span><strong>${manifest.starter_player_match_rows}</strong></div><div><span>REGLA</span><strong>Top ${manifest.requested_top_n} por posición</strong></div></div>`;
}

let radarChart;
function renderAvatar(avatar) {
  const subset = metrics.filter((row) => row.avatar_id === avatar.avatar_id);
  const selectedMembers = members.filter((row) => row.avatar_id === avatar.avatar_id).sort((a, b) => a.position_rank - b.position_rank);
  const benchmark = benchmarks.find((row) => row.position_group === avatar.position_group);
  const positionComparisons = comparisons.filter((row) => row.position_group === avatar.position_group);

  document.querySelector('#avatar-title').textContent = avatar.avatar_id;
  document.querySelector('#avatar-subtitle').textContent = avatar.interpretation_label;
  document.querySelector('#benchmark-line').textContent = benchmark ? `Mejor real actual: ${benchmark.player_name} · ${benchmark.team_name} · índice ${fmt(benchmark.rank_score)}` : '';
  document.querySelector('#sample-seal').innerHTML = `<strong>${avatar.actual_n}</strong><span>de ${avatar.requested_top_n}</span>`;

  document.querySelector('#metric-table').innerHTML = subset.map((metric) => {
    const comparison = positionComparisons.find((row) => row.metric === metric.metric);
    const leader = comparison ? (comparison.descriptive_leader === 'avatar' ? 'Avatar' : comparison.descriptive_leader === 'jugador_real' ? 'Real' : 'Empate') : '—';
    return `<div class="metric-row"><div><strong>${metricLabel(metric.metric)}</strong><span>IC95 ${fmt(metric.ci95_low)}–${fmt(metric.ci95_high)} · líder descriptivo: ${leader}</span></div><b>${fmt(metric.mean)}</b></div>`;
  }).join('');

  const ctx = document.querySelector('#radar');
  if (radarChart) radarChart.destroy();
  radarChart = new Chart(ctx, {
    type: 'radar',
    data: { labels: subset.map((row) => metricLabel(row.metric)), datasets: [{ data: subset.map((row) => row.position_percentile), borderWidth: 2, pointRadius: 3, borderColor: '#ff5c35', backgroundColor: 'rgba(255, 92, 53, .18)', pointBackgroundColor: '#ff5c35' }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { r: { min: 0, max: 100, ticks: { display: false, stepSize: 20 }, grid: { color: 'rgba(255,255,255,.12)' }, angleLines: { color: 'rgba(255,255,255,.1)' }, pointLabels: { color: '#cbd0d8', font: { size: 11 } } } } },
  });

  document.querySelector('#members-body').innerHTML = selectedMembers.slice(0, 20).map((row) => `<tr><td>${row.position_rank}</td><td>${row.player_name}</td><td>${row.team_name}</td><td>${fmt(row.minutes)}</td><td>${fmt(row.rank_score)}</td><td>${Math.round((row.reliability ?? 0) * 100)}%</td></tr>`).join('');
  document.querySelectorAll('.avatar-button').forEach((button) => button.classList.toggle('active', button.dataset.id === avatar.avatar_id));
}

if (avatars.length) {
  document.querySelector('#avatar-buttons').innerHTML = avatars.map((avatar) => `<button class="avatar-button" data-id="${avatar.avatar_id}"><strong>${avatar.position_group}</strong><span>${avatar.actual_n} elegibles</span></button>`).join('');
  document.querySelectorAll('.avatar-button').forEach((button) => button.addEventListener('click', () => renderAvatar(avatars.find((avatar) => avatar.avatar_id === button.dataset.id))));
  renderAvatar(avatars[0]);
}

function teamRows(team) {
  return team.map((row) => `<div class="team-row"><strong>${row.slot}</strong><span>${row.entity_name ?? 'sin dato'}</span><small>${row.team_name ?? row.position_group}</small></div>`).join('');
}
if (syntheticXI.length) {
  document.querySelector('#synthetic-team').innerHTML = teamRows(syntheticXI);
  document.querySelector('#real-team').innerHTML = teamRows(realXI);
}
