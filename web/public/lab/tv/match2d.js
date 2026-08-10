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
    const bg = new Image();
    bg.onload = () => { S.bg = bg; };
    bg.src = cfg.background || 'pitch-bg.png';
    if (cfg.kits) S.kit = cfg.kits;
    else if (window.TeamKits) S.kit = TeamKits.kitsFor(cfg.homeName, cfg.awayName);
    S.numbers = { home: cfg.homeNumbers || {}, away: cfg.awayNumbers || {} };
    S.players = [];
    for (const side of ['home', 'away']) {
      for (const p of cfg[side + 'XI']) {
        const a = side === 'home' ? ANCHOR[p.role] : mirror(ANCHOR[p.role]);
        S.players.push({
          side, role: p.role, name: short(p.name), num: p.number ?? '',
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
    else if (/defende|Grande chance|para fora/i.test(h)) S.pending = { kind: 'shot', side, actor: evt.actor };
    else if (/amarelo|expuls/i.test(h)) card(side, evt.actor, /expuls/i.test(h) ? 'red' : 'yellow');
    else if (/Substitui/i.test(h)) substitute(side, h);
    else if (/Intervalo|Final/i.test(h)) kickoff(other(S.possession));
  }
  function setClock() {}
  function card(side, actor, kind) {
    const p = byName(side, actor) || teamOf(side)[Math.floor(rnd(3, 10))];
    p.card = kind; p.cardT = 3.4;
  }
  function substitute(side, headline) {
    const m = headline.match(/sai (.+?), entra (.+)$/i);
    const leaving = m && byName(side, m[1]);
    if (!leaving) { card(side, null, 'sub'); return; }
    leaving.name = short(m[2]);
    leaving.num = S.numbers[side][m[2]] ?? '';
    leaving.card = 'sub'; leaving.cardT = 3.4;
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

  // ---------- desenho: perspectiva de transmissão ----------
  let last = 0;
  function loop(ts) {
    const dt = Math.min(0.05, (ts - last) / 1000 || 0.016); last = ts;
    step(dt); draw();
    requestAnimationFrame(loop);
  }

  // projeção: câmara elevada suave (topo ~78% da base, como transmissão real)
  // Calibrável via Match2D.tune({sTop,sBot,yTop,yBot,xScale}) para casar com
  // um fundo pintado (pitch-bg.png).
  const PROJ = { sTop: 0.80, sBot: 1.06, yTop: 0.05, yBot: 0.975, xScale: 0.0086, ease: 0.72 };
  function persp(u, v) {
    const W = S.canvas.width, H = S.canvas.height;
    const t = v / PITCH.h;
    const s = PROJ.sTop + (PROJ.sBot - PROJ.sTop) * t;
    const y = H * PROJ.yTop + H * (PROJ.yBot - PROJ.yTop) * (t * (PROJ.ease + (1 - PROJ.ease) * t));
    const x = W / 2 + (u - 52.5) * (W * PROJ.xScale) * s;
    return [x, y, s];
  }
  const metre = (s) => S.canvas.width * PROJ.xScale * s;

  function sampled(points) {
    const { ctx } = S;
    ctx.beginPath();
    points.forEach(([u, v], i) => {
      const [x, y] = persp(u, v);
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
  }
  function seg(u1, v1, u2, v2, n = 10) {
    const pts = [];
    for (let i = 0; i <= n; i++) pts.push([u1 + (u2 - u1) * i / n, v1 + (v2 - v1) * i / n]);
    return pts;
  }
  function circlePts(cu, cv, r, a0 = 0, a1 = Math.PI * 2, n = 48) {
    const pts = [];
    for (let i = 0; i <= n; i++) {
      const a = a0 + (a1 - a0) * i / n;
      pts.push([cu + Math.cos(a) * r, cv + Math.sin(a) * r]);
    }
    return pts;
  }

  const BOARD_COLOURS = ['#1F2A6B', '#0F7A57', '#C0322B', '#C2872C'];

  function draw() {
    const { ctx, canvas } = S;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (S.bg) {                     // arte pintada: só entidades por cima
      ctx.drawImage(S.bg, 0, 0, canvas.width, canvas.height);
      for (const p of [...S.players].sort((a, b) => a.y - b.y)) sprite(p);
      ball();
      return;
    }

    // avental de relva escura à volta do campo
    sampled([...seg(-2.5, -3, 107.5, -3, 12), ...seg(107.5, -3, 107.5, 70.5, 8),
             ...seg(107.5, 70.5, -2.5, 70.5, 12), ...seg(-2.5, 70.5, -2.5, -3, 8)]);
    ctx.closePath(); ctx.fillStyle = '#123A22'; ctx.fill();

    // placas de publicidade no fundo (lado distante)
    for (let i = 0; i < 12; i++) {
      const u0 = -2.5 + i * (110 / 12), u1 = u0 + 110 / 12;
      const [xa, ya, sa] = persp(u0, -3), [xb, yb, sb] = persp(u1, -3);
      const h = 3.1;
      ctx.beginPath();
      ctx.moveTo(xa, ya); ctx.lineTo(xb, yb);
      ctx.lineTo(xb, yb - h * metre(sb)); ctx.lineTo(xa, ya - h * metre(sa));
      ctx.closePath();
      ctx.fillStyle = BOARD_COLOURS[i % BOARD_COLOURS.length]; ctx.fill();
    }
    for (const bu of [22, 83]) {
      const [tx, ty, tsc] = persp(bu, -3);
      ctx.fillStyle = 'rgba(255,255,255,.92)';
      ctx.font = `700 ${Math.max(10, 1.5 * metre(tsc))}px Inter, sans-serif`;
      ctx.textAlign = 'center';
      ctx.fillText('SYNTHETIC XI TV', tx, ty - 1.1 * metre(tsc));
    }

    // relvado com faixas de corte
    for (let i = 0; i < 12; i++) {
      const u0 = i * PITCH.w / 12, u1 = u0 + PITCH.w / 12;
      sampled([...seg(u0, 0, u1, 0, 2), ...seg(u1, 0, u1, PITCH.h, 8),
               ...seg(u1, PITCH.h, u0, PITCH.h, 2), ...seg(u0, PITCH.h, u0, 0, 8)]);
      ctx.closePath();
      ctx.fillStyle = i % 2 ? '#2F9152' : '#288449'; ctx.fill();
    }
    // luz de estádio
    const [cx, cy] = persp(52.5, 30);
    const light = ctx.createRadialGradient(cx, cy, canvas.width * 0.06, cx, cy, canvas.width * 0.62);
    light.addColorStop(0, 'rgba(255,255,240,.10)');
    light.addColorStop(0.65, 'rgba(0,0,0,0)');
    light.addColorStop(1, 'rgba(0,16,6,.36)');
    sampled([...seg(0, 0, 105, 0, 2), ...seg(105, 0, 105, 68, 6),
             ...seg(105, 68, 0, 68, 2), ...seg(0, 68, 0, 0, 6)]);
    ctx.closePath(); ctx.fillStyle = light; ctx.fill();

    // marcações
    ctx.strokeStyle = 'rgba(255,255,255,.92)';
    ctx.lineWidth = Math.max(1.6, canvas.width * 0.0016);
    const stroke = (pts) => { sampled(pts); ctx.stroke(); };
    stroke([...seg(0, 0, 105, 0), ...seg(105, 0, 105, 68, 8),
            ...seg(105, 68, 0, 68), ...seg(0, 68, 0, 0, 8)]);
    stroke(seg(52.5, 0, 52.5, 68, 10));
    stroke(circlePts(52.5, 34, 9.15));
    spot(52.5, 34); spot(11, 34); spot(94, 34);
    for (const left of [true, false]) {
      const u0 = left ? 0 : 105, dir = left ? 1 : -1;
      stroke([...seg(u0, 13.85, u0 + dir * 16.5, 13.85, 6),
              ...seg(u0 + dir * 16.5, 13.85, u0 + dir * 16.5, 54.15, 8),
              ...seg(u0 + dir * 16.5, 54.15, u0, 54.15, 6)]);
      stroke([...seg(u0, 24.85, u0 + dir * 5.5, 24.85, 4),
              ...seg(u0 + dir * 5.5, 24.85, u0 + dir * 5.5, 43.15, 5),
              ...seg(u0 + dir * 5.5, 43.15, u0, 43.15, 4)]);
      const su = left ? 11 : 94;
      const arc = circlePts(su, 34, 9.15).filter(([u]) => left ? u > 16.5 : u < 88.5);
      stroke(arc);
      const cuArc = left ? 0 : 105;
      stroke(circlePts(cuArc, 0, 1, left ? 0 : Math.PI / 2, left ? Math.PI / 2 : Math.PI, 8));
      stroke(circlePts(cuArc, 68, 1, left ? -Math.PI / 2 : Math.PI, left ? 0 : Math.PI * 1.5, 8));
      goal(left);
      flag(cuArc, 0); flag(cuArc, 68);
    }

    // jogadores por profundidade, depois a bola
    for (const p of [...S.players].sort((a, b) => a.y - b.y)) sprite(p);
    ball();
  }

  function spot(u, v) {
    const { ctx } = S; const [x, y, s] = persp(u, v);
    ctx.beginPath(); ctx.ellipse(x, y, 0.32 * metre(s), 0.2 * metre(s), 0, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(255,255,255,.92)'; ctx.fill();
  }

  function flag(u, v) {
    const { ctx } = S; const [x, y, s] = persp(u, v); const m = metre(s);
    ctx.strokeStyle = '#F5F1E6'; ctx.lineWidth = Math.max(1, m * 0.14);
    ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x, y - 2.4 * m); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x, y - 2.4 * m); ctx.lineTo(x + 1.1 * m, y - 2.05 * m);
    ctx.lineTo(x, y - 1.7 * m); ctx.closePath();
    ctx.fillStyle = '#FFB020'; ctx.fill();
  }

  function goal(left) {
    const { ctx } = S;
    const u = left ? 0 : 105, back = left ? -2.1 : 107.1;
    const [x1, y1, s1] = persp(u, 30.34), [x2, y2, s2] = persp(u, 37.66);
    const [bx1, by1, bs1] = persp(back, 30.9), [bx2, by2, bs2] = persp(back, 37.1);
    const h1 = 2.44 * metre(s1) * 1.25, h2 = 2.44 * metre(s2) * 1.25;
    const bh1 = 2.05 * metre(bs1) * 1.25, bh2 = 2.05 * metre(bs2) * 1.25;
    // rede
    ctx.strokeStyle = 'rgba(255,255,255,.34)'; ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const f = i / 4;
      ctx.beginPath();
      ctx.moveTo(x1 + (x2 - x1) * f, y1 + (y2 - y1) * f - (h1 + (h2 - h1) * f));
      ctx.lineTo(bx1 + (bx2 - bx1) * f, by1 + (by2 - by1) * f - (bh1 + (bh2 - bh1) * f));
      ctx.lineTo(bx1 + (bx2 - bx1) * f, by1 + (by2 - by1) * f);
      ctx.stroke();
    }
    for (const f of [0.33, 0.66, 1]) {
      ctx.beginPath();
      ctx.moveTo(bx1, by1 - bh1 * f); ctx.lineTo(bx2, by2 - bh2 * f); ctx.stroke();
    }
    // traves
    ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = Math.max(2, metre(s1) * 0.22);
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x1, y1 - h1); ctx.lineTo(x2, y2 - h2);
    ctx.lineTo(x2, y2); ctx.stroke();
  }

  function luminance(hex) {
    return parseInt(hex.slice(1, 3), 16) * 0.299 +
           parseInt(hex.slice(3, 5), 16) * 0.587 +
           parseInt(hex.slice(5, 7), 16) * 0.114;
  }

  function sprite(p) {
    const { ctx } = S;
    const [x, y, s] = persp(p.x, p.y);
    const m = metre(s), h = 5.3 * m;
    const kit = S.kit[p.side], shirt = p.role === 'GK' ? kit.gk : kit.shirt;
    const run = Math.hypot(p.vx, p.vy) > 0.8 ? Math.sin(p.anim * 6) : 0;
    const swing = run * h * 0.10;

    if (p === S.carrier && S.celebrating <= 0) {
      ctx.beginPath(); ctx.ellipse(x, y + h * 0.03, h * 0.34, h * 0.13, 0, 0, Math.PI * 2);
      ctx.strokeStyle = '#FFD166'; ctx.lineWidth = Math.max(2, m * 0.3); ctx.stroke();
    }
    ctx.beginPath(); ctx.ellipse(x, y + h * 0.02, h * 0.26, h * 0.09, 0, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(0,22,8,.4)'; ctx.fill();

    ctx.save(); ctx.translate(x, y);
    // pernas + meias
    ctx.strokeStyle = '#1A1E24'; ctx.lineCap = 'round'; ctx.lineWidth = h * 0.10;
    ctx.beginPath(); ctx.moveTo(-h * 0.08, -h * 0.30); ctx.lineTo(-h * 0.09 + swing, 0); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(h * 0.08, -h * 0.30); ctx.lineTo(h * 0.09 - swing, 0); ctx.stroke();
    // calção
    ctx.fillStyle = kit.shorts;
    rr(ctx, -h * 0.17, -h * 0.44, h * 0.34, h * 0.17, h * 0.05); ctx.fill();
    ctx.strokeStyle = 'rgba(0,0,0,.18)'; ctx.lineWidth = 1; ctx.stroke();
    // camisa com mangas
    ctx.fillStyle = shirt;
    rr(ctx, -h * 0.30, -h * 0.76, h * 0.60, h * 0.14, h * 0.05); ctx.fill();   // mangas
    rr(ctx, -h * 0.21, -h * 0.80, h * 0.42, h * 0.40, h * 0.09); ctx.fill();   // tronco
    if (p.role !== 'GK' && kit.stripes) {                                       // listras
      ctx.save(); rr(ctx, -h * 0.21, -h * 0.80, h * 0.42, h * 0.40, h * 0.09); ctx.clip();
      ctx.fillStyle = kit.stripes;
      for (const off of [-0.155, 0, 0.155])
        ctx.fillRect(off * h - h * 0.045, -h * 0.82, h * 0.09, h * 0.46);
      ctx.restore();
    }
    ctx.strokeStyle = 'rgba(0,0,0,.16)';
    rr(ctx, -h * 0.21, -h * 0.80, h * 0.42, h * 0.40, h * 0.09); ctx.stroke();
    // número no peito
    const num = p.num ?? '';
    if (num !== '') {
      ctx.font = `800 ${h * 0.24}px Inter, sans-serif`; ctx.textAlign = 'center';
      ctx.fillStyle = kit.num && p.role !== 'GK'
        ? kit.num : (luminance(shirt) > 150 ? '#15181D' : '#FFFFFF');
      ctx.fillText(num, 0, -h * 0.50);
    }
    // cabeça
    ctx.beginPath(); ctx.arc(0, -h * 0.90, h * 0.145, 0, Math.PI * 2);
    ctx.fillStyle = '#C99B6F'; ctx.fill();
    ctx.restore();

    // etiqueta de nome
    const label = p.name.toUpperCase();
    ctx.font = `700 ${Math.max(9, h * 0.155)}px Inter, sans-serif`;
    const w = ctx.measureText(label).width + h * 0.24;
    ctx.fillStyle = 'rgba(12,18,12,.85)';
    rr(ctx, x - w / 2, y + h * 0.10, w, h * 0.24, h * 0.07); ctx.fill();
    ctx.fillStyle = '#FFFFFF'; ctx.textAlign = 'center';
    ctx.fillText(label, x, y + h * 0.275);
    // cartão
    if (p.card) {
      ctx.fillStyle = p.card === 'yellow' ? '#F2C230' : p.card === 'red' ? '#C0322B' : '#8A9099';
      ctx.fillRect(x - h * 0.07, y - h * 1.22, h * 0.14, h * 0.20);
    }
  }

  function rr(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }

  function ball() {
    const { ctx } = S; const b = S.ball;
    const [x, y, s] = persp(b.x, b.y); const m = metre(s);
    ctx.beginPath(); ctx.ellipse(x, y + 0.25 * m, 0.55 * m, 0.22 * m, 0, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(0,22,8,.4)'; ctx.fill();
    const r = 0.42 * m * (1 + b.z * 0.30);
    ctx.beginPath(); ctx.arc(x, y - b.z * m * 1.7, Math.max(3.5, r), 0, Math.PI * 2);
    ctx.fillStyle = '#FFFFFF'; ctx.fill();
    ctx.lineWidth = Math.max(1, m * 0.08); ctx.strokeStyle = '#15181D'; ctx.stroke();
  }

  window.Match2D = { mount, event, setClock, tune: (o) => Object.assign(PROJ, o) };
})();
