/* arena 主程序：三种玩法（观战 / 我来打 / 练习）、比赛流程（三局两胜、开场/KO 演出）、固定 60 帧时间步、
 * 人类/AI/木桩玩家、对手预设、模型按需加载、大脑面板布局、播放控制、叠加层开关、神经元敲除、新手引导接入、
 * 录像/测试钩子（window.ARENA_TEST）。 */
(function () {
  "use strict";
  var F = window.FightRL, C = F.C, B = window.ArenaBrain, SPEC = window.ARENA_SPEC, INDEX = window.ARENA_MODEL_INDEX || [];
  var NM = SPEC.naming || {characters: [{ui: "#7fb0ff", label: "P1（蓝）"}, {ui: "#ff8f87", label: "P2（红）"}]};
  var $ = function (id) { return document.getElementById(id); };
  var COLORS = NM.characters.map(function (c) { return c.ui; });
  var LABELS = NM.characters.map(function (c) { return c.label; });

  // ---------------- 对手预设（按模型 id 依次尝试，取发布包里有的第一个） ----------------
  var PRESETS = [
    {key: "easy", name: "新手", ids: ["w16_d2_human_s0", "w8_d2_human_s0", "w32_d2_human_s0"]},
    {key: "normal", name: "普通", ids: ["w128_d2_human_s0", "w64_d2_human_s2", "w64_d2_human_s0"]},
    {key: "hard", name: "困难", ids: ["w512_d2_human_s0", "w256_d2_human_s0"]},
    {key: "free", name: "无限制", ids: ["w256_d2_free_s0", "w64_d2_free_s0", "w16_d2_free_s0", "legacy_league0"]}
  ];

  // ---------------- 模型加载 ----------------
  var models = {}, waiting = {};
  window.ARENA_REGISTER = function (spec) {
    models[spec.id] = spec;
    (waiting[spec.id] || []).forEach(function (cb) { cb(spec); });
    delete waiting[spec.id];
  };
  function loadModel(id, cb) {
    if (models[id]) { cb(models[id]); return; }
    if (waiting[id]) { waiting[id].push(cb); return; }
    waiting[id] = [cb];
    var s = document.createElement("script");
    s.src = "assets/gen/models/" + id + ".js";
    s.onerror = function () { status("模型文件加载失败：" + id); };
    document.head.appendChild(s);
  }
  function meta(id) { for (var i = 0; i < INDEX.length; i++) if (INDEX[i].id === id) return INDEX[i]; return null; }
  function presetModel(p) { for (var i = 0; i < p.ids.length; i++) if (meta(p.ids[i])) return meta(p.ids[i]); return null; }

  // ---------------- 随机数（可复现录像用） ----------------
  var rngState = 0, seeded = false;
  function rand() {
    if (!seeded) return Math.random();
    rngState = (rngState + 0x6D2B79F5) | 0;
    var t = Math.imul(rngState ^ rngState >>> 15, 1 | rngState);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  }

  // ---------------- 状态 ----------------
  var app = {
    mode: "watch", layout: "all", brainSide: 1, speed: 1, paused: false, dummy: "stand", big: false, stopped: false,
    players: [{kind: "ai", id: null}, {kind: "ai", id: null}],
    match: {round: 1, wins: [0, 0], phase: "intro", t: 0, lastWinner: null},
    snaps: {}, opts: {boxes: false, ghost: true, edges: true, attribution: true, ig: false, sound: true}
  };
  var core = new F.Core({seed: (Date.now() & 0xffff) + 1});
  var gameCv = $("game"), R = new window.ArenaRender(gameCv), sfx = new window.ArenaSfx(), input = new window.ArenaInput();
  input.bind(window);
  var coach = new window.ArenaCoach({getFacing: function () { return core.f[0].facing; }});
  // 手机竖屏操控区（浮动摇杆 + J/K 大圆键 + 技能键）
  var touch = window.ArenaTouch && $("touchctl") ? new window.ArenaTouch($("touchctl"), input) : null;
  // 触屏 + 窄屏：竖屏 = body.touchp（游戏在上、操控区在下）；横屏 = body.touchl（提示竖屏更好）
  var MQ_P = window.matchMedia ? window.matchMedia("(pointer: coarse) and (max-width: 980px) and (orientation: portrait)") : null;
  var MQ_L = window.matchMedia ? window.matchMedia("(pointer: coarse) and (orientation: landscape) and (max-height: 600px)") : null;
  function applyTouchLayout() {
    var p = !!(MQ_P && MQ_P.matches), l = !!(MQ_L && MQ_L.matches);
    var changed = document.body.classList.contains("touchp") !== p;
    document.body.classList.toggle("touchp", p);
    document.body.classList.toggle("touchl", l);
    if (changed) { closeSheets(); if (touch) touch.reset(); setTimeout(function () { refreshBrains(); }, 0); }
  }
  function closeSheets() { document.body.classList.remove("sheet-brain", "sheet-ctrl"); }
  function openSheet(which) {
    closeSheets(); document.body.classList.add("sheet-" + which); toggleMenu(false);
    if (touch) touch.reset();
    setTimeout(function () { refreshBrains(); }, 0);
  }
  function toggleMenu(on) {
    var m = $("menu"); if (!m) return;
    var open = on === undefined ? m.hidden : on;
    m.hidden = !open; $("menu-btn").setAttribute("aria-expanded", open);
  }
  document.querySelectorAll("[data-pad]").forEach(function (btn) {
    var k = btn.getAttribute("data-pad");
    function set(v) { return function (e) { e.preventDefault(); input.touch[k] = v; btn.classList.toggle("on", v); sfx.resume(); }; }
    btn.addEventListener("pointerdown", set(true)); btn.addEventListener("pointerup", set(false));
    btn.addEventListener("pointerleave", set(false)); btn.addEventListener("pointercancel", set(false));
  });
  document.querySelectorAll("[data-easy]").forEach(function (btn) {
    btn.addEventListener("pointerdown", function (e) { e.preventDefault(); if (input.enabled) input.macro(+btn.getAttribute("data-easy")); sfx.resume(); });
  });
  // 右栏的大脑：每个可见的大脑一块画布；按 N 个智能体设计（N ≤ 2 上下堆叠，N = 3–4 时宽度够就 2×2，否则堆叠 + 滚动）
  var views = [];
  function ensureViews(n) {
    while (views.length < n) {
      var cv = document.createElement("canvas");
      cv.setAttribute("aria-label", "神经网络实时可视化");
      $("brain-stack").appendChild(cv);
      var v = new window.ArenaBrainView(cv, SPEC, app.opts);
      v.onChange = updateCutInfo;
      v.onSelect = function (side) { setBrainView(String(side)); };
      views.push(v);
    }
    views.forEach(function (v, i) { v.cv.hidden = i >= n; if (i >= n) v.setPlayer(null); });
  }

  function status(msg) { var el = $("status"); if (el) el.textContent = msg; }
  function playerName(i) {
    var p = app.players[i];
    if (p.kind === "human") return "YOU";
    if (p.kind === "dummy") return "DUMMY";
    var m = meta(p.id);
    return m ? (m.family === "legacy" ? m.id.replace("legacy_", "").toUpperCase() : m.short + (m.cond === "free" ? " FREE" : "")) : "CPU";
  }
  function setAI(i, id, cb) {
    app.players[i] = {kind: "ai", id: id, loading: true};
    status("加载模型 " + id + " …");
    loadModel(id, function (spec) {
      var net = new B.Net(spec);
      var bp = new B.BrainPlayer(net, spec.env_cfg, {rand: rand});
      app.players[i] = {kind: "ai", id: id, net: net, bp: bp, spec: spec};
      status("");
      refreshBrains(); updateModelInfo(); syncPresetButtons();
      if (cb) cb();
    });
  }
  function setHuman(i) { app.players[i] = {kind: "human"}; refreshBrains(); updateModelInfo(); }
  function setDummy(i) { app.players[i] = {kind: "dummy"}; refreshBrains(); updateModelInfo(); }
  function brainTitle(i) { var m = app.players[i].spec; return LABELS[i] + " 的大脑 · " + (m ? m.label : ""); }
  function aiSides() { var out = []; app.players.forEach(function (p, i) { if (p.kind === "ai") out.push(i); }); return out; }
  function buildBrainTabs() {
    var box = $("brain-tabs"), html = "";
    app.players.forEach(function (p, i) {
      html += '<button data-bv="' + i + '"' + (p.kind !== "ai" ? " disabled title=\"这一侧是人类或木桩，没有网络\"" : "") +
        ' style="border-bottom:2px solid ' + COLORS[i % COLORS.length] + '">P' + (i + 1) + " 大脑</button>";
    });
    html += '<button data-bv="all">全部</button>';
    if (box.getAttribute("data-html") !== html) { box.innerHTML = html; box.setAttribute("data-html", html); }
    var cur = app.layout === "all" ? "all" : String(app.brainSide);
    box.querySelectorAll("button").forEach(function (b) { b.classList.toggle("on", b.getAttribute("data-bv") === cur); b.setAttribute("aria-pressed", b.getAttribute("data-bv") === cur); });
  }
  function setBrainView(v) {
    if (v === "all") app.layout = "all"; else { app.layout = "single"; app.brainSide = +v; }
    refreshBrains();
  }
  function refreshBrains() {
    var ai = aiSides(), sides;
    if (app.layout !== "all" && ai.indexOf(app.brainSide) < 0 && ai.length) app.brainSide = ai[ai.length - 1];
    sides = app.layout === "all" ? ai : (ai.indexOf(app.brainSide) >= 0 ? [app.brainSide] : []);
    if (!sides.length) sides = [app.brainSide];
    buildBrainTabs();
    // 窄屏（手机）：大脑在游戏下方；「全部」即使只有一个 AI 也用紧凑画法，避免完整画法挤在 360px 里
    var narrow = window.matchMedia ? window.matchMedia("(max-width: 980px)").matches : window.innerWidth <= 980;
    var compact = app.layout === "all" && (sides.length >= 2 || narrow), stack = $("brain-stack");
    ensureViews(sides.length);
    sides.forEach(function (s, n) {
      var p = app.players[s];
      views[n].setPlayer(p.kind === "ai" ? p.bp : null, p.kind === "ai" ? brainTitle(s) : "", COLORS[s % COLORS.length]);
      views[n].side = s; views[n].mode = compact ? "compact" : "full";
    });
    stack.classList.toggle("all", compact);
    stack.classList.toggle("single", !compact);
    var wide = stack.clientWidth >= 1100;
    stack.classList.toggle("grid2", compact && sides.length >= 3 && wide);
    stack.classList.toggle("scroll", compact && sides.length >= 3 && !wide);
    document.body.classList.toggle("big", app.big);
    resize();
    updateCutInfo();
  }
  function updateCutInfo() {
    var n = 0;
    app.players.forEach(function (p) { if (p.bp) p.bp.masks.forEach(function (m) { for (var i = 0; i < m.length; i++) if (m[i] === 0) n++; }); });
    $("cut-info").textContent = n ? "已敲掉 " + n + " 个神经元（下一次决策起生效）" : "点大脑面板里的任意神经元可以敲掉它";
    $("cut-reset").disabled = !n;
    var kp = keyPlayers();
    $("cut-key").disabled = !kp.length;
    if (kp.length) {
      var inf = app.players[kp[0]].spec.key_info || {};
      $("cut-key").textContent = "敲掉" + (inf.label || "关键神经元");
      $("cut-key-note").textContent = "金框 = " + (inf.label || "") + "的神经元。敲除实验里一起敲掉它们，得分下降 " + Math.round((inf.group_drop || 0) * 100) +
        "%；随机敲掉同样多个平均下降 " + Math.round((inf.random_drop || 0) * 100) + "%——这个网络没有单个“关键”神经元，影响主要取决于敲掉多少个。";
    } else {
      $("cut-key").textContent = "敲掉标注的神经元";
      $("cut-key-note").textContent = "当前模型没有敲除实验的标注（实验对象是 64×2 人类条件种子 2，可在模型下拉框里选）。可以用右边按钮随机敲掉 25%。";
    }
  }
  function keyPlayers() {
    var out = [];
    app.players.forEach(function (p, i) { if (p.spec && p.spec.key_neurons && p.spec.key_neurons.length) out.push(i); });
    return out;
  }
  function cutRandom(frac) {
    app.players.forEach(function (p) {
      if (!p.bp) return;
      p.bp.masks.forEach(function (m) {
        var idx = []; for (var i = 0; i < m.length; i++) idx.push(i);
        for (var k = idx.length - 1; k > 0; k--) { var r = Math.floor(rand() * (k + 1)); var t = idx[k]; idx[k] = idx[r]; idx[r] = t; }
        idx.slice(0, Math.round(m.length * frac)).forEach(function (i) { m[i] = 0; });
      });
    });
    views.forEach(function (v) { v.lastDecision = -1; });
    updateCutInfo();
  }
  function cutKeys() {
    keyPlayers().forEach(function (i) {
      var p = app.players[i];
      p.spec.key_neurons.forEach(function (k) { p.bp.masks[k[0]][k[1]] = 0; });
    });
    views.forEach(function (v) { v.lastDecision = -1; });
    updateCutInfo();
  }
  function restoreAll() {
    app.players.forEach(function (p) { if (p.bp) p.bp.masks.forEach(function (m) { m.fill(1); }); });
    views.forEach(function (v) { v.lastDecision = -1; });
    updateCutInfo();
  }

  // ---------------- 比赛流程 ----------------
  function newRound() {
    core.reset();
    app.players.forEach(function (p) { if (p.bp) p.bp.reset(); });
    app.snaps = {}; R.hpTrail = [C.MAX_HP, C.MAX_HP];
    app.match.phase = app.mode === "practice" ? "fight" : "intro"; app.match.t = 0;
    coach.reset();
  }
  function newMatch() {
    // 练习模式：回合很长、不计时（回血见 tickFrame）
    var rs = app.mode === "practice" ? 3600 : C.DEFAULT_ROUND_SECONDS;
    if (core.round_frames !== Math.floor(rs * C.FPS)) core = new F.Core({seed: (Date.now() & 0xffff) + 1, round_seconds: rs});
    app.match.round = 1; app.match.wins = [0, 0]; newRound();
  }
  function ready() { return app.players.every(function (p) { return p.kind !== "ai" || p.bp; }); }

  function soundForMoves() {
    core.f.forEach(function (f) {
      if (f.move && f.move_frame === 1) {
        var n = f.move.name;
        if (n.indexOf("fireball") === 0) sfx.fireball(); else if (n.indexOf("dp") === 0) sfx.dp(); else sfx.whoosh();
      }
    });
  }
  function tickFrame() {
    var M = app.match;
    if (!ready()) return;
    if (M.phase === "intro") {
      if (M.t === 0) sfx.beep(false);
      if (M.t === 50) sfx.beep(true);
      if (++M.t >= 80) { M.phase = "fight"; M.t = 0; }
    } else if (M.phase === "fight") {
      var macro = null, facing0 = core.f[0].facing;
      var ins = [0, 1].map(function (i) {
        var p = app.players[i];
        if (p.kind === "human") { var c = input.code(core.f[i].facing); macro = input.lastMacro; return c; }
        if (p.kind === "dummy") return window.ArenaCoach.dummyCode(core, i, app.dummy);
        return p.bp.act(core, i);
      });
      core.step(ins[0], ins[1]);
      if (app.players[0].kind === "human") coach.onFrame(core, 0, ins[0], macro, facing0);
      if (app.mode === "practice") core.f.forEach(function (f) { if (f.hp < 400) f.hp = C.MAX_HP; });
      app.snaps[core.frame] = window.ArenaRender.snapshot(core);
      delete app.snaps[core.frame - 40];
      R.onEvents(core, app.opts.sound ? sfx : null);
      if (app.opts.sound) soundForMoves();
      if (core.done) {
        M.phase = "ko"; M.t = 0;
        if (core.winner === 0 || core.winner === 1) M.wins[core.winner]++;
        M.lastWinner = core.winner;
        if (app.opts.sound) sfx.ko();
      }
    } else if (M.phase === "ko") {
      if (++M.t >= 110) {
        if (M.wins[0] >= 2 || M.wins[1] >= 2) { M.phase = "end"; M.t = 0; }
        else { M.round++; newRound(); }
      }
    } else if (M.phase === "end") {
      if (++M.t >= 170) newMatch();
    }
    coach.tick();
    R.tickFx();
  }
  function banner() {
    var M = app.match;
    if (M.phase === "intro") return M.t < 50 ? {text: "ROUND " + M.round, color: "#ffffff"} : {text: "FIGHT!", color: "#ffd23f", size: 22};
    if (M.phase === "ko") {
      var w = M.lastWinner;
      return {text: core.end_reason === "ko" ? "K.O." : "TIME", color: "#ff5a5a", size: 24,
        sub: w === -1 ? "DRAW" : playerName(w) + " WINS ROUND " + M.round};
    }
    if (M.phase === "end") return {text: playerName(M.wins[0] >= 2 ? 0 : 1) + " WINS", color: "#ffd23f", size: 16, sub: M.wins[0] + " - " + M.wins[1]};
    return null;
  }
  function ghosts() {
    if (!app.opts.ghost || app.match.phase !== "fight") return null;
    var out = [];
    [0, 1].forEach(function (i) {
      var p = app.players[i];
      if (!p.bp || p.bp.d <= 0) return;
      var sn = app.snaps[core.frame - p.bp.d];
      if (sn) out.push({snap: sn, who: 1 - i, color: COLORS[i], label: "P" + (i + 1) + " 此刻看到的（" + Math.round(p.bp.d * 1000 / 60) + "ms 前）"});
    });
    return out;
  }
  function render() {
    R.opts.boxes = app.opts.boxes; R.opts.ghost = app.opts.ghost;
    R.draw(core, {names: [playerName(0), playerName(1)], wins: app.match.wins, banner: banner(), ghosts: ghosts(), paused: app.paused, noTimer: app.mode === "practice"});
    var brainsHidden = document.body.classList.contains("touchp") && app.mode !== "watch" && !document.body.classList.contains("sheet-brain");
    if (app.mode !== "practice" && !brainsHidden) views.forEach(function (v) { if (!v.cv.hidden) v.draw(core, v.side); });
    coach.renderHistory();
    updateReadout();
  }
  function updateReadout() {
    var el = $("readout"), parts = [];
    [0, 1].forEach(function (i) {
      var p = app.players[i];
      if (p.bp && p.bp.last) parts.push("P" + (i + 1) + "：" + SPEC.actions[p.bp.last.action] + "（" + Math.round(p.bp.last.fw.probs[p.bp.last.action] * 100) + "%），局势 " + (p.bp.last.value >= 0 ? "+" : "") + p.bp.last.value.toFixed(2));
    });
    el.textContent = parts.join("　｜　") + "　·　第 " + core.frame + " 帧";
    var mi = $("mi-read");
    if (mi && document.body.classList.contains("touchp") && app.mode !== "watch") {
      var p2 = app.players[1], txt;
      if (app.mode === "practice") {
        var t = coach.tasks || {}, n = 0; for (var k in t) if (t[k]) n++;
        txt = "任务 " + n + " / 10 · 点「任务清单」看哪些还没完成";
      } else {
        txt = "比分 " + app.match.wins[0] + " : " + app.match.wins[1] + (p2.bp && p2.bp.last ? " · 对手想：" + SPEC.actions[p2.bp.last.action] + "（" +
          Math.round(p2.bp.last.fw.probs[p2.bp.last.action] * 100) + "%）· 局势 " + (p2.bp.last.value >= 0 ? "+" : "") + p2.bp.last.value.toFixed(2) : "");
      }
      if (mi.textContent !== txt) mi.textContent = txt;
    }
  }

  // ---------------- 主循环（固定时间步） ----------------
  var acc = 0, lastT = null, manual = false, rafId = null;
  function loop(t) {
    if (app.stopped) { rafId = null; return; }
    if (!manual) {
      if (lastT === null) lastT = t;
      var dt = Math.min(0.1, (t - lastT) / 1000); lastT = t;
      if (!app.paused && !app.helpOpen) {
        acc += dt * app.speed;
        var n = 0;
        while (acc >= 1 / 60 && n < 6) { tickFrame(); acc -= 1 / 60; n++; }
      }
      render();
    }
    rafId = requestAnimationFrame(loop);
  }

  // ---------------- 布局 ----------------
  function resize() {
    var r = gameCv.getBoundingClientRect();
    var w = Math.max(320, r.width), h = w * C.STAGE_H / C.STAGE_W;
    var dpr = Math.min(2, window.devicePixelRatio || 1);
    gameCv.width = Math.round(w * dpr); gameCv.height = Math.round(h * dpr);
    R.resize();
    views.forEach(function (v) { v.resize(); });
  }
  var wasNarrow = null;
  function onResize() {   // 跨过窄屏断点时重新安排大脑（紧凑 / 完整）
    var n = window.matchMedia ? window.matchMedia("(max-width: 980px)").matches : window.innerWidth <= 980;
    if (wasNarrow !== null && n !== wasNarrow) refreshBrains(); else resize();
    wasNarrow = n;
  }
  window.addEventListener("resize", onResize);

  // ---------------- 玩法切换 ----------------
  function setMode(mode, cb) {
    app.mode = mode;
    document.body.classList.remove("m-watch", "m-play", "m-practice");
    document.body.classList.add("m-" + mode);
    document.querySelectorAll("[data-mode]").forEach(function (b) { b.classList.toggle("on", b.getAttribute("data-mode") === mode); b.setAttribute("aria-pressed", b.getAttribute("data-mode") === mode); });
    var human = mode !== "watch";
    input.enabled = human;
    closeSheets(); if (touch) touch.reset();
    var bt = $("brain-toggle"); if (bt) bt.textContent = mode === "practice" ? "任务清单" : "看大脑";
    $("inhist").hidden = !human;
    if (mode === "practice") { coach.startPractice(); setHuman(0); setDummy(1); newMatch(); if (cb) cb(); }
    else {
      coach.stopPractice();
      if (human) { setHuman(0); app.brainSide = 1; }
      var n = 0, need = human ? 1 : 2, done = function () { if (++n === need) { refreshBrains(); newMatch(); if (cb) cb(); } };
      if (!human) applyPick(0, done, true);
      applyPick(1, done, true);
    }
    if (human) { gameCv.focus(); sfx.resume(); }
    refreshBrains();
  }

  // ---------------- 控件 ----------------
  var FAMILIES = [["human", "人类条件"], ["free", "无限制"], ["legacy", "旧实验"]];
  function familyOf(m) { return m.family === "legacy" ? "legacy" : m.cond; }
  function pickerHTML(i) {
    return '<div class="picker" id="pick' + i + '">' +
      '<div class="pk-head"><span class="dot" style="background:' + COLORS[i] + '"></span><b>' + LABELS[i] + "</b>" +
      '<span class="pk-you">你来操作（键盘 / 手柄）</span></div>' +
      '<div class="pk-body"><div class="presets" id="pre' + i + '" role="group" aria-label="对手预设">' +
      PRESETS.map(function (p) { return '<button data-pre="' + p.key + '">' + p.name + "</button>"; }).join("") + "</div>" +
      '<p class="minfo" id="preinfo' + i + '"></p>' +
      '<details class="adv"><summary>按网络大小挑选</summary>' +
      '<div class="seg" id="fam' + i + '">' + FAMILIES.map(function (f) { return '<button data-fam="' + f[0] + '">' + f[1] + "</button>"; }).join("") + "</div>" +
      '<label class="row">网络宽度 <input type="range" id="w' + i + '" min="0" max="6" step="1"><output id="wo' + i + '"></output></label>' +
      '<label class="row">深度 <select id="d' + i + '"></select> 种子 <select id="s' + i + '"></select></label>' +
      '<select class="full" id="m' + i + '"></select></details><p class="minfo" id="info' + i + '"></p></div></div>';
  }
  function candidates(i) {
    var fam = app.pick[i].fam;
    return INDEX.filter(function (m) { return familyOf(m) === fam; });
  }
  function syncPicker(i) {
    var P = app.pick[i], cands = candidates(i);
    $("fam" + i).querySelectorAll("button").forEach(function (b) { b.classList.toggle("on", b.getAttribute("data-fam") === P.fam); });
    var widths = uniq(cands.map(function (m) { return m.width; })).sort(function (a, b) { return a - b; });
    var w = $("w" + i);
    w.max = Math.max(0, widths.length - 1); w.disabled = widths.length <= 1;
    if (widths.indexOf(P.width) < 0) P.width = widths[Math.min(widths.length - 1, Math.floor(widths.length / 2))];
    w.value = Math.max(0, widths.indexOf(P.width)); app.pick[i].widths = widths;
    $("wo" + i).textContent = P.width ? P.width + " 个/层" : "—";
    var depths = uniq(cands.filter(function (m) { return m.width === P.width; }).map(function (m) { return m.depth; })).sort();
    if (depths.indexOf(P.depth) < 0) P.depth = depths.indexOf(2) >= 0 ? 2 : depths[0];
    $("d" + i).innerHTML = depths.map(function (d) { return '<option value="' + d + '">' + d + " 层</option>"; }).join("");
    $("d" + i).value = P.depth;
    var seeds = uniq(cands.filter(function (m) { return m.width === P.width && m.depth === P.depth; }).map(function (m) { return m.seed; })).sort();
    if (seeds.indexOf(P.seed) < 0) P.seed = seeds[0];
    $("s" + i).innerHTML = seeds.map(function (s) { return '<option value="' + s + '">' + s + "</option>"; }).join("");
    $("s" + i).value = P.seed;
    $("m" + i).innerHTML = INDEX.map(function (m) { return '<option value="' + m.id + '">' + m.label + "</option>"; }).join("");
    var hit = cands.filter(function (m) { return m.width === P.width && m.depth === P.depth && m.seed === P.seed; })
      .sort(function (a, b) {   // 滑块默认选主轴的 8M 步模型；算力对照（2M/4M/16M）从下拉框选
        var pa = a.steps === 8e6 ? 1e15 : a.steps, pb = b.steps === 8e6 ? 1e15 : b.steps; return pb - pa;
      })[0];
    return hit;
  }
  function uniq(a) { return a.filter(function (v, k) { return a.indexOf(v) === k; }); }
  function applyPick(i, cb, force) {
    if (app.players[i].kind === "human" && !force) return;
    var m = syncPicker(i);
    if (!m) { if (cb) cb(); return; }
    $("m" + i).value = m.id;
    if (app.players[i].id !== m.id || app.players[i].kind !== "ai") setAI(i, m.id, cb || function () { newMatch(); });
    else if (cb) cb();
  }
  function pickModel(i, m) {
    app.pick[i] = {fam: familyOf(m), width: m.width, depth: m.depth, seed: m.seed};
    syncPicker(i); $("m" + i).value = m.id;
    setAI(i, m.id, function () { newMatch(); });
  }
  function eloText(m) { return m && m.elo !== undefined ? "Elo " + Math.round(m.elo) : "Elo —"; }
  function presetInfo(p) {
    var m = presetModel(p); if (!m) return "（发布包里没有这一档的模型）";
    var e = m.env_cfg || {};
    return p.name + "：" + m.width + "×" + m.depth + " 网络（参数 " + m.params_actor.toLocaleString() + "）· " +
      (e.delay_ms ? e.delay_ms + "ms 反应 + APM≤" + e.apm : "0ms 反应、不限手速") + " · " + eloText(m) + "（随机乱按 = 0）";
  }
  function syncPresetButtons() {
    [0, 1].forEach(function (i) {
      var p = app.players[i], hit = null;
      PRESETS.forEach(function (q) { var m = presetModel(q); if (m && p.id === m.id) hit = q; });
      var box = $("pre" + i); if (!box) return;
      box.querySelectorAll("button").forEach(function (b) { b.classList.toggle("on", hit && b.getAttribute("data-pre") === hit.key); });
      $("preinfo" + i).textContent = hit ? presetInfo(hit) : "自选模型（见下方「按网络大小挑选」）";
      if (i === 1) document.querySelectorAll("[data-mpre]").forEach(function (b) { b.classList.toggle("on", !!hit && b.getAttribute("data-mpre") === hit.key); });
    });
  }
  function updateModelInfo() {
    [0, 1].forEach(function (i) {
      var p = app.players[i], m = p.spec || (p.id && meta(p.id)), el = $("info" + i);
      if (!el) return;
      if (p.kind !== "ai") { el.textContent = ""; return; }
      if (!m) { el.textContent = ""; return; }
      var e = m.env_cfg;
      el.textContent = "参数 " + m.params_actor.toLocaleString() + "（策略网络）· " + (e.delay_ms ? e.delay_ms + "ms 反应延迟" : "0ms 反应") +
        (e.apm ? "，APM≤" + e.apm : "，不限 APM") + " · 训练 " + (m.steps / 1e6) + "M 步" + (m.elo !== undefined ? " · 规模赛 Elo " + Math.round(m.elo) : "");
    });
  }
  function bindControls() {
    $("pickers").innerHTML = pickerHTML(0) + pickerHTML(1);
    [0, 1].forEach(function (i) {
      $("pre" + i).addEventListener("click", function (e) {
        var k = e.target.getAttribute && e.target.getAttribute("data-pre"); if (!k) return;
        var m = presetModel(PRESETS.filter(function (p) { return p.key === k; })[0]); if (m) pickModel(i, m);
      });
      $("fam" + i).addEventListener("click", function (e) {
        var f = e.target.getAttribute && e.target.getAttribute("data-fam"); if (!f) return;
        app.pick[i].fam = f; applyPick(i);
      });
      $("w" + i).addEventListener("input", function () { app.pick[i].width = app.pick[i].widths[+this.value]; applyPick(i); });
      $("d" + i).addEventListener("change", function () { app.pick[i].depth = +this.value; applyPick(i); });
      $("s" + i).addEventListener("change", function () { app.pick[i].seed = +this.value; applyPick(i); });
      $("m" + i).addEventListener("change", function () { var m = meta(this.value); if (m) pickModel(i, m); });
    });
    document.querySelectorAll("[data-mode]").forEach(function (b) {
      b.addEventListener("click", function () { setMode(b.getAttribute("data-mode")); });
    });
    $("dummy").addEventListener("click", function (e) {
      var k = e.target.getAttribute && e.target.getAttribute("data-dummy"); if (!k) return;
      app.dummy = k;
      this.querySelectorAll("button").forEach(function (b) { b.classList.toggle("on", b.getAttribute("data-dummy") === k); });
      document.querySelectorAll("[data-mdummy]").forEach(function (b) { b.classList.toggle("on", b.getAttribute("data-mdummy") === k); });
      gameCv.focus();
    });
    $("easy").checked = input.easy;
    $("easy").addEventListener("change", function () { input.easy = this.checked; document.body.classList.toggle("easy", this.checked); });
    document.body.classList.toggle("easy", input.easy);
    input.onEasyOff = function () { coach.flash("新手模式已关闭：U / I 不起作用，请手搓（或在左侧打开新手模式）", "hint"); };
    $("brain-tabs").addEventListener("click", function (e) {
      var v = e.target.getAttribute && e.target.getAttribute("data-bv"); if (v === null || e.target.disabled) return;
      setBrainView(v);
    });
    $("bigmode").addEventListener("change", function () { app.big = this.checked; refreshBrains(); });
    $("exit-btn").addEventListener("click", function () { shutdown(); });
    $("menu-btn").addEventListener("click", function (e) { e.stopPropagation(); toggleMenu(); });
    document.addEventListener("click", function (e) { var m = $("menu"); if (m && !m.hidden && !m.contains(e.target) && e.target !== $("menu-btn")) toggleMenu(false); });
    $("menu-report").addEventListener("click", function () { toggleMenu(false); closeSheets(); });
    $("menu-play").addEventListener("click", function () { toggleMenu(false); });
    $("menu-ctrl").addEventListener("click", function () { if (app.mode === "watch") { toggleMenu(false); $("pickers").scrollIntoView({block: "start"}); } else openSheet("ctrl"); });
    $("menu-help").addEventListener("click", function () { toggleMenu(false); coach.showHelp(); });
    $("menu-exit").addEventListener("click", function () { toggleMenu(false); shutdown(); });
    $("brain-toggle").addEventListener("click", function () { openSheet("brain"); });
    $("brain-close").addEventListener("click", function () { closeSheets(); gameCv.focus(); });
    $("rot-ok").addEventListener("click", function () { document.body.classList.add("rot-ok"); });
    document.querySelectorAll("[data-mpre]").forEach(function (b) {
      b.addEventListener("click", function () { var m = presetModel(PRESETS.filter(function (p) { return p.key === b.getAttribute("data-mpre"); })[0]); if (m) pickModel(1, m); });
    });
    document.querySelectorAll("[data-mdummy]").forEach(function (b) {
      b.addEventListener("click", function () {
        var k = b.getAttribute("data-mdummy"); app.dummy = k;
        document.querySelectorAll("[data-mdummy]").forEach(function (x) { x.classList.toggle("on", x === b); });
        $("dummy").querySelectorAll("button").forEach(function (x) { x.classList.toggle("on", x.getAttribute("data-dummy") === k); });
      });
    });
    $("mi-easy").addEventListener("change", function () { $("easy").checked = this.checked; $("easy").dispatchEvent(new Event("change")); });
    $("easy").addEventListener("change", function () { $("mi-easy").checked = this.checked; });
    $("mi-restart").addEventListener("click", function () { newMatch(); });
    if (MQ_P && MQ_P.addEventListener) { MQ_P.addEventListener("change", applyTouchLayout); MQ_L.addEventListener("change", applyTouchLayout); }
    applyTouchLayout();
    $("pause").addEventListener("click", function () { app.paused = !app.paused; app.pausedByUser = app.paused; this.textContent = app.paused ? "继续" : "暂停"; });
    $("step").addEventListener("click", function () { app.paused = true; $("pause").textContent = "继续"; tickFrame(); });
    $("speed").addEventListener("change", function () { app.speed = +this.value; });
    $("restart").addEventListener("click", function () { newMatch(); });
    $("cut-reset").addEventListener("click", restoreAll);
    $("cut-key").addEventListener("click", cutKeys);
    $("cut-rand").addEventListener("click", function () { cutRandom(0.25); });
    ["boxes", "ghost", "edges", "attribution", "ig", "sound"].forEach(function (k) {
      var el = $("opt-" + k); if (!el) return;
      el.checked = !!app.opts[k];
      el.addEventListener("change", function () { app.opts[k] = this.checked; views.forEach(function (v) { v.lastDecision = -1; }); if (k === "sound") sfx.enabled = this.checked; });
    });
    $("help-btn").addEventListener("click", function () { coach.toggleHelp(); });
    coach.onHelp = function (open) { app.helpOpen = open; if (!open && app.mode !== "watch") gameCv.focus(); };
    coach.bindHelp();
    coach.buildMoveList($("movelist"));
    document.addEventListener("pointerdown", function () { sfx.resume(); }, {once: false});
    window.addEventListener("keydown", function (e) {
      var tag = (e.target && e.target.tagName) || "";
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      if (e.key === "Escape" && !$("help").hidden) { coach.hideHelp(); return; }
      if ((e.key === "h" || e.key === "H" || e.key === "?") && !e.ctrlKey && !e.metaKey) { coach.toggleHelp(); e.preventDefault(); return; }
      if (e.key === " " && (e.target === document.body || e.target === gameCv)) { e.preventDefault(); $("pause").click(); }
      if (e.key === "." && app.paused) tickFrame();
    });
  }
  function fillCredits() {
    var cr = SPEC.credits || {}, el = $("credits"); if (!el) return;
    function v(k) { return cr[k] ? String(cr[k]) : "{{" + k + "}}"; }
    el.innerHTML = "<span>" + v("SERIES_NAME") + " 系列</span>" +
      "<span>" + v("AUTHOR_EN") + " · " + (cr.UNIVERSITY_LOGO ? '<img class="logo" src="' + cr.UNIVERSITY_LOGO + '" alt="" height="18"> ' : "") +
      (cr.UNIVERSITY_SHORT || v("UNIVERSITY_EN")) + ' · <span lang="ko">' + v("UNIVERSITY_KO") + "</span></span>" +
      "<span>代码 MIT · 文档与教学素材 CC BY 4.0</span><span>代码由 Claude Code 辅助编写，经作者审阅</span>";
  }

  // ---------------- 启动 ----------------
  function defaultPick() {
    var hard = presetModel(PRESETS[2]) || INDEX[0], norm = presetModel(PRESETS[1]) || INDEX[INDEX.length - 1];
    return [hard, norm].map(function (m) { return {fam: familyOf(m), width: m.width, depth: m.depth, seed: m.seed}; });
  }
  var reportDrawn = false;
  function parseHash() {
    var h = (location.hash || "").replace("#", "");
    if (h === "dual" || h === "all") app.layout = "all";
    if (h === "single") app.layout = "single";
    if (h === "big") { app.big = true; var bm = $("bigmode"); if (bm) bm.checked = true; }
    var rep = h === "report";
    document.body.classList.toggle("reportmode", rep);
    $("tab-report").classList.toggle("on", rep); $("tab-play").classList.toggle("on", !rep);
    app.paused = rep ? true : app.pausedByUser || false;
    if (rep && !reportDrawn && window.ARENA_REPORT_RENDER) { reportDrawn = true; window.ARENA_REPORT_RENDER(); }
    if (!rep) setTimeout(resize, 0);
  }
  window.addEventListener("hashchange", onHash);
  function onHash() { parseHash(); refreshBrains(); }

  // ---------------- 退出：停止一切计算、释放资源 ----------------
  var devServer = /^https?:$/.test(location.protocol) && /^(127\.0\.0\.1|localhost)$/.test(location.hostname);
  var beatTimer = null;
  function beat() {   // 只有 python -m arena 起的本地服务才需要心跳；静态网页（file://、GitHub Pages）不发
    if (!devServer || app.stopped || !window.fetch) return;
    fetch("/heartbeat", {method: "POST", cache: "no-store"}).catch(function () { clearInterval(beatTimer); beatTimer = null; });
  }
  if (devServer) { beat(); beatTimer = setInterval(beat, 5000); }
  function shutdown() {
    if (app.stopped) return;
    app.stopped = true; app.paused = true;
    if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null; }
    if (beatTimer) { clearInterval(beatTimer); beatTimer = null; }
    coach.stop();
    input.unbind();
    if (touch) { touch.reset(); touch.unbind(); }
    var closing = sfx.close();
    window.removeEventListener("resize", onResize);
    window.removeEventListener("hashchange", onHash);
    // 释放模型数据（权重数组）的引用
    app.players.forEach(function (p) { p.net = null; p.bp = null; p.spec = null; });
    views.forEach(function (v) { v.setPlayer(null); v.ex = null; });
    for (var k in models) delete models[k];
    if (devServer && window.fetch) fetch("/shutdown", {method: "POST", cache: "no-store", keepalive: true}).catch(function () {});
    app.audioClosed = closing && closing.then ? "closing" : "closed";
    if (closing && closing.then) closing.then(function () { app.audioClosed = "closed"; });
    try { window.close(); } catch (e) { /* 浏览器一般只允许关闭由脚本打开的窗口 */ }
    setTimeout(function () {   // 关不掉时显示结束页
      document.body.innerHTML = '<div id="ended" role="status"><div><h2>已停止运行</h2>' +
        "<p>所有计算都已结束：游戏循环、定时器、音效、手柄监听都已关闭，模型数据已释放" + (devServer ? "，本地服务也已退出" : "") + "。</p>" +
        "<p>可以直接关闭这个标签页。</p></div></div>";
    }, 150);
  }
  function start() {
    fillCredits();
    if (!INDEX.length) { status("没有找到模型：先运行 python -m arena.export"); return; }
    parseHash();
    app.pick = defaultPick();
    bindControls();
    syncPicker(0); syncPicker(1);
    document.body.classList.add("m-watch");
    var m0 = syncPicker(0), m1 = syncPicker(1);
    var n = 0, done = function () { if (++n === 2) { refreshBrains(); newMatch(); } };
    setAI(0, (m0 || INDEX[0]).id, done); setAI(1, (m1 || INDEX[0]).id, done);
    resize();
    if (coach.firstVisit() && !/[?&]nohelp/.test(location.search)) coach.showHelp();
    rafId = requestAnimationFrame(loop);
  }

  // ---------------- 测试 / 录像钩子 ----------------
  window.ARENA_TEST = {
    manual: function (on) { manual = on; },
    seed: function (s) { seeded = true; rngState = s | 0; core = new F.Core({seed: s + 1, round_seconds: app.mode === "practice" ? 3600 : C.DEFAULT_ROUND_SECONDS}); app.match.round = 1; app.match.wins = [0, 0]; newRound(); },
    step: function (n) { for (var i = 0; i < (n || 1); i++) tickFrame(); render(); return core.frame; },
    render: render,
    state: function () {
      return {frame: core.frame, phase: app.match.phase, round: app.match.round, wins: app.match.wins.slice(), mode: app.mode,
        hp: [core.f[0].hp, core.f[1].hp], ready: ready(), players: app.players.map(function (p) { return p.kind === "ai" ? p.id : p.kind; }),
        decisions: app.players.map(function (p) { return p.bp ? p.bp.decisions : 0; }), facing: [core.f[0].facing, core.f[1].facing],
        moves: core.f.map(function (f) { return f.move ? f.move.name : null; }), states: core.f.map(function (f) { return f.state; }),
        x: core.f.map(function (f) { return f.x; }), proj: core.f.map(function (f) { return f.proj !== null; }), layout: app.layout,
        help: !$("help").hidden, tasks: coach.tasks ? JSON.parse(JSON.stringify(coach.tasks)) : null, hist: coach.hist.slice(0, 6),
        flash: $("coach-flash").hidden ? "" : $("coach-flash").textContent};
    },
    setModels: function (a, b, cb) {
      var n = 0, d = function () { if (++n === 2) { refreshBrains(); newMatch(); if (cb) cb(); } };
      [a, b].forEach(function (id, i) { var m = meta(id); if (m) { app.pick[i] = {fam: familyOf(m), width: m.width, depth: m.depth, seed: m.seed}; syncPicker(i); $("m" + i).value = id; } });
      setAI(0, a, d); setAI(1, b, d);
    },
    setMode: setMode,
    preset: function (i, key) { var m = presetModel(PRESETS.filter(function (p) { return p.key === key; })[0]); if (m) pickModel(i, m); return m ? m.id : null; },
    dummy: function (k) { app.dummy = k; },
    setLayout: function (l, side) { app.layout = (l === "dual" || l === "all") ? "all" : "single"; if (side !== undefined) app.brainSide = side; refreshBrains(); },
    setBig: function (on) { app.big = !!on; $("bigmode").checked = !!on; refreshBrains(); },
    brains: function () {
      return views.filter(function (v) { return !v.cv.hidden; }).map(function (v) {
        var r = v.cv.getBoundingClientRect(), n = v.player && v.player.net;
        return {side: v.side, mode: v.mode, w: Math.round(r.width), h: Math.round(r.height), structure: v.structure(),
          widths: n ? n.widths.slice() : null, nIn: n ? n.actor.layers[0].nIn : null, nActions: n ? n.nActions : null, nParams: n ? n.nParams : null};
      });
    },
    touch: function () { return {touchp: document.body.classList.contains("touchp"), dir: $("touchctl").getAttribute("data-dir"),
      t: JSON.parse(JSON.stringify(input.touch)), sheet: document.body.classList.contains("sheet-brain") ? "brain" : (document.body.classList.contains("sheet-ctrl") ? "ctrl" : "")}; },
    exitState: function () { return {stopped: app.stopped, raf: rafId !== null, audio: sfx.ctx ? sfx.ctx.state : (app.audioClosed || "none"), beat: beatTimer !== null}; },
    shutdown: shutdown,
    cutKeys: cutKeys,
    cutRandom: cutRandom,
    humanP1: function (on) { setMode(on ? "play" : "watch"); },
    caption: function (t) { var c = $("caption"); c.textContent = t || ""; c.hidden = !t; },
    knock: function (side, layer, idxs) { var p = app.players[side]; idxs.forEach(function (j) { p.bp.masks[layer][j] = 0; }); updateCutInfo(); },
    cuts: function () { var n = 0; app.players.forEach(function (p) { if (p.bp) p.bp.masks.forEach(function (m) { for (var i = 0; i < m.length; i++) if (m[i] === 0) n++; }); }); return n; },
    restore: restoreAll,
    setOpt: function (k, v) { app.opts[k] = v; },
    hideHelp: function () { coach.hideHelp(); },
    easy: function (on) { input.easy = !!on; $("easy").checked = !!on; },
    skipIntro: function () { if (app.match.phase === "intro") { app.match.phase = "fight"; app.match.t = 0; } },
    presets: PRESETS,
    app: app
  };
  start();
})();
