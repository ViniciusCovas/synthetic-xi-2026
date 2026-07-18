const replayState = {
  data: null,
  replay: null,
  minute: 0,
  playing: false,
  timer: null,
  voice: true,
  lastEventIndex: -1,
};

const HOME_POSITIONS = [[.08,.5],[.24,.16],[.23,.38],[.23,.62],[.24,.84],[.38,.5],[.51,.34],[.55,.66],[.70,.17],[.70,.83],[.78,.5]];
const AWAY_POSITIONS = [[.92,.5],[.76,.16],[.77,.38],[.77,.62],[.76,.84],[.62,.5],[.49,.34],[.45,.66],[.30,.17],[.30,.83],[.22,.5]];

const clip = (value, low = 0, high = 1) => Math.max(low, Math.min(high, value));
const pad = (value) => String(value).padStart(2, '0');

function narration(event, mode, data) {
  const teamName = event.team === 'home' ? data.teams.home.name : data.teams.away.name;
  if (mode === 'emotional') {
    if (event.type === 'goal') return `¡Gooooool! ¡${event.actor} marca para ${teamName} en el minuto ${event.minute}!`;
    if (event.type === 'shot_on_target') return `¡Atención! ${event.actor} saca el disparo y aparece una gran atajada.`;
    if (event.type === 'shot_off_target') return `¡La tuvo ${event.actor}! El balón se escapa por muy poco.`;
    return `¡Presión total! ${event.actor} no logra conservar la pelota.`;
  }
  if (mode === 'analytical') {
    if (event.type === 'goal') return `Minuto ${event.minute}. Conversión de ${event.actor} para ${teamName}; la ocasión tenía xG ${Number(event.xg).toFixed(2)}.`;
    if (event.type === 'shot_on_target') return `Minuto ${event.minute}. Remate a puerta de ${event.actor}, xG ${Number(event.xg).toFixed(2)}, neutralizado por el portero.`;
    if (event.type === 'shot_off_target') return `Minuto ${event.minute}. Finalización de ${event.actor} con xG ${Number(event.xg).toFixed(2)}; no encuentra portería.`;
    return `Minuto ${event.minute}. Pérdida de ${event.actor} en zona ${event.zone}; la posesión cambia de equipo.`;
  }
  if (event.type === 'goal') return `Minuto ${event.minute}. Gol de ${event.actor} para ${teamName}.`;
  if (event.type === 'shot_on_target') return `Minuto ${event.minute}. ${event.actor} remata a portería y el guardameta responde.`;
  if (event.type === 'shot_off_target') return `Minuto ${event.minute}. El disparo de ${event.actor} se marcha fuera.`;
  return `Minuto ${event.minute}. ${event.actor} pierde la posesión bajo presión.`;
}

function enrichReplay(replay, data) {
  let home = 0;
  let away = 0;
  return {
    ...replay,
    events: replay.events.map((event, index) => {
      if (event.type === 'goal') {
        if (event.team === 'home') home += 1;
        else away += 1;
      }
      const laneSeed = ([...event.actor].reduce((sum, char) => sum + char.charCodeAt(0), 0) + event.minute) % 3;
      const direction = event.team === 'home' ? 1 : -1;
      const zoneX = {1: .63, 2: .76, 3: .88}[event.zone] ?? .70;
      const endX = direction === 1 ? zoneX : 1 - zoneX;
      const endY = [.25, .50, .75][laneSeed];
      const startX = .50 - .10 * direction;
      const startY = .50 + (laneSeed - 1) * .13;
      return {
        ...event,
        id: index + 1,
        second: (event.minute * 37 + event.actor.length * 11) % 60,
        scoreAfter: {home, away},
        motion: {
          start: {x: startX, y: startY},
          control: {x: (startX + endX) / 2, y: (startY + endY) / 2 - .08},
          end: {x: endX, y: endY},
        },
        narration: {
          neutral: narration(event, 'neutral', data),
          emotional: narration(event, 'emotional', data),
          analytical: narration(event, 'analytical', data),
        },
      };
    }),
  };
}

function renderShell(container) {
  container.innerHTML = `
    <div class="replay-heading">
      <div><p class="eyebrow">SIMULADOR CALIBRADO · EXPERIENCIA 2D</p><h3>Ver el partido que nunca existió</h3><p>Un replay probabilístico con narración automática y universos alternativos.</p></div>
      <div class="replay-live"><span></span> MOTOR v0.2</div>
    </div>
    <div class="replay-layout">
      <article class="replay-stage">
        <div class="replay-scoreboard">
          <div><span>Synthetic XI</span><strong id="replay-home-score">0</strong></div>
          <div class="replay-clock"><b id="replay-clock">00:00</b><small id="replay-phase">PREPARTIDO</small></div>
          <div class="away"><strong id="replay-away-score">0</strong><span>Real Best XI</span></div>
        </div>
        <div class="replay-canvas-wrap"><canvas id="replay-canvas" width="1200" height="740"></canvas><div id="replay-event-title" class="replay-event-title"></div></div>
        <div class="replay-controls">
          <button id="replay-play" class="replay-button primary">▶ Reproducir</button>
          <button id="replay-reset" class="replay-button">↺</button>
          <input id="replay-timeline" type="range" min="0" max="90" step=".1" value="0">
          <select id="replay-mode"><option value="neutral">Narración neutra</option><option value="emotional">Narración emocional</option><option value="analytical">Narración analítica</option></select>
          <button id="replay-voice" class="replay-button">🔊 ON</button>
        </div>
        <div class="replay-stats"><div><span>xG</span><strong id="replay-xg">—</strong></div><div><span>Chutes</span><strong id="replay-shots">—</strong></div><div><span>A puerta</span><strong id="replay-sot">—</strong></div><div><span>Posesión</span><strong id="replay-possession">—</strong></div></div>
      </article>
      <aside class="replay-side">
        <div class="replay-probabilities" id="replay-probabilities"></div>
        <div class="replay-tabs" id="replay-tabs"></div>
        <div class="replay-feed" id="replay-feed"></div>
        <p id="replay-note" class="replay-note"></p>
      </aside>
    </div>`;
}

function bezier(a, control, b, t) {
  const u = 1 - t;
  return {x: u*u*a.x + 2*u*t*control.x + t*t*b.x, y: u*u*a.y + 2*u*t*control.y + t*t*b.y};
}

function drawPitch(canvas, currentEvent, progress) {
  const ctx = canvas.getContext('2d');
  const {width: w, height: h} = canvas;
  ctx.clearRect(0, 0, w, h);
  const gradient = ctx.createLinearGradient(0, 0, w, 0);
  gradient.addColorStop(0, '#184b35'); gradient.addColorStop(.5, '#123f2f'); gradient.addColorStop(1, '#184b35');
  ctx.fillStyle = gradient; ctx.fillRect(0, 0, w, h);
  for (let i = 0; i < 10; i += 1) {ctx.fillStyle = i % 2 ? 'rgba(255,255,255,.012)' : 'rgba(0,0,0,.025)'; ctx.fillRect(i*w/10, 0, w/10, h);}
  ctx.strokeStyle = 'rgba(255,255,255,.76)'; ctx.lineWidth = 3;
  ctx.strokeRect(34, 34, w-68, h-68); ctx.beginPath(); ctx.moveTo(w/2, 34); ctx.lineTo(w/2, h-34); ctx.stroke();
  ctx.beginPath(); ctx.arc(w/2, h/2, 82, 0, Math.PI*2); ctx.stroke();
  ctx.strokeRect(34, h*.25, w*.16, h*.5); ctx.strokeRect(w-34-w*.16, h*.25, w*.16, h*.5);
  ctx.strokeRect(34, h*.37, w*.065, h*.26); ctx.strokeRect(w-34-w*.065, h*.37, w*.065, h*.26);
  [['home','#4ab7ff',HOME_POSITIONS],['away','#ff7654',AWAY_POSITIONS]].forEach(([, color, positions]) => positions.forEach((position, index) => {
    const x = position[0] * w; const y = position[1] * h;
    ctx.beginPath(); ctx.arc(x, y, 12, 0, Math.PI*2); ctx.fillStyle = color; ctx.fill(); ctx.strokeStyle = '#071018'; ctx.lineWidth = 3; ctx.stroke();
    ctx.fillStyle = '#fff'; ctx.font = '700 10px sans-serif'; ctx.textAlign = 'center'; ctx.fillText(index + 1, x, y + 4);
  }));
  if (currentEvent) {
    const start = {x: currentEvent.motion.start.x*w, y: currentEvent.motion.start.y*h};
    const control = {x: currentEvent.motion.control.x*w, y: currentEvent.motion.control.y*h};
    const end = {x: currentEvent.motion.end.x*w, y: currentEvent.motion.end.y*h};
    const ball = bezier(start, control, end, progress);
    ctx.beginPath(); ctx.arc(ball.x, ball.y, 8, 0, Math.PI*2); ctx.fillStyle = '#fff'; ctx.shadowColor = '#fff'; ctx.shadowBlur = 12; ctx.fill(); ctx.shadowBlur = 0;
  }
}

function speak(text) {
  if (!replayState.voice || !('speechSynthesis' in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'es-MX'; utterance.rate = 1.08;
  window.speechSynthesis.speak(utterance);
}

function stop() {
  replayState.playing = false;
  clearInterval(replayState.timer);
  const button = document.querySelector('#replay-play');
  if (button) button.textContent = '▶ Reproducir';
}

function populateReplay() {
  const {data, replay} = replayState;
  const p = data.probabilities;
  document.querySelector('#replay-probabilities').innerHTML = `<h4>Probabilidad antes del partido</h4><div><span><b>${(p.synthetic_win*100).toFixed(1)}%</b>SYN</span><span><b>${(p.draw*100).toFixed(1)}%</b>EMPATE</span><span><b>${(p.real_win*100).toFixed(1)}%</b>REAL XI</span></div>`;
  document.querySelector('#replay-tabs').innerHTML = data.replays.map(item => `<button class="replay-tab ${item.id === replay.id ? 'active' : ''}" data-id="${item.id}">${item.label}</button>`).join('');
  const mode = document.querySelector('#replay-mode').value;
  document.querySelector('#replay-feed').innerHTML = replay.events.map(event => `<article class="replay-card"><span>${pad(event.minute)}:${pad(event.second)} · ${event.actor}</span><p>${event.narration[mode]}</p></article>`).join('');
  const s = replay.stats;
  document.querySelector('#replay-xg').textContent = `${s.home_xg.toFixed(2)} — ${s.away_xg.toFixed(2)}`;
  document.querySelector('#replay-shots').textContent = `${s.home_shots} — ${s.away_shots}`;
  document.querySelector('#replay-sot').textContent = `${s.home_shots_on_target} — ${s.away_shots_on_target}`;
  document.querySelector('#replay-possession').textContent = `${(s.home_possession*100).toFixed(1)}% — ${((1-s.home_possession)*100).toFixed(1)}%`;
  document.querySelector('#replay-note').textContent = `${replay.description} · ${(replay.scoreline_probability*100).toFixed(2)}% de las simulaciones. ${data.methodological_note}`;
  document.querySelectorAll('.replay-tab').forEach(button => button.addEventListener('click', () => {
    stop(); replayState.replay = data.replays.find(item => item.id === button.dataset.id); replayState.minute = 0; replayState.lastEventIndex = -1; document.querySelector('#replay-timeline').value = 0; populateReplay(); renderFrame();
  }));
}

function renderFrame() {
  const replay = replayState.replay;
  const minute = replayState.minute;
  const occurred = replay.events.filter(event => event.minute <= minute);
  const last = occurred.at(-1);
  const upcoming = replay.events.find(event => event.minute >= minute) || last;
  let progress = 0;
  if (upcoming) {const startMinute = Math.max(0, upcoming.minute - 3); progress = clip((minute-startMinute) / Math.max(1, upcoming.minute-startMinute));}
  drawPitch(document.querySelector('#replay-canvas'), upcoming, progress);
  document.querySelector('#replay-home-score').textContent = last?.scoreAfter.home ?? 0;
  document.querySelector('#replay-away-score').textContent = last?.scoreAfter.away ?? 0;
  document.querySelector('#replay-clock').textContent = `${pad(Math.floor(minute))}:${pad(Math.floor((minute%1)*60))}`;
  document.querySelector('#replay-phase').textContent = minute < 45 ? 'PRIMER TIEMPO' : minute < 90 ? 'SEGUNDO TIEMPO' : 'FINAL';
  document.querySelectorAll('.replay-card').forEach((card, index) => card.classList.toggle('active', index === occurred.length-1));
  if (occurred.length-1 > replayState.lastEventIndex) {
    replayState.lastEventIndex = occurred.length-1;
    if (last) {
      const mode = document.querySelector('#replay-mode').value;
      const title = document.querySelector('#replay-event-title');
      title.innerHTML = `${last.narration[mode]}<small>${last.type === 'turnover' ? 'CAMBIO DE POSESIÓN' : `xG ${Number(last.xg).toFixed(2)}`}</small>`;
      title.classList.add('show'); setTimeout(() => title.classList.remove('show'), 2500); speak(last.narration[mode]);
    }
  }
}

export async function mountReplayBroadcast(container) {
  renderShell(container);
  const response = await fetch('/data/replay_package.json', {cache: 'no-store'});
  if (!response.ok) {container.innerHTML = '<div class="setup-panel"><p>No fue posible cargar el replay probabilístico.</p></div>'; return;}
  const data = await response.json();
  data.replays = data.replays.map(replay => enrichReplay(replay, data));
  replayState.data = data; replayState.replay = data.replays[0];
  populateReplay(); renderFrame();
  document.querySelector('#replay-play').addEventListener('click', () => {
    if (replayState.playing) {stop(); return;}
    replayState.playing = true; document.querySelector('#replay-play').textContent = '⏸ Pausar';
    replayState.timer = setInterval(() => {replayState.minute += .18; document.querySelector('#replay-timeline').value = replayState.minute; if (replayState.minute >= 90) {replayState.minute = 90; stop();} renderFrame();}, 70);
  });
  document.querySelector('#replay-reset').addEventListener('click', () => {stop(); replayState.minute = 0; replayState.lastEventIndex = -1; document.querySelector('#replay-timeline').value = 0; window.speechSynthesis?.cancel(); renderFrame();});
  document.querySelector('#replay-timeline').addEventListener('input', event => {replayState.minute = Number(event.target.value); replayState.lastEventIndex = replayState.replay.events.filter(item => item.minute <= replayState.minute).length - 2; renderFrame();});
  document.querySelector('#replay-mode').addEventListener('change', () => {populateReplay(); renderFrame();});
  document.querySelector('#replay-voice').addEventListener('click', () => {replayState.voice = !replayState.voice; document.querySelector('#replay-voice').textContent = `🔊 ${replayState.voice ? 'ON' : 'OFF'}`; if (!replayState.voice) window.speechSynthesis?.cancel();});
}
