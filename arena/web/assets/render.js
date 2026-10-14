/* 游戏画面渲染：程序化绘制的角色骨架动画、命中火花、屏幕震动、血条/回合/计时 HUD、开场与 KO 演出、
 * "AI 看到的画面"幽灵叠加。只读 core 的状态和事件，绝不修改游戏状态（与 Python 的逐帧一致性不受影响）。 */
(function () {
  "use strict";
  var F = window.FightRL, C = F.C;
  var W = C.STAGE_W, H = C.STAGE_H, FLOOR = H - 26;
  // 角色配色来自 envs/fighting2d/naming.json（经 spec.js 导出）；缺失时用默认值
  var NAMING = (window.ARENA_SPEC && window.ARENA_SPEC.naming) || {};
  var PAL = NAMING.characters || [{"label": "P1（蓝）", "ui": "#7fb0ff", "top": "#2f6fd6", "top_dark": "#1c3f86", "bottom": "#2a3550", "bottom_dark": "#1a2236", "accent": "#7ee8fa", "skin": "#e9c4a0", "hair": "#20202a", "sleeves": "long", "headwear": "cap", "light": "#9cc3ff"}, {"label": "P2（红）", "ui": "#ff8f87", "top": "#c2334a", "top_dark": "#7a1c2c", "bottom": "#34343e", "bottom_dark": "#22222a", "accent": "#ffcc4d", "skin": "#d9a882", "hair": "#4a2a6a", "sleeves": "none", "headwear": "ponytail", "light": "#ffa39c"}];
  function sy(y) { return FLOOR - y; }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function clamp(x, a, b) { return x < a ? a : (x > b ? b : x); }

  // ---------------- 背景（只画一次到离屏画布） ----------------
  function makeBackdrop(scale) {
    var cv = document.createElement("canvas");
    cv.width = W * scale; cv.height = H * scale;
    var c = cv.getContext("2d");
    c.scale(scale, scale);
    var g = c.createLinearGradient(0, 0, 0, FLOOR);
    g.addColorStop(0, "#0b0d24"); g.addColorStop(0.55, "#2a1747"); g.addColorStop(1, "#6b2b55");
    c.fillStyle = g; c.fillRect(0, 0, W, FLOOR);
    // 月亮
    c.fillStyle = "rgba(255,236,200,0.85)"; c.beginPath(); c.arc(318, 40, 13, 0, Math.PI * 2); c.fill();
    c.fillStyle = "rgba(255,236,200,0.12)"; c.beginPath(); c.arc(318, 40, 24, 0, Math.PI * 2); c.fill();
    // 远景楼群（确定性伪随机）
    var seed = 7;
    function rnd() { seed = (seed * 16807) % 2147483647; return seed / 2147483647; }
    for (var layer = 0; layer < 2; layer++) {
      var x = -10, base = FLOOR - (layer ? 18 : 6);
      c.fillStyle = layer ? "#1a1233" : "#120c26";
      while (x < W + 10) {
        var bw = 18 + rnd() * 34, bh = (layer ? 40 : 70) + rnd() * (layer ? 50 : 70);
        c.fillRect(x, base - bh, bw, bh + 30);
        // 窗户
        for (var wy = base - bh + 6; wy < base - 6; wy += 7) {
          for (var wx = x + 4; wx < x + bw - 4; wx += 6) {
            if (rnd() < (layer ? 0.18 : 0.12)) {
              c.fillStyle = rnd() < 0.5 ? "rgba(255,210,120,0.75)" : "rgba(140,200,255,0.6)";
              c.fillRect(wx, wy, 2.5, 3);
            }
          }
        }
        c.fillStyle = layer ? "#1a1233" : "#120c26";
        x += bw + 2 + rnd() * 6;
      }
    }
    // 霓虹招牌
    c.save();
    c.shadowColor = "#ff4fa3"; c.shadowBlur = 8;
    c.strokeStyle = "#ff7ac0"; c.lineWidth = 1.5;
    c.strokeRect(42, 70, 46, 18);
    c.fillStyle = "#ffb3dc"; c.font = "bold 11px 'ZCOOL QingKe HuangYou', 'Microsoft YaHei', sans-serif";
    c.fillText("格斗街机", 46, 83);
    c.shadowColor = "#4fd6ff"; c.strokeStyle = "#7fe3ff";
    c.strokeRect(238, 92, 30, 14);
    c.fillStyle = "#c9f4ff"; c.font = "bold 9px 'Press Start 2P', monospace"; c.fillText("24H", 241, 103);
    c.restore();
    // 地面
    var fg = c.createLinearGradient(0, FLOOR, 0, H);
    fg.addColorStop(0, "#3a2c3e"); fg.addColorStop(1, "#140f19");
    c.fillStyle = fg; c.fillRect(0, FLOOR, W, H - FLOOR);
    c.strokeStyle = "rgba(255,180,220,0.35)"; c.lineWidth = 1;
    c.beginPath(); c.moveTo(0, FLOOR + 0.5); c.lineTo(W, FLOOR + 0.5); c.stroke();
    c.strokeStyle = "rgba(255,255,255,0.06)";
    for (var k = -12; k <= 12; k++) {
      c.beginPath(); c.moveTo(W / 2 + k * 18, FLOOR); c.lineTo(W / 2 + k * 60, H); c.stroke();
    }
    for (var r = 1; r < 4; r++) {
      var yy = FLOOR + r * r * 2.6;
      c.beginPath(); c.moveTo(0, yy); c.lineTo(W, yy); c.stroke();
    }
    return cv;
  }

  // ---------------- 角色姿势 ----------------
  // 姿势 = 各关节角度（弧度，0 = 朝前水平，正 = 向上）与髋部高度。前 = 角色朝向。
  function pose(f, frame) {
    var P = {hip: 44, lean: 0, rise: 0,
      fua: -1.9, ffa: 0.9, bua: -2.2, bfa: 0.7,   // 前/后 上臂、前臂（相对水平）
      fth: -1.35, fsh: -1.75, bth: -1.85, bsh: -1.5, // 前/后 大腿、小腿
      lying: false, guard: false};
    var s = f.state, t = frame;
    if (s === C.S_IDLE || s === C.S_LANDING) {
      var bob = Math.sin(t * 0.12) * 0.8;
      P.hip += bob; P.fua = -1.0; P.ffa = 1.2; P.bua = -1.4; P.bfa = 1.0;
    } else if (s === C.S_WALK_F || s === C.S_WALK_B) {
      var ph = t * 0.28 * (s === C.S_WALK_F ? 1 : -1);
      P.fth = -1.57 + Math.sin(ph) * 0.45; P.bth = -1.57 - Math.sin(ph) * 0.45;
      P.fsh = P.fth - 0.25 - Math.max(0, Math.cos(ph)) * 0.5; P.bsh = P.bth - 0.25 - Math.max(0, -Math.cos(ph)) * 0.5;
      P.fua = -1.0; P.ffa = 1.2; P.bua = -1.4; P.bfa = 1.0; P.hip += Math.abs(Math.sin(ph)) * 1.2;
    } else if (s === C.S_CROUCH || s === C.S_JUMPSQUAT) {
      P.hip = 28; P.fth = -0.35; P.fsh = -2.2; P.bth = -2.6; P.bsh = -1.3; P.lean = 0.15;
      P.fua = -0.8; P.ffa = 1.3; P.bua = -1.2; P.bfa = 1.1;
    } else if (s === C.S_AIR) {
      P.hip = 40; P.fth = -0.4; P.fsh = -2.0; P.bth = -1.0; P.bsh = -2.4; P.fua = -0.4; P.ffa = 1.0; P.bua = 0.6; P.bfa = 1.4;
    } else if (s === C.S_HITSTUN || s === C.S_AIR_HIT) {
      P.lean = -0.35; P.fua = 0.4; P.ffa = 0.6; P.bua = 2.4; P.bfa = 2.0; P.fth = -1.2; P.bth = -1.95;
    } else if (s === C.S_BLOCKSTUN) {
      P.guard = true; P.lean = -0.12; P.fua = -0.2; P.ffa = 1.55; P.bua = -0.5; P.bfa = 1.45;
      if (f.crouching()) { P.hip = 28; P.fth = -0.35; P.fsh = -2.2; P.bth = -2.6; P.bsh = -1.3; }
    } else if (s === C.S_KNOCKDOWN || s === C.S_KO) {
      P.lying = true;
    }
    if (f.dir_now === 4 || f.dir_now === 1) {
      if (s === C.S_IDLE || s === C.S_WALK_B || s === C.S_CROUCH) { P.guard = true; P.fua = -0.25; P.ffa = 1.5; P.bua = -0.6; P.bfa = 1.4; }
    }
    var m = f.move;
    if (m && !P.lying && s !== C.S_HITSTUN && s !== C.S_BLOCKSTUN) {
      var k = f.move_frame, ext;
      if (k <= m.startup) ext = -0.3 * (k / m.startup);
      else if (k <= m.startup + m.active) ext = 1;
      else ext = 1 - (k - m.startup - m.active) / Math.max(1, m.recovery);
      ext = clamp(ext, -0.3, 1);
      var n = m.name;
      if (n === "st_L") { P.fua = lerp(-1.0, 0.05, ext); P.ffa = lerp(1.2, 0.05, ext); P.lean = 0.08 * ext; }
      else if (n === "st_H") { P.fua = lerp(-1.0, 0.12, ext); P.ffa = lerp(1.2, 0.1, ext); P.lean = 0.22 * ext; P.bua = -1.8; P.fth = -1.2; }
      else if (n === "cr_L") { P.hip = 28; P.fth = -0.35; P.fsh = -2.2; P.bth = -2.6; P.bsh = -1.3; P.fua = lerp(-0.8, -0.35, ext); P.ffa = lerp(1.3, -0.3, ext); }
      else if (n === "cr_H") { P.hip = 22; P.bth = -2.6; P.bsh = -1.3; P.fth = lerp(-0.35, -0.12, ext); P.fsh = lerp(-2.2, -0.08, ext); P.lean = -0.25 * ext; P.fua = 2.4; P.ffa = 2.0; }
      else if (n === "j_L" || n === "j_H") { P.fth = lerp(-0.4, -0.55, ext); P.fsh = lerp(-2.0, -0.6, ext); P.lean = -0.15 * ext; }
      else if (n === "throw") { P.fua = lerp(-1.0, -0.1, ext); P.ffa = lerp(1.2, 0.3, ext); P.bua = lerp(-1.4, -0.2, ext); P.bfa = lerp(1.0, 0.35, ext); P.lean = 0.15; }
      else if (n.indexOf("fireball") === 0) {
        var push = k <= m.startup ? -0.6 : 1;
        P.fua = lerp(-0.6, -0.05, push > 0 ? 1 : 0); P.ffa = lerp(0.6, 0.0, push > 0 ? 1 : 0);
        P.bua = P.fua - 0.08; P.bfa = P.ffa; P.lean = push > 0 ? 0.18 : -0.2; P.hip = 40;
      } else if (n.indexOf("dp") === 0) {
        P.fua = lerp(-1.0, 1.45, ext); P.ffa = lerp(1.2, 1.5, ext); P.bua = -2.0; P.fth = -1.3; P.bth = -2.1;
        P.rise = (k > m.startup && k <= m.startup + m.active + 6) ? 22 * Math.sin(Math.PI * clamp((k - m.startup) / (m.active + 6), 0, 1)) : 0;
      }
    }
    return P;
  }
  function seg(c, x, y, ang, len, dir, width, color) {
    var x2 = x + Math.cos(ang) * len * dir, y2 = y - Math.sin(ang) * len;
    c.strokeStyle = color; c.lineWidth = width; c.lineCap = "round";
    c.beginPath(); c.moveTo(x, y); c.lineTo(x2, y2); c.stroke();
    return [x2, y2];
  }
  // 角色：P1 长袖外套 + 鸭舌帽，P2 无袖背心 + 马尾 + 手套（外观参数全部来自 naming.json）
  function drawFighter(c, f, i, frame, alpha, flashWhite, ghost) {
    var pal = PAL[i], dir = f.facing, P = pose(f, frame);
    if (ghost) pal = {top: ghost, top_dark: ghost, bottom: ghost, bottom_dark: ghost, accent: ghost, skin: ghost, hair: ghost,
      sleeves: pal.sleeves, headwear: pal.headwear};
    c.save(); c.globalAlpha = alpha;
    if (!ghost) {   // 影子
      c.fillStyle = "rgba(0,0,0,0.35)";
      c.beginPath(); c.ellipse(f.x, FLOOR + 2, 20 - Math.min(10, f.y * 0.1), 3.5, 0, 0, Math.PI * 2); c.fill();
    }
    if (ghost) flashWhite = false;
    var ko = f.state === C.S_KO;
    var W1 = flashWhite ? "#ffffff" : null;
    var top = W1 || (ko ? "#6c6c78" : pal.top), topD = W1 || (ko ? "#3c3c46" : pal.top_dark);
    var bot = W1 || (ko ? "#55555f" : pal.bottom), botD = W1 || (ko ? "#33333b" : pal.bottom_dark);
    var skin = W1 || pal.skin, hair = W1 || pal.hair, acc = W1 || pal.accent;
    var sleeve = pal.sleeves === "none" ? skin : top, sleeveD = pal.sleeves === "none" ? skin : topD;
    if (P.lying) {
      var yb = sy(f.y) - 6;
      c.lineCap = "round";
      c.strokeStyle = botD; c.lineWidth = 8;
      c.beginPath(); c.moveTo(f.x - 26 * dir, yb + 1); c.lineTo(f.x + 6 * dir, yb); c.stroke();
      c.strokeStyle = top; c.lineWidth = 10;
      c.beginPath(); c.moveTo(f.x + 4 * dir, yb); c.lineTo(f.x + 24 * dir, yb - 1); c.stroke();
      c.fillStyle = skin; c.beginPath(); c.arc(f.x + 32 * dir, yb - 2, 7.5, 0, Math.PI * 2); c.fill();
      c.fillStyle = hair; c.beginPath(); c.arc(f.x + 33 * dir, yb - 4, 7.5, Math.PI, Math.PI * 2); c.fill();
      c.restore(); return;
    }
    var hipX = f.x, hipY = sy(f.y + P.hip + P.rise);
    var torsoAng = Math.PI / 2 - P.lean;
    var sh = [hipX + Math.cos(torsoAng) * 30 * dir, hipY - Math.sin(torsoAng) * 30];
    var hx = sh[0] + Math.cos(torsoAng) * 10 * dir, hy = sh[1] - Math.sin(torsoAng) * 10;
    // 马尾在身后（先画，被头挡住）
    if (pal.headwear === "ponytail") {
      var sw = Math.sin(frame * 0.25 + i) * 3;
      c.strokeStyle = hair; c.lineWidth = 4.5; c.lineCap = "round";
      c.beginPath(); c.moveTo(hx - 6 * dir, hy - 5);
      c.quadraticCurveTo(hx - 16 * dir, hy - 4 + sw, hx - 18 * dir, hy + 9 + sw); c.stroke();
    }
    // 后腿 / 后臂（暗色）
    var k1 = seg(c, hipX - 3 * dir, hipY, P.bth, 19, dir, 7, botD); seg(c, k1[0], k1[1], P.bsh, 19, dir, 6, botD);
    var e1 = seg(c, sh[0] - 3 * dir, sh[1] + 2, P.bua, 14, dir, 6, sleeveD); var h1 = seg(c, e1[0], e1[1], P.bfa, 13, dir, 5.5, sleeveD);
    if (pal.sleeves === "none") { c.fillStyle = acc; c.beginPath(); c.arc(h1[0], h1[1], 3.4, 0, Math.PI * 2); c.fill(); }
    // 躯干
    c.lineCap = "round";
    c.strokeStyle = top; c.lineWidth = pal.sleeves === "none" ? 13 : 15;
    c.beginPath(); c.moveTo(hipX, hipY); c.lineTo(sh[0], sh[1]); c.stroke();
    if (pal.sleeves === "none") {   // 背心：肩部露出，胸前横条
      c.strokeStyle = acc; c.lineWidth = 2.2;
      var mx = (hipX + sh[0]) / 2, my = (hipY + sh[1]) / 2;
      c.beginPath(); c.moveTo(mx - 6, my); c.lineTo(mx + 6, my); c.stroke();
    } else {   // 外套：拉链竖条 + 衣摆
      c.strokeStyle = acc; c.lineWidth = 1.6;
      c.beginPath(); c.moveTo(hipX + 3 * dir, hipY - 2); c.lineTo(sh[0] + 3 * dir, sh[1] + 3); c.stroke();
      c.strokeStyle = topD; c.lineWidth = 3;
      c.beginPath(); c.moveTo(hipX - 7, hipY + 1); c.lineTo(hipX + 7, hipY + 1); c.stroke();
    }
    // 头
    c.fillStyle = skin; c.beginPath(); c.arc(hx, hy, 8.5, 0, Math.PI * 2); c.fill();
    if (pal.headwear === "cap") {   // 鸭舌帽：半圆帽顶 + 朝前的帽檐
      c.fillStyle = W1 || pal.top; c.beginPath(); c.arc(hx, hy - 1, 8.8, Math.PI, Math.PI * 2); c.fill();
      c.strokeStyle = W1 || acc; c.lineWidth = 2.4;
      c.beginPath(); c.moveTo(hx, hy - 1.5); c.lineTo(hx + 13 * dir, hy - 1); c.stroke();
    } else {   // 刘海
      c.fillStyle = hair; c.beginPath(); c.arc(hx - 1 * dir, hy - 1.5, 9, Math.PI * 1.02, Math.PI * 1.98); c.fill();
    }
    c.fillStyle = "#1a1a22"; c.beginPath(); c.arc(hx + 4 * dir, hy + 0.5, 1.4, 0, Math.PI * 2); c.fill();
    // 前腿 / 前臂
    var k2 = seg(c, hipX + 3 * dir, hipY, P.fth, 19, dir, 7.5, bot); seg(c, k2[0], k2[1], P.fsh, 19, dir, 6.5, bot);
    var e2 = seg(c, sh[0] + 2 * dir, sh[1] + 2, P.fua, 14, dir, 6.5, sleeve);
    var hand = seg(c, e2[0], e2[1], P.ffa, 13, dir, 6, sleeve);
    c.fillStyle = pal.sleeves === "none" ? acc : skin;   // P2 戴手套，P1 露手
    c.beginPath(); c.arc(hand[0], hand[1], pal.sleeves === "none" ? 4.2 : 3.6, 0, Math.PI * 2); c.fill();
    if (P.guard) {
      c.strokeStyle = f.state === C.S_BLOCKSTUN ? "rgba(255,230,90,0.9)" : "rgba(200,190,120,0.45)"; c.lineWidth = 2;
      c.beginPath(); c.arc(f.x + 6 * dir, sy(f.y + 50), 24, -0.9, 0.9, dir < 0); c.stroke();
    }
    c.restore();
  }

  // ---------------- 特效 ----------------
  function Particles() { this.list = []; }
  Particles.prototype.burst = function (x, y, color, n, speed, life, size) {
    for (var i = 0; i < n; i++) {
      var a = Math.random() * Math.PI * 2, v = speed * (0.4 + Math.random() * 0.8);
      this.list.push({x: x, y: y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: life, max: life, color: color, size: size});
    }
  };
  Particles.prototype.tick = function () {
    this.list = this.list.filter(function (p) { p.x += p.vx; p.y += p.vy; p.vy += 0.06; p.vx *= 0.95; return --p.life > 0; });
  };
  Particles.prototype.draw = function (c) {
    this.list.forEach(function (p) {
      c.globalAlpha = p.life / p.max; c.fillStyle = p.color;
      c.fillRect(p.x - p.size / 2, p.y - p.size / 2, p.size, p.size);
    });
    c.globalAlpha = 1;
  };

  function Renderer(canvas) {
    this.cv = canvas; this.c = canvas.getContext("2d");
    this.scale = canvas.width / W;
    this.bg = makeBackdrop(this.scale);
    this.parts = new Particles(); this.flashes = []; this.shake = 0;
    this.hpTrail = [C.MAX_HP, C.MAX_HP]; this.popups = [];
    this.opts = {boxes: false, ghost: true};
  }
  Renderer.prototype.resize = function () {
    this.scale = this.cv.width / W; this.bg = makeBackdrop(this.scale);
  };
  Renderer.prototype.onEvents = function (core, sfx) {
    var self = this;
    core.events.forEach(function (e) {
      var kind = e[0];
      if (kind === "hit" || kind === "block" || kind === "throw") {
        var att = kind === "block" ? core.f[1 - e[1]] : core.f[e[1]], def = core.f[1 - att.idx];
        var px = def.x - def.facing * 0, py = sy(def.y + 58), heavy = false;
        var m = att.move;
        if (m && m.hitbox[1] > 0) {
          var wb = F.worldBox(att, m.hitbox);
          px = clamp((Math.max(wb[0], def.x - 18) + Math.min(wb[1], def.x + 18)) / 2, 0, W);
          py = sy((wb[2] + wb[3]) / 2);
          heavy = m.damage >= 70;
        }
        if (kind === "hit") {
          self.parts.burst(px, py, heavy ? "#fff3a0" : "#ffffff", heavy ? 22 : 12, heavy ? 3.2 : 2.2, 18, heavy ? 3 : 2);
          self.parts.burst(px, py, "#ff8a3d", heavy ? 10 : 5, 1.6, 22, 2);
          self.flashes.push({x: px, y: py, r: heavy ? 22 : 14, life: 8, max: 8, color: "255,250,220"});
          self.shake = Math.max(self.shake, heavy ? 6 : 2.5);
          if (e[2] >= 2) self.popups.push({text: e[2] + " HITS", x: att.idx === 0 ? 60 : W - 60, y: 70, life: 50});
          if (sfx) sfx.hit(heavy);
        } else if (kind === "block") {
          self.parts.burst(px, py, "#9fe8ff", 8, 1.8, 14, 2);
          self.flashes.push({x: px, y: py, r: 10, life: 6, max: 6, color: "160,230,255"});
          if (sfx) sfx.block();
        } else {
          self.flashes.push({x: def.x, y: sy(def.y + 50), r: 30, life: 10, max: 10, color: "255,255,255"});
          self.shake = Math.max(self.shake, 7);
          self.popups.push({text: "THROW", x: def.x, y: sy(def.y + 105), life: 40});
          if (sfx) sfx.throwHit();
        }
      } else if (kind === "throw_tech") {
        self.popups.push({text: "TECH", x: W / 2, y: 90, life: 35});
        if (sfx) sfx.block();
      } else if (kind === "proj_clash") {
        self.parts.burst(W / 2, sy(60), "#d0c8ff", 16, 2.4, 20, 2);
      } else if (kind === "cancel") {
        self.popups.push({text: "CANCEL", x: core.f[e[1]].x, y: sy(core.f[e[1]].y + 112), life: 25});
      }
    });
  };
  Renderer.prototype.tickFx = function () {
    this.parts.tick();
    this.flashes = this.flashes.filter(function (f) { return --f.life > 0; });
    this.popups = this.popups.filter(function (p) { p.y -= 0.25; return --p.life > 0; });
    this.shake *= 0.85; if (this.shake < 0.2) this.shake = 0;
  };
  Renderer.prototype.draw = function (core, hud) {
    var c = this.c, s = this.scale, self = this;
    hud = hud || {};
    var dx = this.shake ? (Math.random() - 0.5) * this.shake * 2 : 0, dy = this.shake ? (Math.random() - 0.5) * this.shake * 2 : 0;
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.drawImage(this.bg, dx * s, dy * s);
    c.setTransform(s, 0, 0, s, dx * s, dy * s);
    // 幽灵：AI 实际"看到的"（延迟后）状态
    if (this.opts.ghost && hud.ghosts) {
      var placed = [];   // 已放置的标签矩形，避免两个标签互相压住
      hud.ghosts.forEach(function (g) {
        if (!g || !g.snap) return;
        g.snap.forEach(function (fs, i) { drawFighter(c, fs, i, fs.frame, 0.26, false, g.color); });
        var gf = g.snap[g.who];
        c.save(); c.fillStyle = g.color; c.font = "6.5px 'Noto Sans SC', 'Microsoft YaHei', sans-serif";
        var tw = c.measureText(g.label).width;
        var lx = clamp(gf.x - tw / 2, 4, W - tw - 4), ly = clamp(sy(gf.y + 108), 72, H - 10);
        for (var t = 0; t < 4; t++) {
          var hit = placed.some(function (r) { return lx < r[0] + r[2] + 4 && r[0] < lx + tw + 4 && Math.abs(ly - r[1]) < 9; });
          if (!hit) break;
          ly = clamp(ly + 9, 72, H - 10);
        }
        placed.push([lx, ly, tw]);
        c.fillStyle = "rgba(10,12,22,.62)"; c.fillRect(lx - 2, ly - 6.5, tw + 4, 8.5);
        c.fillStyle = g.color; c.fillText(g.label, lx, ly); c.restore();
      });
    }
    // 飞行道具
    core.projs.forEach(function (p) {
      var col = PAL[p.owner].light, y = sy(60);
      var gr = c.createRadialGradient(p.x, y, 1, p.x, y, 16);
      gr.addColorStop(0, "#ffffff"); gr.addColorStop(0.35, col); gr.addColorStop(1, "rgba(0,0,0,0)");
      c.fillStyle = gr; c.beginPath(); c.arc(p.x, y, 16, 0, Math.PI * 2); c.fill();
      for (var t = 1; t <= 4; t++) {
        c.globalAlpha = 0.25 / t; c.fillStyle = col;
        c.beginPath(); c.arc(p.x - p.vx * t * 2.2, y, 9 - t, 0, Math.PI * 2); c.fill();
      }
      c.globalAlpha = 1;
    });
    for (var i = 0; i < 2; i++) {
      var f = core.f[i], flash = (f.state === C.S_HITSTUN || f.state === C.S_AIR_HIT) && (core.frame % 4 < 2);
      drawFighter(c, f, i, core.frame, 1, flash);
      if (this.opts.boxes) {
        c.lineWidth = 0.8; c.strokeStyle = "#3cdc5a";
        f.hurtboxes().forEach(function (b) { c.strokeRect(b[0], sy(b[3]), b[1] - b[0], b[3] - b[2]); });
        var hb = f.activeHitbox();
        if (hb) { c.lineWidth = 1.4; c.strokeStyle = "#ff2828"; c.strokeRect(hb[0], sy(hb[3]), hb[1] - hb[0], hb[3] - hb[2]); }
        if (f.move) { c.fillStyle = "#fff"; c.font = "6px 'JetBrains Mono', monospace"; c.fillText(f.move.name + " " + f.move_frame + "f", f.x - 16, sy(f.y + 112)); }
      }
    }
    this.parts.draw(c);
    this.flashes.forEach(function (fl) {
      var a = fl.life / fl.max, gr = c.createRadialGradient(fl.x, fl.y, 0, fl.x, fl.y, fl.r);
      gr.addColorStop(0, "rgba(" + fl.color + "," + a + ")"); gr.addColorStop(1, "rgba(" + fl.color + ",0)");
      c.fillStyle = gr; c.beginPath(); c.arc(fl.x, fl.y, fl.r, 0, Math.PI * 2); c.fill();
    });
    c.setTransform(s, 0, 0, s, 0, 0);
    this.drawHud(core, hud);
  };
  Renderer.prototype.drawHud = function (core, hud) {
    var c = this.c, names = hud.names || ["P1", "P2"], wins = hud.wins || [0, 0];
    for (var i = 0; i < 2; i++) {
      var hp = core.f[i].hp;
      this.hpTrail[i] = Math.max(hp, this.hpTrail[i] - 6);
      if (this.hpTrail[i] < hp) this.hpTrail[i] = hp;
      var bw = 150, x0 = i === 0 ? 14 : W - 14 - bw, y0 = 12;
      c.fillStyle = "rgba(10,8,20,0.75)"; c.fillRect(x0 - 2, y0 - 2, bw + 4, 13);
      var fr = hp / C.MAX_HP, tr = this.hpTrail[i] / C.MAX_HP;
      c.fillStyle = "#c0262c";
      if (i === 0) c.fillRect(x0 + bw * (1 - tr), y0, bw * tr, 9); else c.fillRect(x0, y0, bw * tr, 9);
      var low = fr < 0.25 && (core.frame % 30 < 15);
      var g = c.createLinearGradient(0, y0, 0, y0 + 9);
      g.addColorStop(0, low ? "#ffe9a8" : "#ffe26a"); g.addColorStop(1, low ? "#ff9b3b" : "#e6a417");
      c.fillStyle = g;
      if (i === 0) c.fillRect(x0 + bw * (1 - fr), y0, bw * fr, 9); else c.fillRect(x0, y0, bw * fr, 9);
      c.strokeStyle = "#f6f0ff"; c.lineWidth = 0.8; c.strokeRect(x0 - 2, y0 - 2, bw + 4, 13);
      c.font = "6px 'Press Start 2P', monospace"; c.fillStyle = PAL[i].light;
      var nm = names[i];
      c.fillText(nm, i === 0 ? x0 : x0 + bw - c.measureText(nm).width, y0 + 21);
      for (var r = 0; r < 2; r++) {
        c.fillStyle = r < wins[i] ? "#ffd23f" : "rgba(255,255,255,0.18)";
        var cx = i === 0 ? x0 + bw - 6 - r * 9 : x0 + 6 + r * 9;
        c.beginPath(); c.arc(cx, y0 + 18, 3, 0, Math.PI * 2); c.fill();
      }
    }
    var secs = Math.ceil(core.timeLeft() / C.FPS), ts = hud.noTimer ? "--" : (secs < 10 ? "0" : "") + secs;
    if (hud.noTimer) secs = 99;
    c.fillStyle = "rgba(10,8,20,0.75)"; c.fillRect(W / 2 - 13, 8, 26, 18);
    c.font = "10px 'Press Start 2P', monospace"; c.fillStyle = secs <= 5 ? "#ff6a6a" : "#ffffff";
    c.fillText(ts, W / 2 - c.measureText(ts).width / 2, 22);
    this.popups.forEach(function (p) {
      c.globalAlpha = Math.min(1, p.life / 15); c.font = "7px 'Press Start 2P', monospace"; c.fillStyle = "#ffd23f";
      c.fillText(p.text, p.x - c.measureText(p.text).width / 2, p.y); c.globalAlpha = 1;
    });
    if (hud.banner) {
      var b = hud.banner;
      c.save(); c.globalAlpha = b.alpha === undefined ? 1 : b.alpha;
      c.fillStyle = "rgba(0,0,0,0.35)"; c.fillRect(0, 84, W, 40);
      c.font = (b.size || 18) + "px 'Press Start 2P', monospace";
      c.lineWidth = 4; c.strokeStyle = "#1a0d2a"; c.fillStyle = b.color || "#ffd23f";
      var tw = c.measureText(b.text).width;
      c.strokeText(b.text, W / 2 - tw / 2, 112); c.fillText(b.text, W / 2 - tw / 2, 112);
      if (b.sub) {
        c.font = "7px 'Press Start 2P', monospace"; c.fillStyle = "#ffffff";
        var sw = c.measureText(b.sub).width; c.fillText(b.sub, W / 2 - sw / 2, 122 + 8);
      }
      c.restore();
    }
    if (hud.paused) {
      c.font = "8px 'Press Start 2P', monospace"; c.fillStyle = "#ffffff"; c.fillText("PAUSE", W / 2 - 18, 44);
    }
  };
  // 记录角色快照（给"延迟幽灵"用）
  Renderer.snapshot = function (core) {
    return core.f.map(function (f) {
      var st = f.state, dn = f.dir_now;
      return {x: f.x, y: f.y, facing: f.facing, state: st, move: f.move, move_frame: f.move_frame, dir_now: dn, frame: core.frame,
        airborne: function () { return st === C.S_AIR || st === C.S_AIR_HIT; },
        crouching: function () { return dn === 1 || dn === 2 || dn === 3; }};
    });
  };
  window.ArenaRender = Renderer;
})();
