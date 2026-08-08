/* Match2D — animador tático 2D da final simulada.
 *
 * O motor científico decide OS LANCES (quem, quando, o quê); este animador
 * inventa movimento plausível ENTRE os lances — como o visualizador 2D do
 * Football Manager: formação viva, cadeias de passe, o autor do lance recebe
 * a bola antes do lance, remate com voo de bola, defesa do goleiro,
 * celebração e reinício. Nenhum lance é alterado: a coreografia converge
 * sempre para o evento seguinte da timeline.
 *
 * window.Match2D.mount(canvas, {homeName, awayName, homeXI, awayXI})
 * window.Match2D.setClock(minute)         — sincroniza com o relógio da TV
 * window.Match2D.event(evt)               — lance da timeline (headline, side, actor)
 */
(function () {
  const PITCH = { w: 105, h: 68 };
  // âncoras 4-3-3 (x: 0=própria baliza→105=baliza rival; y: 0 topo)
  const ANCHOR = {
    GK: [5, 34], CB1: [18, 24], CB2: [18, 44], FB1: [22, 8], FB2: [22, 60],
    DM: [34, 34], CM: [45, 22], AM: [45, 46], W1: [62, 10], W2: [62, 58], ST: [64, 34],
  };
  const ROLE_RANGE = { GK: 3, CB1: 9, CB2: 9, FB1: 16, FB2: 16, DM: 13, CM: 15, AM: 15, W1: 17, W2: 17, ST: 15 };

  const state = {
    canvas: null, ctx: null, players: [], ball: { x: 52.5, y: 34, z: 0 },
    possession: 'home', carrier: null, target: null, phase: 'kickoff',
    phaseT: 0, names: { home: '', away: '' }, colors: { home: '#0F7A57', away: '#3D4DBE' },
    pending: null, celebrating: 0, lastMinute: 0, rng: mulberry(20260719),
  };

  function mulberry(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  const rnd = (lo, hi) => lo + (hi - lo) * state.rng();
  const short = (n) => { const p = String(n).split(' '); return p[p.length - 1]; };

  function mirror([x, y]) { return [PITCH.w - x, PITCH.h - y]; }

  function mount(canvas, cfg) {
    state.canvas = canvas; state.ctx = canvas.getContext('2d');
    state.names = { home: cfg.homeName, away: cfg.awayName };
    state.players = [];
    for (const side of ['home', 'away']) {
      const xi = cfg[side + 'XI'];
      for (const p of xi) {
        const anchor = side === 'home' ? ANCHOR[p.role] : mirror(ANCHOR[p.role]);
        state.players.push({
          side, role: p.role, name: short(p.name),
          x: anchor[0], y: anchor[1], ax: anchor[0], ay: anchor[1],
          tx: anchor[0], ty: anchor[1], card: null, cardT: 0,
        });
      }
    }
    kickoff('home');
    requestAnimationFrame(loop);
  }

  function teamOf(side) { return state.players.filter((p) => p.side === side); }
  function byName(side, actor) {
    const team = teamOf(side);
    return team.find((p) => actor && actor.includes(p.name)) || null;
  }

  function kickoff(side) {
    state.possession = side; state.phase = 'build'; state.phaseT = 0;
    state.ball = { x: 52.5, y: 34, z: 0 };
    state.carrier = teamOf(side).find((p) => p.role === 'ST') || teamOf(side)[10];
  }

  // ---- direção de ataque de cada lado ----
  const attackX = (side) => (side === 'home' ? PITCH.w - 2 : 2);

  function chooseReceiver() {
    const team = teamOf(state.possession).filter((p) => p !== state.carrier && p.role !== 'GK');
    const forward = attackX(state.possession);
    // preferir quem está mais perto da baliza rival, com ruído
    team.sort((a, b) => Math.abs(a.x - forward) - Math.abs(b.x - forward));
    const k = Math.min(team.length - 1, Math.floor(rnd(0, 4)));
    return team[k];
  }

  // ---- eventos vindos da timeline do motor ----
  function event(evt) {
    const h = evt.headline || '';
    const side = evt.side === 'away' ? 'away' : 'home';
    if (/^GOL/i.test(h)) state.pending = { kind: 'goal', side, actor: evt.actor };
    else if (/defendeu|Grande chance/i.test(h)) state.pending = { kind: 'shot', side, actor: evt.actor };
    else if (/amarelo|expuls/i.test(h)) showCard(side, evt.actor, /expuls/i.test(h) ? 'red' : 'yellow');
    else if (/Substitui/i.test(h)) flashSub(side);
    else if (/Falta/i.test(h)) state.pending = { kind: 'foul', side, actor: evt.actor };
  }
  function setClock(minute) { state.lastMinute = minute; }

  function showCard(side, actor, kind) {
    const p = byName(side, actor) || teamOf(side)[Math.floor(rnd(3, 10))];
    p.card = kind; p.cardT = 3.2;
  }
  function flashSub(side) {
    const team = teamOf(side).filter((p) => p.role !== 'GK');
    const p = team[Math.floor(rnd(0, team.length))];
    p.card = 'sub'; p.cardT = 2.6;
  }

  // ---- laço de animação ----
  let last = 0;
  function loop(ts) {
    const dt = Math.min(0.05, (ts - last) / 1000 || 0.016); last = ts;
    step(dt); draw();
    requestAnimationFrame(loop);
  }

  function step(dt) {
    state.phaseT += dt;
    if (state.celebrating > 0) { state.celebrating -= dt; drift(dt, 0.4); return; }

    // fase orientada ao próximo lance do motor
    if (state.pending && state.phase === 'build' && state.phaseT > 0.5) {
      const target = byName(state.pending.side, state.pending.actor);
      if (state.possession !== state.pending.side) {
        // turnover rápido para o lado do lance
        state.possession = state.pending.side;
        state.carrier = target || teamOf(state.pending.side)[6];
      }
      if (target && state.carrier !== target) passTo(target);
      else if (state.pending.kind !== 'foul') { state.phase = 'shoot'; state.phaseT = 0; }
      else { state.pending = null; }                       // falta: segue o jogo
    } else if (state.phase === 'build' && state.phaseT > rnd(0.9, 1.6)) {
      passTo(chooseReceiver());
    }

    if (state.phase === 'pass') {
      const t = Math.min(1, state.phaseT / 0.55);
      state.ball.x = lerp(state.ball.px, state.target.x, t);
      state.ball.y = lerp(state.ball.py, state.target.y, t);
      state.ball.z = Math.sin(t * Math.PI) * rnd(0.5, 2.2);
      if (t >= 1) { state.carrier = state.target; state.phase = 'build'; state.phaseT = 0; }
    } else if (state.phase === 'shoot') {
      const goal = [attackX(state.possession), 34];
      const t = Math.min(1, state.phaseT / 0.5);
      state.ball.x = lerp(state.ball.px ?? state.ball.x, goal[0], t);
      state.ball.y = lerp(state.ball.py ?? state.ball.y, goal[1] + rnd(-3, 3), t);
      state.ball.z = Math.sin(t * Math.PI) * 1.4;
      if (t >= 1) {
        const wasGoal = state.pending && state.pending.kind === 'goal';
        const scorerSide = state.possession;
        state.pending = null;
        if (wasGoal) { state.celebrating = 2.6; celebrate(scorerSide); setTimeout(() => kickoff(other(scorerSide)), 2600); }
        else kickoff(other(scorerSide));                    // defesa/perdido: bola do rival
      }
    } else {
      // portador conduz ao ataque; bola cola no pé
      if (state.carrier) {
        state.carrier.tx = clamp(state.carrier.x + Math.sign(attackX(state.possession) - state.carrier.x) * rnd(2, 5), 3, 102);
        state.ball.x = state.carrier.x + (state.possession === 'home' ? 1 : -1);
        state.ball.y = state.carrier.y; state.ball.z = 0;
      }
      drift(dt, 1);
    }
    // guarda posição de partida do passe
    if (state.phase === 'pass' || state.phase === 'shoot') {
      if (state.ball.px === undefined) { state.ball.px = state.ball.x; state.ball.py = state.ball.y; }
    } else { delete state.ball.px; delete state.ball.py; }

    for (const p of state.players) {
      p.x += (p.tx - p.x) * Math.min(1, dt * 2.2);
      p.y += (p.ty - p.y) * Math.min(1, dt * 2.2);
      if (p.cardT > 0) p.cardT -= dt; else p.card = p.card === 'red' ? 'red' : null;
    }
  }

  function passTo(target) {
    state.target = target; state.phase = 'pass'; state.phaseT = 0;
    state.ball.px = state.ball.x; state.ball.py = state.ball.y;
  }
  function other(side) { return side === 'home' ? 'away' : 'home'; }
  function lerp(a, b, t) { return a + (b - a) * (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2); }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  function drift(dt, amp) {
    // a formação desliza com a bola; cada jogador orbita a âncora deslocada
    const shift = (state.ball.x - 52.5) * 0.35;
    for (const p of state.players) {
      if (p === state.carrier) continue;
      const range = ROLE_RANGE[p.role] * amp;
      const dir = p.side === 'home' ? 1 : -1;
      const bx = clamp(p.ax + dir * shift, 3, 102);
      if (Math.hypot(p.tx - p.x, p.ty - p.y) < 1.2) {
        p.tx = clamp(bx + rnd(-range * 0.45, range * 0.45), 2, 103);
        p.ty = clamp(p.ay + rnd(-range * 0.4, range * 0.4), 2, 66);
      }
    }
    if (state.carrier) void dt;
  }

  function celebrate(side) {
    const scorer = state.carrier;
    for (const p of teamOf(side)) {
      p.tx = clamp(scorer.x + rnd(-6, 6), 4, 101);
      p.ty = clamp(scorer.y + rnd(-6, 6), 4, 64);
    }
  }

  // ---- desenho ----
  function draw() {
    const { ctx, canvas } = state;
    const W = canvas.width, H = canvas.height;
    const sx = W / PITCH.w, sy = H / PITCH.h;
    ctx.clearRect(0, 0, W, H);

    // relvado com faixas
    for (let i = 0; i < 10; i++) {
      ctx.fillStyle = i % 2 ? '#EDF3EE' : '#E5EEE7';
      ctx.fillRect((i * PITCH.w / 10) * sx, 0, (PITCH.w / 10) * sx, H);
    }
    ctx.strokeStyle = '#C9DACD'; ctx.lineWidth = Math.max(1.5, sx * 0.22);
    const line = (x1, y1, x2, y2) => { ctx.beginPath(); ctx.moveTo(x1 * sx, y1 * sy); ctx.lineTo(x2 * sx, y2 * sy); ctx.stroke(); };
    ctx.strokeRect(1 * sx, 1 * sy, (PITCH.w - 2) * sx, (PITCH.h - 2) * sy);
    line(52.5, 1, 52.5, PITCH.h - 1);
    ctx.beginPath(); ctx.arc(52.5 * sx, 34 * sy, 9 * sx, 0, Math.PI * 2); ctx.stroke();
    for (const gx of [1, PITCH.w - 17.5]) {
      const x = gx === 1 ? 1 : PITCH.w - 17.5;
      ctx.strokeRect(x * sx, (34 - 20) * sy, 16.5 * sx, 40 * sy);
      ctx.strokeRect((gx === 1 ? 1 : PITCH.w - 6.5) * sx, (34 - 9) * sy, 5.5 * sx, 18 * sy);
    }

    // jogadores
    ctx.textAlign = 'center';
    for (const p of state.players) {
      const px = p.x * sx, py = p.y * sy, r = Math.max(7, sx * 1.15);
      ctx.beginPath(); ctx.ellipse(px, py + r * 0.55, r * 0.85, r * 0.32, 0, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(21,24,29,.14)'; ctx.fill();
      ctx.beginPath(); ctx.arc(px, py, r, 0, Math.PI * 2);
      ctx.fillStyle = state.colors[p.side]; ctx.fill();
      ctx.lineWidth = 2; ctx.strokeStyle = p === state.carrier ? '#FFD166' : 'rgba(255,255,255,.85)'; ctx.stroke();
      ctx.fillStyle = '#3A4A40'; ctx.font = `600 ${Math.max(9, sx * 1.05)}px Inter, sans-serif`;
      ctx.fillText(p.name, px, py + r + Math.max(10, sx * 1.2));
      if (p.card) {
        ctx.fillStyle = p.card === 'yellow' ? '#F2C230' : p.card === 'red' ? '#C0322B' : '#8A9099';
        ctx.fillRect(px - r * 0.35, py - r - Math.max(9, sx * 1.3), r * 0.7, r * 0.95);
      }
    }
    // bola
    const b = state.ball, bz = 1 + b.z * 0.35;
    ctx.beginPath(); ctx.ellipse(b.x * sx, (b.y + 0.8) * sy, 4.2 * bz * 0.8, 1.8, 0, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(21,24,29,.18)'; ctx.fill();
    ctx.beginPath(); ctx.arc(b.x * sx, b.y * sy - b.z * 8, Math.max(4, sx * 0.5) * bz, 0, Math.PI * 2);
    ctx.fillStyle = '#fff'; ctx.strokeStyle = '#15181D'; ctx.lineWidth = 1.4; ctx.fill(); ctx.stroke();
  }

  window.Match2D = { mount, event, setClock };
})();
