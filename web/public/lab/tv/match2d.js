/* Match2D v2 — "parece um jogo": bonecos vetoriais animados, pressão
 * defensiva, desmarques e câmara que segue a bola.
 *
 * O motor científico decide OS LANCES; este animador coreografa movimento
 * plausível entre eles e converge sempre para o lance seguinte (o autor
 * recebe a bola antes do seu remate). Nada do que o motor decidiu é alterado.
 *
 * API: Match2D.mount(canvas, cfg) · Match2D.event(evt) · Match2D.setClock(m)
 */
(function () {
  const PITCH = { w: 105, h: 68 };
  const ANCHOR = {
    GK: [5, 34], CB1: [18, 24], CB2: [18, 44], FB1: [22, 8], FB2: [22, 60],
    DM: [34, 34], CM: [45, 22], AM: [45, 46], W1: [62, 10], W2: [62, 58], ST: [64, 34],
  };
  const RANGE = { GK: 2.5, CB1: 8, CB2: 8, FB1: 15, FB2: 15, DM: 12, CM: 14, AM: 14, W1: 16, W2: 16, ST: 14 };
  const RUNNERS = ['W1', 'W2', 'ST', 'AM'];

  const S = {
    canvas: null, ctx: null, players: [], ball: { x: 52.5, y: 34, z: 0 },
    possession: 'home', carrier: null, target: null, phase: 'build', phaseT: 0,
    pending: null, celebrating: 0, rng: mulberry(20260719),
    cam: { x: 52.5, y: 34, zoom: 1.0, tzoom: 1.18 },
    kit: {
      home: { shirt: '#0F7A57', shorts: '#FAF8F4', gk: '#C2872C' },
      away: { shirt: '#3D4DBE', shorts: '#15181D', gk: '#7A3D8F' },
    },
  };

  function mulberry(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  const rnd = (lo, hi) => lo + (hi - lo) * S.rng();
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const short = (n) => { const p = String(n).split(' '); return p[p.length - 1]; };
  const mirror = ([x, y]) => [PITCH.w - x, PITCH.h - y];
  const other = (s) => (s === 'home' ? 'away' : 'home');
  const attackX = (s) => (s === 'home' ? PITCH.w - 2 : 2);

  function mount(canvas, cfg) {
    S.canvas = canvas; S.ctx = canvas.getContext('2d');
    S.players = [];
    for (const side of ['home', 'away']) {
      for (const p of cfg[side + 'XI']) {
        const a = side === 'home' ? ANCHOR[p.role] : mirror(ANCHOR[p.role]);
        S.players.push({
          side, role: p.role, name: short(p.name),
          x: a[0], y: a[1], ax: a[0], ay: a[1], tx: a[0], ty: a[1],
          vx: 0, vy: 0, anim: rnd(0, 6), face: side === 'home' ? 1 : -1,
          maxv: p.role === 'GK' ? 6 : 7.4, card: null, cardT: 0, runT: 0,
        });
      }
    }
    kickoff('home');
    requestAnimationFrame(loop);
  }

  const teamOf = (s) => S.players.filter((p) => p.side === s);
  const byName = (s, actor) => teamOf(s).find((p) => actor && actor.includes(p.name)) || null;

  function kickoff(side) {
    S.possession = side; S.phase = 'build'; S.phaseT = 0; S.pending = S.pending;
    S.ball = { x: 52.5, y: 34, z: 0 };
    S.carrier = teamOf(side).find((p) => p.role === 'ST');
    for (const p of S.players) { p.tx = p.ax; p.ty = p.ay; }
    if (S.carrier) { S.carrier.tx = 52.5; S.carrier.ty = 34; }
  }

  // ---------- eventos do motor ----------
  function event(evt) {
    const h = evt.headline || '';
    const side = evt.side === 'away' ? 'away' : 'home';
    if (/^GOL/i.test(h)) S.pending = { kind: 'goal', side, actor: evt.actor };
    else if (/defendeu|Grande chance|para fora/i.test(h)) S.pending = { kind: 'shot', side, actor: evt.actor };
    else if (/amarelo|expuls/i.test(h)) card(side, evt.actor, /expuls/i.test(h) ? 'red' : 'yellow');
    else if (/Substitui/i.test(h)) card(side, null, 'sub');
    else if (/Intervalo|Final/i.test(h)) kickoff(other(S.possession));
  }
  function setClock() {}
  function card(side, actor, kind) {
    const p = byName(side, actor) || teamOf(side)[Math.floor(rnd(3, 10))];
    p.card = kind; p.cardT = 3.4;
  }

  // ---------- comportamento ----------
  function assignTargets(dt) {
    const att = S.possession, def = other(att);
    const goal = [attackX(att), 34];
    const shift = (S.ball.x - 52.5) * 0.35;

    // pressão: os dois defensores de linha mais próximos caçam
    const defenders = teamOf(def).filter((p) => p.role !== 'GK')
      .sort((a, b) => dist(a, S.ball) - dist(b, S.ball));
    const presser = defenders[0], cover = defenders[1];
    if (presser) { presser.tx = S.ball.x; presser.ty = S.ball.y; presser.maxv = 8.2; }
    if (cover) {
      cover.tx = (S.ball.x + attackX(def)) / 2 + rnd(-2, 2);
      cover.ty = (S.ball.y + 34) / 2 + rnd(-2, 2);
      cover.maxv = 7.8;
    }
    for (const p of S.players) {
      if (p === S.carrier || p === presser || p === cover) continue;
      p.maxv = p.role === 'GK' ? 6 : 7.2;
      const dir = p.side === 'home' ? 1 : -1;
      const back = p.side === def ? dir * -6 : 0;     // bloco defensivo recua
      const bx = clamp(p.ax + dir * shift + back, 3, 102);
      // desmarque: atacantes avançados arrancam periodicamente
      if (p.side === att && RUNNERS.includes(p.role)) {
        p.runT -= dt;
        if (p.runT <= 0) {
          p.runT = rnd(2.5, 5);
          p.tx = clamp(goal[0] + (att === 'home' ? -rnd(4, 14) : rnd(4, 14)), 4, 101);
          p.ty = clamp(34 + rnd(-22, 22), 4, 64);
          continue;
        }
      }
      if (Math.hypot(p.tx - p.x, p.ty - p.y) < 1.4) {
        const r = RANGE[p.role];
        p.tx = clamp(bx + rnd(-r * 0.45, r * 0.45), 2, 103);
        p.ty = clamp(p.ay + rnd(-r * 0.4, r * 0.4), 2, 66);
      }
    }
    // portador: conduz ao gol fugindo do pressionador
    if (S.carrier && S.phase === 'build') {
      let fx = Math.sign(goal[0] - S.carrier.x) * 4.5, fy = (34 - S.carrier.y) * 0.06;
      if (presser) {
        const d = Math.max(1.5, dist(S.carrier, presser));
        fx += (S.carrier.x - presser.x) / d * 3.2;
        fy += (S.carrier.y - presser.y) / d * 3.2;
      }
      S.carrier.tx = clamp(S.carrier.x + fx, 3, 102);
      S.carrier.ty = clamp(S.carrier.y + fy, 3, 65);
      S.carrier.maxv = 6.4;
      // pressão bem-sucedida ocasional: turnover natural
      if (presser && dist(S.carrier, presser) < 1.6 && !S.pending && S.rng() < 0.012) {
        S.possession = def; S.carrier = presser; S.phase = 'build'; S.phaseT = 0;
      }
    }
  }
  const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

  function chooseReceiver() {
    const fwd = attackX(S.possession);
    const mates = teamOf(S.possession).filter((p) => p !== S.carrier && p.role !== 'GK')
      .sort((a, b) => Math.abs(a.x - fwd) - Math.abs(b.x - fwd));
    return mates[Math.min(mates.length - 1, Math.floor(rnd(0, 4)))];
  }
  function passTo(t) {
    S.target = t; S.phase = 'pass'; S.phaseT = 0;
    S.ball.px = S.ball.x; S.ball.py = S.ball.y;
    S.ball.dur = clamp(dist(S.ball, t) / 26, 0.35, 0.9);
  }

  function step(dt) {
    S.phaseT += dt;
    if (S.celebrating > 0) { S.celebrating -= dt; movePlayers(dt); return; }

    if (S.pending && S.phase === 'build' && S.phaseT > 0.45) {
      const target = byName(S.pending.side, S.pending.actor);
      if (S.possession !== S.pending.side) {
        S.possession = S.pending.side;
        S.carrier = target || teamOf(S.pending.side)[6];
        S.phaseT = 0;
      } else if (target && S.carrier !== target) passTo(target);
      else { S.phase = 'shoot'; S.phaseT = 0; S.ball.px = S.ball.x; S.ball.py = S.ball.y; }
    } else if (S.phase === 'build' && S.phaseT > rnd(0.8, 1.5)) {
      passTo(chooseReceiver());
    }

    if (S.phase === 'pass') {
      const t = Math.min(1, S.phaseT / S.ball.dur);
      const e = ease(t);
      S.ball.x = S.ball.px + (S.target.x - S.ball.px) * e;
      S.ball.y = S.ball.py + (S.target.y - S.ball.py) * e;
      S.ball.z = Math.sin(t * Math.PI) * (S.ball.dur > 0.6 ? 2.4 : 0.8);
      S.target.tx = S.target.x; S.target.ty = S.target.y;  // receptor espera
      if (t >= 1) { S.carrier = S.target; S.phase = 'build'; S.phaseT = 0; }
    } else if (S.phase === 'shoot') {
      const g = [attackX(S.possession), 34 + rnd(-3.2, 3.2)];
      const gk = teamOf(other(S.possession)).find((p) => p.role === 'GK');
      const t = Math.min(1, S.phaseT / 0.45);
      S.ball.x = S.ball.px + (g[0] - S.ball.px) * t;
      S.ball.y = S.ball.py + (g[1] - S.ball.py) * t;
      S.ball.z = Math.sin(t * Math.PI) * 1.2;
      if (gk) { gk.tx = g[0]; gk.ty = S.ball.y; gk.maxv = 9; } // mergulho
      if (t >= 1) {
        const wasGoal = S.pending && S.pending.kind === 'goal';
        const side = S.possession;
        S.pending = null;
        if (wasGoal) {
          S.celebrating = 2.4;
          const scorer = S.carrier;
          for (const p of teamOf(side)) { p.tx = clamp(scorer.x + rnd(-6, 6), 4, 101); p.ty = clamp(scorer.y + rnd(-5, 5), 4, 64); }
          setTimeout(() => kickoff(other(side)), 2400);
        } else {
          S.possession = other(side); S.phase = 'build'; S.phaseT = 0;
          S.carrier = gk || teamOf(S.possession)[0];
          S.ball.z = 0;
        }
      }
    } else {
      assignTargets(dt);
      if (S.carrier) {
        const spd = Math.hypot(S.carrier.vx, S.carrier.vy);
        S.ball.x = S.carrier.x + (spd > 0.5 ? S.carrier.vx / spd : S.carrier.face) * 1.1;
        S.ball.y = S.carrier.y + (spd > 0.5 ? S.carrier.vy / spd : 0) * 1.1;
        S.ball.z = 0;
      }
    }
    movePlayers(dt);
    // câmara persegue a bola
    S.cam.x += (S.ball.x - S.cam.x) * Math.min(1, dt * 2.4);
    S.cam.y += (S.ball.y - S.cam.y) * Math.min(1, dt * 2.4);
    S.cam.zoom += (S.cam.tzoom - S.cam.zoom) * Math.min(1, dt * 1.5);
  }

  function movePlayers(dt) {
    for (const p of S.players) {
      const dx = p.tx - p.x, dy = p.ty - p.y, d = Math.hypot(dx, dy);
      const want = d > 0.3 ? Math.min(p.maxv, d * 3) : 0;
      const ux = d > 0.01 ? dx / d : 0, uy = d > 0.01 ? dy / d : 0;
      p.vx += (ux * want - p.vx) * Math.min(1, dt * 5);
      p.vy += (uy * want - p.vy) * Math.min(1, dt * 5);
      p.x = clamp(p.x + p.vx * dt, 1.5, PITCH.w - 1.5);
      p.y = clamp(p.y + p.vy * dt, 1.5, PITCH.h - 1.5);
      const spd = Math.hypot(p.vx, p.vy);
      p.anim += spd * dt * 1.6;
      if (Math.abs(p.vx) > 0.6) p.face = Math.sign(p.vx);
      if (p.cardT > 0) p.cardT -= dt; else if (p.card !== 'red') p.card = null;
    }
  }
  const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);

  // ---------- desenho ----------
  let last = 0;
  function loop(ts) {
    const dt = Math.min(0.05, (ts - last) / 1000 || 0.016); last = ts;
    step(dt); draw();
    requestAnimationFrame(loop);
  }

  function view() {
    const vw = PITCH.w / S.cam.zoom, vh = PITCH.h / S.cam.zoom;
    const cx = clamp(S.cam.x, vw / 2, PITCH.w - vw / 2);
    const cy = clamp(S.cam.y, vh / 2, PITCH.h - vh / 2);
    const k = S.canvas.width / vw;
    return { k, ox: cx - vw / 2, oy: cy - vh / 2 };
  }

  function draw() {
    const { ctx, canvas } = S;
    const { k, ox, oy } = view();
    const X = (u) => (u - ox) * k, Y = (u) => (u - oy) * k;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // relvado
    for (let i = 0; i < 12; i++) {
      ctx.fillStyle = i % 2 ? '#DDEBDF' : '#D3E4D6';
      ctx.fillRect(X(i * PITCH.w / 12), Y(0), (PITCH.w / 12) * k + 1, PITCH.h * k);
    }
    ctx.strokeStyle = '#FFFFFF'; ctx.globalAlpha = 0.85;
    ctx.lineWidth = Math.max(1.5, k * 0.18);
    ctx.strokeRect(X(1), Y(1), (PITCH.w - 2) * k, (PITCH.h - 2) * k);
    ctx.beginPath(); ctx.moveTo(X(52.5), Y(1)); ctx.lineTo(X(52.5), Y(PITCH.h - 1)); ctx.stroke();
    ctx.beginPath(); ctx.arc(X(52.5), Y(34), 9 * k, 0, Math.PI * 2); ctx.stroke();
    for (const left of [true, false]) {
      const bx = left ? 1 : PITCH.w - 17.5;
      ctx.strokeRect(X(left ? 1 : PITCH.w - 17.5), Y(14), 16.5 * k, 40 * k);
      ctx.strokeRect(X(left ? 1 : PITCH.w - 6.5), Y(25), 5.5 * k, 18 * k);
      ctx.fillStyle = '#FFFFFF';
      ctx.fillRect(X(left ? 0.2 : PITCH.w - 0.9), Y(30.3), 0.7 * k, 7.4 * k);
      void bx;
    }
    ctx.globalAlpha = 1;

    // jogadores ordenados por y (profundidade)
    const sorted = [...S.players].sort((a, b) => a.y - b.y);
    for (const p of sorted) drawPlayer(p, X, Y, k);
    drawBall(X, Y, k);
  }

  function drawPlayer(p, X, Y, k) {
    const { ctx } = S;
    const x = X(p.x), y = Y(p.y), h = k * 3.1;      // altura do boneco
    const kit = S.kit[p.side], shirt = p.role === 'GK' ? kit.gk : kit.shirt;
    const run = Math.sin(p.anim * 6);
    const speed = Math.hypot(p.vx, p.vy);
    const legSwing = (speed > 0.8 ? run : 0) * h * 0.16;

    // anel do portador (no chão)
    if (p === S.carrier && S.celebrating <= 0) {
      ctx.beginPath(); ctx.ellipse(x, y + h * 0.06, h * 0.42, h * 0.17, 0, 0, Math.PI * 2);
      ctx.strokeStyle = '#FFD166'; ctx.lineWidth = Math.max(2, k * 0.28); ctx.stroke();
    }
    // sombra
    ctx.beginPath(); ctx.ellipse(x, y + h * 0.05, h * 0.3, h * 0.11, 0, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(21,24,29,.22)'; ctx.fill();

    ctx.save();
    ctx.translate(x, y);
    ctx.scale(p.face < 0 ? -1 : 1, 1);
    // pernas
    ctx.strokeStyle = '#20242B'; ctx.lineCap = 'round';
    ctx.lineWidth = h * 0.13;
    ctx.beginPath(); ctx.moveTo(-h * 0.09, -h * 0.32); ctx.lineTo(-h * 0.10 + legSwing, 0); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(h * 0.09, -h * 0.32); ctx.lineTo(h * 0.10 - legSwing, 0); ctx.stroke();
    // calção
    ctx.fillStyle = kit.shorts;
    rr(ctx, -h * 0.20, -h * 0.46, h * 0.40, h * 0.18, h * 0.05); ctx.fill();
    // tronco/camisa
    ctx.fillStyle = shirt;
    rr(ctx, -h * 0.22, -h * 0.78, h * 0.44, h * 0.36, h * 0.10); ctx.fill();
    // braços (balançam em oposição às pernas)
    ctx.strokeStyle = shirt; ctx.lineWidth = h * 0.11;
    ctx.beginPath(); ctx.moveTo(-h * 0.20, -h * 0.70); ctx.lineTo(-h * 0.26 - legSwing * 0.7, -h * 0.44); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(h * 0.20, -h * 0.70); ctx.lineTo(h * 0.26 + legSwing * 0.7, -h * 0.44); ctx.stroke();
    // cabeça
    ctx.beginPath(); ctx.arc(0, -h * 0.92, h * 0.17, 0, Math.PI * 2);
    ctx.fillStyle = '#C99B6F'; ctx.fill();
    ctx.restore();

    // nome
    ctx.textAlign = 'center';
    ctx.font = `600 ${Math.max(9, k * 0.95)}px Inter, sans-serif`;
    ctx.fillStyle = 'rgba(21,24,29,.78)';
    ctx.fillText(p.name, x, y + h * 0.42);
    // cartão
    if (p.card) {
      ctx.fillStyle = p.card === 'yellow' ? '#F2C230' : p.card === 'red' ? '#C0322B' : '#8A9099';
      ctx.fillRect(x - h * 0.09, y - h * 1.28, h * 0.18, h * 0.26);
    }
  }

  function rr(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }

  function drawBall(X, Y, k) {
    const { ctx } = S; const b = S.ball;
    ctx.beginPath(); ctx.ellipse(X(b.x), Y(b.y) + k * 0.5, k * 0.55, k * 0.22, 0, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(21,24,29,.25)'; ctx.fill();
    const r = k * 0.42 * (1 + b.z * 0.28);
    ctx.beginPath(); ctx.arc(X(b.x), Y(b.y) - b.z * k * 1.6, r, 0, Math.PI * 2);
    ctx.fillStyle = '#FFFFFF'; ctx.fill();
    ctx.lineWidth = Math.max(1, k * 0.1); ctx.strokeStyle = '#15181D'; ctx.stroke();
  }

  window.Match2D = { mount, event, setClock };
})();
