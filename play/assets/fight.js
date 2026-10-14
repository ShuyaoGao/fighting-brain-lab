/* 格斗大脑实验台 浏览器版：envs/fighting2d/core.py 的逐行 JS 移植 + 策略推理（MLP，tanh）。
 * 与 Python 版逐帧一致（tests/test_js_parity.py 用 QuickJS 对拍）。不依赖任何库。
 * 暴露全局对象 FightRL：{C, MOVES, Core, Policy, PolicyPlayer, encodeInput, decodeInput, MACROS}
 */
(function (root) {
  "use strict";

  // ---------------- 常量（constants.py） ----------------
  var C = {
    FPS: 60, STAGE_W: 384.0, STAGE_H: 224, MAX_HP: 1000, DEFAULT_ROUND_SECONDS: 30,
    BODY_HALF_W: 20.0, STAND_H: 90.0, CROUCH_H: 56.0, AIR_HURT: [-18.0, 18.0, 10.0, 80.0],
    WALK_F: 2.5, WALK_B: 2.0, JUMP_VY: 11.0, JUMP_VX: 3.0, GRAVITY: 0.75, JUMPSQUAT: 3, LANDING_LAG: 3,
    KNOCKDOWN_FRAMES: 40, AIR_HIT_KNOCKBACK: 3.0, INPUT_BUFFER: 4, MOTION_WINDOW: 15, THROW_RANGE: 56.0,
    THROW_TECH_WINDOW: 5, COMBO_SCALING: 0.1, MIN_SCALING: 0.3,
    S_IDLE: 0, S_WALK_F: 1, S_WALK_B: 2, S_CROUCH: 3, S_JUMPSQUAT: 4, S_AIR: 5, S_LANDING: 6, S_ATTACK: 7,
    S_HITSTUN: 8, S_BLOCKSTUN: 9, S_KNOCKDOWN: 10, S_AIR_HIT: 11, S_KO: 12, N_STATES: 13,
    DIRS: [5, 6, 4, 2, 8, 3, 1, 9, 7], BTN_NONE: 0, BTN_L: 1, BTN_H: 2, N_FRAME_INPUTS: 27
  };
  C.START_X = [C.STAGE_W / 2 - 72.0, C.STAGE_W / 2 + 72.0];
  var ACTIONABLE = [C.S_IDLE, C.S_WALK_F, C.S_WALK_B, C.S_CROUCH];
  var THROW_IMMUNE = [C.S_HITSTUN, C.S_BLOCKSTUN, C.S_KNOCKDOWN, C.S_KO, C.S_AIR, C.S_AIR_HIT];

  function encodeInput(d, b) { return C.DIRS.indexOf(d) * 3 + b; }
  function decodeInput(code) { return [C.DIRS[Math.floor(code / 3)], code % 3]; }
  function inArr(x, arr) { return arr.indexOf(x) >= 0; }
  // Python round()：银行家舍入
  function pyRound(x) {
    var r = Math.round(x);
    if (Math.abs(x - Math.trunc(x)) === 0.5) r = 2 * Math.round(x / 2);
    return r;
  }

  // ---------------- 招式表（moves.py） ----------------
  function M(o) {
    var d = {damage: 0, hitstun: 0, blockstun: 0, level: "mid", hitbox: [0, 0, 0, 0], push_hit: 4.0, push_block: 5.0,
      knockdown: false, cancelable: false, chip: 0, air: false, invuln: [0, 0], projectile: null, throw_: false,
      special: false};
    for (var k in o) d[k] = o[k];
    d.total = d.startup + d.active + d.recovery;
    return d;
  }
  var MOVES = [
    M({name: "st_L", startup: 4, active: 3, recovery: 7, damage: 30, hitstun: 15, blockstun: 11, level: "mid",
      hitbox: [15, 55, 55, 75], push_hit: 3.0, push_block: 4.0, cancelable: true}),
    M({name: "st_H", startup: 8, active: 4, recovery: 18, damage: 80, hitstun: 20, blockstun: 16, level: "mid",
      hitbox: [15, 82, 50, 80], push_hit: 5.0, push_block: 6.0, cancelable: true}),
    M({name: "cr_L", startup: 4, active: 2, recovery: 7, damage: 25, hitstun: 14, blockstun: 10, level: "low",
      hitbox: [15, 55, 5, 25], push_hit: 3.0, push_block: 4.0, cancelable: true}),
    M({name: "cr_H", startup: 9, active: 4, recovery: 22, damage: 70, hitstun: 0, blockstun: 14, level: "low",
      hitbox: [15, 88, 0, 18], push_hit: 4.0, push_block: 6.0, knockdown: true}),
    M({name: "j_L", startup: 4, active: 8, recovery: 4, damage: 40, hitstun: 15, blockstun: 10, level: "high",
      hitbox: [5, 45, -5, 30], push_hit: 2.0, push_block: 3.0, air: true}),
    M({name: "j_H", startup: 7, active: 6, recovery: 6, damage: 70, hitstun: 20, blockstun: 14, level: "high",
      hitbox: [5, 58, -10, 25], push_hit: 3.0, push_block: 4.0, air: true}),
    M({name: "throw", startup: 3, active: 1, recovery: 20, damage: 110, knockdown: true, throw_: true}),
    M({name: "fireball_L", startup: 12, active: 1, recovery: 30, projectile: [4.0, 60, 20, 16, 10], special: true}),
    M({name: "fireball_H", startup: 12, active: 1, recovery: 30, projectile: [6.5, 60, 20, 16, 10], special: true}),
    M({name: "dp_L", startup: 3, active: 8, recovery: 28, damage: 90, hitstun: 0, blockstun: 18, level: "mid",
      hitbox: [5, 42, 30, 125], push_hit: 2.0, push_block: 3.0, knockdown: true, invuln: [1, 6], special: true}),
    M({name: "dp_H", startup: 4, active: 8, recovery: 36, damage: 120, hitstun: 0, blockstun: 18, level: "mid",
      hitbox: [5, 45, 30, 135], push_hit: 2.0, push_block: 3.0, knockdown: true, invuln: [1, 9], special: true})
  ];
  var BY = {};
  MOVES.forEach(function (m, i) { m.idx = i; BY[m.name] = m; });
  var N_MOVES = MOVES.length;
  var PROJ_HALF_W = 12.0, PROJ_Y0 = 48.0, PROJ_Y1 = 72.0;
  var M_FB = [null, BY.fireball_L, BY.fireball_H], M_DP = [null, BY.dp_L, BY.dp_H];

  // ---------------- 角色 ----------------
  function Fighter(idx, x, facing) {
    this.idx = idx; this.x = x; this.y = 0.0; this.vx = 0.0; this.vy = 0.0; this.facing = facing;
    this.hp = C.MAX_HP; this.state = C.S_IDLE; this.stun = 0; this.move = null; this.move_frame = 0;
    this.move_done = false; this.move_contact = false; this.push_v = 0.0;
    this.dir_hist = []; for (var i = 0; i < C.MOTION_WINDOW; i++) this.dir_hist.push(5);
    this.prev_btn = 0; this.buf_btn = 0; this.buf_left = 0; this.proj = null; this.combo = 0;
    this.air_used = false; this.jump_vx = 0.0; this.dir_now = 5; this.last_input = 0; this.last_press = -999;
  }
  Fighter.prototype.airborne = function () { return this.state === C.S_AIR || this.state === C.S_AIR_HIT; };
  Fighter.prototype.crouching = function () { return inArr(this.dir_now, [1, 2, 3]); };
  Fighter.prototype.invulnerable = function () {
    if (this.state === C.S_KNOCKDOWN || this.state === C.S_KO) return true;
    var m = this.move;
    if (m !== null && m.invuln[1] > 0) return m.invuln[0] <= this.move_frame && this.move_frame <= m.invuln[1];
    return false;
  };
  Fighter.prototype.canAct = function () { return inArr(this.state, ACTIONABLE); };
  function worldBox(f, box) {
    if (f.facing > 0) return [f.x + box[0], f.x + box[1], f.y + box[2], f.y + box[3]];
    return [f.x - box[1], f.x - box[0], f.y + box[2], f.y + box[3]];
  }
  Fighter.prototype.hurtboxes = function () {
    if (this.invulnerable()) return [];
    var x = this.x, y = this.y, boxes;
    if (this.airborne()) {
      var a = C.AIR_HURT;
      boxes = [[x + a[0], x + a[1], y + a[2], y + a[3]]];
    } else if (this.state === C.S_CROUCH || ((this.state === C.S_BLOCKSTUN || this.state === C.S_HITSTUN) && this.crouching()) ||
               (this.move !== null && (this.move.name === "cr_L" || this.move.name === "cr_H"))) {
      boxes = [[x - C.BODY_HALF_W - 2, x + C.BODY_HALF_W + 2, 0.0, C.CROUCH_H]];
    } else {
      boxes = [[x - C.BODY_HALF_W, x + C.BODY_HALF_W, 0.0, C.STAND_H]];
    }
    var m = this.move;
    if (m !== null && m.hitbox[1] > 0 && this.move_frame > m.startup) {
      boxes.push(worldBox(this, [m.hitbox[0], m.hitbox[1] - 6, m.hitbox[2], m.hitbox[3]]));
    }
    return boxes;
  };
  Fighter.prototype.activeHitbox = function () {
    var m = this.move;
    if (m === null || this.move_done || m.hitbox[1] <= 0) return null;
    if (m.startup < this.move_frame && this.move_frame <= m.startup + m.active) return worldBox(this, m.hitbox);
    return null;
  };
  function overlap(a, b) { return a[0] < b[1] && b[0] < a[1] && a[2] < b[3] && b[2] < a[3]; }
  function motion(hist, seq, tail) {
    tail = tail || 5;
    var n = hist.length, i = n - 1, stop = n - tail;
    while (i >= stop && hist[i] !== seq[seq.length - 1]) i--;
    if (i < stop) return false;
    for (var k = seq.length - 2; k >= 0; k--) {
      i--;
      while (i >= 0 && hist[i] !== seq[k]) i--;
      if (i < 0) return false;
    }
    return true;
  }

  // ---------------- 核心 ----------------
  function mulberry32(a) {
    return function () {
      a |= 0; a = a + 0x6D2B79F5 | 0;
      var t = Math.imul(a ^ a >>> 15, 1 | a);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }
  function Core(opts) {
    opts = opts || {};
    this.round_frames = Math.floor((opts.round_seconds || C.DEFAULT_ROUND_SECONDS) * C.FPS);
    this.random_start = opts.random_start !== undefined ? opts.random_start : true;
    this.rand = mulberry32(opts.seed || 12345);
    this.reset();
  }
  Core.prototype.reset = function () {
    var x0 = C.START_X[0], x1 = C.START_X[1];
    if (this.random_start) {
      var shift = -60 + 120 * this.rand(), gap = -30 + 70 * this.rand();
      x0 = x0 + shift - gap / 2; x1 = x1 + shift + gap / 2;
    }
    this.f = [new Fighter(0, x0, 1), new Fighter(1, x1, -1)];
    this.projs = []; this.frame = 0; this.done = false; this.winner = null; this.events = [];
    this.end_reason = null;
    this.stats = [{damage: 0, hits: 0, blocks: 0, throws: 0, techs: 0, cancels: 0, max_combo: 0},
                  {damage: 0, hits: 0, blocks: 0, throws: 0, techs: 0, cancels: 0, max_combo: 0}];
    return this;
  };
  Core.prototype.timeLeft = function () { return Math.max(0, this.round_frames - this.frame); };
  Core.prototype.step = function (in0, in1) {
    if (this.done) return [0, 0];
    this.events = [];
    var f0 = this.f[0], f1 = this.f[1], hp0 = f0.hp, hp1 = f1.hp;
    this._ingest(f0, in0); this._ingest(f1, in1);
    this._tick(f0); this._tick(f1);
    this._decide(f0, f1); this._decide(f1, f0);
    this._physics(f0); this._physics(f1);
    this._separateAndFace(f0, f1);
    this._updateProjectiles();
    this._resolveHits(f0, f1);
    this.frame += 1;
    this._checkEnd();
    return [hp1 - f1.hp, hp0 - f0.hp];
  };
  Core.prototype._ingest = function (f, code) {
    var db = decodeInput(code), d = db[0], b = db[1];
    f.last_input = code; f.dir_now = d;
    f.dir_hist.push(d); if (f.dir_hist.length > C.MOTION_WINDOW) f.dir_hist.shift();
    if (b && b !== f.prev_btn) { f.buf_btn = b; f.buf_left = C.INPUT_BUFFER; f.last_press = this.frame; }
    else if (f.buf_left > 0) { f.buf_left -= 1; if (f.buf_left === 0) f.buf_btn = 0; }
    f.prev_btn = b;
  };
  Core.prototype._tick = function (f) {
    var s = f.state;
    if (f.move !== null) {
      f.move_frame += 1;
      if (f.move_frame > f.move.total) {
        var air = f.move.air;
        f.move = null; f.move_frame = 0;
        if (!air && s === C.S_ATTACK) f.state = C.S_IDLE;
      }
    }
    if (s === C.S_HITSTUN || s === C.S_BLOCKSTUN || s === C.S_KNOCKDOWN || s === C.S_LANDING) {
      f.stun -= 1;
      if (f.stun <= 0) { f.state = C.S_IDLE; f.stun = 0; }
    } else if (s === C.S_JUMPSQUAT) {
      f.stun -= 1;
      if (f.stun <= 0) { f.state = C.S_AIR; f.vy = C.JUMP_VY; f.vx = f.jump_vx; f.y = 0.01; f.air_used = false; }
    }
    if (f.state !== C.S_HITSTUN && f.state !== C.S_AIR_HIT) f.combo = 0;
  };
  Core.prototype._takeButton = function (f) { var b = f.buf_btn; f.buf_btn = 0; f.buf_left = 0; return b; };
  Core.prototype._startMove = function (f, m) {
    f.move = m; f.move_frame = 1; f.move_done = false; f.move_contact = false;
    if (!m.air) f.state = C.S_ATTACK;
  };
  Core.prototype._specialFromMotion = function (f, b) {
    if (motion(f.dir_hist, [6, 2, 3])) return M_DP[b];
    if (motion(f.dir_hist, [2, 3, 6]) && f.proj === null) return M_FB[b];
    return null;
  };
  Core.prototype._decide = function (f, opp) {
    var s = f.state, m, d, b;
    if (inArr(s, ACTIONABLE)) {
      if (f.buf_btn) {
        b = this._takeButton(f);
        m = this._specialFromMotion(f, b);
        if (m === null) {
          d = f.dir_now;
          if (b === C.BTN_H && d === 6 && Math.abs(opp.x - f.x) <= C.THROW_RANGE && !opp.airborne()) m = BY["throw"];
          else if (inArr(d, [1, 2, 3])) m = (b === C.BTN_L) ? BY.cr_L : BY.cr_H;
          else m = (b === C.BTN_L) ? BY.st_L : BY.st_H;
        }
        f.vx = 0.0;
        this._startMove(f, m);
        return;
      }
      d = f.dir_now;
      if (inArr(d, [7, 8, 9])) {
        f.state = C.S_JUMPSQUAT; f.stun = C.JUMPSQUAT;
        f.jump_vx = ({7: -1, 8: 0, 9: 1})[d] * C.JUMP_VX * f.facing; f.vx = 0.0;
      } else if (inArr(d, [1, 2, 3])) f.state = C.S_CROUCH;
      else if (d === 6) f.state = C.S_WALK_F;
      else if (d === 4) f.state = C.S_WALK_B;
      else f.state = C.S_IDLE;
    } else if (s === C.S_ATTACK && f.move !== null && f.move.cancelable && f.move_contact && f.buf_btn &&
               f.move_frame <= f.move.startup + f.move.active + 8) {
      m = this._specialFromMotion(f, f.buf_btn);
      if (m !== null) { this._takeButton(f); this.events.push(["cancel", f.idx]); this.stats[f.idx].cancels++; this._startMove(f, m); }
    } else if (s === C.S_AIR && f.move === null && !f.air_used && f.buf_btn) {
      b = this._takeButton(f); f.air_used = true;
      this._startMove(f, b === C.BTN_L ? BY.j_L : BY.j_H);
    }
  };
  Core.prototype._physics = function (f) {
    var s = f.state;
    if (s === C.S_WALK_F) f.x += C.WALK_F * f.facing;
    else if (s === C.S_WALK_B) f.x -= C.WALK_B * f.facing;
    else if (s === C.S_AIR || s === C.S_AIR_HIT) {
      f.x += f.vx; f.y += f.vy; f.vy -= C.GRAVITY;
      if (f.y <= 0.0) {
        f.y = 0.0; f.vy = 0.0; f.vx = 0.0;
        if (s === C.S_AIR) { f.state = C.S_LANDING; f.stun = C.LANDING_LAG; f.move = null; f.move_frame = 0; }
        else { f.state = C.S_KNOCKDOWN; f.stun = C.KNOCKDOWN_FRAMES; f.move = null; }
      }
    }
    if (f.push_v !== 0.0 && !f.airborne()) {
      f.x += f.push_v; f.push_v *= 0.75;
      if (Math.abs(f.push_v) < 0.2) f.push_v = 0.0;
    }
    var lo = C.BODY_HALF_W, hi = C.STAGE_W - C.BODY_HALF_W;
    if (f.x < lo) f.x = lo; else if (f.x > hi) f.x = hi;
  };
  Core.prototype._separateAndFace = function (a, b) {
    var lo = C.BODY_HALF_W, hi = C.STAGE_W - C.BODY_HALF_W;
    if (Math.abs(a.y - b.y) < 60.0) {
      var dx = b.x - a.x, minD = 2 * C.BODY_HALF_W;
      if (Math.abs(dx) < minD) {
        var sgn = (dx > 0 || (dx === 0 && a.facing > 0)) ? 1.0 : -1.0;
        var over = (minD - Math.abs(dx)) / 2;
        a.x -= sgn * over; b.x += sgn * over;
        if (a.x < lo) { b.x += lo - a.x; a.x = lo; } else if (a.x > hi) { b.x -= a.x - hi; a.x = hi; }
        if (b.x < lo) { a.x += lo - b.x; b.x = lo; } else if (b.x > hi) { a.x -= b.x - hi; b.x = hi; }
      }
    }
    var pairs = [[a, b], [b, a]];
    for (var i = 0; i < 2; i++) {
      var f = pairs[i][0], o = pairs[i][1];
      if (inArr(f.state, ACTIONABLE) || f.state === C.S_LANDING) {
        if (o.x > f.x + 0.5) f.facing = 1; else if (o.x < f.x - 0.5) f.facing = -1;
      }
    }
  };
  Core.prototype._updateProjectiles = function () {
    var alive = [], self = this;
    this.projs.forEach(function (p) {
      p.x += p.vx;
      if (-PROJ_HALF_W <= p.x && p.x <= C.STAGE_W + PROJ_HALF_W) alive.push(p);
      else self.f[p.owner].proj = null;
    });
    if (alive.length === 2 && alive[0].owner !== alive[1].owner && Math.abs(alive[0].x - alive[1].x) < 2 * PROJ_HALF_W) {
      alive.forEach(function (p) { self.f[p.owner].proj = null; });
      this.events.push(["proj_clash", -1]);
      alive = [];
    }
    this.projs = alive;
  };
  Core.prototype._canBlock = function (d, level) {
    if (inArr(d.state, ACTIONABLE)) { if (!inArr(d.dir_now, [4, 1])) return false; }
    else if (d.state !== C.S_BLOCKSTUN) return false;
    var crouch = inArr(d.dir_now, [1, 2, 3]);
    if (level === "low" && !crouch) return false;
    if (level === "high" && crouch) return false;
    return true;
  };
  Core.prototype._resolveHits = function (f0, f1) {
    var pending = [], pairs = [[f0, f1], [f1, f0]], self = this;
    for (var i = 0; i < 2; i++) {
      var a = pairs[i][0], d = pairs[i][1], m = a.move;
      if (m === null) continue;
      if (m.throw_) {
        if (a.move_frame === m.startup + 1 && !a.move_done) {
          a.move_done = true;
          var ok = Math.abs(d.x - a.x) <= C.THROW_RANGE && !inArr(d.state, THROW_IMMUNE) && !d.invulnerable() &&
                   d.state !== C.S_JUMPSQUAT && !(d.move !== null && d.move.throw_ && d.move_frame <= d.move.startup + 1);
          if (ok && d.last_press >= this.frame - C.THROW_TECH_WINDOW) {
            this.events.push(["throw_tech", d.idx]); this.stats[d.idx].techs++;
            [a, d].forEach(function (g) { g.move = null; g.move_frame = 0; g.state = C.S_IDLE; });
            var sg = d.x >= a.x ? 1.0 : -1.0;
            a.push_v = -sg * 6.0; d.push_v = sg * 6.0;
          } else if (ok) pending.push(["throw", a, d, m]);
          else if (d.move !== null && d.move.throw_) this.events.push(["throw_tech", a.idx]);
        }
        continue;
      }
      if (m.projectile !== null) {
        if (a.move_frame === m.startup + 1 && !a.move_done && a.proj === null) {
          a.move_done = true;
          var pr = m.projectile;
          var p = {owner: a.idx, x: a.x + a.facing * 30.0, vx: pr[0] * a.facing, damage: pr[1], hitstun: pr[2],
                   blockstun: pr[3], chip: pr[4]};
          a.proj = p; this.projs.push(p);
        }
        continue;
      }
      var hb = a.activeHitbox();
      if (hb === null) continue;
      var hus = d.hurtboxes();
      for (var k = 0; k < hus.length; k++) {
        if (overlap(hb, hus[k])) { pending.push(["melee", a, d, m]); a.move_done = true; break; }
      }
    }
    this.projs.slice().forEach(function (p) {
      var dd = self.f[1 - p.owner];
      var pbox = [p.x - PROJ_HALF_W, p.x + PROJ_HALF_W, PROJ_Y0, PROJ_Y1];
      var hus2 = dd.hurtboxes();
      for (var k = 0; k < hus2.length; k++) {
        if (overlap(pbox, hus2[k])) {
          pending.push(["proj", self.f[p.owner], dd, p]);
          self.projs.splice(self.projs.indexOf(p), 1);
          self.f[p.owner].proj = null;
          break;
        }
      }
    });
    pending.forEach(function (e) { self._applyHit(e[0], e[1], e[2], e[3]); });
  };
  Core.prototype._applyHit = function (kind, a, d, src) {
    var sa = this.stats[a.idx], sd = this.stats[d.idx], dmg, hs, bs, chip, level, pushHit, pushBlock, kd, dir;
    if (kind === "throw") {
      dmg = src.damage; d.hp -= dmg; d.state = C.S_KNOCKDOWN; d.stun = C.KNOCKDOWN_FRAMES; d.move = null;
      d.push_v = a.facing * 6.0; sa.throws++; sa.damage += dmg; this.events.push(["throw", a.idx]);
      this._koCheck(d); return;
    }
    if (kind === "proj") {
      dmg = src.damage; hs = src.hitstun; bs = src.blockstun; chip = src.chip; level = "mid";
      pushHit = 4.0; pushBlock = 5.0; kd = false; dir = src.vx > 0 ? 1.0 : -1.0;
    } else {
      dmg = src.damage; hs = src.hitstun; bs = src.blockstun; chip = src.chip; level = src.level;
      pushHit = src.push_hit; pushBlock = src.push_block; kd = src.knockdown; dir = a.facing; a.move_contact = true;
    }
    if (!d.airborne() && this._canBlock(d, level)) {
      d.state = C.S_BLOCKSTUN; d.stun = bs; d.move = null; d.hp -= chip; sa.damage += chip; sd.blocks++;
      this._push(a, d, dir * pushBlock, kind); this.events.push(["block", d.idx]); this._koCheck(d); return;
    }
    var inCombo = d.state === C.S_HITSTUN || d.state === C.S_AIR_HIT;
    d.combo = inCombo ? d.combo + 1 : 1;
    var scale = Math.max(C.MIN_SCALING, 1.0 - C.COMBO_SCALING * (d.combo - 1));
    dmg = pyRound(dmg * scale);
    d.hp -= dmg; sa.damage += dmg; sa.hits++; sa.max_combo = Math.max(sa.max_combo, d.combo);
    d.move = null; d.move_frame = 0;
    if (d.airborne() || d.state === C.S_JUMPSQUAT) {
      d.state = C.S_AIR_HIT; d.vx = dir * C.AIR_HIT_KNOCKBACK; d.vy = Math.max(d.vy, 4.0); d.y = Math.max(d.y, 0.01);
    } else if (kd) {
      d.state = C.S_KNOCKDOWN; d.stun = C.KNOCKDOWN_FRAMES; this._push(a, d, dir * pushHit * 1.5, kind);
    } else {
      d.state = C.S_HITSTUN; d.stun = hs; this._push(a, d, dir * pushHit, kind);
    }
    this.events.push(["hit", a.idx, d.combo]);
    this._koCheck(d);
  };
  Core.prototype._push = function (a, d, v, kind) {
    var lo = C.BODY_HALF_W + 2, hi = C.STAGE_W - C.BODY_HALF_W - 2;
    var atWall = (v > 0 && d.x >= hi) || (v < 0 && d.x <= lo);
    if (atWall && kind !== "proj" && !a.airborne()) a.push_v = -v; else d.push_v = v;
  };
  Core.prototype._koCheck = function (d) { if (d.hp <= 0) { d.hp = 0; d.state = C.S_KO; d.move = null; } };
  Core.prototype._checkEnd = function () {
    var f0 = this.f[0], f1 = this.f[1], ko0 = f0.hp <= 0, ko1 = f1.hp <= 0;
    if (ko0 || ko1) { this.done = true; this.winner = (ko0 && ko1) ? -1 : (ko0 ? 1 : 0); this.end_reason = "ko"; }
    else if (this.frame >= this.round_frames) {
      this.done = true; this.winner = f0.hp > f1.hp ? 0 : (f1.hp > f0.hp ? 1 : -1); this.end_reason = "timeout";
    }
  };
  // 观测（core.observe），返回普通数组（90 维）
  var OBS_PER_FIGHTER = 6 + C.N_STATES + N_MOVES + 4 + 6 + 3;
  var OBS_DIM = 2 * OBS_PER_FIGHTER + 4;
  var PHASE_IDX = 6 + C.N_STATES + N_MOVES;
  function fighterFeats(q, m, cx, out) {
    out.push((q.x - cx) * m / cx, q.y / 100.0, q.vx * m / 6.0, q.vy / 12.0, q.facing * m, q.hp / C.MAX_HP);
    var i;
    for (i = 0; i < C.N_STATES; i++) out.push(i === q.state ? 1.0 : 0.0);
    for (i = 0; i < N_MOVES; i++) out.push(q.move !== null && q.move.idx === i ? 1.0 : 0.0);
    var phase = 0, su = 0, ac = 0, re = 0;
    if (q.move !== null) {
      var mm = q.move;
      phase = q.move_frame / mm.total;
      if (q.move_frame <= mm.startup) su = 1; else if (q.move_frame <= mm.startup + mm.active) ac = 1; else re = 1;
    }
    out.push(phase, su, ac, re);
    out.push(q.stun / 30.0, q.invulnerable() ? 1 : 0, q.canAct() ? 1 : 0, inArr(q.dir_now, [4, 1]) ? 1 : 0,
             inArr(q.dir_now, [1, 2, 3]) ? 1 : 0, Math.min(q.combo, 10) / 10.0);
    var p = q.proj;
    out.push(p !== null ? 1 : 0, p !== null ? (p.x - cx) * m / cx : 0.0, p !== null ? p.vx * m / 6.0 : 0.0);
  }
  Core.prototype.observe = function (p, visibleOnly) {
    var me = this.f[p], op = this.f[1 - p], m = me.facing, cx = C.STAGE_W / 2, out = [];
    fighterFeats(me, m, cx, out); fighterFeats(op, m, cx, out);
    out.push((op.x - me.x) * m / C.STAGE_W, (op.y - me.y) / 100.0, this.timeLeft() / this.round_frames,
             Math.abs(op.x - me.x) / C.STAGE_W);
    if (visibleOnly) {
      [0, 1].forEach(function (k) {
        [PHASE_IDX, PHASE_IDX + 4, PHASE_IDX + 5].forEach(function (j) { out[k * OBS_PER_FIGHTER + j] = 0.0; });
      });
    }
    return out;
  };

  // ---------------- 宏 / APM（wrappers/macros.py, human.py） ----------------
  var E = encodeInput;
  var MACROS = [
    [E(2, 0), E(3, 0), E(6, 1), E(6, 0)], [E(2, 0), E(3, 0), E(6, 2), E(6, 0)],
    [E(6, 0), E(2, 0), E(3, 1), E(3, 0)], [E(6, 0), E(2, 0), E(3, 2), E(3, 0)]
  ];
  var MACRO_NAMES = ["236L", "236H", "623L", "623H"];
  function release(code) { return E(decodeInput(code)[0], 0); }
  function expand(action, k) {
    var seq = action >= 27 ? MACROS[action - 27].slice() : [action];
    if (seq.length < k) { var fill = release(seq[seq.length - 1]); while (seq.length < k) seq.push(fill); }
    return seq;
  }
  function inputCost(prev, cur) {
    var p = decodeInput(prev), c = decodeInput(cur);
    return (c[0] !== p[0] ? 1 : 0) + ((c[1] !== 0 && c[1] !== p[1]) ? 1 : 0);
  }

  // ---------------- 策略（numpy_policy.py） ----------------
  function b64ToF32(s) {
    var tbl = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/", lut = {};
    for (var i = 0; i < 64; i++) lut[tbl.charAt(i)] = i;
    s = s.replace(/=+$/, "");
    var bytes = new Uint8Array(Math.floor(s.length * 3 / 4)), j = 0, buf = 0, bits = 0;
    for (i = 0; i < s.length; i++) {
      buf = (buf << 6) | lut[s.charAt(i)]; bits += 6;
      if (bits >= 8) { bits -= 8; bytes[j++] = (buf >> bits) & 255; }
    }
    return new Float32Array(bytes.buffer, 0, Math.floor(j / 4));
  }
  function toF32(x) { return typeof x === "string" ? b64ToF32(x) : new Float32Array(x); }
  function Policy(json) {
    // json.layers = [{W: (in*out 行主序), b, in, out}]，json.out 同理
    this.layers = json.layers.map(function (L) { return {W: toF32(L.W), b: toF32(L.b), n_in: L["in"], n_out: L.out}; });
    var O = json.out;
    this.outL = {W: toF32(O.W), b: toF32(O.b), n_in: O["in"], n_out: O.out};
    this.obs_dim = this.layers[0].n_in; this.n_actions = this.outL.n_out;
  }
  function dense(x, L, act) {
    var y = new Float64Array(L.n_out), W = L.W, nOut = L.n_out, i, j;
    for (j = 0; j < nOut; j++) y[j] = L.b[j];
    for (i = 0; i < L.n_in; i++) {
      var xi = x[i]; if (xi === 0) continue;
      var row = i * nOut;
      for (j = 0; j < nOut; j++) y[j] += xi * W[row + j];
    }
    if (act) for (j = 0; j < nOut; j++) y[j] = Math.tanh(y[j]);
    return y;
  }
  Policy.prototype.logits = function (obs) {
    var x = obs;
    for (var i = 0; i < this.layers.length; i++) x = dense(x, this.layers[i], true);
    return dense(x, this.outL, false);
  };
  Policy.prototype.act = function (obs, rand, deterministic) {
    var lg = this.logits(obs), n = lg.length, i, best = 0;
    for (i = 1; i < n; i++) if (lg[i] > lg[best]) best = i;
    if (deterministic) return best;
    var mx = lg[best], sum = 0, p = new Float64Array(n);
    for (i = 0; i < n; i++) { p[i] = Math.exp(lg[i] - mx); sum += p[i]; }
    var u = rand() * sum, acc = 0;
    for (i = 0; i < n; i++) { acc += p[i]; if (u < acc) return i; }
    return n - 1;
  };

  // ---------------- 策略玩家（agents/policy_opponent.py） ----------------
  function PolicyPlayer(policy, cfg, opts) {
    cfg = cfg || {}; opts = opts || {};
    this.policy = policy;
    this.k = cfg.frame_skip || 4;
    this.d = Math.round((cfg.delay_ms || 0) * C.FPS / 1000);
    this.n_hist = cfg.action_history !== undefined ? cfg.action_history : 4;
    this.visible_only = !!cfg.visible_only;
    this.apm_rate = cfg.apm ? cfg.apm / 60.0 / C.FPS : null;
    this.apm_burst = 4.0;
    this.deterministic = !!opts.deterministic;
    this.rand = opts.rand || Math.random;
    this.n_actions = policy.n_actions;
    this.lastAction = null;
    this.reset();
  }
  PolicyPlayer.prototype.reset = function () {
    this.buf = []; this.hist = []; this.queue = []; this.fresh = true; this.prev_in = 0; this.tokens = this.apm_burst;
  };
  PolicyPlayer.prototype._obs = function (raw) {
    if (this.n_hist <= 0) return raw;
    var out = raw.slice(), na = this.n_actions;
    for (var i = 0; i < this.n_hist; i++) {
      for (var j = 0; j < na; j++) out.push(i < this.hist.length && this.hist[i] === j ? 1.0 : 0.0);
    }
    return out;
  };
  PolicyPlayer.prototype.act = function (core, idx) {
    var raw = core.observe(idx, this.visible_only);
    if (this.fresh) { for (var i = 0; i <= this.d; i++) this.buf.push(raw); this.fresh = false; }
    else { this.buf.push(raw); if (this.buf.length > this.d + 1) this.buf.shift(); }
    if (this.queue.length === 0) {
      var a = this.policy.act(this._obs(this.buf[0]), this.rand, this.deterministic);
      this.lastAction = a;
      this.queue = expand(a, this.k);
      if (this.n_hist > 0) { this.hist.push(a); if (this.hist.length > this.n_hist) this.hist.shift(); }
    }
    var inp = this.queue.shift();
    if (this.apm_rate !== null) {
      this.tokens = Math.min(this.apm_burst, this.tokens + this.apm_rate);
      var cost = inputCost(this.prev_in, inp);
      if (cost > 0) { if (this.tokens >= cost) this.tokens -= cost; else inp = this.prev_in; }
    }
    this.prev_in = inp;
    return inp;
  };

  root.FightRL = {C: C, MOVES: MOVES, MOVE_BY_NAME: BY, Core: Core, Policy: Policy, PolicyPlayer: PolicyPlayer,
    encodeInput: encodeInput, decodeInput: decodeInput, MACROS: MACROS, MACRO_NAMES: MACRO_NAMES, expand: expand,
    OBS_DIM: OBS_DIM, worldBox: worldBox};
})(typeof window !== "undefined" ? window : globalThis);
