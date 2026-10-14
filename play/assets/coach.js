/* 新手引导：操作说明浮层（键盘示意图）、招式表（悬停时按顺序点亮方向键）、输入历史栏、搓招成败提示、
 * 练习模式（木桩对手 + 任务清单）。只读游戏状态，不改变游戏规则（练习模式的回血除外，只在练习模式里发生）。
 * 招式名称全部来自 naming.json（window.ARENA_SPEC.naming），改名只改那一处。 */
(function () {
  "use strict";
  var F = window.FightRL, C = F.C, E = F.encodeInput;
  var NM = (window.ARENA_SPEC && window.ARENA_SPEC.naming) || {specials: {fireball: "气功波", dp: "冲天拳"}};
  var FB = NM.specials.fireball, DP = NM.specials.dp;
  var $ = function (id) { return document.getElementById(id); };
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;"}[c]; }); }

  // ---------------- 方向：相对（6 = 朝对手）↔ 屏幕箭头 / 实际按键 ----------------
  var ARROW = {1: "↙", 2: "↓", 3: "↘", 4: "←", 5: "·", 6: "→", 7: "↖", 8: "↑", 9: "↗"};
  var MIRROR = {1: 3, 3: 1, 4: 6, 6: 4, 7: 9, 9: 7, 2: 2, 5: 5, 8: 8};
  function absDir(rel, facing) { return facing > 0 ? rel : MIRROR[rel]; }
  function arrow(rel, facing) { return ARROW[absDir(rel, facing)]; }
  function keysFor(rel, facing) {   // 键盘上实际要按的键
    var a = absDir(rel, facing), out = [];
    if (a === 7 || a === 8 || a === 9) out.push("W");
    if (a === 1 || a === 2 || a === 3) out.push("S");
    if (a === 1 || a === 4 || a === 7) out.push("A");
    if (a === 3 || a === 6 || a === 9) out.push("D");
    return out.join("+") || "（松开）";
  }

  // ---------------- 招式表 ----------------
  // steps: [相对方向, 按键]，按键 "J"/"K"/"J/K"/null
  var MOVELIST = [
    {id: "walk", name: "前进 / 后退", desc: "朝对手走 / 远离对手走", steps: [[6, null]], alt: [[4, null]]},
    {id: "jump", name: "跳", desc: "W；W+A / W+D 斜跳", steps: [[8, null]]},
    {id: "crouch", name: "蹲", desc: "S", steps: [[2, null]]},
    {id: "block", name: "站防", desc: "按住「后」（远离对手的方向）。挡得住站着打的和跳着打的", steps: [[4, null]]},
    {id: "cblock", name: "蹲防", desc: "按住「下后」。挡得住下段（扫腿、蹲轻），挡不住跳攻击", steps: [[1, null]]},
    {id: "light", name: "轻攻击", desc: "J：出手快、伤害低", steps: [[5, "J"]]},
    {id: "heavy", name: "重攻击", desc: "K：出手慢、伤害高；蹲着按 K 是扫腿（击倒）", steps: [[5, "K"]]},
    {id: "throw", name: "投", desc: "贴身时 前+K，防御挡不住", steps: [[6, "K"]]},
    {id: "fireball", name: FB, desc: "↓ ↘ → 连贯地搓下来，同时按 J（轻）或 K（重）。新手模式：U（Shift+U 重）", steps: [[2, null], [3, null], [6, "J"]], special: true},
    {id: "dp", name: DP, desc: "→ ↓ ↘ + J/K：出招瞬间无敌，专门打断对手。新手模式：I（Shift+I 重）", steps: [[6, null], [2, null], [3, "J"]], special: true}
  ];

  function Coach(opts) {
    this.getFacing = opts.getFacing || function () { return 1; };
    this.hist = [];          // 输入历史栏条目 {arrow, btn, n, macro}
    this.rel = [];           // 最近 40 帧的相对方向（与核心判定用的同一套）
    this.pending = [];       // 待判定的按键 {frame, snap, facing}
    this.flashT = 0;
    this.tasks = null;
    this.counts = {};
    this.tipTimer = null;
  }

  // ---------- 帮助浮层 ----------
  Coach.prototype.keyboardSVG = function () {
    var keys = [
      // x, y, 字母, 说明, 类别, 宽
      [74, 14, "W", "跳", "mv"], [24, 82, "A", "左", "mv"], [74, 82, "S", "蹲", "mv"], [124, 82, "D", "右", "mv"],
      [24, 150, "Shift", "按住：重版本", "ez", 88],
      [270, 14, "U", FB, "ez"], [324, 14, "I", DP, "ez"], [282, 82, "J", "轻攻击", "atk"], [336, 82, "K", "重攻击", "atk"],
      [430, 14, "H", "说明", "ui"], [430, 82, "空格", "暂停", "ui", 52]
    ];
    var col = {mv: "var(--p1)", atk: "var(--gold)", ez: "#5fd39a", ui: "var(--ink-3)"};
    var s = '<svg viewBox="0 0 500 236" role="img" aria-label="键盘示意图：WASD 移动，J 轻攻击，K 重攻击，U/I 一键必杀技，Shift 重版本，H 打开说明，空格暂停">';
    keys.forEach(function (k) {
      var w = k[5] || 38;
      s += '<g><rect x="' + k[0] + '" y="' + k[1] + '" width="' + w + '" height="36" rx="6" fill="var(--surface-2)" stroke="' + col[k[4]] + '" stroke-width="2"/>' +
        '<text x="' + (k[0] + w / 2) + '" y="' + (k[1] + 24) + '" text-anchor="middle" class="kk">' + esc(k[2]) + "</text>" +
        '<text x="' + (k[0] + w / 2) + '" y="' + (k[1] + 52) + '" text-anchor="middle" class="kl">' + esc(k[3]) + "</text></g>";
    });
    s += '<text x="24" y="230" class="kh" text-anchor="start">左手：移动 / 跳 / 蹲 / 防御</text><text x="270" y="230" class="kh" text-anchor="start">右手：攻击与必杀技</text></svg>';
    return s;
  };
  Coach.prototype.helpHTML = function () {
    return '<div class="help-card" role="dialog" aria-modal="true" aria-labelledby="help-title">' +
      '<button class="help-x" id="help-close" aria-label="关闭说明">×</button>' +
      '<h2 id="help-title">怎么玩</h2>' +
      '<div class="help-kbd">' + this.keyboardSVG() + "</div>" +
      '<p class="help-touch">手机 / 平板：打开就是两个 AI 对打，往下滑看它们的大脑。想亲手玩就点顶部「我来打」或「练习」，' +
      "画面下方会出现虚拟按键：← ↑ ↓ → 移动、跳、蹲（按住「后」防御），「轻 J」「重 K」攻击，「气功」「冲天」一键放必杀技。</p>" +
      '<div class="help-cols"><div><h3>基本操作</h3><ul>' +
      "<li><kbd>A</kbd><kbd>D</kbd> 左右移动，<kbd>W</kbd> 跳（<kbd>W</kbd>+<kbd>A</kbd>/<kbd>D</kbd> 斜跳），<kbd>S</kbd> 蹲。</li>" +
      "<li><b>防御不用按键</b>：按住「后」（远离对手的方向）就是站防；按住「下后」就是蹲防。下段攻击只能蹲防，跳攻击只能站防。</li>" +
      "<li><kbd>J</kbd> 轻攻击（快），<kbd>K</kbd> 重攻击（慢、疼）。蹲着按 <kbd>K</kbd> 是扫腿。贴身 前+<kbd>K</kbd> 是投，挡不住。</li>" +
      "<li>手柄也行：十字键/左摇杆移动，A/X 轻，B/Y 重，LB/RB 一键必杀技。</li></ul></div>" +
      "<div><h3>必杀技</h3><ul>" +
      "<li><b>" + esc(FB) + "</b>：↓ ↘ → 连贯地搓（约 ¼ 秒内），到 → 时按 <kbd>J</kbd> 或 <kbd>K</kbd>。</li>" +
      "<li><b>" + esc(DP) + "</b>：→ ↓ ↘ + <kbd>J</kbd>/<kbd>K</kbd>，出招瞬间无敌。</li>" +
      "<li>「→」永远指<b>朝对手的方向</b>；对手在你左边时，左右要反过来按。招式表里悬停可以看实际要按的键。</li>" +
      "<li><b>新手模式</b>（默认开）：<kbd>U</kbd> = " + esc(FB) + "，<kbd>I</kbd> = " + esc(DP) + "，按住 <kbd>Shift</kbd> 放重版本。" +
      "AI 的动作空间里本来就有这 4 个「搓招宏」（↓↘→+攻击、→↓↘+攻击），每一下方向和按键照样计入手速；所以给人类一键搓招是公平的。</li></ul></div></div>" +
      '<div class="help-cols"><div><h3>三种玩法</h3><ul>' +
      "<li><b>观战</b>：两个神经网络对打，右侧显示它们的「大脑」（窄屏时在游戏下方）。</li>" +
      "<li><b>我来打</b>：你操作蓝色 P1，对手可选新手 / 普通 / 困难 / 无限制。</li>" +
      "<li><b>练习</b>：对手是木桩，任务清单逐项打勾（宽屏在右侧，窄屏在游戏下方）。</li></ul></div>" +
      "<div><h3>看大脑</h3><ul><li>每个大脑顶部写着结构式。输入 214 个 = 游戏状态 90 + 最近 4 次动作 124；中间是隐藏层神经元（橙正蓝负）；输出是 31 个动作的概率和 1 个局势评估。</li>" +
      "<li>右栏顶部切换「P1 大脑 / P2 大脑 / 全部」；「全部」里点任一个大脑看完整画法。</li>" +
      "<li>点神经元可以把它「敲掉」，看看 AI 会不会变笨。</li><li>随时按 <kbd>H</kbd> 或右上角 <b>?</b> 再打开这页。</li></ul></div></div>" +
      '<div class="help-foot"><button class="b big" id="help-go">知道了，开始</button></div></div>';
  };
  Coach.prototype.bindHelp = function () {
    var self = this, ov = $("help");
    ov.innerHTML = this.helpHTML();
    $("help-close").addEventListener("click", function () { self.hideHelp(); });
    $("help-go").addEventListener("click", function () { self.hideHelp(); });
    ov.addEventListener("click", function (e) { if (e.target === ov) self.hideHelp(); });
  };
  Coach.prototype.showHelp = function () {
    var ov = $("help"); ov.hidden = false; ov.scrollTop = 0;
    var b = $("help-go"); if (b) { try { b.focus({preventScroll: true}); } catch (e) { b.focus(); } }   // 不要因为聚焦把浮层滚到底
    if (this.onHelp) this.onHelp(true);
  };
  Coach.prototype.hideHelp = function () {
    $("help").hidden = true;
    try { window.localStorage.setItem("fbl_help_seen", "1"); } catch (e) { /* 隐私模式等：忽略 */ }
    if (this.onHelp) this.onHelp(false);
  };
  Coach.prototype.toggleHelp = function () { if ($("help").hidden) this.showHelp(); else this.hideHelp(); };
  Coach.prototype.firstVisit = function () {
    try { return !window.localStorage.getItem("fbl_help_seen"); } catch (e) { return true; }
  };

  // ---------- 招式表（悬停时按顺序点亮） ----------
  Coach.prototype.buildMoveList = function (el) {
    var self = this;
    el.innerHTML = MOVELIST.map(function (m) {
      return '<button type="button" class="mv' + (m.special ? " sp" : "") + '" data-mv="' + m.id + '"><span class="mvn">' + esc(m.name) +
        '</span><span class="mvs">' + m.steps.map(function (s) { return '<i data-rel="' + s[0] + '">' + ARROW[s[0]] + "</i>" + (s[1] ? "<b>+" + s[1] + "</b>" : ""); }).join("") + "</span></button>";
    }).join("");
    var tip = $("mvtip");
    function show(btn) {
      var m = MOVELIST.filter(function (x) { return x.id === btn.getAttribute("data-mv"); })[0];
      if (!m) return;
      var fc = self.getFacing();
      var seq = m.steps.map(function (s) { return {arrow: arrow(s[0], fc), keys: keysFor(s[0], fc), btn: s[1]}; });
      tip.innerHTML = "<b>" + esc(m.name) + "</b><span class='fc'>你现在朝" + (fc > 0 ? "右" : "左") + "</span>" +
        '<div class="seq">' + seq.map(function (q, k) {
          return '<span class="st" data-k="' + k + '"><span class="ar">' + q.arrow + "</span><kbd>" + q.keys + "</kbd>" + (q.btn ? "<kbd class='bt'>+" + q.btn + "</kbd>" : "") + "</span>";
        }).join('<span class="sep">›</span>') + "</div><p>" + esc(m.desc) + "</p>";
      var r = btn.getBoundingClientRect();
      tip.hidden = false;
      var x = Math.min(window.innerWidth - tip.offsetWidth - 8, Math.max(8, r.left));
      var y = r.top - tip.offsetHeight - 8; if (y < 8) y = r.bottom + 8;
      tip.style.left = x + "px"; tip.style.top = y + "px";
      var k = 0, sts = tip.querySelectorAll(".st");
      clearInterval(self.tipTimer);
      function tick() { sts.forEach(function (e, j) { e.classList.toggle("lit", j === k % (sts.length + 1)); e.classList.toggle("done", j < k % (sts.length + 1)); }); k++; }
      tick(); self.tipTimer = setInterval(tick, 260);
    }
    function hide() { clearInterval(self.tipTimer); tip.hidden = true; }
    el.querySelectorAll(".mv").forEach(function (b) {
      b.addEventListener("mouseenter", function () { show(b); });
      b.addEventListener("focus", function () { show(b); });
      b.addEventListener("mouseleave", hide);
      b.addEventListener("blur", hide);
    });
  };

  // ---------- 输入历史 + 搓招判定 ----------
  Coach.prototype.reset = function () { this.hist = []; this.rel = []; this.pending = []; this.prevBtn = 0; };
  /* 每个对局帧调用一次（人类玩家）：code = 这一帧的输入编号（相对朝向），macro = 简易搓招的宏名或 null */
  Coach.prototype.onFrame = function (core, idx, code, macro, facing) {
    var db = F.decodeInput(code), d = db[0], b = db[1], f = core.f[idx];
    this.rel.push(d); if (this.rel.length > 40) this.rel.shift();
    var press = b && b !== this.prevBtn; this.prevBtn = b;
    var ar = ARROW[absDir(d, facing)], top = this.hist[0];
    if (press || !top || top.arrow !== ar || top.btn) {
      this.hist.unshift({arrow: ar, btn: press ? (b === 1 ? "J" : "K") : "", n: 1, macro: macro && press ? true : false});
      if (this.hist.length > 14) this.hist.pop();
    } else top.n++;
    if (press) this.pending.push({frame: core.frame, snap: this.rel.slice(), facing: facing, macro: !!macro, proj: f.proj !== null, act: [0, 1, 2, 3].indexOf(f.state) >= 0});
    // 这一帧是否放出了必杀技
    if (f.move && f.move_frame === 1 && f.move.special) {
      var nm = f.move.name.indexOf("fireball") === 0 ? FB : DP;
      this.flash(nm + " ✓" + (this.pending.some(function (p) { return p.macro; }) ? "（新手键）" : ""), "ok");
      this.pending = [];
    }
    var self = this;
    this.pending = this.pending.filter(function (p) {
      if (core.frame - p.frame < 6) return true;
      var hint = self.diagnose(p);
      if (hint) self.flash(hint, "hint");
      return false;
    });
    this.track(core, idx, macro);
  };
  /* 没放出必杀技时，猜测玩家想搓什么、差在哪（与核心判定同一规则：三个方向在 15 帧内，最后一个方向在按键前 5 帧内） */
  Coach.prototype.diagnose = function (p) {
    var h = p.snap, n = h.length, last = n - 1, fc = p.facing;
    function lastIdx(v, from, lo) { for (var i = from; i >= Math.max(0, lo); i--) if (h[i] === v) return i; return -1; }
    function A(rel) { return arrow(rel, fc); }
    // 有没有像在搓：最近 20 帧里出现过带「下」的方向
    if (lastIdx(2, last, last - 20) < 0 && lastIdx(1, last, last - 20) < 0 && lastIdx(3, last, last - 20) < 0) return null;
    var res = [];
    // 气功波：2 3 6
    var j6 = lastIdx(6, last, last - 8);
    if (j6 >= 0) {
      var j3 = lastIdx(3, j6, last - 25), j2 = lastIdx(2, j3 >= 0 ? j3 : j6, last - 25);
      if (j2 >= 0 && j2 < j6) {
        var r = null;
        if (j3 < 0 || j3 < j2) r = "少了 " + A(3) + "：" + A(2) + " 之后先经过 " + A(3) + " 再到 " + A(6);
        else if (last - j6 > 4) r = "按键晚了：搓到 " + A(6) + " 的同时就按 J/K";
        else if (last - j2 > 14) r = "方向太慢了：" + A(2) + A(3) + A(6) + " 要在 ¼ 秒内连贯搓完";
        else if (p.proj) r = "场上已经有你的" + FB + "，等它消失再放";
        else if (!p.act) r = "正在出招或受击，这时放不出必杀技";
        if (r) res.push([3, FB + "没出来：" + r]);
      }
    }
    // 冲天拳：6 2 3
    var k3 = lastIdx(3, last, last - 5);
    if (k3 >= 0) {
      var k2 = lastIdx(2, k3, last - 25), k6 = lastIdx(6, k2 >= 0 ? k2 : k3, last - 25);
      if (k6 >= 0 && k2 >= 0 && k6 < k2) {
        var r2 = null;
        if (last - k6 > 14) r2 = "方向太慢了：" + A(6) + A(2) + A(3) + " 要在 ¼ 秒内搓完";
        else if (!p.act) r2 = "正在出招或受击，这时放不出必杀技";
        if (r2) res.push([3, DP + "没出来：" + r2]);
      } else if (k6 < 0 && k2 >= 0 && lastIdx(6, last, last - 25) < 0) {
        res.push([1, "想放" + DP + "？要先按 " + A(6) + "，再 " + A(2) + A(3) + " + J/K"]);
      }
    } else if (j6 < 0 && lastIdx(3, last, last - 8) < 0 && h[last] === 2) {
      return null;   // 只是蹲着出拳
    }
    if (!res.length) return null;
    res.sort(function (a, b) { return b[0] - a[0]; });
    return res[0][1];
  };
  Coach.prototype.flash = function (text, kind) {
    var el = $("coach-flash"); if (!el) return;
    el.textContent = text; el.className = "flash " + kind; el.hidden = false;
    this.flashT = 90;
  };
  Coach.prototype.tick = function () {
    if (this.flashT > 0 && --this.flashT === 0) { var el = $("coach-flash"); if (el) el.hidden = true; }
  };
  Coach.prototype.renderHistory = function () {
    var el = $("inhist"); if (!el || el.hidden) return;
    var html = this.hist.map(function (h) {
      return '<li class="' + (h.macro ? "mc" : "") + '"><span class="a">' + h.arrow + '</span><span class="bt">' + (h.btn || "") + "</span>" +
        '<span class="n">' + Math.min(99, h.n) + "</span></li>";
    }).join("");
    if (html !== this._lastHist) { el.innerHTML = html; this._lastHist = html; }
  };

  // ---------- 练习模式 ----------
  var TASKS = [
    ["walkF", "前进", "朝对手走一段"], ["walkB", "后退", "远离对手走一段"], ["jump", "跳", "W"], ["crouch", "蹲", "S"],
    ["blockS", "站防", "木桩选「会出拳」，按住后挡住它的站重拳"], ["blockC", "蹲防", "木桩选「会出拳」，按住下后挡住它的扫腿/蹲轻"],
    ["light", "轻攻击", "J"], ["heavy", "重攻击", "K"],
    ["fireball", FB, "↓↘→ + J/K（或新手键 U）"], ["dp", DP, "→↓↘ + J/K（或新手键 I）"]
  ];
  /* 退出时调用：停掉招式表提示的动画定时器 */
  Coach.prototype.stop = function () {
    clearInterval(this.tipTimer); this.tipTimer = null; this.tasks = null;
    var tip = $("mvtip"); if (tip) tip.hidden = true;
  };
  Coach.prototype.startPractice = function () { this.tasks = {}; this.counts = {}; this.renderTasks(); };
  Coach.prototype.stopPractice = function () { this.tasks = null; };
  Coach.prototype.track = function (core, idx, macro) {
    if (!this.tasks) return;
    var f = core.f[idx], c = this.counts, t = this.tasks, before = JSON.stringify(t);
    function cnt(k, ok, need) { c[k] = (c[k] || 0) + (ok ? 1 : 0); if (c[k] >= need) t[k] = t[k] || "done"; }
    cnt("walkF", f.state === C.S_WALK_F, 20); cnt("walkB", f.state === C.S_WALK_B, 20);
    cnt("crouch", f.state === C.S_CROUCH, 15);
    if (f.state === C.S_JUMPSQUAT) t.jump = t.jump || "done";
    if (f.state === C.S_BLOCKSTUN && this._prevState !== C.S_BLOCKSTUN) {
      if ([1, 2, 3].indexOf(f.dir_now) >= 0) t.blockC = t.blockC || "done"; else t.blockS = t.blockS || "done";
    }
    this._prevState = f.state;
    if (f.move && f.move_frame === 1) {
      var n = f.move.name, tag = macro || this.pending.some(function (p) { return p.macro; }) ? "easy" : "done";
      if (/_L$/.test(n) && !f.move.special) t.light = t.light || "done";
      if (/_H$/.test(n) && !f.move.special) t.heavy = t.heavy || "done";
      if (n.indexOf("fireball") === 0) t.fireball = t.fireball === "done" ? "done" : tag;
      if (n.indexOf("dp") === 0) t.dp = t.dp === "done" ? "done" : tag;
    }
    if (JSON.stringify(t) !== before) this.renderTasks();
  };
  Coach.prototype.renderTasks = function () {
    var el = $("tasks"); if (!el || !this.tasks) return;
    var t = this.tasks, n = 0;
    el.innerHTML = TASKS.map(function (k) {
      var st = t[k[0]]; if (st) n++;
      return '<li class="' + (st ? "ok" : "") + '"><span class="ck">' + (st ? "✓" : "") + "</span><b>" + esc(k[1]) + "</b>" +
        '<span class="hint">' + (st === "easy" ? "用新手键完成；关掉新手模式手搓一次可以变成实心勾" : esc(k[2])) + "</span></li>";
    }).join("");
    var p = $("tasks-progress"); if (p) p.textContent = n + " / " + TASKS.length;
  };
  /* 木桩对手：stand 站着不动 / block 只防御 / jump 只跳 / attack 会出拳（练防御用） */
  Coach.dummyCode = function (core, idx, mode) {
    var me = core.f[idx], op = core.f[1 - idx], t = core.frame;
    if (mode === "block") {
      var low = (op.move && op.move.level === "low") || [1, 2, 3].indexOf(op.dir_now) >= 0;
      return E(low ? 1 : 4, 0);
    }
    if (mode === "jump") return E((t % 70) < 3 ? 8 : 5, 0);
    if (mode === "attack") {
      if (Math.abs(op.x - me.x) > 62 && !me.move) return E(6, 0);
      var k = Math.floor(t / 70) % 2, ph = t % 70;
      if (k === 0) return E(5, ph === 0 ? 2 : 0);              // 站重拳（中段）
      return ph < 12 ? E(2, ph === 2 ? 1 : 0) : E(5, 0);       // 蹲轻（下段）
    }
    return E(5, 0);
  };
  Coach.MOVELIST = MOVELIST;
  window.ArenaCoach = Coach;
})();
