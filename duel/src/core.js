/* 拆招擂台 · 引擎 + AI
 * 纯逻辑、确定性、固定 60 帧/秒。浏览器和 node 通用（node 里用来跑 AI 对打测试）。
 * 坐标：x 向右，y 向上（0 = 地面）。intent 里的 h 是相对方向：1 = 朝对手，-1 = 背对手（按住即防御）。
 */
(function (root) {
  'use strict';

  const WALL_L = 40, WALL_R = 920, GRAV = 0.8;
  const JUMP_V = 15, JUMP_VX = 4.2, WALK_F = 3.4, WALK_B = 2.7;
  const MAX_HP = 1000, MAX_METER = 100, ROUND_FRAMES = 60 * 60;
  const DOWN_FRAMES = 40, RISE_FRAMES = 14, BODY_W = 56;

  // s 起手帧 / a 持续帧 / r 收招帧；hb 判定框（相对脚底中心，朝右时）；guard: high 须站防 / low 须蹲防 / mid 都能防
  const MOVES = {
    jab:   { name: '轻拳', s: 4, a: 3, r: 8,  dmg: 30, hb: { x: 18, w: 64, y: 96, h: 28 }, hs: 15, bs: 11, kb: 3.2, guard: 'mid', cancel: true, meter: 4, stop: 6 },
    heavy: { name: '重踢', s: 8, a: 4, r: 17, dmg: 72, hb: { x: 20, w: 92, y: 74, h: 40 }, hs: 20, bs: 15, kb: 5.5, guard: 'mid', cancel: true, meter: 8, stop: 9 },
    cA:    { name: '下段拳', s: 5, a: 3, r: 9, dmg: 26, hb: { x: 18, w: 68, y: 22, h: 30 }, hs: 14, bs: 10, kb: 2.6, guard: 'low', cancel: true, crouch: true, meter: 4, stop: 6 },
    cB:    { name: '扫腿', s: 9, a: 4, r: 22, dmg: 58, hb: { x: 18, w: 100, y: 0, h: 22 }, hs: 0, bs: 13, kb: 4, guard: 'low', kd: true, crouch: true, meter: 8, stop: 9 },
    over:  { name: '下劈', s: 19, a: 3, r: 14, dmg: 62, hb: { x: 14, w: 78, y: 80, h: 80 }, hs: 18, bs: 12, kb: 4.5, guard: 'high', meter: 8, stop: 10 },
    jA:    { name: '空中拳', s: 4, a: 8, r: 6, dmg: 42, hb: { x: 8, w: 62, y: 18, h: 52 }, hs: 16, bs: 12, kb: 3, guard: 'high', air: true, meter: 5, stop: 7 },
    jB:    { name: '空中踢', s: 7, a: 6, r: 10, dmg: 66, hb: { x: 14, w: 78, y: -4, h: 50 }, hs: 19, bs: 13, kb: 4, guard: 'high', air: true, meter: 7, stop: 9 },
    throw: { name: '投技', s: 4, a: 2, r: 22, dmg: 95, range: 62, throw: true, meter: 10, stop: 12 },
    fbA:   { name: '慢波', s: 13, a: 1, r: 26, proj: { vx: 6, dmg: 52, hs: 18, bs: 14, kb: 4, chip: 8 }, meter: 6 },
    fbB:   { name: '快波', s: 13, a: 1, r: 30, proj: { vx: 10, dmg: 52, hs: 18, bs: 14, kb: 4, chip: 8 }, meter: 6 },
    dpA:   { name: '升龙', s: 3, a: 10, r: 26, dmg: 85, hb: { x: 0, w: 58, y: 40, h: 140 }, hs: 0, bs: 14, kb: 3, guard: 'mid', kd: true, launch: 11, inv: 8, rise: 11, rvx: 1.6, meter: 10, stop: 10, chip: 10 },
    dpB:   { name: '大升龙', s: 3, a: 12, r: 32, dmg: 110, hb: { x: 0, w: 60, y: 40, h: 150 }, hs: 0, bs: 16, kb: 3, guard: 'mid', kd: true, launch: 12, inv: 11, rise: 13, rvx: 2.4, meter: 10, stop: 12, chip: 14 },
    super: { name: '气功炮', s: 8, a: 1, r: 34, cost: 100, inv: 14, proj: { vx: 13, dmg: 240, hs: 0, bs: 18, kb: 6, chip: 45, super: true, kd: true }, stop: 18 },
  };
  const SPECIALS = { fbA: 1, fbB: 1, dpA: 1, dpB: 1, super: 1 };

  // ---------------- 状态 ----------------
  function newFighter(x, face) {
    return {
      x, y: 0, vx: 0, vy: 0, face, hp: MAX_HP, meter: 0,
      st: 'stand', t: 0, mv: '', mt: 0, hit: false, conn: false, connT: 0,
      hs: 0, combo: 0, juggle: 0, cr: false, airUsed: false,
      hbk: false, wantCr: false, flash: 0,
    };
  }

  function newGame(opts) {
    opts = opts || {};
    return {
      t: 0, roundT: ROUND_FRAMES, hitstop: 0, koT: 0, over: false, winner: -1,
      f: [newFighter(330, 1), newFighter(630, -1)],
      projs: [], pid: 0,
      events: opts.silent ? null : [],
    };
  }

  function cloneGame(g) {
    const projs = new Array(g.projs.length);
    for (let i = 0; i < g.projs.length; i++) projs[i] = Object.assign({}, g.projs[i]);
    return {
      t: g.t, roundT: g.roundT, hitstop: g.hitstop, koT: g.koT, over: g.over, winner: g.winner,
      f: [Object.assign({}, g.f[0]), Object.assign({}, g.f[1])],
      projs, pid: g.pid, events: null,
    };
  }

  function emit(g, e) { if (g.events) g.events.push(e); }

  // ---------------- 判定框 ----------------
  function worldBox(f, b) {
    const x0 = f.face === 1 ? f.x + b.x : f.x - b.x - b.w;
    return { x0, x1: x0 + b.w, y0: f.y + b.y, y1: f.y + b.y + b.h };
  }
  function overlap(a, b) { return a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1; }

  function isCrouching(f) {
    if (f.y > 0) return false;
    if (f.st === 'crouch') return true;
    if (f.st === 'atk') return !!MOVES[f.mv].crouch;
    if (f.st === 'block' || f.st === 'hit') return f.cr;
    return false;
  }

  function bodyBox(f) {
    if (f.st === 'down' || f.st === 'rise' || f.st === 'ko') return null;
    const h = f.y > 0 ? 118 : isCrouching(f) ? 92 : 150;
    return { x0: f.x - BODY_W / 2, x1: f.x + BODY_W / 2, y0: f.y, y1: f.y + h };
  }

  // 出招时伸出的手脚也能被打（收招前半段）
  function limbBox(f) {
    if (f.st !== 'atk') return null;
    const m = MOVES[f.mv];
    if (!m.hb || f.mt < m.s) return null;
    if (f.mt > m.s + m.a + (m.r >> 1)) return null;
    const b = worldBox(f, m.hb);
    const pad = 6;
    return { x0: b.x0 + pad, x1: b.x1 - pad, y0: b.y0 + 2, y1: b.y1 - 2 };
  }

  function invulnerable(f) {
    if (f.st === 'down' || f.st === 'rise' || f.st === 'ko') return true;
    if (f.st === 'airhit' && f.juggle >= 3) return true;
    if (f.st === 'atk') { const m = MOVES[f.mv]; if (m.inv && f.mt <= m.inv) return true; }
    return false;
  }

  function hurtOverlap(box, d) {
    const b = bodyBox(d);
    if (b && overlap(box, b)) return true;
    const l = limbBox(d);
    return !!(l && overlap(box, l));
  }

  // ---------------- 流程 ----------------
  function actionable(f) { return f.st === 'stand' || f.st === 'crouch'; }

  function canCancel(f, id) {
    if (f.st !== 'atk' || !SPECIALS[id]) return false;
    const m = MOVES[f.mv];
    return !!(m.cancel && f.conn && f.mt - f.connT <= 12);
  }

  function hasProj(g, i) {
    for (let k = 0; k < g.projs.length; k++) if (g.projs[k].owner === i) return true;
    return false;
  }

  function moveAllowed(g, i, id) {
    const f = g.f[i], m = MOVES[id];
    if (!m) return false;
    if (m.air ? !(f.st === 'air' && !f.airUsed) : f.y > 0) return false;
    if (m.cost && f.meter < m.cost) return false;
    if (m.proj && hasProj(g, i)) return false;
    return true;
  }

  function startMove(g, i, id) {
    if (!moveAllowed(g, i, id)) return false;
    const f = g.f[i], m = MOVES[id];
    f.st = 'atk'; f.mv = id; f.mt = 0; f.t = 0; f.hit = false; f.conn = false; f.connT = 0;
    if (!m.air) f.vx = 0; else f.airUsed = true;
    if (m.cost) f.meter -= m.cost;
    if (id === 'super') emit(g, { type: 'super', who: i });
    return true;
  }

  function toNeutral(f) {
    f.st = f.wantCr ? 'crouch' : 'stand';
    f.mv = ''; f.t = 0; f.vx = 0; f.hs = 0; f.combo = 0; f.juggle = 0; f.airUsed = false;
  }

  function think(g, i, it) {
    const f = g.f[i], o = g.f[1 - i];
    f.hbk = it.h === -1;
    f.wantCr = it.v === -1;
    if (f.st === 'ko' || g.koT) return;
    if (f.y <= 0 && (f.st === 'stand' || f.st === 'crouch')) f.face = o.x >= f.x ? 1 : -1;

    if (it.atk && canCancel(f, it.atk)) { startMove(g, i, it.atk); return; }
    if (actionable(f)) {
      if (it.atk && startMove(g, i, it.atk)) return;
      if (it.v === 1) {
        f.st = 'air'; f.t = 0; f.vy = JUMP_V; f.vx = it.h * JUMP_VX * f.face; f.y = 0.01;
        emit(g, { type: 'jump', who: i });
        return;
      }
      if (it.v === -1) { if (f.st !== 'crouch') { f.st = 'crouch'; f.t = 0; } f.vx = 0; return; }
      if (f.st !== 'stand') { f.st = 'stand'; f.t = 0; }
      f.vx = it.h === 1 ? WALK_F * f.face : it.h === -1 ? -WALK_B * f.face : 0;
      return;
    }
    if (f.st === 'air' && it.atk && MOVES[it.atk] && MOVES[it.atk].air) startMove(g, i, it.atk);
  }

  function spawnProj(g, i, m) {
    const f = g.f[i], p = m.proj;
    g.projs.push({
      id: ++g.pid, owner: i, x: f.x + f.face * 58, y: p.super ? 70 : 84, vx: p.vx * f.face,
      w: p.super ? 70 : 38, h: p.super ? 56 : 30, dmg: p.dmg, hs: p.hs, bs: p.bs, kb: p.kb, chip: p.chip,
      super: !!p.super, kd: !!p.kd, life: 200,
    });
    emit(g, { type: 'proj', who: i, super: !!p.super });
  }

  function land(g, f, i) {
    f.y = 0; f.vy = 0;
    if (f.st === 'air') { toNeutral(f); emit(g, { type: 'land', who: i }); }
    else if (f.st === 'atk') {
      if (MOVES[f.mv].air) { toNeutral(f); emit(g, { type: 'land', who: i }); }
      else f.vx = 0;
    } else if (f.st === 'airhit') {
      f.vx = 0;
      if (f.hp <= 0) { f.st = 'ko'; f.t = 0; }
      else { f.st = 'down'; f.hs = DOWN_FRAMES; f.t = 0; }
      emit(g, { type: 'fall', who: i, x: f.x });
    }
  }

  function advance(g, i) {
    const f = g.f[i];
    f.t++;
    if (f.flash > 0) f.flash--;
    switch (f.st) {
      case 'atk': {
        f.mt++;
        const m = MOVES[f.mv];
        if (m.rise && f.mt === m.s) { f.vy = m.rise; f.vx = m.rvx * f.face; f.y = Math.max(f.y, 0.01); }
        if (m.proj && f.mt === m.s) spawnProj(g, i, m);
        if (f.mt >= m.s + m.a + m.r && f.y <= 0) toNeutral(f);
        break;
      }
      case 'hit': case 'block':
        f.hs--; f.vx *= 0.82;
        if (f.hs <= 0) toNeutral(f);
        break;
      case 'down':
        if (--f.hs <= 0) { f.st = 'rise'; f.hs = RISE_FRAMES; f.t = 0; }
        break;
      case 'rise':
        if (--f.hs <= 0) toNeutral(f);
        break;
    }
    if (f.y > 0 || f.vy > 0) {
      f.x += f.vx; f.y += f.vy; f.vy -= GRAV;
      if (f.y <= 0) land(g, f, i);
    } else {
      f.x += f.vx;
    }
  }

  function separate(g) {
    const a = g.f[0], b = g.f[1];
    for (const f of g.f) {
      if (f.x < WALL_L) f.x = WALL_L;
      if (f.x > WALL_R) f.x = WALL_R;
    }
    if (a.st === 'ko' || b.st === 'ko' || a.st === 'down' || b.st === 'down') return;
    const ha = a.y > 0 ? 118 : 150, hb = b.y > 0 ? 118 : 150;
    if (a.y >= b.y + hb || b.y >= a.y + ha) return;
    const dx = b.x - a.x, ad = Math.abs(dx);
    if (ad >= BODY_W) return;
    const dir = dx !== 0 ? Math.sign(dx) : (a.face === 1 ? 1 : -1);
    const push = (BODY_W - ad) / 2;
    a.x -= dir * push; b.x += dir * push;
    if (a.x < WALL_L) { b.x += WALL_L - a.x; a.x = WALL_L; }
    if (a.x > WALL_R) { b.x -= a.x - WALL_R; a.x = WALL_R; }
    if (b.x < WALL_L) { a.x += WALL_L - b.x; b.x = WALL_L; }
    if (b.x > WALL_R) { a.x -= b.x - WALL_R; b.x = WALL_R; }
  }

  function canBlock(d) {
    return d.y <= 0 && (d.st === 'stand' || d.st === 'crouch' || d.st === 'block');
  }
  function guardOK(guard, d) {
    if (guard === 'high') return !d.wantCr;
    if (guard === 'low') return d.wantCr;
    return true;
  }

  // m: 招式或飞行道具参数；ai: 攻击方下标（飞行道具为其主人）；dir: 击退方向
  function applyHit(g, ai, di, m, dir, isProj) {
    const a = g.f[ai], d = g.f[di];
    const blocked = !m.throw && canBlock(d) && d.hbk && guardOK(m.guard || 'mid', d);
    if (blocked) {
      d.st = 'block'; d.hs = m.bs; d.cr = d.wantCr; d.vx = dir * m.kb; d.mv = '';
      const chip = m.chip || 0;
      d.hp = Math.max(0, d.hp - chip);
      a.meter = Math.min(MAX_METER, a.meter + (m.meter || 4) * 0.5);
      d.meter = Math.min(MAX_METER, d.meter + 3);
      g.hitstop = Math.max(g.hitstop, 5);
      emit(g, { type: 'block', who: di, x: d.x - dir * 18, y: d.y + (d.wantCr ? 50 : 95), big: m.dmg >= 70 });
      if (d.hp <= 0) { d.st = 'airhit'; d.vy = 7; d.vx = dir * 3; d.y = Math.max(d.y, 0.01); }
    } else {
      const counter = d.st === 'atk' && d.mt < MOVES[d.mv].s;
      const scale = Math.max(0.35, 1 - 0.12 * d.combo);
      const dmg = Math.round(m.dmg * scale * (counter ? 1.2 : 1));
      d.hp = Math.max(0, d.hp - dmg);
      d.combo++;
      d.mv = ''; d.flash = 6;
      const air = d.y > 0 || m.kd || m.launch || m.throw || d.st === 'airhit' || d.hp <= 0;
      if (air) {
        d.st = 'airhit'; d.juggle++;
        d.vy = m.launch || (m.throw ? 8 : 6.5);
        d.vx = dir * (m.throw ? 5 : m.kb * 0.6 + 1.5);
        d.y = Math.max(d.y, 0.01);
      } else {
        d.cr = d.wantCr && (d.st === 'crouch' || d.st === 'block');
        d.st = 'hit';
        d.hs = Math.max(8, m.hs + (counter ? 4 : 0) - d.combo);
        d.vx = dir * m.kb;
      }
      a.meter = Math.min(MAX_METER, a.meter + (m.meter || 5));
      d.meter = Math.min(MAX_METER, d.meter + (m.meter || 5) * 0.5);
      g.hitstop = Math.max(g.hitstop, m.stop || 8);
      emit(g, {
        type: 'hit', who: di, x: d.x - dir * 16, y: d.y + (isCrouching(d) ? 55 : 100),
        dmg, combo: d.combo, counter, big: dmg >= 70, throw: !!m.throw, super: !!m.super,
      });
    }
    // 对手贴墙时，击退转成攻击方后退
    if (!isProj && a.y <= 0 && ((dir > 0 && d.x > WALL_R - 12) || (dir < 0 && d.x < WALL_L + 12))) {
      a.vx = -dir * m.kb * 0.8;
      if (a.st === 'atk') a.x -= dir * m.kb * 2;
    }
  }

  function collide(g) {
    const res = [];
    for (let i = 0; i < 2; i++) {
      const a = g.f[i], d = g.f[1 - i];
      if (a.st !== 'atk' || a.hit) continue;
      const m = MOVES[a.mv];
      if (a.mt < m.s || a.mt >= m.s + m.a) continue;
      if (m.throw) {
        const ok = a.y <= 0 && d.y <= 0 && Math.abs(d.x - a.x) <= m.range &&
          (d.st === 'stand' || d.st === 'crouch' || (d.st === 'atk' && !MOVES[d.mv].air && d.mt > MOVES[d.mv].s + MOVES[d.mv].a)) &&
          !invulnerable(d);
        if (ok) res.push(i);
        continue;
      }
      if (!m.hb || invulnerable(d)) continue;
      if (d.st === 'airhit' && d.juggle >= 3) continue;
      if (hurtOverlap(worldBox(a, m.hb), d)) res.push(i);
    }
    // 两个都打中 = 相杀，同时结算
    const hits = res.map(i => {
      const a = g.f[i], d = g.f[1 - i];
      a.hit = true; a.conn = true; a.connT = a.mt;
      return [i, MOVES[a.mv], d.x >= a.x ? 1 : -1];
    });
    for (const [i, m, dir] of hits) applyHit(g, i, 1 - i, m, dir, false);
  }

  function updateProjs(g) {
    const ps = g.projs;
    for (const p of ps) { p.x += p.vx; p.life--; }
    // 波对波：互相抵消（气功炮穿透普通波）
    for (let i = 0; i < ps.length; i++) for (let j = i + 1; j < ps.length; j++) {
      const p = ps[i], q = ps[j];
      if (p.owner === q.owner || p.life <= 0 || q.life <= 0) continue;
      if (Math.abs(p.x - q.x) < (p.w + q.w) / 2) {
        if (p.super && !q.super) q.life = 0;
        else if (q.super && !p.super) p.life = 0;
        else { p.life = 0; q.life = 0; }
        emit(g, { type: 'clash', x: (p.x + q.x) / 2, y: 95 });
      }
    }
    for (const p of ps) {
      if (p.life <= 0) continue;
      const d = g.f[1 - p.owner];
      if (invulnerable(d)) continue;
      const box = { x0: p.x - p.w / 2, x1: p.x + p.w / 2, y0: p.y, y1: p.y + p.h };
      if (hurtOverlap(box, d)) {
        p.life = 0;
        applyHit(g, p.owner, 1 - p.owner, {
          dmg: p.dmg, hs: p.hs, bs: p.bs, kb: p.kb, chip: p.chip, guard: 'mid', kd: p.kd,
          super: p.super, meter: 6, stop: p.super ? 20 : 8,
        }, p.vx > 0 ? 1 : -1, true);
      }
    }
    g.projs = ps.filter(p => p.life > 0 && p.x > WALL_L - 80 && p.x < WALL_R + 80);
  }

  function step(g, i0, i1) {
    g.t++;
    if (g.over) return;
    if (g.hitstop > 0) {
      g.hitstop--;
      g.f[0].hbk = i0.h === -1; g.f[0].wantCr = i0.v === -1;
      g.f[1].hbk = i1.h === -1; g.f[1].wantCr = i1.v === -1;
      return;
    }
    if (g.koT) {
      g.koT++;
      if (g.koT > 150) g.over = true;
    } else if (--g.roundT <= 0) {
      g.roundT = 0;
      const a = g.f[0].hp, b = g.f[1].hp;
      g.winner = a > b ? 0 : b > a ? 1 : 2;
      g.koT = 1;
      emit(g, { type: 'timeup' });
    }
    think(g, 0, i0); think(g, 1, i1);
    advance(g, 0); advance(g, 1);
    separate(g);
    collide(g);
    updateProjs(g);
    if (!g.koT) {
      const k0 = g.f[0].hp <= 0, k1 = g.f[1].hp <= 0;
      if (k0 || k1) {
        g.winner = k0 && k1 ? 2 : k0 ? 1 : 0;
        g.koT = 1;
        emit(g, { type: 'ko', who: g.winner });
      }
    }
  }

  // ---------------- 人类输入（键盘/手柄 → intent，含搓招识别） ----------------
  // 方向按小键盘记法记录（相对朝向）：6 前 4 后 2 下 3 前下 8 上
  function makeInputReader() {
    const hist = []; // 最近的方向
    let prev = { a: false, b: false, c: false };
    function dirNum(h, v) { return v === -1 ? (h === 1 ? 3 : h === -1 ? 1 : 2) : v === 1 ? (h === 1 ? 9 : h === -1 ? 7 : 8) : (h === 1 ? 6 : h === -1 ? 4 : 5); }
    function seen(seq, win) {
      // 在最近 win 帧里按顺序出现 seq
      let k = seq.length - 1;
      for (let i = hist.length - 1; i >= 0 && i >= hist.length - win && k >= 0; i--) {
        if (seq[k].indexOf(hist[i]) >= 0) k--;
      }
      return k < 0;
    }
    return function read(raw, face, inAir) {
      const right = raw.right && !raw.left, left = raw.left && !raw.right;
      const h = right ? face : left ? -face : 0;
      const v = raw.down ? -1 : raw.up ? 1 : 0;
      hist.push(dirNum(h, v));
      if (hist.length > 30) hist.shift();
      const pa = raw.a && !prev.a, pb = raw.b && !prev.b, pc = raw.c && !prev.c;
      // 一键必杀（和上一版格斗大脑实验台一样）：fb 波动、dp 升龙、su 气功炮；shift 放重版本
      const pf = raw.fb && !prev.fb, pd = raw.dp && !prev.dp, ps = raw.su && !prev.su;
      prev = { a: raw.a, b: raw.b, c: raw.c, fb: raw.fb, dp: raw.dp, su: raw.su };
      let atk = '';
      const qcf = seen([[2], [3], [6]], 14), dp = seen([[6], [2, 1], [3]], 16);
      if (inAir) { if (pb) atk = 'jB'; else if (pa) atk = 'jA'; }
      else if (ps) atk = 'super';
      else if (pd) atk = raw.shift ? 'dpB' : 'dpA';
      else if (pf) atk = raw.shift ? 'fbB' : 'fbA';
      else if (pc) atk = qcf ? 'super' : 'throw';
      else if (pa || pb) {
        if (dp) atk = pa ? 'dpA' : 'dpB';
        else if (qcf) atk = pa ? 'fbA' : 'fbB';
        else if (v === -1) atk = pa ? 'cA' : 'cB';
        else if (pb && h === 1) atk = 'over';
        else atk = pa ? 'jab' : 'heavy';
      }
      return { h, v: inAir ? 0 : v, atk };
    };
  }

  // ---------------- AI：每次决策推演所有候选招式 × 对手的可能应对 ----------------
  const LEVELS = {
    easy:   { name: '入门', delay: 22, every: 9, rand: 0.35, horizon: 30, hold: 12, noSuper: true },
    normal: { name: '进阶', delay: 15, every: 6, rand: 0.12, horizon: 36, hold: 10 },
    hard:   { name: '高手', delay: 8,  every: 3, rand: 0.03, horizon: 40, hold: 8 },
    god:    { name: '魔王', delay: 0,  every: 2, rand: 0,    horizon: 44, hold: 6 },
  };

  const now = () => (typeof performance !== 'undefined' ? performance.now() : Date.now());
  const I = (h, v, atk) => ({ h, v, atk: atk || '' });
  const IDLE = I(0, 0);

  // 候选：seq 是 [第几帧, intent]，之后按住最后一个方向直到 hold 结束
  function groundCands(g, i, L) {
    const f = g.f[i], o = g.f[1 - i], dx = Math.abs(o.x - f.x);
    const c = [
      { k: 'idle', seq: [[0, IDLE]] },
      { k: 'fwd', seq: [[0, I(1, 0)]] },
      { k: 'back', seq: [[0, I(-1, 0)]] },
      { k: 'cblock', seq: [[0, I(-1, -1)]] },
      { k: 'jumpF', seq: [[0, I(1, 1)]] },
      { k: 'jumpF+B', seq: [[0, I(1, 1)], [13, I(0, 0, 'jB')]] },
      { k: 'jumpF+A', seq: [[0, I(1, 1)], [17, I(0, 0, 'jA')]] },
      { k: 'jumpN', seq: [[0, I(0, 1)]] },
      { k: 'jumpB', seq: [[0, I(-1, 1)]] },
      { k: 'jab', seq: [[0, I(0, 0, 'jab')]] },
      { k: 'heavy', seq: [[0, I(0, 0, 'heavy')]] },
      { k: 'cA', seq: [[0, I(0, -1, 'cA')]] },
      { k: 'cB', seq: [[0, I(0, -1, 'cB')]] },
      { k: 'over', seq: [[0, I(0, 0, 'over')]] },
      { k: 'jab>fbA', seq: [[0, I(0, 0, 'jab')], [6, I(0, 0, 'fbA')]] },
      { k: 'cA>fbB', seq: [[0, I(0, -1, 'cA')], [7, I(0, 0, 'fbB')]] },
      { k: 'heavy>dpB', seq: [[0, I(0, 0, 'heavy')], [11, I(0, 0, 'dpB')]] },
      { k: 'dpA', seq: [[0, I(0, 0, 'dpA')]] },
      { k: 'dpB', seq: [[0, I(0, 0, 'dpB')]] },
    ];
    if (!hasProj(g, i)) c.push({ k: 'fbA', seq: [[0, I(0, 0, 'fbA')]] }, { k: 'fbB', seq: [[0, I(0, 0, 'fbB')]] });
    if (dx < 110) c.push({ k: 'throw', seq: [[0, I(0, 0, 'throw')]] });
    if (f.meter >= 100 && !L.noSuper) c.push({ k: 'super', seq: [[0, I(0, 0, 'super')]] });
    return c;
  }

  // 对手可能的应对；habit 是这局里观察到的对手习惯（招式 → 次数），用得越多权重越高
  function oppOptions(g, j, habit) {
    const f = g.f[j], o = g.f[1 - j];
    if (f.st === 'air' && !f.airUsed) {
      return [
        { w: 1, seq: [[0, IDLE]] },
        { w: 1, seq: [[0, I(0, 0, 'jA')]] },
        { w: 1, seq: [[0, I(0, 0, 'jB')]] },
        { w: 1, seq: [[6, I(0, 0, 'jB')]] },
      ];
    }
    if (!actionable(f)) return [{ w: 1, seq: null }];
    const dx = Math.abs(o.x - f.x);
    const r = [
      { w: 1.0, k: 'idle', seq: [[0, IDLE]] },
      { w: 1.0, k: 'fwd', seq: [[0, I(1, 0)]] },
      { w: 1.2, k: 'back', seq: [[0, I(-1, 0)]] },
      { w: 1.4, k: 'cblock', seq: [[0, I(-1, -1)]] },
      { w: 0.8, k: 'jump', seq: [[0, I(1, 1)], [13, I(0, 0, 'jB')]] },
      { w: 1.0, k: 'jab', seq: [[0, I(0, 0, 'jab')]] },
      { w: 1.0, k: 'cA', seq: [[0, I(0, -1, 'cA')]] },
      { w: 0.7, k: 'heavy', seq: [[0, I(0, 0, 'heavy')]] },
      { w: 0.6, k: 'cB', seq: [[0, I(0, -1, 'cB')]] },
      { w: 0.6, k: 'dp', seq: [[0, I(0, 0, 'dpA')]] },
      // 等一下再出：对空升龙、迎击
      { w: 0.5, k: 'dp', seq: [[0, I(-1, -1)], [7, I(0, 0, 'dpB')]] },
      { w: 0.5, k: 'dp', seq: [[0, I(-1, -1)], [14, I(0, 0, 'dpB')]] },
      { w: 0.4, k: 'heavy', seq: [[0, I(-1, 0)], [9, I(0, 0, 'heavy')]] },
    ];
    if (!hasProj(g, j)) r.push({ w: 0.7, k: 'fb', seq: [[0, I(0, 0, 'fbA')]] });
    if (dx < 110) r.push({ w: 0.6, k: 'throw', seq: [[0, I(0, 0, 'throw')]] });
    if (habit) {
      let total = 0;
      for (const key in habit) total += habit[key];
      if (total > 0) for (const o2 of r) if (o2.k && habit[o2.k]) o2.w *= 1 + 4 * habit[o2.k] / total;
    }
    return r;
  }

  function habitKey(mv) {
    if (mv === 'dpA' || mv === 'dpB') return 'dp';
    if (mv === 'fbA' || mv === 'fbB' || mv === 'super') return 'fb';
    if (mv === 'jA' || mv === 'jB') return 'jump';
    if (mv === 'over') return 'heavy';
    return mv;
  }

  // 推演里双方“打完一招后”的默认行为：看得到的攻击就按正确高度防，否则不动
  function guardPolicy(g, i) {
    const f = g.f[i], o = g.f[1 - i];
    let threat = '';
    if (o.st === 'atk') {
      const m = MOVES[o.mv];
      if (m.hb && o.mt < m.s + m.a) threat = m.guard;
    }
    if (!threat) {
      for (const p of g.projs) {
        if (p.owner !== i && Math.abs(p.x - f.x) < 260 && Math.sign(f.x - p.x) === Math.sign(p.vx)) { threat = 'mid'; break; }
      }
    }
    if (!threat && o.y > 0 && Math.abs(o.x - f.x) < 160 && o.vy < 2) threat = 'high';
    if (!threat) return IDLE;
    return threat === 'high' ? I(-1, 0) : I(-1, -1);
  }

  function seqIntent(seq, k, hold, sim, i) {
    if (!seq) return guardPolicy(sim, i);
    let cur = null;
    for (const s of seq) if (s[0] <= k) cur = s;
    if (!cur) return IDLE;
    const last = seq[seq.length - 1][0];
    if (k > Math.max(hold, last)) return guardPolicy(sim, i);
    if (cur[0] === k) return cur[1];
    return { h: cur[1].h, v: cur[1].v, atk: '' };
  }

  function evaluate(s0, s, i) {
    const me0 = s0.f[i], op0 = s0.f[1 - i], me = s.f[i], op = s.f[1 - i];
    let v = (op0.hp - op.hp) - (me0.hp - me.hp) * 1.1;
    if (op.hp <= 0) v += 2000;
    if (me.hp <= 0) v -= 2000;
    const bad = st => st === 'hit' || st === 'airhit' || st === 'down';
    if (bad(op.st)) v += 18;
    if (bad(me.st)) v -= 18;
    v += 0.25 * (me.meter - me0.meter);
    const behind = me.face === 1 ? me.x - WALL_L : WALL_R - me.x;
    if (behind < 90) v -= 6;
    const oppBehind = op.face === 1 ? op.x - WALL_L : WALL_R - op.x;
    if (oppBehind < 90) v += 4;
    // 主动贴近施压：离 110 左右最舒服；把对手压在防御里也算优势
    v -= Math.abs(Math.abs(op.x - me.x) - 110) * 0.06;
    if (op.st === 'block') v += 6;
    return v;
  }

  function rollout(s0, i, cand, opp, L) {
    const s = cloneGame(s0);
    const j = 1 - i;
    for (let k = 0; k < L.horizon; k++) {
      const mi = seqIntent(cand.seq, k, L.hold, s, i);
      const oi = seqIntent(opp.seq, k, L.hold, s, j);
      if (i === 0) step(s, mi, oi); else step(s, oi, mi);
      if (s.koT) break;
    }
    return evaluate(s0, s, i);
  }

  function makeAI(levelKey, i, seed) {
    const L = LEVELS[levelKey];
    let rng = (seed || 12345) >>> 0;
    const rand = () => { rng = (rng * 1664525 + 1013904223) >>> 0; return rng / 4294967296; };
    const seen = []; // 对手过去的样子（模拟反应延迟）
    let plan = null, planT = -999, lastSig = '';
    const stats = { decisions: 0, rollouts: 0 };
    const habit = {}; // 这局里对手每类招式用了几次
    let lastOppMv = '';

    function perceive(g) {
      const o = g.f[1 - i];
      const curMv = o.st === 'atk' ? o.mv : '';
      if (curMv && curMv !== lastOppMv) { const k = habitKey(curMv); habit[k] = (habit[k] || 0) + 1; }
      lastOppMv = curMv;
      // 没出招时的站位习惯：每 15 帧算一次
      if (actionable(o)) {
        const k = o.hbk ? (o.wantCr ? 'cblock' : 'back') : (o.vx * o.face > 0.5 ? 'fwd' : 'idle');
        habit[k] = (habit[k] || 0) + 1 / 15;
      }
      seen.push({ f: Object.assign({}, o), projs: g.projs.filter(p => p.owner !== i).map(p => Object.assign({}, p)) });
      if (seen.length > 40) seen.shift();
      const idx = Math.max(0, seen.length - 1 - L.delay);
      const view = cloneGame(g);
      view.f[1 - i] = Object.assign({}, seen[idx].f);
      view.projs = g.projs.filter(p => p.owner === i).map(p => Object.assign({}, p)).concat(seen[idx].projs.map(p => Object.assign({}, p)));
      return view;
    }

    function decide(view) {
      const f = view.f[i];
      const cands = f.st === 'air'
        ? [{ k: 'none', seq: [[0, IDLE]] }, { k: 'jA', seq: [[0, I(0, 0, 'jA')]] }, { k: 'jB', seq: [[0, I(0, 0, 'jB')]] }]
        : groundCands(view, i, L);
      const opts = oppOptions(view, 1 - i, habit);
      // 平均分 + 最坏情况；最坏情况只看对手真会用的应对（权重不低于最高者的一半）
      const score = (c, os) => {
        let sum = 0, wsum = 0, worst = Infinity, wmax = 0;
        for (const o of os) if (o.w > wmax) wmax = o.w;
        for (const o of os) {
          const v = rollout(view, i, c, o, L);
          stats.rollouts++;
          sum += v * o.w; wsum += o.w;
          if (o.w >= wmax * 0.5 && v < worst) worst = v;
        }
        return 0.6 * (sum / wsum) + 0.4 * worst;
      };
      let pool = cands.filter(c => !c.seq[0][1].atk || moveAllowed(view, i, c.seq[0][1].atk));
      // 候选太多时先粗筛：只拿几种最重要的对手应对打分，留前 8 名做完整推演
      if (pool.length * opts.length > 160) {
        const quick = opts.slice().sort((a, b) => b.w - a.w).slice(0, 4);
        pool = pool.map(c => [score(c, quick), c]).sort((a, b) => b[0] - a[0]).slice(0, 8).map(x => x[1]);
      }
      let best = null, bestV = -Infinity;
      const scored = [];
      const t0 = now();
      for (const c of pool) {
        if (best && now() - t0 > 8) { stats.cut = (stats.cut || 0) + 1; break; } // 每帧最多算 8ms，保证不卡
        const v = score(c, opts);
        scored.push([v, c]);
        if (v > bestV) { bestV = v; best = c; }
      }
      stats.decisions++;
      if (L.rand && rand() < L.rand && scored.length) {
        scored.sort((a, b) => b[0] - a[0]);
        best = scored[Math.floor(rand() * Math.min(scored.length, 6))][1];
      }
      return best;
    }

    function intent(g) {
      const view = perceive(g);
      const f = g.f[i], o = view.f[1 - i];
      const sig = o.st + o.mv + (o.y > 0 ? 'A' : 'G') + view.projs.length;
      const free = actionable(f) || (f.st === 'air' && !f.airUsed);
      if (!free) {
        // 出招中：按计划继续（比如打中后的取消）；被打/防御中：按看到的攻击防御
        if (plan && f.st === 'atk') {
          const k = g.t - planT;
          const it = seqIntent(plan.seq, k, L.hold, view, i);
          if (it.atk) return it;
        }
        plan = null;
        return guardPolicy(view, i);
      }
      const k = g.t - planT;
      const stale = !plan || k >= L.hold || k >= L.every && sig !== lastSig || (f.st === 'air' && plan.air !== true);
      if (stale || (k >= L.every && L.every <= 3)) {
        plan = decide(view);
        if (f.st === 'air') plan = Object.assign({ air: true }, plan);
        planT = g.t; lastSig = sig;
        return seqIntent(plan.seq, 0, L.hold, view, i);
      }
      return seqIntent(plan.seq, k, L.hold, view, i);
    }
    return { intent, stats, level: L, habit };
  }

  const api = {
    MOVES, LEVELS, MAX_HP, MAX_METER, ROUND_FRAMES, WALL_L, WALL_R,
    newGame, cloneGame, step, makeInputReader, makeAI, worldBox, isCrouching,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.FightCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
