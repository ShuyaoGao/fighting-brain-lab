/* 实验报告页：从 window.ARENA_REPORT（arena/export.py 从 results/*.json 导出）画全部图表并填数字。
 * 图表是手写 inline SVG，颜色走 CSS 变量；每个图都有悬停提示。 */
(function () {
  "use strict";
  var D = window.ARENA_REPORT || {}, NS = "http://www.w3.org/2000/svg";
  var tip;
  function $(id) { return document.getElementById(id); }
  function el(tag, attrs, parent, text) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (text !== undefined) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }
  function svg(box, w, h) { var s = el("svg", {viewBox: "0 0 " + w + " " + h}); box.innerHTML = ""; box.appendChild(s); return s; }
  function pct(v) { return v === null || v === undefined ? "–" : Math.round(v * 100) + "%"; }
  function r0(v) { return v === null || v === undefined ? "–" : Math.round(v).toLocaleString(); }
  function showTip(html, ev) {
    if (!tip) { tip = document.createElement("div"); tip.className = "rtip"; document.body.appendChild(tip); }
    tip.innerHTML = html; tip.hidden = false;
    var x = ev.clientX + 14, y = ev.clientY + 14;
    if (x + 280 > window.innerWidth) x = ev.clientX - 280;
    tip.style.left = x + "px"; tip.style.top = y + "px";
  }
  function hideTip() { if (tip) tip.hidden = true; }
  function hover(node, html) {
    node.addEventListener("mousemove", function (ev) { showTip(typeof html === "function" ? html() : html, ev); });
    node.addEventListener("mouseleave", hideTip);
  }
  function scale(d0, d1, r0_, r1, log) {
    if (log) { var a = Math.log(d0), b = Math.log(d1); return function (v) { return r0_ + (Math.log(v) - a) / (b - a) * (r1 - r0_); }; }
    return function (v) { return r0_ + (v - d0) / (d1 - d0) * (r1 - r0_); };
  }
  function niceTicks(lo, hi, n) {
    var step = Math.pow(10, Math.floor(Math.log10((hi - lo) / n))), err = (hi - lo) / n / step;
    step *= err >= 7.5 ? 10 : err >= 3 ? 5 : err >= 1.5 ? 2 : 1;
    var out = []; for (var v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(6));
    return out;
  }
  function frame(s, X0, X1, Y0, Y1, x, y, xt, yt, xl, yl, xf, yf) {
    yt.forEach(function (t) {
      el("line", {x1: X0, x2: X1, y1: y(t), y2: y(t), "class": "gr"}, s);
      el("text", {x: X0 - 8, y: y(t) + 4, "text-anchor": "end"}, s, yf ? yf(t) : t);
    });
    xt.forEach(function (t) {
      el("line", {x1: x(t), x2: x(t), y1: Y1, y2: Y1 + 5, "class": "ax"}, s);
      el("text", {x: x(t), y: Y1 + 18, "text-anchor": "middle"}, s, xf ? xf(t) : t);
    });
    el("line", {x1: X0, x2: X1, y1: Y1, y2: Y1, "class": "ax"}, s);
    if (xl) el("text", {x: (X0 + X1) / 2, y: Y1 + 38, "text-anchor": "middle", "class": "lab"}, s, xl);
    if (yl) el("text", {x: 14, y: (Y0 + Y1) / 2, transform: "rotate(-90 14 " + (Y0 + Y1) / 2 + ")", "text-anchor": "middle", "class": "lab"}, s, yl);
  }
  function fmtParams(p) { return p >= 1e6 ? (p / 1e6).toFixed(1) + "M" : p >= 1e3 ? Math.round(p / 1e3) + "k" : p; }
  var C1 = "var(--c1)", C2 = "var(--c2)", C3 = "var(--c3)", C4 = "var(--c4)";

  // ---------------- 规模：Elo vs 参数量 ----------------
  function eloVsParams() {
    var S = D.scaling; if (!S) return;
    var W = 820, H = 380, X0 = 70, X1 = W - 24, Y0 = 16, Y1 = H - 52, s = svg($("ch-elo"), W, H);
    var pts = [], all = [];
    Object.keys(S.width_axis).forEach(function (w) { var g = S.width_axis[w]; if (g.elo) { pts.push([g.params_actor, g, +w]); all = all.concat(g.elo.values); } });
    Object.keys(S.depth_variants).forEach(function (k) { var g = S.depth_variants[k]; if (g.elo) all = all.concat(g.elo.values); });
    Object.keys(S.free_controls).forEach(function (k) { var g = S.free_controls[k]; if (g.elo) all = all.concat(g.elo.values); });
    var bots = Object.keys(S.elo_scripted).map(function (k) { return S.elo_scripted[k]; });
    all = all.concat(bots);
    var lo = Math.min.apply(null, all), hi = Math.max.apply(null, all), pad = (hi - lo) * 0.08;
    var y = scale(lo - pad, hi + pad, Y1, Y0), x = scale(80, 2e6, X0, X1, true);
    var xt = [100, 1000, 10000, 100000, 1000000];
    frame(s, X0, X1, Y0, Y1, x, y, xt, niceTicks(lo - pad, hi + pad, 6), "策略网络参数量（对数轴）", "循环赛 BT-Elo", fmtParams);
    el("rect", {x: X0, y: y(Math.max.apply(null, bots)), width: X1 - X0, height: Math.max(2, y(Math.min.apply(null, bots)) - y(Math.max.apply(null, bots))), style: "fill:var(--ink-3);opacity:.16"}, s);
    el("text", {x: X1 - 6, y: y(Math.max.apply(null, bots)) - 6, "text-anchor": "end"}, s, "脚本 CPU 区间");
    // 无限制对照
    var fr = Object.keys(S.free_controls).map(function (k) { return S.free_controls[k]; }).filter(function (g) { return g.elo; })
      .sort(function (a, b) { return a.params_actor - b.params_actor; });
    if (fr.length) el("path", {d: fr.map(function (g, i) { return (i ? "L" : "M") + x(g.params_actor) + "," + y(g.elo.mean); }).join(""), style: "fill:none;stroke:" + C3 + ";stroke-width:2;stroke-dasharray:6 4"}, s);
    fr.forEach(function (g) {
      var r = el("rect", {x: x(g.params_actor) - 5, y: y(g.elo.mean) - 5, width: 10, height: 10, style: "fill:" + C3}, s);
      hover(r, "<b>无限制对照 " + g.width + "×2</b><br>Elo 均值 " + r0(g.elo.mean) + "（种子：" + g.elo.values.map(r0).join(" / ") + "）");
    });
    // 主轴
    pts.sort(function (a, b) { return a[0] - b[0]; });
    el("path", {d: pts.map(function (p, i) { return (i ? "L" : "M") + x(p[0]) + "," + y(p[1].elo.mean); }).join(""), style: "fill:none;stroke:" + C1 + ";stroke-width:2.5"}, s);
    pts.forEach(function (p) {
      var g = p[1];
      g.elo.values.forEach(function (v, k) {
        el("circle", {cx: x(p[0]) + (k - 1) * 4, cy: y(v), r: 3, style: "fill:" + C1 + ";opacity:.4"}, s);
      });
      if (g.elo.ci95) el("line", {x1: x(p[0]), x2: x(p[0]), y1: y(g.elo.ci95[0]), y2: y(g.elo.ci95[1]), style: "stroke:" + C1 + ";stroke-width:1.5"}, s);
      var c = el("circle", {cx: x(p[0]), cy: y(g.elo.mean), r: 6, style: "fill:" + C1 + ";stroke:var(--bg);stroke-width:2"}, s);
      el("text", {x: x(p[0]), y: y(g.elo.mean) - 12, "text-anchor": "middle", "class": "num"}, s, p[2]);
      hover(c, "<b>宽度 " + p[2] + " × 深度 2（人类条件）</b><br>参数 " + g.params_actor.toLocaleString() + "<br>Elo 均值 " + r0(g.elo.mean) +
        (g.elo.ci95 ? "（95% CI " + r0(g.elo.ci95[0]) + "–" + r0(g.elo.ci95[1]) + "）" : "") + "<br>3 个种子：" + g.elo.values.map(r0).join(" / ") +
        "<br>对防守反击 CPU：" + pct(g.vs_scripted.counter.mean));
    });
    // 深度变体
    Object.keys(S.depth_variants).forEach(function (k) {
      var g = S.depth_variants[k]; if (!g.elo || /_d2$/.test(k)) return;
      var d = +k.split("_d")[1], px = x(g.params_actor), py = y(g.elo.mean);
      var tri = d === 1 ? [[px - 6, py - 5], [px + 6, py - 5], [px, py + 6]] : [[px - 6, py + 5], [px + 6, py + 5], [px, py - 6]];
      var t = el("polygon", {points: tri.map(function (q) { return q.join(","); }).join(" "), style: "fill:" + C2}, s);
      hover(t, "<b>" + k.replace("_d", " × 深度 ") + "</b><br>参数 " + g.params_actor.toLocaleString() + "<br>Elo 均值 " + r0(g.elo.mean) + "（种子：" + g.elo.values.map(r0).join(" / ") + "）");
    });
  }
  function vsScripted() {
    var S = D.scaling; if (!S) return;
    var W = 820, H = 300, X0 = 64, X1 = W - 24, Y0 = 14, Y1 = H - 52, s = svg($("ch-cpu"), W, H);
    var x = scale(80, 2e6, X0, X1, true), y = scale(0, 1, Y1, Y0);
    frame(s, X0, X1, Y0, Y1, x, y, [100, 1000, 10000, 100000, 1000000], [0, 0.25, 0.5, 0.75, 1], "策略网络参数量（对数轴）", "胜率", fmtParams, pct);
    [["random", C1, "随机 CPU"], ["greedy", C2, "贪心进攻 CPU"], ["counter", C3, "防守反击 CPU"]].forEach(function (b) {
      var pts = Object.keys(S.width_axis).map(function (w) { return [S.width_axis[w], +w]; }).filter(function (p) { return p[0].elo; })
        .sort(function (a, c) { return a[0].params_actor - c[0].params_actor; });
      el("path", {d: pts.map(function (p, i) { return (i ? "L" : "M") + x(p[0].params_actor) + "," + y(p[0].vs_scripted[b[0]].mean); }).join(""), style: "fill:none;stroke:" + b[1] + ";stroke-width:2"}, s);
      pts.forEach(function (p) {
        var c = el("circle", {cx: x(p[0].params_actor), cy: y(p[0].vs_scripted[b[0]].mean), r: 4.5, style: "fill:" + b[1]}, s);
        hover(c, "<b>宽度 " + p[1] + " 对" + b[2] + "</b><br>胜率 " + pct(p[0].vs_scripted[b[0]].mean) + "（种子：" + p[0].vs_scripted[b[0]].values.map(pct).join(" / ") + "）");
      });
    });
  }
  function h2hMatrix() {
    var S = D.scaling; if (!S) return;
    var ws = Object.keys(S.width_axis).filter(function (w) { return S.width_axis[w].elo; }).map(Number).sort(function (a, b) { return a - b; });
    var n = ws.length, cs = 64, M0 = 70, s = svg($("ch-h2h"), M0 + n * cs + 20, M0 + n * cs + 30);
    ws.forEach(function (wa, i) {
      el("text", {x: M0 - 8, y: M0 + i * cs + cs / 2 + 4, "text-anchor": "end"}, s, wa);
      el("text", {x: M0 + i * cs + cs / 2, y: M0 - 10, "text-anchor": "middle"}, s, wa);
      ws.forEach(function (wb, j) {
        var v = S.head_to_head_width["w" + wa + "_vs_w" + wb], X = M0 + j * cs, Y = M0 + i * cs;
        el("rect", {x: X, y: Y, width: cs - 2, height: cs - 2, style: "fill:var(--heat-mid)"}, s);
        if (v === null || v === undefined) return;
        el("rect", {x: X, y: Y, width: cs - 2, height: cs - 2, style: "fill:" + (v >= 0.5 ? C1 : "var(--p2)") + ";opacity:" + (Math.abs(v - 0.5) * 2).toFixed(2)}, s);
        el("text", {x: X + cs / 2, y: Y + cs / 2 + 4, "text-anchor": "middle", "class": "num"}, s, pct(v));
        var hit = el("rect", {x: X, y: Y, width: cs - 2, height: cs - 2, style: "fill:transparent"}, s);
        hover(hit, "<b>宽度 " + wa + " 对 宽度 " + wb + "</b><br>行方平均得分 " + pct(v) + "（3×3 个模型对）");
      });
    });
    el("text", {x: M0, y: M0 + n * cs + 22, "class": "lab"}, s, "行 = 网络宽度，列 = 对手宽度（深度都是 2，人类条件）");
  }
  var WCOL = ["#5b8def", "#4fb3d9", "#3cc4a0", "#8bd35a", "#e3c13b", "#f08a3c", "#e8505b"];
  function exploiters() {
    var S = D.scaling; if (!S || !S.exploiters_2M) return;
    var ks = Object.keys(S.exploiters_2M).filter(function (k) { return S.exploiters_2M[k].curve && S.exploiters_2M[k].curve.length; })
      .sort(function (a, b) { return +a.split("_")[0].slice(1) - +b.split("_")[0].slice(1); });
    if (!ks.length) return;
    var W = 820, H = 300, X0 = 64, X1 = W - 70, Y0 = 14, Y1 = H - 52, s = svg($("ch-exp"), W, H);
    var x = scale(0, 2e6, X0, X1), y = scale(0, 1, Y1, Y0);
    frame(s, X0, X1, Y0, Y1, x, y, [0, 5e5, 1e6, 1.5e6, 2e6], [0, 0.25, 0.5, 0.75, 1], "利用者训练步数", "利用者对目标的胜率",
      function (t) { return (t / 1e6) + "M"; }, pct);
    el("line", {x1: X0, x2: X1, y1: y(0.5), y2: y(0.5), style: "stroke:var(--ink-2);stroke-dasharray:5 4"}, s);
    el("text", {x: X1 - 4, y: y(0.5) + 16, "text-anchor": "end"}, s, "虚线以上 = 针对成功");
    var widths = [8, 16, 32, 64, 128, 256, 512], labs = [];
    ks.forEach(function (k) {
      var e = S.exploiters_2M[k], w = +k.split("_")[0].slice(1), col = WCOL[Math.max(0, widths.indexOf(w))];
      el("path", {d: e.curve.map(function (p, i) { return (i ? "L" : "M") + x(p[0]) + "," + y(p[1]); }).join(""), style: "fill:none;stroke:" + col + ";stroke-width:2.2"}, s);
      e.curve.forEach(function (p) {
        var c = el("circle", {cx: x(p[0]), cy: y(p[1]), r: 3.5, style: "fill:" + col}, s);
        hover(c, "<b>目标 " + w + "×2（seed0）</b><br>利用者训练 " + (p[0] / 1e6).toFixed(2) + "M 步：胜率 " + pct(p[1]));
      });
      var last = e.curve[e.curve.length - 1];
      labs.push([y(last[1]) + 4, col, w + "×2"]);
    });
    labs.sort(function (a, b) { return a[0] - b[0]; });   // 末端标签按高度排开，避免重叠
    var prev = -1e9;
    labs.forEach(function (l) { var yy = Math.max(l[0], prev + 13); prev = yy; el("text", {x: X1 + 6, y: yy, style: "fill:" + l[1]}, s, l[2]); });
  }
  function computeCtrl() {
    var S = D.scaling; if (!S) return;
    var W = 560, H = 300, X0 = 64, X1 = W - 24, Y0 = 14, Y1 = H - 52, s = svg($("ch-compute"), W, H);
    var ks = ["2", "4", "8", "16"].filter(function (k) { return S.compute_control_w64[k] && S.compute_control_w64[k].elo; });
    if (!ks.length) return;
    var all = []; ks.forEach(function (k) { all = all.concat(S.compute_control_w64[k].elo.values); });
    var lo = Math.min.apply(null, all), hi = Math.max.apply(null, all), pad = (hi - lo) * 0.12 + 20;
    var x = scale(2, 16, X0 + 20, X1 - 20, true), y = scale(lo - pad, hi + pad, Y1, Y0);
    [["128", "var(--ink-2)"], ["256", C1]].forEach(function (r) {
      var g = S.width_axis[r[0]]; if (g && g.elo) { all.push(g.elo.mean); }
    });
    lo = Math.min.apply(null, all); hi = Math.max.apply(null, all); pad = (hi - lo) * 0.12 + 20;
    y = scale(lo - pad, hi + pad, Y1, Y0);
    frame(s, X0, X1, Y0, Y1, x, y, [2, 4, 8, 16], niceTicks(lo - pad, hi + pad, 5), "训练步数（64×2，人类条件）", "Elo", function (t) { return t + "M"; });
    [["128", "var(--ink-2)"], ["256", C1]].forEach(function (r) {
      var g = S.width_axis[r[0]]; if (!g || !g.elo) return;
      el("line", {x1: X0, x2: X1, y1: y(g.elo.mean), y2: y(g.elo.mean), style: "stroke:" + r[1] + ";stroke-dasharray:5 4"}, s);
      el("text", {x: X0 + 6, y: y(g.elo.mean) - 5, style: "fill:" + r[1]}, s, r[0] + "×2 · 8M 步");
    });
    el("path", {d: ks.map(function (k, i) { return (i ? "L" : "M") + x(+k) + "," + y(S.compute_control_w64[k].elo.mean); }).join(""), style: "fill:none;stroke:" + C4 + ";stroke-width:2.5"}, s);
    ks.forEach(function (k) {
      var g = S.compute_control_w64[k];
      g.elo.values.forEach(function (v, j) { el("circle", {cx: x(+k) + (j - 1) * 4, cy: y(v), r: 3, style: "fill:" + C4 + ";opacity:.45"}, s); });
      var c = el("circle", {cx: x(+k), cy: y(g.elo.mean), r: 6, style: "fill:" + C4 + ";stroke:var(--bg);stroke-width:2"}, s);
      hover(c, "<b>64×2 训练 " + k + "M 步</b><br>Elo 均值 " + r0(g.elo.mean) + "（种子：" + g.elo.values.map(r0).join(" / ") + "）");
    });
  }
  // ---------------- 敲除与探针 ----------------
  function knockout() {
    var K = D.knockout; if (!K) return;
    var rows = K.rows, W = 820, H = 260, X0 = 56, X1 = W - 16, Y0 = 14, Y1 = H - 44, s = svg($("ch-ko"), W, H);
    var drops = rows.map(function (r) { return r.drop; }), lo = Math.min(0, Math.min.apply(null, drops)), hi = Math.max.apply(null, drops);
    var y = scale(lo - 0.01, hi + 0.01, Y1, Y0), bw = (X1 - X0) / rows.length;
    frame(s, X0, X1, Y0, Y1, function (v) { return v; }, y, [], niceTicks(lo - 0.01, hi + 0.01, 5), "神经元（左：隐藏层 1，右：隐藏层 2）", "得分下降", null, pct);
    el("line", {x1: X0, x2: X1, y1: y(0), y2: y(0), style: "stroke:var(--ink-2)"}, s);
    var se = K.drop_distribution.screen_noise_se;
    if (se) {
      el("rect", {x: X0, y: y(1.96 * se), width: X1 - X0, height: y(-1.96 * se) - y(1.96 * se), style: "fill:var(--ink-3);opacity:.12"}, s);
      el("text", {x: X1 - 4, y: y(1.96 * se) - 4, "text-anchor": "end"}, s, "灰带 = 单个神经元筛选的噪声范围（±1.96 SE）");
    }
    var keyset = {};
    ((K.key && K.key.members) || []).forEach(function (m) { keyset[m.layer + "_" + m.neuron] = true; });
    rows.forEach(function (r, i) {
      var isKey = keyset[r.layer + "_" + r.neuron];
      var b = el("rect", {x: X0 + i * bw + 0.5, y: Math.min(y(0), y(r.drop)), width: Math.max(1, bw - 1), height: Math.max(0.5, Math.abs(y(r.drop) - y(0))),
        style: "fill:" + (isKey ? "var(--gold)" : r.layer === 0 ? C1 : C2)}, s);
      hover(b, "<b>隐藏层 " + (r.layer + 1) + " · #" + r.neuron + "</b><br>单独敲掉：得分下降 " + pct(r.drop) + "<br>梯度重要度 " + r.importance.toFixed(3) + (isKey ? "<br>属于关键神经元组" : ""));
    });
    // 剂量-反应
    var Dd = K.dose;
    if (Dd) {
      var W2 = 560, H2 = 300, A0 = 64, A1 = W2 - 20, B0 = 14, B1 = H2 - 52, s2 = svg($("ch-dose"), W2, H2);
      var all = Dd.importance.concat(Dd.screen, Dd.random_mean); Dd.random_each.forEach(function (e) { all = all.concat(e); });
      var ylo = Math.min(0, Math.min.apply(null, all)) - 0.02, yhi = Math.max.apply(null, all) + 0.03;
      var xx = scale(4, 32, A0 + 20, A1 - 20, true), yy = scale(ylo, yhi, B1, B0);
      frame(s2, A0, A1, B0, B1, xx, yy, Dd.k, niceTicks(ylo, yhi, 5), "一起敲掉的神经元个数（共 " + rows.length + " 个）", "得分下降", null, pct);
      [["importance", C1, "按梯度重要度挑"], ["screen", C2, "按单个敲除筛选挑"], ["random_mean", "var(--ink-3)", "随机挑（3 次平均）"]].forEach(function (sr) {
        el("path", {d: Dd.k.map(function (k, i) { return (i ? "L" : "M") + xx(k) + "," + yy(Dd[sr[0]][i]); }).join(""),
          style: "fill:none;stroke:" + sr[1] + ";stroke-width:2.2" + (sr[0] === "random_mean" ? ";stroke-dasharray:6 4" : "")}, s2);
        Dd.k.forEach(function (k, i) {
          var c = el("circle", {cx: xx(k), cy: yy(Dd[sr[0]][i]), r: 4.5, style: "fill:" + sr[1]}, s2);
          hover(c, "<b>" + sr[2] + "，一起敲掉 " + k + " 个</b><br>得分下降 " + pct(Dd[sr[0]][i]) + (sr[0] === "random_mean" ? "<br>3 次：" + Dd.random_each[i].map(pct).join(" / ") : ""));
        });
      });
      Dd.k.forEach(function (k, i) { Dd.random_each[i].forEach(function (v) { el("circle", {cx: xx(k), cy: yy(v), r: 2, style: "fill:var(--ink-3)"}, s2); }); });
    }
    // 关键神经元表
    var byId = {}; rows.forEach(function (r) { byId[r.layer + "_" + r.neuron] = r; });
    var impRank = rows.slice().sort(function (a, b) { return b.importance - a.importance; }).map(function (r) { return r.layer + "_" + r.neuron; });
    var tb = ((K.key && K.key.members) || []).map(function (m) {
      var id = m.layer + "_" + m.neuron, r = byId[id] || {};
      var cc = (K.concepts[id] || []).map(function (c) { return c[0] + "（r=" + c[1].toFixed(2) + "）"; }).join("；");
      return "<tr><td>层 " + (m.layer + 1) + " · #" + m.neuron + "</td><td class='n'>" + pct(r.drop) + "</td><td class='n'>第 " + (impRank.indexOf(id) + 1) +
        "</td><td>" + (cc || "–") + "</td></tr>";
    }).join("");
    $("ko-table").innerHTML = "<table><thead><tr><th>筛选出的前 8 个</th><th>单独敲掉（筛选）</th><th>重要度排名</th><th>最相关的游戏概念（相关系数）</th></tr></thead><tbody>" + tb + "</tbody></table>";
    // 探针
    var P = K.probes, names = Object.keys(P);
    if (!names.length) return;
    var layers = Object.keys(P[names[0]]);
    var rowH = 26, H3 = names.length * rowH + 60, s3 = svg($("ch-probe"), 820, H3), X0b = 210, X1b = 790;
    var x3 = scale(0.4, 1, X0b, X1b);
    frame(s3, X0b, X1b, 10, H3 - 40, x3, function () { return 0; }, [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1], [], "线性探针平衡准确率（0.5 = 瞎猜）", null, pct);
    var cols = {layer1: C1, layer2: C2, layer3: C3, input_obs: "var(--ink-3)"};
    names.forEach(function (n, i) {
      var yy3 = 14 + i * rowH;
      el("text", {x: X0b - 8, y: yy3 + 14, "text-anchor": "end"}, s3, n);
      layers.forEach(function (l, k) {
        var v = P[n][l].balanced_acc;
        var r = el("rect", {x: X0b, y: yy3 + k * (rowH - 6) / layers.length, width: Math.max(1, x3(Math.max(0.4, v)) - X0b), height: (rowH - 8) / layers.length,
          style: "fill:" + (cols[l] || C4)}, s3);
        hover(r, "<b>" + n + "</b><br>" + (l === "input_obs" ? "直接用 90 维输入" : l.replace("layer", "隐藏层 ")) + "：平衡准确率 " + pct(v) +
          "<br>正例比例 " + pct(P[n][l].pos_rate) + " · 测试集 " + P[n][l].n_test + " 个状态");
      });
    });
    $("lg-probe").innerHTML = layers.map(function (l) { return '<span><i style="background:' + (cols[l] || C4) + '"></i>' + (l === "input_obs" ? "直接用输入（参照）" : l.replace("layer", "隐藏层 ")) + "</span>"; }).join("");
  }
  // ---------------- 旧实验：反应延迟 / APM ----------------
  function delayApm() {
    var E = D.delay; if (!E) return;
    var g = E.elo_by_group, keys = Object.keys(g), W = 820, H = 300, X0 = 64, X1 = W - 20, Y0 = 14, Y1 = H - 52, s = svg($("ch-delay"), W, H);
    var all = []; keys.forEach(function (k) { all = all.concat(g[k].per_seed); });
    var hi = Math.max.apply(null, all), y = scale(0, hi * 1.1, Y1, Y0), bw = (X1 - X0) / keys.length;
    frame(s, X0, X1, Y0, Y1, function () { return 0; }, y, [], niceTicks(0, hi * 1.1, 5), "训练与对战条件（各 3 个种子，6M 步联赛）", "Elo");
    keys.forEach(function (k, i) {
      var cx = X0 + bw * (i + 0.5), col = k.indexOf("APM") >= 0 ? "var(--p2)" : C1;
      el("text", {x: cx, y: Y1 + 18, "text-anchor": "middle"}, s, k);
      el("line", {x1: cx - bw * 0.3, x2: cx + bw * 0.3, y1: y(g[k].mean), y2: y(g[k].mean), style: "stroke:" + col + ";stroke-width:3"}, s);
      g[k].per_seed.forEach(function (v, j) {
        var c = el("circle", {cx: cx + (j - 1) * 14, cy: y(v), r: 5, style: "fill:" + col}, s);
        hover(c, "<b>" + k + " · 种子 " + j + "</b><br>Elo " + r0(v) + "<br>组均值 " + r0(g[k].mean) + " · 实测 APM " + r0(g[k].apm_mean));
      });
    });
  }
  // ---------------- 帧表 ----------------
  function frameMeter() {
    var box = $("ch-frames"); if (!box || !window.FightRL) return;
    var moves = window.FightRL.MOVES, cell = 13, X0 = 96, rowH = 22, maxT = 48;
    var s = svg(box, X0 + maxT * cell + 20, moves.length * rowH + 40);
    for (var f = 0; f <= maxT; f += 6) {
      el("line", {x1: X0 + f * cell, x2: X0 + f * cell, y1: 6, y2: moves.length * rowH + 10, "class": "gr"}, s);
      el("text", {x: X0 + f * cell, y: moves.length * rowH + 26, "text-anchor": "middle"}, s, f + "f");
    }
    var zh = (window.ARENA_SPEC && window.ARENA_SPEC.move_zh) || {};
    moves.forEach(function (m, i) {
      var y = 10 + i * rowH;
      el("text", {x: X0 - 10, y: y + 13, "text-anchor": "end"}, s, zh[m.name] || m.name);
      for (var k = 1; k <= m.total; k++) {
        var c = k <= m.startup ? C3 : (k <= m.startup + m.active ? "var(--p2)" : C1);
        var r = el("rect", {x: X0 + (k - 1) * cell + 1, y: y + 2, width: cell - 2, height: rowH - 6, style: "fill:" + c}, s);
        if (m.invuln[1] && k >= m.invuln[0] && k <= m.invuln[1]) el("rect", {x: X0 + (k - 1) * cell + 1, y: y - 1, width: cell - 2, height: 3, style: "fill:var(--gold)"}, s);
        (function (m, k) {
          hover(r, function () {
            var ph = k <= m.startup ? "发生" : (k <= m.startup + m.active ? "持续（有判定）" : "收招");
            return "<b>" + (zh[m.name] || m.name) + "</b> 第 " + k + " 帧：" + ph + "<br>发生 " + m.startup + " · 持续 " + m.active + " · 收招 " + m.recovery +
              (m.damage ? "<br>伤害 " + m.damage : "") + (m.blockstun ? " · 被防有利 " + (m.blockstun - m.active - m.recovery) + "f" : "");
          });
        })(m, k);
      }
    });
  }
  // ---------------- 早期实验 ----------------
  function early() {
    var E1 = D.exp1, E2 = D.exp2;
    if (E1) {
      var bots = ["random", "greedy", "counter"], cols = [C1, C2, C3], seeds = Object.keys(E1.curves), steps = E1.curves[seeds[0]].step;
      var W = 520, H = 300, X0 = 54, X1 = W - 14, Y0 = 14, Y1 = H - 50, s = svg($("ch-exp1"), W, H);
      var x = scale(0, steps[steps.length - 1], X0, X1), y = scale(0, 1, Y1, Y0);
      frame(s, X0, X1, Y0, Y1, x, y, [0, 500000, 1000000, 1500000, 2000000], [0, 0.25, 0.5, 0.75, 1], "训练步数（打脚本 CPU 池）", "胜率",
        function (t) { return (t / 1e6) + "M"; }, pct);
      bots.forEach(function (b, bi) {
        var mean = steps.map(function (st, i) { var v = 0; seeds.forEach(function (sd) { v += E1.curves[sd][b][i]; }); return v / seeds.length; });
        el("path", {d: steps.map(function (st, i) { return (i ? "L" : "M") + x(st) + "," + y(mean[i]); }).join(""), style: "fill:none;stroke:" + cols[bi] + ";stroke-width:2.2"}, s);
        steps.forEach(function (st, i) {
          var c = el("circle", {cx: x(st), cy: y(mean[i]), r: 6, style: "fill:transparent"}, s);
          hover(c, "<b>" + (st / 1e6).toFixed(2) + "M 步</b><br>" + ["随机", "贪心进攻", "防守反击"][bi] + " CPU：" + pct(mean[i]));
        });
      });
    }
    if (E2) {
      var sn = E2.snapshots, W2 = 520, H2 = 300, A0 = 54, A1 = W2 - 14, B0 = 14, B1 = H2 - 50, s2 = svg($("ch-exp2"), W2, H2);
      var top = Math.ceil(Math.max.apply(null, sn.map(function (q) { return q.ci[1]; })) / 500) * 500;
      var x2 = scale(0, sn[sn.length - 1].step, A0, A1), y2 = scale(0, top, B1, B0), ticks = [];
      for (var t = 0; t <= top; t += 1000) ticks.push(t);
      frame(s2, A0, A1, B0, B1, x2, y2, [0, 2e6, 4e6, 6e6, 8e6, 10e6], ticks, "训练步数（自博弈联赛，0ms、不限 APM）", "Elo", function (t) { return (t / 1e6) + "M"; });
      var band = sn.map(function (q) { return [x2(q.step), y2(q.ci[1])]; }).concat(sn.slice().reverse().map(function (q) { return [x2(q.step), y2(q.ci[0])]; }));
      el("path", {d: band.map(function (p, i) { return (i ? "L" : "M") + p[0] + "," + p[1]; }).join("") + "Z", style: "fill:" + C4 + ";opacity:.18"}, s2);
      el("path", {d: sn.map(function (q, i) { return (i ? "L" : "M") + x2(q.step) + "," + y2(q.elo); }).join(""), style: "fill:none;stroke:" + C4 + ";stroke-width:2.2"}, s2);
      sn.forEach(function (q) {
        var c = el("circle", {cx: x2(q.step), cy: y2(q.elo), r: 3.5, style: "fill:" + C4}, s2);
        hover(c, "<b>" + (q.step / 1e6).toFixed(1) + "M 步快照</b><br>Elo " + r0(q.elo) + "（95% CI " + r0(q.ci[0]) + "–" + r0(q.ci[1]) + "）");
      });
      var bv = Object.keys(E2.bots).map(function (k) { return E2.bots[k]; });
      el("rect", {x: A0, y: y2(Math.max.apply(null, bv)), width: A1 - A0, height: Math.max(2, y2(0) - y2(Math.max.apply(null, bv))), style: "fill:var(--ink-3);opacity:.16"}, s2);
      el("text", {x: A1 - 4, y: y2(Math.max.apply(null, bv)) - 5, "text-anchor": "end"}, s2, "脚本 CPU 区间");
    }
    if (E1 && E2) {
      var S1 = E1.summary.by_opponent, S2 = E2.summary;
      setHTML("rp-early-text", "左：只对三种脚本 CPU 训练 2M 步（3 个种子），对防守反击 CPU 的胜率 " + pct(S1.counter.final_score_mean) +
        "，最快 " + Math.round(Math.min.apply(null, S1.counter["steps_to_0.9_per_seed"]) / 1000) + "k 步就到 90%——靠的是钻 CPU 确反逻辑的漏洞（每回合二三十发" + ((window.ARENA_SPEC && ARENA_SPEC.naming && ARENA_SPEC.naming.specials.fireball) || "气功波") + "）。" +
        "右：自博弈联赛 10M 步，快照循环赛 Elo 从 " + r0(S2.elo_first_snapshot) + " 升到 " + r0(S2.elo_final) + "，" + S2.n_triples + " 个快照三元组里克制循环 " +
        S2["intransitive_triples_(>0.55)"] + " 个。胜率贴近 100% 时 Elo 的绝对值不稳定，只看排序。");
    }
  }
  // ---------------- 文字（全部由数据计算，措辞随结果变化） ----------------
  function setHTML(id, h) { var e = $(id); if (e) e.innerHTML = h; }
  function texts() {
    var S = D.scaling, K = D.knockout, E = D.delay;
    if (S) {
      var ws = Object.keys(S.width_axis).filter(function (w) { return S.width_axis[w].elo; }).map(Number).sort(function (a, b) { return a - b; });
      var g = function (w) { return S.width_axis[String(w)]; };
      var best = ws.slice().sort(function (a, b) { return g(b).elo.mean - g(a).elo.mean; })[0];
      var sm = ws[0], bg = ws[ws.length - 1], rho = S.spearman_params_vs_elo_seedlevel;
      var trend = !rho ? "" : (rho.p < 0.05 && rho.rho > 0.3 ? "整体上网络越大越强" : (rho.p < 0.05 && rho.rho < -0.3 ? "整体上网络越大反而越弱" : "参数量和强度之间没有显著的单调关系"));
      setHTML("rp-scaling-text", "宽度从 " + sm + " 到 " + bg + "（策略网络参数 " + g(sm).params_actor.toLocaleString() + " → " + g(bg).params_actor.toLocaleString() +
        "），每个大小 3 个种子，全部在人类条件（200ms 反应延迟 + APM≤600）下用同样的 8M 步自博弈联赛训练，最后所有模型和 4 个脚本 CPU 打一场循环赛。" +
        (rho ? "<b>" + trend + "</b>（种子级 Spearman ρ = " + rho.rho.toFixed(2) + "，p " + (rho.p < 0.001 ? "< 0.001" : "= " + rho.p.toFixed(3)) + "，n = " + rho.n + "）。" : "") +
        "Elo 最高的是宽度 " + best + "（均值 " + r0(g(best).elo.mean) + "），最小的 " + sm + " 是 " + r0(g(sm).elo.mean) + "、最大的 " + bg + " 是 " + r0(g(bg).elo.mean) + "。" +
        (function () {   // 相邻宽度之间最大的一跳
          var jmp = null; for (var i = 1; i < ws.length; i++) { var dlt = g(ws[i]).elo.mean - g(ws[i - 1]).elo.mean; if (!jmp || dlt > jmp[2]) jmp = [ws[i - 1], ws[i], dlt]; }
          return jmp ? "曲线不是平滑上升：" + jmp[0] + " 到 " + jmp[1] + " 之间跳了 " + r0(jmp[2]) + " 分，" + sm + "～" + jmp[0] + " 之间各组的区间大面积重叠。" : "";
        })() +
        (function () {
          var fv = S.head_to_head_free_vs_human, fk = S.free_controls; if (!fv || !fk) return "";
          var fws = Object.keys(fk).filter(function (k) { return fk[k].elo; }).map(Number).sort(function (a, b) { return a - b; });
          if (!fws.length) return "";
          var f0 = fws[0], v = fv["free_w" + f0 + "_vs_human_w" + bg];
          return v == null ? "" : "<b>但人类条件本身的影响比网络大小大得多</b>：不受约束（0ms、不限 APM）的 " + f0 + " 宽网络（参数 " + fk[String(f0)].params_actor.toLocaleString() +
            "）对人类条件下 " + bg + " 宽的网络（参数 " + g(bg).params_actor.toLocaleString() + "）得分 " + pct(v) + "。";
        })());
      setHTML("rp-elo-cap", "BT-Elo 以随机 CPU 为 0；每对模型 " + S.games_per_pair + " 局。小点是单个种子，竖线是种子间 95% 置信区间（t 分布，3 个种子，所以区间很宽）。三角是深度 1/3 的变体，方块虚线是不受人类条件约束的对照组。");
      var hb = S.head_to_head_width["w" + bg + "_vs_w" + sm], hm = S.head_to_head_width["w" + best + "_vs_w" + sm];
      setHTML("rp-h2h-text", "直接对战更直观：宽度 " + bg + " 对宽度 " + sm + " 的平均得分 " + pct(hb) + (best !== bg ? "，最强的宽度 " + best + " 对 " + sm + " 是 " + pct(hm) : "") +
        "。矩阵里每格是 3×3 个模型对的平均。");
      var cc = S.compute_control_w64, ks = ["2", "4", "8", "16"].filter(function (k) { return cc[k] && cc[k].elo; });
      if (ks.length > 1) {
        var cp = S.compute_proxy || {}, c16 = cp["w64_d2_human_16M"], c128 = cp["w128_d2_human"], c256 = cp["w256_d2_human"];
        setHTML("rp-compute-text", "同一个 64×2 网络：" + ks.map(function (k) { return k + "M 步 " + r0(cc[k].elo.mean); }).join("，") + "，每翻一倍步数都在涨。" +
          (c16 && c128 && c256 ? "按「参数量 × 步数」粗算训练算力：64×2 训 16M 步（" + r0(c16.params_x_steps_1e9) + "）和 128×2 训 8M 步（" + r0(c128.params_x_steps_1e9) +
            "）差不多，Elo " + r0(c16.elo_mean) + " 对 " + r0(c128.elo_mean) + "；256×2 训 8M 步用了约 " + (c256.params_x_steps_1e9 / c16.params_x_steps_1e9).toFixed(1) +
            " 倍的算力，Elo " + r0(c256.elo_mean) + "。所以「大网络更强」里有一部分是算力更多，这组对照还分不开两者。" : ""));
      }
      var ex = S.exploiters_2M || {}, ek = Object.keys(ex);
      if (ek.length) {
        var exs = ek.map(function (k) { return [+k.split("_")[0].slice(1), ex[k].final]; }).sort(function (a, b) { return a[0] - b[0]; });
        var fx = S.exploiters_2M_free || {}, f0 = Object.keys(fx).map(function (k) { return fx[k].score_at_step0; }).filter(function (v) { return v != null; });
        setHTML("rp-exp-text", "对每个宽度的 seed0 模型，从零训练一个 2M 步的 PPO 利用者（256×2，和目标一样是 200ms + APM≤600），每 25 万步打 40 局。利用者最终胜率：" +
          exs.map(function (e) { return e[0] + "：" + pct(e[1]); }).join("，") + "。" +
          (function () {
            var hit = exs.filter(function (e) { return e[1] > 0.5; }), miss = exs.filter(function (e) { return e[1] <= 0.5; });
            var big = exs.slice(-2).filter(function (e) { return e[1] > 0.5; });
            return "<b>" + exs.length + " 个目标里 " + hit.length + " 个被打到 50% 以上</b>" + (miss.length ? "（没打穿的：" + miss.map(function (e) { return e[0] + " 宽"; }).join("、") + "）" : "") +
              (big.length ? "，Elo 最高的两档也在内（" + big.map(function (e) { var st = ex["w" + e[0] + "_d2_human"]["first_eval_step_over_0.5"]; return st ? e[0] + " 宽在 " + Math.round(st / 1e4) / 100 + "M 步时就过半" : e[0] + " 宽"; }).join("，") + "）" : "") +
              "。也就是说，循环赛里更强的模型并不更难被针对。只有一个种子、一个利用者，结论要谨慎。";
          })() +
          (f0.length ? "另外做过一组不受约束（0ms、不限 APM）的利用者：还没训练时就对 " + f0.length + " 个目标里的 " + f0.filter(function (v) { return v > 0.5; }).length + " 个胜率过半（最高 " + pct(Math.max.apply(null, f0)) + "）" +
            "，50 万步时对所有大小都是 100%——它测的是条件不对等，不是可利用性，所以不作为结论。" : ""));
      }
      var tiles = [
        ["网络宽度范围", sm + " → " + bg, "参数 " + fmtParams(g(sm).params_actor) + " → " + fmtParams(g(bg).params_actor)],
        ["最强宽度（Elo 均值）", String(best), "Elo " + r0(g(best).elo.mean)],
        ["参数量与 Elo 秩相关", rho ? rho.rho.toFixed(2) : "–", rho ? "p " + (rho.p < 0.001 ? "< 0.001" : "= " + rho.p.toFixed(3)) + "，n = " + rho.n : ""],
        ["大 vs 小直接对战", pct(hb), "宽度 " + bg + " 对 " + sm]
      ];
      if (S.head_to_head_free_vs_human && S.free_controls && S.free_controls["16"]) {
        var fv16 = S.head_to_head_free_vs_human["free_w16_vs_human_w" + bg];
        if (fv16 != null) tiles.push(["无约束小网络 vs 人类条件大网络", pct(fv16), "16 宽（0ms、不限 APM）对 " + bg + " 宽（200ms + APM≤600）"]);
      }
      if (K && K.dose) tiles.push(["敲掉 8 个关键神经元", pct(K.key.group_drop_k8), "随机敲掉 8 个：" + pct(K.dose.random_mean[1])]);
      setHTML("rp-tiles", tiles.map(function (t) { return '<div class="tile"><span class="k">' + t[0] + '</span><span class="v">' + t[1] + '</span><span class="d">' + t[2] + "</span></div>"; }).join(""));
    }
    if (K) {
      var Dd = K.dose || {}, kk = K.key || {}, i8 = (Dd.k || []).indexOf(8), cf = K.confirm || {};
      var reg = (cf.top || []).map(function (t) { return t.drop_confirm; });
      setHTML("rp-ko-text", "对象：" + K.model.replace("_s", "，种子 ").replace("w", "宽度 ").replace("_d2_human", "×2（人类条件）") +
        "，共 " + K.rows.length + " 个隐藏神经元。先逐个「敲掉」（激活置零），每个对 " + K.panel.length + " 个固定对手各打 " + K.games +
        " 局：单个神经元的影响都很小（下降平均 " + pct(K.drop_distribution.mean) + "，最大 " + pct(K.drop_distribution.max) +
        "，噪声标准误约 " + pct(K.drop_distribution.screen_noise_se) + "）。筛选出的前 " + (cf.top || []).length + " 个用 " + cf.games_per_opponent +
        " 局/对手复核，下降缩小到 " + reg.map(pct).join("、") + "——典型的「赢家诅咒」，单个神经元的效应大多落在噪声里。" +
        (i8 >= 0 ? "成组敲掉更说明问题：一起敲掉 8 个时，按梯度重要度挑的下降 <b>" + pct(Dd.importance[i8]) + "</b>，按单个敲除筛选挑的下降 " + pct(Dd.screen[i8]) +
          "，随机挑的平均下降 " + pct(Dd.random_mean[i8]) + "；敲掉 32 个时分别是 " + pct(Dd.importance[3]) + "、" + pct(Dd.screen[3]) + "、" + pct(Dd.random_mean[3]) + "。" : "") +
        "结论：这个网络里<b>没有单个\"关键\"神经元</b>，破坏程度主要取决于敲掉多少个，而不是敲掉哪几个。实验台里标金框的是梯度重要度前 32 的神经元，可以和\"随机敲掉 25%\"对比。");
      setHTML("rp-probe-text", "线性探针：在对局中收集 " + K.n_probe_samples.toLocaleString() + " 个决策时刻的隐藏层激活，用逻辑回归预测游戏概念（70/30 划分，报告平衡准确率）。" +
        "灰色是直接用 90 维输入的参照（概念本身就是从输入定义的，所以接近上限）；隐藏层能达到多少，说明这一层还保留了多少这个信息。相关不代表网络\"用\"了它。");
    }
    if (E) {
      var gg = E.elo_by_group, h = E.head_to_head;
      setHTML("rp-delay-text", "早期实验（2×256 网络）：反应延迟从 0 加到 200ms，同批模型互打看不出削弱（0ms 组对 200ms 组得分 " + pct(h["0ms_vs_200ms"].score) +
        "）；但把每分钟操作数限到 300，Elo 均值从 " + r0(gg["200ms"].mean) + " 掉到 " + r0(gg["200ms+APM300"].mean) + "，不限 APM 的模型实测每分钟操作约 " +
        r0(gg["0ms"].apm_mean) + " 次。所以规模实验统一用「200ms + APM≤600」作为人类条件。");
    }
    setHTML("rp-lede", "这一页汇总三组问题：网络大小对强度和可被针对性的影响、单个神经元的作用、以及把反应时间和手速限制到人类水平之后 AI 还剩多强。所有数字来自仓库 results/*/result.json。");
    var v = "<h3>现在还不能说 RL 必然打得过职业选手</h3><ul>";
    if (S) v += "<li>人类条件下网络越大越强，但主要是 128 → 256 之间的一跳；小网络之间种子差距很大，3 个种子不足以给出精确的规模定律，而且大网络也用了更多算力。</li>";
    if (S && S.head_to_head_free_vs_human && S.head_to_head_free_vs_human.free_w16_vs_human_w512 != null)
      v += "<li>把反应和手速限制到人类水平，比把网络缩小 90 倍影响更大：不受约束的最小网络对人类条件下最大的网络得分 " + pct(S.head_to_head_free_vs_human.free_w16_vs_human_w512) + "。</li>";
    if (E) v += "<li>限制手速（APM）对强度的影响远大于加 200ms 反应延迟；不限 APM 的 AI 每分钟操作上千次，这不是公平比较。</li>";
    var exh = S && S.exploiters_2M ? Object.keys(S.exploiters_2M).map(function (k) { return S.exploiters_2M[k].final; }) : [];
    if (exh.length) v += "<li>同样受人类条件约束的利用者，2M 步就把 " + exh.length + " 个目标里的 " + exh.filter(function (x) { return x > 0.5; }).length + " 个打到 50% 以上，包括最强的两档。循环赛强不等于打不穿。</li>";
    else if (D.exploit_old) v += "<li>专门训练的利用者能打穿一部分模型（早期实验 12 个目标里 " + D.exploit_old.n_exploited + " 个被打到 50% 以上）。</li>";
    v += "<li>我们没有真实游戏的数据，也没有任何真人对局记录。要回答这个问题，需要在真实游戏里、用人类级反应和 APM，对高手盲测，并且利用者打不穿。</li></ul>";
    setHTML("rp-verdict", v);
    setHTML("rp-method", "环境：自带的 60 帧 2D 格斗小街机（单角色镜像对战，帧数据驱动），JS 版与 Python 版逐帧一致。训练：CleanRL 风格 PPO，tanh MLP（actor/critic 分离），自博弈联赛（历史快照池按胜率加权 + 25% 脚本 CPU），每 4 帧决策一次。" +
      "人类条件：观测延迟 12 帧（200ms）+ APM 令牌桶（每分钟 600 次操作，容量 4）。评估：全体循环赛，Bradley–Terry 拟合 Elo（随机 CPU 锚定为 0）。局限：单角色简化游戏；每个配置 3 个种子；利用者只做了 seed0；探针和归因只说明相关性；APM 上限没有真人基准。");
    var M = D.media;
    if (M) setHTML("rp-media", Object.keys(M).map(function (k) {
      var m = M[k];
      return "<figure><video src=\"assets/media/" + m.mp4 + "\" controls muted loop playsinline preload=\"metadata\" poster=\"assets/media/" + m.png.replace(/\.png$/, ".jpg") + "\"></video><figcaption class=\"cap\"><b>" + m.title + "</b>：" + m.desc + "</figcaption></figure>";
    }).join(""));
  }
  window.ARENA_REPORT_RENDER = function () {
    [frameMeter, early, eloVsParams, vsScripted, h2hMatrix, exploiters, computeCtrl, knockout, delayApm, texts].forEach(function (fn) {
      try { fn(); } catch (e) { console.error(e); }
    });
  };
})();
