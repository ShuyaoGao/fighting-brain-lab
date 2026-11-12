/* 拆招擂台 · 画面、输入、流程 */
(function () {
  'use strict';
  const C = window.FightCore;
  const cv = document.getElementById('view');
  const ctx = cv.getContext('2d');
  const W = 960, H = 540, GY = 478;
  const $ = id => document.getElementById(id);
  const reduceMotion = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;

  const COLORS = [
    { gi: '#d9493a', giDark: '#8f2a22', band: '#f2d27a', glow: '255,120,80' },
    { gi: '#24a594', giDark: '#13635a', band: '#e9eef0', glow: '80,230,210' },
  ];
  const SKIN = '#e9c49d', SKIN_D = '#b88e6b', INK = '#0b0b12';
  const HABIT_NAMES = { dp: '升龙', fb: '波动', jump: '跳入', jab: '轻拳', heavy: '重踢', cA: '下段拳', cB: '扫腿', throw: '投技' };

  // ---------------- 存储（只是本机战绩，读不到也照常玩） ----------------
  function loadRec() { try { return JSON.parse(localStorage.getItem('fight-rec') || '{}'); } catch (e) { return {}; } }
  function saveRec(r) { try { localStorage.setItem('fight-rec', JSON.stringify(r)); } catch (e) { /* 忽略 */ } }
  let rec = loadRec();
  function showRec() {
    document.querySelectorAll('[data-rec]').forEach(el => {
      const r = rec[el.dataset.rec];
      el.textContent = r ? `你的战绩 ${r.w} 胜 ${r.l} 负` : '还没挑战过';
    });
  }

  // ---------------- 声音（Web Audio 现场合成） ----------------
  let ac = null, muted = false;
  function audio() {
    if (!ac) { try { ac = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { ac = null; } }
    if (ac && ac.state === 'suspended') ac.resume();
    return ac;
  }
  function noise(dur, freq, gain, q) {
    if (muted || !ac) return;
    const len = Math.floor(ac.sampleRate * dur), buf = ac.createBuffer(1, len, ac.sampleRate), d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 2);
    const src = ac.createBufferSource(); src.buffer = buf;
    const f = ac.createBiquadFilter(); f.type = 'bandpass'; f.frequency.value = freq; f.Q.value = q || 1;
    const g = ac.createGain(); g.gain.value = gain;
    src.connect(f).connect(g).connect(ac.destination); src.start();
  }
  function tone(f0, f1, dur, gain, type) {
    if (muted || !ac) return;
    const o = ac.createOscillator(), g = ac.createGain(), t = ac.currentTime;
    o.type = type || 'sine'; o.frequency.setValueAtTime(f0, t); o.frequency.exponentialRampToValueAtTime(Math.max(20, f1), t + dur);
    g.gain.setValueAtTime(gain, t); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(ac.destination); o.start(t); o.stop(t + dur + 0.02);
  }
  const SFX = {
    hit: big => { noise(big ? 0.22 : 0.12, big ? 900 : 1600, big ? 0.9 : 0.6, 0.8); tone(big ? 140 : 200, 50, big ? 0.25 : 0.12, big ? 0.7 : 0.4); },
    block: () => { noise(0.08, 3200, 0.35, 3); tone(900, 600, 0.06, 0.12, 'square'); },
    proj: s => { tone(s ? 220 : 420, s ? 90 : 160, s ? 0.6 : 0.3, 0.25, 'sawtooth'); },
    jump: () => tone(300, 500, 0.08, 0.05),
    ko: () => { tone(110, 40, 1.6, 0.8, 'triangle'); noise(0.9, 400, 0.6, 0.5); },
    super: () => { tone(80, 800, 0.5, 0.3, 'sawtooth'); },
    bell: () => { tone(880, 860, 0.9, 0.2, 'triangle'); tone(1320, 1300, 0.6, 0.08); },
  };

  // ---------------- 背景（只画一次） ----------------
  const bg = document.createElement('canvas'); bg.width = W; bg.height = H;
  (function paintBg() {
    const b = bg.getContext('2d');
    const sky = b.createLinearGradient(0, 0, 0, GY);
    sky.addColorStop(0, '#141329'); sky.addColorStop(0.55, '#2c2240'); sky.addColorStop(1, '#5b3646');
    b.fillStyle = sky; b.fillRect(0, 0, W, H);
    // 星
    let s = 7; const r = () => ((s = (s * 16807) % 2147483647) / 2147483647);
    for (let i = 0; i < 90; i++) { b.fillStyle = `rgba(255,245,225,${0.15 + r() * 0.5})`; b.fillRect(r() * W, r() * 260, 1.2, 1.2); }
    // 月
    const mx = 700, my = 120;
    const glow = b.createRadialGradient(mx, my, 20, mx, my, 170);
    glow.addColorStop(0, 'rgba(250,232,190,.35)'); glow.addColorStop(1, 'rgba(250,232,190,0)');
    b.fillStyle = glow; b.fillRect(0, 0, W, H);
    b.fillStyle = '#f4e7c6'; b.beginPath(); b.arc(mx, my, 46, 0, Math.PI * 2); b.fill();
    b.fillStyle = 'rgba(200,180,150,.25)'; b.beginPath(); b.arc(mx - 14, my - 8, 9, 0, 7); b.arc(mx + 12, my + 14, 6, 0, 7); b.fill();
    // 远山三层
    const ridge = (base, amp, col, seed) => {
      b.fillStyle = col; b.beginPath(); b.moveTo(0, GY);
      for (let x = 0; x <= W; x += 8) {
        const y = base - amp * (0.55 * Math.sin(x * 0.006 + seed) + 0.3 * Math.sin(x * 0.017 + seed * 2) + 0.15 * Math.sin(x * 0.041 + seed * 3));
        b.lineTo(x, y);
      }
      b.lineTo(W, GY); b.closePath(); b.fill();
    };
    ridge(300, 70, '#3a2b4a', 1.3); ridge(345, 55, '#2a2038', 4.1); ridge(390, 40, '#1d1729', 2.2);
    // 雾
    const fog = b.createLinearGradient(0, 330, 0, 420);
    fog.addColorStop(0, 'rgba(120,90,120,0)'); fog.addColorStop(1, 'rgba(120,90,120,.28)');
    b.fillStyle = fog; b.fillRect(0, 330, W, 90);
    // 檐角剪影
    b.fillStyle = '#120f1c';
    const roof = (x, w, y) => { b.beginPath(); b.moveTo(x - 20, y); b.quadraticCurveTo(x + w / 2, y - 26, x + w + 20, y); b.lineTo(x + w, y + 8); b.lineTo(x, y + 8); b.closePath(); b.fill(); b.fillRect(x + 8, y + 8, w - 16, GY - y); };
    roof(-30, 150, 360); roof(850, 150, 350);
    // 地板
    const floor = b.createLinearGradient(0, GY - 6, 0, H);
    floor.addColorStop(0, '#5a3d2c'); floor.addColorStop(1, '#2a1b14');
    b.fillStyle = floor; b.fillRect(0, GY - 6, W, H - GY + 6);
    b.strokeStyle = 'rgba(0,0,0,.35)'; b.lineWidth = 1;
    for (let i = -12; i <= 12; i++) { b.beginPath(); b.moveTo(W / 2 + i * 40, GY - 6); b.lineTo(W / 2 + i * 110, H); b.stroke(); }
    for (let y = GY + 6, k = 1; y < H; y += 8 + k * 3, k++) { b.strokeStyle = 'rgba(0,0,0,.25)'; b.beginPath(); b.moveTo(0, y); b.lineTo(W, y); b.stroke(); }
    b.fillStyle = 'rgba(255,200,150,.10)'; b.fillRect(0, GY - 6, W, 2);
  })();

  // ---------------- 姿势（角度：0 = 向下，正 = 朝前转；π/2 = 平伸向前，π = 向上） ----------------
  const P = {
    stand:  { lean: .08, aF: [.5, 2.5], aB: [.25, 2.2], lF: [.32, .05], lB: [-.28, -.2] },
    crouch: { lean: .45, aF: [.9, 2.6], aB: [.6, 2.3], lF: [1.25, -.25], lB: [.55, -.95] },
    air:    { lean: .1, aF: [.9, 2.4], aB: [.4, 2.0], lF: [1.3, .1], lB: [.6, -.5] },
    block:  { lean: -.05, aF: [1.0, 2.9], aB: [.7, 2.8], lF: [.3, .05], lB: [-.3, -.2] },
    cblock: { lean: .3, aF: [1.1, 2.9], aB: [.8, 2.8], lF: [1.25, -.25], lB: [.55, -.95] },
    hit:    { lean: -.4, aF: [-.4, .2], aB: [-.7, -.3], lF: [.4, .1], lB: [-.35, -.25] },
    chit:   { lean: -.1, aF: [-.4, .2], aB: [-.7, -.3], lF: [1.25, -.25], lB: [.55, -.95] },
    airhit: { lean: -1.0, aF: [-1.2, -.8], aB: [-1.6, -1.2], lF: [.9, .4], lB: [.5, 0] },
    down:   { lean: -1.52, aF: [-1.4, -1.3], aB: [-1.6, -1.5], lF: [1.52, 1.5], lB: [1.45, 1.52], lift: 13 },
  };
  const MP = {
    jab:   { base: 'stand', s: { lean: .1, aF: [.3, 2.6] }, a: { lean: .2, aF: [1.57, 1.57], aB: [.2, 2.2] } },
    heavy: { base: 'stand', s: { lean: -.1, lF: [.9, -.3] }, a: { lean: -.35, lF: [1.65, 1.6], lB: [-.15, -.1], aF: [.4, 2.4], aB: [-.4, 1.0] } },
    cA:    { base: 'crouch', s: { aF: [.6, 2.4] }, a: { aF: [1.45, 1.5] } },
    cB:    { base: 'crouch', s: { lF: [1.1, -.6] }, a: { lean: .55, lF: [1.62, 1.6], lB: [.7, -.9], aB: [.3, .3] } },
    over:  { base: 'stand', s: { lean: -.25, aF: [3.0, 3.4], aB: [2.6, 3.0] }, a: { lean: .45, aF: [1.25, 1.05], aB: [1.0, .9] } },
    jA:    { base: 'air', s: { aF: [.4, 2.3] }, a: { aF: [1.2, 1.0] } },
    jB:    { base: 'air', s: { lF: [.9, -.4] }, a: { lean: -.15, lF: [1.15, 1.05] } },
    throw: { base: 'stand', s: { aF: [1.2, 1.6], aB: [1.0, 1.4] }, a: { lean: .25, aF: [1.5, 1.65], aB: [1.3, 1.5] } },
    fbA:   { base: 'stand', s: { lean: -.12, aF: [-.4, .6], aB: [-.6, .4] }, a: { lean: .25, aF: [1.55, 1.55], aB: [1.45, 1.5] } },
    fbB:   { base: 'stand', s: { lean: -.12, aF: [-.4, .6], aB: [-.6, .4] }, a: { lean: .25, aF: [1.55, 1.55], aB: [1.45, 1.5] } },
    dpA:   { base: 'crouch', s: { aF: [1.0, 2.0] }, a: { lean: -.05, aF: [3.0, 3.1], aB: [.5, 2.2], lF: [1.0, .2], lB: [.2, -.4] } },
    dpB:   { base: 'crouch', s: { aF: [1.0, 2.0] }, a: { lean: -.05, aF: [3.0, 3.1], aB: [.5, 2.2], lF: [1.0, .2], lB: [.2, -.4] } },
    super: { base: 'stand', s: { lean: -.2, aF: [-.6, .5], aB: [-.8, .3], lF: [.6, .1], lB: [-.6, -.3] }, a: { lean: .3, aF: [1.55, 1.55], aB: [1.5, 1.52], lF: [.6, .1], lB: [-.6, -.3] } },
  };
  const ease = t => t < 0 ? 0 : t > 1 ? 1 : t * t * (3 - 2 * t);
  function merge(base, part) { return Object.assign({}, base, part || {}); }
  function mix(p, q, t) {
    const r = {};
    for (const k of ['lean', 'aF', 'aB', 'lF', 'lB', 'lift']) {
      const a = p[k] === undefined ? (k === 'lift' ? 0 : p[k]) : p[k], b = q[k] === undefined ? (k === 'lift' ? 0 : q[k]) : q[k];
      if (Array.isArray(a)) r[k] = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
      else r[k] = (a || 0) + ((b || 0) - (a || 0)) * t;
    }
    return r;
  }

  function poseOf(f, t) {
    const crouching = C.isCrouching(f);
    switch (f.st) {
      case 'stand': {
        let p = merge(P.stand, {});
        if (Math.abs(f.vx) > 0.2) {
          const ph = t * 0.28 * Math.sign(f.vx * f.face);
          p.lF = [0.42 * Math.sin(ph), 0.42 * Math.sin(ph) - 0.35 * (1 + Math.cos(ph)) / 2];
          p.lB = [0.42 * Math.sin(ph + Math.PI), 0.42 * Math.sin(ph + Math.PI) - 0.35 * (1 + Math.cos(ph + Math.PI)) / 2];
        }
        if (f.hbk) p = merge(p, { aF: P.block.aF, aB: P.block.aB, lean: 0 });
        p.lean += 0.025 * Math.sin(t * 0.07);
        return p;
      }
      case 'crouch': return f.hbk ? P.cblock : P.crouch;
      case 'air': return P.air;
      case 'block': return f.cr ? P.cblock : P.block;
      case 'hit': return f.cr ? P.chit : P.hit;
      case 'airhit': return P.airhit;
      case 'down': case 'ko': return P.down;
      case 'rise': return mix(P.down, P.crouch, ease(f.t / 14));
      case 'atk': {
        const m = C.MOVES[f.mv], mp = MP[f.mv];
        const base = P[mp.base];
        const S = merge(base, mp.s), A = merge(base, mp.a);
        if (f.mt < m.s) return mix(base, S, ease(f.mt / m.s));
        if (f.mt < m.s + m.a) return mix(S, A, ease((f.mt - m.s + 1) / 2));
        const back = crouching ? P.crouch : f.y > 0 ? P.air : P.stand;
        return mix(A, back, ease((f.mt - m.s - m.a) / m.r));
      }
    }
    return P.stand;
  }

  const L = { torso: 54, ua: 28, fa: 28, th: 38, sh: 40, head: 13 };
  function ext(a, l) { return Math.max(0, Math.cos(a)) * l; }
  function drawFighter(f, i, t) {
    const col = COLORS[i];
    const p = poseOf(f, t);
    const legH = Math.max(ext(p.lF[0], L.th) + ext(p.lF[1], L.sh), ext(p.lB[0], L.th) + ext(p.lB[1], L.sh));
    const baseY = GY - f.y;
    const hipY = -(legH + (p.lift || 0));
    // 影子
    ctx.save();
    ctx.fillStyle = 'rgba(0,0,0,.35)';
    const sw = 46 * Math.max(0.4, 1 - f.y / 250);
    ctx.beginPath(); ctx.ellipse(f.x, GY + 2, sw, 7, 0, 0, Math.PI * 2); ctx.fill();
    ctx.restore();

    ctx.save();
    ctx.translate(f.x, baseY);
    ctx.scale(f.face, 1);
    const pt = (x, y, a, l) => [x + Math.sin(a) * l, y + Math.cos(a) * l];
    const hip = [0, hipY];
    const neck = [Math.sin(p.lean) * L.torso, hipY - Math.cos(p.lean) * L.torso];
    const sh = [neck[0] - Math.sin(p.lean) * 6, neck[1] + Math.cos(p.lean) * 6];
    const head = [neck[0] + Math.sin(p.lean) * 15, neck[1] - Math.cos(p.lean) * 15];
    const limb = (start, ang, lens, widths, colors) => {
      const k = pt(start[0], start[1], ang[0], lens[0]);
      const e = pt(k[0], k[1], ang[1], lens[1]);
      ctx.lineCap = 'round'; ctx.lineJoin = 'round';
      ctx.strokeStyle = INK; ctx.lineWidth = widths[0] + 5;
      ctx.beginPath(); ctx.moveTo(start[0], start[1]); ctx.lineTo(k[0], k[1]); ctx.lineTo(e[0], e[1]); ctx.stroke();
      ctx.strokeStyle = colors[0]; ctx.lineWidth = widths[0];
      ctx.beginPath(); ctx.moveTo(start[0], start[1]); ctx.lineTo(k[0], k[1]); ctx.stroke();
      ctx.strokeStyle = colors[1]; ctx.lineWidth = widths[1];
      ctx.beginPath(); ctx.moveTo(k[0], k[1]); ctx.lineTo(e[0], e[1]); ctx.stroke();
      return e;
    };
    const fist = (e, c) => { ctx.fillStyle = INK; ctx.beginPath(); ctx.arc(e[0], e[1], 8.5, 0, 7); ctx.fill(); ctx.fillStyle = c; ctx.beginPath(); ctx.arc(e[0], e[1], 6, 0, 7); ctx.fill(); };
    const foot = (e, a, c) => { ctx.save(); ctx.translate(e[0], e[1]); ctx.rotate(-a + Math.PI / 2 * 0); ctx.fillStyle = INK; ctx.fillRect(-4, -5, 20, 10); ctx.fillStyle = c; ctx.fillRect(-2, -3, 16, 6); ctx.restore(); };

    // 后侧手脚（暗色）
    const eB = limb(hip, p.lB, [L.th, L.sh], [15, 13], [col.giDark, col.giDark]);
    foot(eB, p.lB[1], SKIN_D);
    const hB = limb(sh, p.aB, [L.ua, L.fa], [12, 10], [col.giDark, SKIN_D]);
    fist(hB, SKIN_D);
    // 躯干
    ctx.lineCap = 'round';
    ctx.strokeStyle = INK; ctx.lineWidth = 31;
    ctx.beginPath(); ctx.moveTo(hip[0], hip[1]); ctx.lineTo(sh[0], sh[1]); ctx.stroke();
    const tg = ctx.createLinearGradient(-14, 0, 14, 0); tg.addColorStop(0, col.giDark); tg.addColorStop(0.6, col.gi); tg.addColorStop(1, col.gi);
    ctx.strokeStyle = tg; ctx.lineWidth = 26;
    ctx.beginPath(); ctx.moveTo(hip[0], hip[1]); ctx.lineTo(sh[0], sh[1]); ctx.stroke();
    // 衣襟 + 腰带
    ctx.strokeStyle = SKIN; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.moveTo(sh[0] + 4, sh[1] + 2); ctx.lineTo((hip[0] + sh[0]) / 2 + 3, (hip[1] + sh[1]) / 2 - 4); ctx.stroke();
    ctx.strokeStyle = INK; ctx.lineWidth = 7;
    const bx = hip[0] + Math.sin(p.lean) * 8, by = hip[1] - Math.cos(p.lean) * 8;
    ctx.beginPath(); ctx.moveTo(bx - 14 * Math.cos(p.lean), by - 14 * Math.sin(p.lean)); ctx.lineTo(bx + 14 * Math.cos(p.lean), by + 14 * Math.sin(p.lean)); ctx.stroke();
    // 前腿
    const eF = limb(hip, p.lF, [L.th, L.sh], [16, 14], [col.gi, col.gi]);
    foot(eF, p.lF[1], SKIN);
    // 头 + 头带
    ctx.fillStyle = INK; ctx.beginPath(); ctx.arc(head[0], head[1], L.head + 3, 0, 7); ctx.fill();
    ctx.fillStyle = SKIN; ctx.beginPath(); ctx.arc(head[0], head[1], L.head, 0, 7); ctx.fill();
    ctx.fillStyle = '#1c1414'; ctx.beginPath(); ctx.arc(head[0] - 2, head[1] - 3, L.head, Math.PI * 1.05, Math.PI * 1.95); ctx.fill();
    ctx.strokeStyle = col.band; ctx.lineWidth = 4;
    ctx.beginPath(); ctx.arc(head[0], head[1], L.head - 1, Math.PI * 1.08, Math.PI * 1.9); ctx.stroke();
    const sway = Math.sin(t * 0.18 + i) * 5 - f.vx * 2;
    ctx.beginPath(); ctx.moveTo(head[0] - L.head + 1, head[1] - 4);
    ctx.quadraticCurveTo(head[0] - L.head - 14, head[1] - 2 + sway * 0.5, head[0] - L.head - 26, head[1] + 4 + sway); ctx.stroke();
    ctx.fillStyle = INK; ctx.fillRect(head[0] + 5, head[1] - 2, 3, 3);
    // 前手
    const hF = limb(sh, p.aF, [L.ua, L.fa], [13, 11], [col.gi, SKIN]);
    fist(hF, SKIN);
    // 被打白闪
    if (f.flash > 3) {
      ctx.globalCompositeOperation = 'source-atop';
      ctx.fillStyle = 'rgba(255,255,255,.55)'; ctx.fillRect(-80, -200, 160, 210);
      ctx.globalCompositeOperation = 'source-over';
    }
    ctx.restore();
  }

  // ---------------- 特效 ----------------
  let parts = [], shake = 0, flashScreen = 0, superDim = 0;
  const popups = []; // 文字：反击 / 连击
  function burst(x, y, color, n, speed, life) {
    for (let k = 0; k < n; k++) {
      const a = Math.random() * Math.PI * 2, v = speed * (0.4 + Math.random());
      parts.push({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life, max: life, color, kind: 'line' });
    }
  }
  function ring(x, y, color) { parts.push({ x, y, r: 6, life: 14, max: 14, color, kind: 'ring' }); }
  function dust(x) { for (let k = 0; k < 8; k++) parts.push({ x: x + (Math.random() - .5) * 40, y: GY - 2, vx: (Math.random() - .5) * 2.5, vy: -Math.random() * 1.5, life: 24, max: 24, color: '200,170,140', kind: 'dot' }); }
  function stepParts() {
    for (const p of parts) { p.life--; if (p.kind === 'ring') p.r += 3.2; else { p.x += p.vx; p.y += p.vy; p.vx *= 0.9; p.vy *= 0.9; if (p.kind === 'dot') p.vy -= 0.02; } }
    parts = parts.filter(p => p.life > 0);
    for (const q of popups) q.life--;
    while (popups.length && popups[0].life <= 0) popups.shift();
    if (shake > 0) shake *= 0.82;
    if (flashScreen > 0) flashScreen--;
    if (superDim > 0) superDim--;
  }
  function drawParts() {
    for (const p of parts) {
      const a = p.life / p.max;
      if (p.kind === 'line') {
        ctx.strokeStyle = `rgba(${p.color},${a})`; ctx.lineWidth = 3 * a + 1;
        ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x - p.vx * 3, p.y - p.vy * 3); ctx.stroke();
      } else if (p.kind === 'ring') {
        ctx.strokeStyle = `rgba(${p.color},${a})`; ctx.lineWidth = 4 * a;
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.stroke();
      } else {
        ctx.fillStyle = `rgba(${p.color},${a * 0.6})`; ctx.beginPath(); ctx.arc(p.x, p.y, 3 + (1 - a) * 4, 0, 7); ctx.fill();
      }
    }
  }
  function drawProj(p) {
    const col = COLORS[p.owner].glow, x = p.x, y = GY - p.y - p.h / 2, r = p.super ? 32 : 17;
    for (let k = 5; k >= 1; k--) {
      const tx = x - Math.sign(p.vx) * k * (p.super ? 14 : 9);
      ctx.fillStyle = `rgba(${col},${0.08 * (6 - k)})`;
      ctx.beginPath(); ctx.arc(tx, y, r * (1 - k * 0.1), 0, 7); ctx.fill();
    }
    const g = ctx.createRadialGradient(x, y, 2, x, y, r * 1.6);
    g.addColorStop(0, 'rgba(255,255,255,1)'); g.addColorStop(0.35, `rgba(${col},.95)`); g.addColorStop(1, `rgba(${col},0)`);
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r * 1.6, 0, 7); ctx.fill();
  }

  // ---------------- HUD ----------------
  const shown = [{ hp: 1000, drain: 1000 }, { hp: 1000, drain: 1000 }];
  function bar(x, y, w, h, ratio, drain, flip, color) {
    const slant = 12;
    const path = (x0, x1) => { ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.lineTo(x1 - slant, y + h); ctx.lineTo(x0 - slant, y + h); ctx.closePath(); };
    ctx.fillStyle = 'rgba(0,0,0,.55)'; path(x - 3, x + w + 3); ctx.fill();
    const seg = r => flip ? [x + w * (1 - r), x + w] : [x, x + w * r];
    let [a, b] = seg(drain); ctx.fillStyle = '#f2efe6'; path(a, b); ctx.fill();
    [a, b] = seg(ratio);
    const gr = ctx.createLinearGradient(0, y, 0, y + h); gr.addColorStop(0, '#ffe27a'); gr.addColorStop(1, color);
    ctx.fillStyle = ratio < 0.25 ? '#ff5a3c' : gr; path(a, b); ctx.fill();
    ctx.strokeStyle = 'rgba(255,255,255,.5)'; ctx.lineWidth = 1.5; path(x - 3, x + w + 3); ctx.stroke();
  }
  function drawHUD() {
    const g = game;
    ctx.save();
    ctx.textBaseline = 'middle';
    for (let i = 0; i < 2; i++) {
      const f = g.f[i], s = shown[i];
      s.hp = f.hp;
      if (s.drain > s.hp) s.drain = Math.max(s.hp, s.drain - (game.hitstop ? 0 : 6)); else s.drain = s.hp;
      const x = i === 0 ? 40 : 540, w = 380;
      bar(x, 26, w, 22, s.hp / C.MAX_HP, s.drain / C.MAX_HP, i === 0, '#e0a43a');
      ctx.font = '600 15px "Noto Sans SC", sans-serif';
      ctx.fillStyle = '#ece4d3';
      ctx.textAlign = i === 0 ? 'left' : 'right';
      ctx.fillText(names[i], i === 0 ? 34 : 926, 64);
      // 回合胜场
      for (let k = 0; k < 2; k++) {
        const cx = i === 0 ? 404 - k * 18 : 556 + k * 18;
        ctx.fillStyle = match.wins[i] > k ? '#efc25a' : 'rgba(255,255,255,.18)';
        ctx.beginPath(); ctx.arc(cx, 64, 6, 0, 7); ctx.fill();
      }
      // 气槽
      const mw = 220, mx = i === 0 ? 40 : 920 - mw, my = 506, r = f.meter / C.MAX_METER;
      ctx.fillStyle = 'rgba(0,0,0,.55)'; ctx.fillRect(mx - 2, my - 2, mw + 4, 14);
      ctx.fillStyle = r >= 1 ? `hsl(${45 + 10 * Math.sin(g.t * 0.2)},95%,62%)` : '#b98b2e';
      if (i === 0) ctx.fillRect(mx, my, mw * r, 10); else ctx.fillRect(mx + mw * (1 - r), my, mw * r, 10);
      ctx.font = '22px "Zhi Mang Xing", serif'; ctx.fillStyle = r >= 1 ? '#efc25a' : 'rgba(236,228,211,.7)';
      ctx.textAlign = i === 0 ? 'left' : 'right';
      ctx.fillText(r >= 1 ? '气 · 满' : '气', i === 0 ? mx + mw + 10 : mx - 10, my + 4);
      // 连击
      const victim = g.f[1 - i];
      if (victim.combo >= 2 && (victim.st === 'hit' || victim.st === 'airhit')) {
        ctx.font = '700 34px "Oxanium", sans-serif'; ctx.fillStyle = '#efc25a';
        ctx.textAlign = i === 0 ? 'left' : 'right';
        const cx = i === 0 ? 40 : 920;
        ctx.fillText(victim.combo, cx, 150);
        ctx.font = '26px "Zhi Mang Xing", serif'; ctx.fillStyle = '#ece4d3';
        ctx.fillText('连击', i === 0 ? cx + 22 + String(victim.combo).length * 18 : cx - 22 - String(victim.combo).length * 18, 152);
      }
    }
    // 计时
    ctx.textAlign = 'center';
    ctx.fillStyle = 'rgba(0,0,0,.6)'; ctx.fillRect(452, 14, 56, 46);
    ctx.strokeStyle = 'rgba(255,255,255,.35)'; ctx.strokeRect(452, 14, 56, 46);
    const sec = Math.ceil(g.roundT / 60);
    ctx.font = '700 32px "Oxanium", sans-serif'; ctx.fillStyle = sec <= 10 ? '#ff7a5c' : '#ece4d3';
    ctx.fillText(String(sec).padStart(2, '0'), 480, 38);
    // 弹出字
    for (const q of popups) {
      const a = Math.min(1, q.life / 20);
      ctx.font = `${q.size || 30}px "Zhi Mang Xing", serif`;
      ctx.fillStyle = `rgba(${q.color},${a})`; ctx.textAlign = 'center';
      ctx.fillText(q.text, q.x, q.y - (q.max - q.life) * 0.6);
    }
    ctx.restore();
  }

  function banner(text, sub, color) {
    ctx.save();
    ctx.fillStyle = 'rgba(0,0,0,.45)'; ctx.fillRect(0, 210, W, 120);
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.font = '96px "Zhi Mang Xing", serif';
    ctx.fillStyle = INK; ctx.fillText(text, 484, 274);
    ctx.fillStyle = color || '#ece4d3'; ctx.fillText(text, 480, 270);
    if (sub) { ctx.font = '500 16px "Noto Sans SC", sans-serif'; ctx.fillStyle = 'rgba(236,228,211,.8)'; ctx.fillText(sub, 480, 318); }
    ctx.restore();
  }

  // ---------------- 输入：键盘 + 手柄 + 触屏 ----------------
  const keys = {};
  const KEYMAP = {
    ArrowLeft: 'left', KeyA: 'left', ArrowRight: 'right', KeyD: 'right', ArrowUp: 'up', KeyW: 'up', ArrowDown: 'down', KeyS: 'down',
    KeyJ: 'a', KeyZ: 'a', KeyK: 'b', KeyX: 'b', KeyL: 'c', KeyC: 'c',
    KeyU: 'fb', KeyI: 'dp', KeyO: 'su', ShiftLeft: 'shift', ShiftRight: 'shift',
  };
  const touchKeys = {};
  let padPrev = {};

  function onOtherButton() { const a = document.activeElement; return !!(a && a.tagName === 'BUTTON' && !a.classList.contains('level') && a.id !== 'start' && a.id !== 'again'); }
  function inMatch() { return mode === 'fight' || mode === 'intro'; }

  addEventListener('keydown', e => {
    const k = KEYMAP[e.code];
    if (k) {
      keys[k] = true;
      // 对战时方向键、空格不要滚动页面
      if (inMatch()) e.preventDefault();
    }
    if (e.repeat) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const code = e.code;
    // 说明浮层最优先：Esc / H 关闭
    if (!$('help').hidden) {
      if (code === 'Escape' || code === 'KeyH' || code === 'Enter') { e.preventDefault(); closeHelp(); }
      return;
    }
    if (code === 'KeyH') { openHelp(); return; }
    if (code === 'KeyM') { toggleMute(); return; }
    switch (mode) {
      case 'menu':
        if (code === 'Enter' || code === 'NumpadEnter') { if (onOtherButton()) return; e.preventDefault(); startMatch(false); }
        else if (code === 'KeyV') startMatch(true);
        else if (code === 'ArrowLeft' || code === 'ArrowRight') { e.preventDefault(); shiftLevel(code === 'ArrowRight' ? 1 : -1); }
        else if (/^(Digit|Numpad)[1-4]$/.test(code)) setLevel(LEVEL_ORDER[+code.slice(-1) - 1]);
        break;
      case 'intro': case 'fight':
        if (code === 'Escape' || code === 'KeyP' || code === 'Space') { e.preventDefault(); pause(); }
        break;
      case 'paused':
        if (code === 'Escape' || code === 'KeyP' || code === 'Space') { e.preventDefault(); resume(); }
        else if (code === 'KeyR') restartMatch();
        else if (code === 'KeyQ') toMenu();
        break;
      case 'result':
        if (code === 'Enter' || code === 'NumpadEnter') { if (onOtherButton()) return; e.preventDefault(); startMatch(demo); }
        else if (code === 'Escape' || code === 'KeyQ') toMenu();
        break;
    }
  });
  addEventListener('keyup', e => { const k = KEYMAP[e.code]; if (k) keys[k] = false; });
  function releaseAll() { for (const k in keys) keys[k] = false; for (const k in touchKeys) touchKeys[k] = false; }
  addEventListener('blur', () => { releaseAll(); if (inMatch()) pause('切到别的窗口了，已自动暂停。'); });
  document.addEventListener('visibilitychange', () => { if (document.hidden && inMatch()) { releaseAll(); pause('切到别的页面了，已自动暂停。'); } });

  function readRaw() {
    const r = {};
    for (const k of ['left', 'right', 'up', 'down', 'a', 'b', 'c', 'fb', 'dp', 'su', 'shift']) r[k] = !!(keys[k] || touchKeys[k]);
    const pads = navigator.getGamepads ? navigator.getGamepads() : [];
    for (const p of pads) {
      if (!p) continue;
      const b = k => !!(p.buttons[k] && p.buttons[k].pressed);
      const ax = p.axes[0] || 0, ay = p.axes[1] || 0;
      r.left = r.left || b(14) || ax < -0.5; r.right = r.right || b(15) || ax > 0.5;
      r.up = r.up || b(12) || ay < -0.6; r.down = r.down || b(13) || ay > 0.5;
      r.a = r.a || b(2); r.b = r.b || b(3); r.c = r.c || b(0); r.su = r.su || b(1);
      r.fb = r.fb || b(4); r.dp = r.dp || b(5); r.shift = r.shift || b(7);
    }
    return r;
  }
  // 手柄 Start 键：暂停 / 继续 / 菜单里开战
  function pollPadButtons() {
    const pads = navigator.getGamepads ? navigator.getGamepads() : [];
    for (const p of pads) {
      if (!p) continue;
      const st = !!(p.buttons[9] && p.buttons[9].pressed);
      const prev = padPrev[p.index] || false;
      if (st && !prev) {
        if (!$('help').hidden) closeHelp();
        else if (inMatch()) pause();
        else if (mode === 'paused') resume();
        else if (mode === 'menu') startMatch(false);
        else if (mode === 'result') startMatch(demo);
      }
      padPrev[p.index] = st;
    }
  }

  // 触屏：左边摇杆（8 方向，可以搓招），右边按键（多点触控）
  function setupTouch() {
    const isTouch = (window.matchMedia && matchMedia('(pointer: coarse)').matches) || 'ontouchstart' in window;
    if (isTouch) document.body.classList.add('touchp');
    addEventListener('touchstart', () => document.body.classList.add('touchp'), { once: true, passive: true });
    const stick = $('stick'), knob = $('knob');
    let sid = null, cx = 0, cy = 0;
    const setDir = (dx, dy) => {
      const d = Math.hypot(dx, dy), dead = 16, max = 46;
      const s = d > max ? max / d : 1;
      knob.style.transform = `translate(${dx * s}px, ${dy * s}px)`;
      const on = d > dead, ang = Math.atan2(dy, dx);
      touchKeys.right = on && Math.cos(ang) > 0.38;
      touchKeys.left = on && Math.cos(ang) < -0.38;
      touchKeys.down = on && Math.sin(ang) > 0.38;
      touchKeys.up = on && Math.sin(ang) < -0.55;
    };
    stick.addEventListener('pointerdown', e => {
      e.preventDefault(); sid = e.pointerId; stick.setPointerCapture(sid);
      const r = stick.querySelector('.base').getBoundingClientRect();
      cx = r.left + r.width / 2; cy = r.top + r.height / 2;
      setDir(e.clientX - cx, e.clientY - cy);
    });
    stick.addEventListener('pointermove', e => { if (e.pointerId === sid) setDir(e.clientX - cx, e.clientY - cy); });
    const end = e => { if (e.pointerId === sid) { sid = null; setDir(0, 0); } };
    stick.addEventListener('pointerup', end); stick.addEventListener('pointercancel', end);
    document.querySelectorAll('.tk').forEach(btn => {
      const k = btn.dataset.k;
      btn.addEventListener('pointerdown', e => { e.preventDefault(); btn.setPointerCapture(e.pointerId); touchKeys[k] = true; btn.classList.add('on'); audio(); });
      const up = () => { touchKeys[k] = false; btn.classList.remove('on'); };
      btn.addEventListener('pointerup', up); btn.addEventListener('pointercancel', up); btn.addEventListener('lostpointercapture', up);
      btn.addEventListener('contextmenu', e => e.preventDefault());
    });
  }

  // ---------------- 流程 ----------------
  const LEVEL_ORDER = ['easy', 'normal', 'hard', 'god'];
  let level = 'hard', demo = false, mode = 'menu', modeT = 0, prevMode = 'fight';
  let game = C.newGame(), reader = C.makeInputReader(), ais = [null, null];
  const match = { wins: [0, 0], round: 1, dmg: 0, maxCombo: 0 };
  let names = ['你', 'AI'];
  let helpReturn = null; // 关掉说明后回到哪里

  function setLevel(lv) {
    level = lv;
    document.querySelectorAll('.level').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.level === lv)));
    try { localStorage.setItem('fight-level', lv); } catch (e) { /* 忽略 */ }
  }
  function shiftLevel(d) { setLevel(LEVEL_ORDER[(LEVEL_ORDER.indexOf(level) + d + 4) % 4]); $('lv-' + level).focus(); }
  document.querySelectorAll('.level').forEach(b => {
    b.addEventListener('click', () => setLevel(b.dataset.level));
    b.addEventListener('dblclick', () => { setLevel(b.dataset.level); startMatch(false); });
  });

  function show(id) { for (const k of ['menu', 'pause', 'result']) $(k).hidden = k !== id; }
  function setStatus(t) { $('status').textContent = t; }
  function syncBar() {
    const pb = $('tb-pause');
    pb.disabled = !(inMatch() || mode === 'paused');
    pb.innerHTML = mode === 'paused' ? '继续 <kbd>Esc</kbd>' : '暂停 <kbd>Esc</kbd>';
  }
  function setMode(m) {
    mode = m; modeT = 0; syncBar();
    // 进入对战时把焦点从按钮上拿走，免得空格/回车同时点到按钮
    if ((m === 'fight' || m === 'intro') && document.activeElement && document.activeElement.blur) document.activeElement.blur();
  }

  function menuBattle() { game = C.newGame(); ais = [C.makeAI('hard', 0, Date.now() & 0xff), C.makeAI('normal', 1, 9)]; }

  function newRound() {
    game = C.newGame();
    reader = C.makeInputReader();
    const seed = (Date.now() & 0xffff) + match.round;
    if (demo) ais = [C.makeAI('god', 0, seed), C.makeAI('hard', 1, seed + 9)];
    else {
      const keep = ais[1] && ais[1].level === C.LEVELS[level] ? ais[1].habit : null;
      ais = [null, C.makeAI(level, 1, seed)];
      if (keep) Object.assign(ais[1].habit, keep); // 整场比赛都记得你的习惯
    }
    shown[0].drain = shown[1].drain = C.MAX_HP;
    parts = []; popups.length = 0;
    setMode('intro');
    SFX.bell();
  }

  function seenHelp() { try { return localStorage.getItem('fight-help-seen') === '1'; } catch (e) { return true; } }
  function startMatch(isDemo) {
    audio();
    if (!isDemo && !seenHelp()) { openHelp(() => startMatch(false)); return; } // 第一次开战先看一眼操作说明
    demo = !!isDemo;
    match.wins = [0, 0]; match.round = 1; match.dmg = 0; match.maxCombo = 0;
    ais = [null, null];
    names = demo ? ['AI · 魔王', 'AI · 高手'] : ['你', 'AI · ' + C.LEVELS[level].name];
    show(null);
    releaseAll();
    setStatus(demo ? '观战中：左边魔王，右边高手。按 Esc 暂停或退出观战。' : `对手：${C.LEVELS[level].name}。按 Esc 暂停，按 H 看操作说明。`);
    $('wrap').scrollIntoView({ block: 'nearest', behavior: reduceMotion ? 'auto' : 'smooth' });
    newRound();
  }
  function restartMatch() { startMatch(demo); }

  function pause(why) {
    if (!inMatch()) return;
    prevMode = mode; setMode('paused');
    $('pause-hint').textContent = why || (demo ? '正在观战。选“回主菜单”退出观战。' : '切换到别的窗口时会自动暂停。');
    $('resume').innerHTML = (demo ? '继续观战' : '继续') + ' <kbd>Esc</kbd>';
    show('pause'); $('resume').focus();
    setStatus('已暂停。');
  }
  function resume() {
    if (mode !== 'paused') return;
    show(null); setMode(prevMode === 'intro' ? 'intro' : 'fight');
    releaseAll();
    setStatus(demo ? '观战中：按 Esc 暂停或退出观战。' : `对手：${C.LEVELS[level].name}。按 Esc 暂停。`);
  }
  function toMenu() {
    menuBattle(); setMode('menu'); show('menu'); showRec();
    setStatus('选好难度后点“开战”。'); $('start').focus();
  }
  function toggleMute() { muted = !muted; $('tb-mute').innerHTML = '声音：' + (muted ? '关' : '开') + ' <kbd>M</kbd>'; }

  function openHelp(after) {
    if ($('help').hidden === false) return;
    if (inMatch()) pause();
    helpReturn = after || null;
    $('help').hidden = false;
    $('help-close').focus();
  }
  function closeHelp() {
    $('help').hidden = true;
    try { localStorage.setItem('fight-help-seen', '1'); } catch (e) { /* 忽略 */ }
    const after = helpReturn; helpReturn = null;
    if (after) { after(); return; }
    if (mode === 'paused') $('resume').focus();
    else if (mode === 'menu') $('start').focus();
    else if (mode === 'result') $('again').focus();
  }

  $('start').addEventListener('click', () => startMatch(false));
  $('demo').addEventListener('click', () => startMatch(true));
  $('menu-help').addEventListener('click', () => openHelp());
  $('resume').addEventListener('click', resume);
  $('restart').addEventListener('click', restartMatch);
  $('pause-help').addEventListener('click', () => openHelp());
  $('quit').addEventListener('click', toMenu);
  $('again').addEventListener('click', () => startMatch(demo));
  $('back').addEventListener('click', toMenu);
  $('help-close').addEventListener('click', closeHelp);
  $('help-close-x').addEventListener('click', closeHelp);
  $('help').addEventListener('click', e => { if (e.target === $('help')) closeHelp(); });
  $('tb-help').addEventListener('click', () => openHelp());
  $('tb-mute').addEventListener('click', toggleMute);
  $('tb-pause').addEventListener('click', () => { if (mode === 'paused') resume(); else pause(); });
  // 主菜单按钮：对战中先暂停，让人在暂停页确认“回主菜单”，免得误点丢掉一场
  $('tb-menu').addEventListener('click', () => {
    if (!$('help').hidden) closeHelp();
    if (inMatch()) { pause('要离开这场吗？点“回主菜单”确认，或按 Esc 继续。'); $('quit').focus(); }
    else toMenu();
  });

  function endMatch() {
    setMode('result');
    const w = match.wins;
    const t = $('result-title');
    if (demo) { t.textContent = w[0] > w[1] ? '魔王胜' : '高手胜'; t.className = 'big win'; }
    else if (w[0] > w[1]) { t.textContent = '你赢了'; t.className = 'big win'; }
    else { t.textContent = 'AI 获胜'; t.className = 'big lose'; }
    $('st-dmg').textContent = match.dmg;
    $('st-combo').textContent = match.maxCombo;
    $('st-rounds').textContent = `${w[0]} : ${w[1]}`;
    const h = ais[1] ? ais[1].habit : {};
    const top = Object.keys(h).filter(k => HABIT_NAMES[k]).sort((a, b) => h[b] - h[a])[0];
    $('st-habit').innerHTML = demo ? '' : top
      ? `AI 记下了你这场最爱用的招：<em>${HABIT_NAMES[top]}</em>（${Math.round(h[top])} 次）。下一场它会更提防这一招。`
      : '你这场几乎没出招，AI 没摸到你的习惯。';
    if (!demo) {
      const r = rec[level] || { w: 0, l: 0 };
      if (w[0] > w[1]) r.w++; else r.l++;
      rec[level] = r; saveRec(rec);
    }
    show('result');
    $('again').focus();
    setStatus('Enter 再来一场，Esc 换难度。');
  }

  function handleEvents() {
    for (const e of game.events) {
      if (e.type === 'hit') {
        const x = e.x, y = GY - e.y;
        burst(x, y, e.super ? '255,230,120' : '255,240,200', e.big ? 18 : 10, e.big ? 9 : 6, 16);
        ring(x, y, '255,220,150');
        shake = Math.max(shake, e.big ? 9 : 4);
        if (e.super) { flashScreen = 10; shake = 16; }
        SFX.hit(e.big);
        if (e.counter) popups.push({ text: '反击', x, y: y - 60, life: 40, max: 40, color: '255,120,90', size: 34 });
        if (e.throw) popups.push({ text: '投', x, y: y - 60, life: 36, max: 36, color: '236,228,211', size: 40 });
        if (!demo && e.who === 1) { match.dmg += e.dmg; match.maxCombo = Math.max(match.maxCombo, e.combo); }
      } else if (e.type === 'block') {
        ring(e.x, GY - e.y, '140,200,255'); burst(e.x, GY - e.y, '160,210,255', 6, 4, 10); SFX.block();
      } else if (e.type === 'proj') SFX.proj(e.super);
      else if (e.type === 'super') { superDim = 30; SFX.super(); }
      else if (e.type === 'clash') { burst(e.x, GY - e.y, '255,255,255', 14, 7, 18); SFX.block(); }
      else if (e.type === 'fall') { dust(e.x); shake = Math.max(shake, 5); }
      else if (e.type === 'land') dust(game.f[e.who].x);
      else if (e.type === 'jump') SFX.jump();
      else if (e.type === 'ko') { SFX.ko(); flashScreen = 6; }
    }
    game.events.length = 0;
  }

  let slowTick = 0;
  function tick() {
    modeT++;
    stepParts();
    if (mode === 'menu') {
      if (ais[0] && ais[1]) {
        C.step(game, ais[0].intent(game), ais[1].intent(game)); game.events.length = 0;
        if (game.over) menuBattle();
      }
      return;
    }
    if (mode === 'intro') {
      if (modeT >= 100) setMode('fight');
      return;
    }
    if (mode !== 'fight') return;
    if (game.koT > 0 && game.koT < 60 && !reduceMotion && (slowTick++ % 2)) return; // KO 后慢动作
    const f0 = game.f[0];
    const it0 = ais[0] ? ais[0].intent(game) : reader(readRaw(), f0.face, f0.st === 'air' && !f0.airUsed);
    const it1 = ais[1].intent(game);
    C.step(game, it0, it1);
    handleEvents();
    if (game.over) {
      if (game.winner === 0 || game.winner === 1) match.wins[game.winner]++;
      if (match.wins[0] >= 2 || match.wins[1] >= 2 || match.round >= 5) endMatch();
      else { match.round++; newRound(); }
    }
  }

  const ROUND_NAMES = ['', '第一回合', '第二回合', '第三回合', '第四回合', '决胜回合'];
  function render() {
    ctx.save();
    if (shake > 0.5 && !reduceMotion) ctx.translate((Math.random() - 0.5) * shake, (Math.random() - 0.5) * shake);
    ctx.drawImage(bg, -10, -10, W + 20, H + 20);
    if (superDim > 0) { ctx.fillStyle = `rgba(5,5,15,${Math.min(0.6, superDim / 30)})`; ctx.fillRect(0, 0, W, H); }
    const order = game.f[0].st === 'atk' ? [1, 0] : [0, 1];
    for (const i of order) drawFighter(game.f[i], i, game.t);
    for (const p of game.projs) drawProj(p);
    drawParts();
    ctx.restore();
    if (flashScreen > 0) { ctx.fillStyle = `rgba(255,255,255,${flashScreen / 14})`; ctx.fillRect(0, 0, W, H); }
    if (mode !== 'menu') drawHUD();
    if (mode === 'intro') {
      if (modeT < 60) banner(ROUND_NAMES[Math.min(match.round, 5)], `${match.wins[0]} : ${match.wins[1]}`);
      else banner('开 战', null, '#efc25a');
    }
    if ((mode === 'fight' || mode === 'paused') && game.koT && game.koT > 20) {
      const w = game.winner;
      const txt = game.roundT === 0 ? '时间到' : 'K.O.';
      const sub = w === 2 ? '平局' : demo ? (w === 0 ? '魔王拿下这一回合' : '高手拿下这一回合') : (w === 0 ? '你拿下这一回合' : 'AI 拿下这一回合');
      banner(txt, sub, txt === 'K.O.' ? '#ff6b4a' : '#ece4d3');
    }
  }

  // 主循环：固定 60 帧逻辑，画面跟随刷新率
  let last = performance.now(), acc = 0;
  function loop(now) {
    acc += Math.min(100, now - last); last = now;
    let n = 0;
    while (acc >= 1000 / 60 && n < 4) { tick(); acc -= 1000 / 60; n++; }
    if (n === 4) acc = 0;
    pollPadButtons();
    render();
    requestAnimationFrame(loop);
  }

  // 招式表（直接读引擎里的帧数据，和游戏永远一致）
  function fillMoveTable() {
    const M = C.MOVES;
    const rows = [
      ['jab', '<kbd>J</kbd>', '最快的出手，打中可以接必杀'],
      ['heavy', '<kbd>K</kbd>', '距离远、伤害高，打中可以接升龙'],
      ['cA', '下 + <kbd>J</kbd>', '蹲着戳脚，对手必须蹲防'],
      ['cB', '下 + <kbd>K</kbd>', '打中直接倒地；收招慢'],
      ['over', '前 + <kbd>K</kbd>', '专破蹲防，慢但能反应'],
      ['jA', '空中 <kbd>J</kbd>', '跳入起手，出得快'],
      ['jB', '空中 <kbd>K</kbd>', '跳入主力，伤害高'],
      ['throw', '贴身 <kbd>L</kbd>', '防不住；对手出招时投不到'],
      ['fbA', '<kbd>U</kbd> 或 ↓↘→+J', '慢速波，跟在后面一起压上去'],
      ['fbB', '<kbd>Shift</kbd>+<kbd>U</kbd> 或 ↓↘→+K', '快速波，远距离消耗'],
      ['dpA', '<kbd>I</kbd> 或 →↓↘+J', `前 ${M.dpA.inv} 帧无敌，专打跳过来的人`],
      ['dpB', '<kbd>Shift</kbd>+<kbd>I</kbd> 或 →↓↘+K', `前 ${M.dpB.inv} 帧无敌，伤害更高、破绽更大`],
      ['super', '气满 <kbd>O</kbd> 或 ↓↘→+L', `前 ${M.super.inv} 帧无敌，被防住也掉不少血`],
    ];
    const guardTag = m => {
      if (m.throw) return '<span class="tag un">防不住</span>';
      if (m.proj) return '<span class="tag">站蹲都行</span>';
      return m.guard === 'high' ? '<span class="tag hi">只能站防</span>' : m.guard === 'low' ? '<span class="tag lo">只能蹲防</span>' : '<span class="tag">站蹲都行</span>';
    };
    $('move-table').innerHTML = rows.map(([id, key, use]) => {
      const m = M[id];
      const dmg = m.proj ? m.proj.dmg : m.dmg;
      return `<tr><td>${m.name}</td><td>${key}</td><td class="num">${m.s} 帧</td><td class="num">${dmg}</td><td>${guardTag(m)}</td><td>${use}</td></tr>`;
    }).join('');
  }

  function boot() {
    let saved = null;
    try { saved = localStorage.getItem('fight-level'); } catch (e) { /* 忽略 */ }
    if (saved && C.LEVELS[saved]) setLevel(saved);
    showRec();
    fillMoveTable();
    setupTouch();
    menuBattle();
    syncBar();
    requestAnimationFrame(loop);
    $('start').focus({ preventScroll: true });
    if (document.fonts && document.fonts.load) {
      ['96px "Zhi Mang Xing"', '700 32px "Oxanium"', '600 15px "Noto Sans SC"'].forEach(f => document.fonts.load(f).catch(() => {}));
    }
    // #demo 直接看 AI 互打；#demo600 先快进 600 帧（测试截图用）；#help 打开说明
    const dm = location.hash.match(/^#demo(\d+)?$/);
    if (dm) { startMatch(true); for (let k = 0; k < Math.min(+dm[1] || 0, 20000); k++) tick(); }
    else if (location.hash === '#help') openHelp();
  }
  boot();
})();
