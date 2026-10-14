/* 大脑面板：把一个 BrainPlayer 的真实网络画出来。
 * 输入层：90 维观测按语义分组、真实特征名、数值条（AI 看到的值；开启延迟时另标出"此刻真实值"）、归因条；
 * 隐藏层：按激活着色，宽层只展开对当前决策最重要的 K 个并附全层热力方阵；
 * 连线：只画贡献（激活 × 权重）最大的若干条；
 * 输出层：31 个动作的概率条（中文名，高亮实际选择）、价值头"局势评估"仪表与本回合价值曲线。
 * 点神经元 = 敲掉（激活置零），再点 = 恢复。 */
(function () {
  "use strict";
  var COL = {bg: "#0f1220", panel: "#151a2c", text: "#d9ddf2", muted: "#8a90ab", faint: "#2a3047", pos: "#ffb547", neg: "#4aa3ff",
    zero: "#2a2d3a", chosen: "#ffd23f", cut: "#ff5a6a", real: "#ffffff"};
  var FONT = "'Noto Sans SC', 'Microsoft YaHei', 'PingFang SC', sans-serif", MONO = "'JetBrains Mono', Consolas, monospace";

  function mix(a, b, t) {
    var pa = [parseInt(a.substr(1, 2), 16), parseInt(a.substr(3, 2), 16), parseInt(a.substr(5, 2), 16)];
    var pb = [parseInt(b.substr(1, 2), 16), parseInt(b.substr(3, 2), 16), parseInt(b.substr(5, 2), 16)];
    return "rgb(" + pa.map(function (v, i) { return Math.round(v + (pb[i] - v) * t); }).join(",") + ")";
  }
  function actColor(v) { return v >= 0 ? mix(COL.zero, COL.pos, Math.min(1, v)) : mix(COL.zero, COL.neg, Math.min(1, -v)); }
  function topIdx(arr, k, keyFn) {
    var idx = []; for (var i = 0; i < arr.length; i++) idx.push(i);
    idx.sort(function (a, b) { return keyFn(arr[b], b) - keyFn(arr[a], a); });
    return idx.slice(0, k);
  }
  function fmt(v, n) { return (v >= 0 ? "+" : "") + v.toFixed(n === undefined ? 2 : n); }

  function BrainView(canvas, spec, opts) {
    this.cv = canvas; this.c = canvas.getContext("2d"); this.spec = spec;
    this.opts = opts || {edges: true, attribution: true, ig: false};
    this.player = null; this.title = ""; this.color = "#ffffff";
    this.hit = []; this.hover = null; this.lastDecision = -1; this.ex = null; this.onChange = null;
    this.mode = "full"; this.onSelect = null; this.label = "";
    var self = this;
    canvas.addEventListener("mousemove", function (e) { var p = self._pos(e); self.hover = self._hitTest(p.x, p.y); self.mouse = p; });
    canvas.addEventListener("mouseleave", function () { self.hover = null; });
    canvas.addEventListener("click", function (e) {
      if (self.mode === "compact") { if (self.onSelect) self.onSelect(self.side); return; }
      var p = self._pos(e), h = self._hitTest(p.x, p.y);
      if (h && h.kind === "neuron" && self.player) {
        var m = self.player.masks[h.layer]; m[h.j] = m[h.j] === 0 ? 1 : 0;
        self._recompute(true);
        if (self.onChange) self.onChange();
      }
    });
  }
  BrainView.prototype._pos = function (e) {
    var r = this.cv.getBoundingClientRect();
    return {x: (e.clientX - r.left) * (this.cssW / r.width), y: (e.clientY - r.top) * (this.cssH / r.height)};
  };
  BrainView.prototype._hitTest = function (x, y) {
    for (var i = this.hit.length - 1; i >= 0; i--) {
      var h = this.hit[i];
      if (x >= h.x0 && x <= h.x1 && y >= h.y0 && y <= h.y1) return h;
    }
    return null;
  };
  // 把独热组（状态 13 维、招式 11 维）合并成一行，其余每维一行
  BrainView.prototype._rows = function (feats) {
    if (this._rowsCache) return this._rowsCache;
    var rows = [], cur = null;
    feats.forEach(function (f, k) {
      var m = /^(me|op)\.(state|move)\./.exec(f.key);
      if (m) {
        var gk = m[1] + "." + m[2];
        if (!cur || cur.gk !== gk) {
          cur = {onehot: true, gk: gk, ks: [], label: (m[1] === "me" ? "自身" : "对手") + (m[2] === "state" ? "状态" : "招式")};
          rows.push(cur);
        }
        cur.ks.push(k);
      } else { cur = null; rows.push({onehot: false, ks: [k]}); }
    });
    // 按分组顺序稳定排序，每组只出现一次表头
    var order = this.spec.groups;
    rows.forEach(function (r, n) { r.n = n; r.g = order.indexOf(feats[r.ks[0]].group); });
    rows.sort(function (a, b) { return a.g - b.g || a.n - b.n; });
    this._rowsCache = rows;
    return rows;
  };
  // 敲除实验找出的"关键神经元"（金框）
  BrainView.prototype._keySet = function (layer) {
    var P = this.player, out = {};
    var kn = P && P.net && P.net.spec && P.net.spec.key_neurons;
    if (kn) kn.forEach(function (k) { if (k[0] === layer) out[k[1]] = k; });
    return out;
  };
  // 网络结构式：输入 214 → 隐藏 512 → 隐藏 512 → 输出 31 个动作 + 1 个局势评估
  BrainView.prototype.structure = function () {
    var net = this.player && this.player.net; if (!net) return "";
    var nIn = net.actor.layers[0].nIn;
    return "输入 " + nIn + " → " + net.widths.map(function (w) { return "隐藏 " + w; }).join(" → ") +
      " → 输出 " + net.nActions + " 个动作 + 1 个局势评估";
  };
  BrainView.prototype.setPlayer = function (player, title, color) {
    this.player = player; this.title = title; this.color = color || "#ffffff"; this.lastDecision = -1; this.ex = null;
  };
  BrainView.prototype.resize = function () {
    var dpr = window.devicePixelRatio || 1, r = this.cv.getBoundingClientRect();
    this.cssW = Math.max(320, Math.round(r.width)); this.cssH = Math.max(260, Math.round(r.height));
    this.cv.width = this.cssW * dpr; this.cv.height = this.cssH * dpr; this.dpr = dpr;
  };
  BrainView.prototype._recompute = function (force) {
    var P = this.player; if (!P || !P.last) return;
    if (!force && P.last.decision === this.lastDecision) return;
    this.lastDecision = P.last.decision;
    var masks = P.anyMasked() ? P.masks : null;
    this.ex = P.net.explain(P.last.obs, P.last.action, masks, {ig: !!this.opts.ig});
  };
  BrainView.prototype.draw = function (core, idx) {
    var c = this.c, W = this.cssW, H = this.cssH;
    if (!W) { this.resize(); W = this.cssW; H = this.cssH; }
    c.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    c.fillStyle = COL.bg; c.fillRect(0, 0, W, H);
    this.hit = [];
    var P = this.player;
    if (!P || !P.last) {
      c.fillStyle = COL.muted; c.font = "14px " + FONT;
      c.fillText(P ? "等待第一次决策…" : "这一侧是人类玩家，没有网络可显示。", 20, 40);
      return;
    }
    if (this.mode === "compact") { this._recompute(false); this.drawCompact(core, idx); return; }
    this._recompute(false);
    var ex = this.ex, last = P.last, net = P.net, spec = this.spec, fw = ex.fw;
    var nObs = spec.obs_dim, real = core ? core.observe(idx, P.visibleOnly) : null;
    var delayed = P.d > 0;
    // ---- 标题 ----
    c.fillStyle = this.color; c.font = "bold 15px " + FONT;
    c.fillText(this.title, 12, 20);
    c.fillStyle = COL.text; c.font = "bold 12px " + FONT;
    c.fillText("结构：" + this.structure() + " · 参数 " + net.nParams.toLocaleString(), 12, 38, W - 24);
    c.fillStyle = COL.muted; c.font = "11px " + FONT;
    var sub = "第 " + last.decision + " 次决策 · 每 " + P.k + " 帧决策一次";
    if (delayed) sub += " · 输入来自 " + (last.nowFrame - last.seenFrame) + " 帧（" + Math.round((last.nowFrame - last.seenFrame) * 1000 / 60) + "ms）前";
    if (P.apmRate) sub += " · APM≤" + Math.round(P.apmRate * 60 * 60);
    c.fillText(sub, 12, 54, W - 262);
    // 颜色图例
    var lx = W - 238, ly = 52;
    c.font = "10px " + FONT;
    [[COL.pos, "正激活 / 正贡献"], [COL.neg, "负激活 / 负贡献"], [COL.chosen, "实际选择"]].forEach(function (it, n) {
      c.fillStyle = it[0]; c.fillRect(lx + n * 82, ly - 7, 8, 8);
      c.fillStyle = COL.muted; c.fillText(it[1], lx + 11 + n * 82, ly);
    });
    var nCut = 0; P.masks.forEach(function (m) { for (var i = 0; i < m.length; i++) if (m[i] === 0) nCut++; });
    if (nCut) { c.fillStyle = COL.cut; c.font = "bold 11px " + FONT; c.fillText("已敲掉 " + nCut + " 个神经元", W - 120, 20); }
    var top = 72, footH = delayed ? 74 : 56, bottom = H - footH;
    // ---- 列布局 ----
    var xInR = Math.round(W * 0.37), xOutL = Math.round(W * 0.72);
    var L = net.widths.length, hx = [];
    for (var l = 0; l < L; l++) hx.push(xInR + 70 + (xOutL - xInR - 140) * (L === 1 ? 0.5 : l / (L - 1)));
    // ---- 输入层 ----
    var attr = ex.attr, maxA = 1e-9, i;
    for (i = 0; i < attr.length; i++) maxA = Math.max(maxA, Math.abs(attr[i]));
    var histAttr = 0; for (i = nObs; i < attr.length; i++) histAttr += attr[i];
    var feats = spec.features, rowsAll = this._rows(feats);
    var rowAttr = function (r) { var s2 = 0; r.ks.forEach(function (k) { s2 += attr[k]; }); return s2; };
    var rowVal = function (r) { var s2 = 0; r.ks.forEach(function (k) { s2 += Math.abs(last.obs[k]); }); return s2; };
    var nGroups = spec.groups.length, rowsAvail = bottom - top - 36 - 34;
    var full = rowsAvail / (rowsAll.length + nGroups) >= 11 && !this.opts.compact;
    var rows;
    if (full) rows = rowsAll;
    else {
      var nShow = Math.max(6, Math.floor(rowsAvail / 15) - 1);
      var keyf = this.opts.attribution ? function (r) { return Math.abs(rowAttr(r)); } : rowVal;
      rows = rowsAll.slice().sort(function (r1, r2) { return keyf(r2) - keyf(r1); }).slice(0, nShow)
        .sort(function (r1, r2) { return r1.g - r2.g || r1.n - r2.n; });
    }
    var rowH = full ? rowsAvail / (rows.length + nGroups) : Math.min(16, rowsAvail / (rows.length + 1));
    var fs = Math.max(8.5, Math.min(12, rowH - 2));
    var nShownFeat = 0; rows.forEach(function (r) { nShownFeat += r.ks.length; });
    var nIn = net.actor.layers[0].nIn, nHistDim = nIn - nObs;
    c.fillStyle = COL.text; c.font = "bold 11px " + FONT;
    c.fillText("输入 " + nIn + " 维 = 游戏状态 " + nObs + " + 最近 " + P.nHist + " 次动作 " + nHistDim, 12, top + 2, xInR + 40);
    c.fillStyle = COL.muted; c.font = "10.5px " + FONT;
    c.fillText(full ? "独热组（状态、招式、最近动作）各合并成一行显示" :
      "只列影响最大的 " + rows.length + " 行（" + nShownFeat + "/" + nObs + " 维）；独热组合并成一行", 12, top + 16, xInR + 40);
    var bw = 46, ax = xInR - 30, vx = ax - 22 - bw / 2;
    var y = top + 30, inPos = {}, lastGroup = null, shown = [];
    rows.forEach(function (r) {
      var f0 = feats[r.ks[0]];
      if (full && f0.group !== lastGroup) {
        lastGroup = f0.group;
        c.fillStyle = "#7d89bd"; c.font = "bold " + Math.max(8.5, fs - 0.5) + "px " + FONT;
        c.fillText(f0.group, 12, y + rowH * 0.78); y += rowH;
      }
      var cy = y + rowH / 2, label, hasVal = rowVal(r) > 1e-6;
      if (r.onehot) {
        var act = r.ks.filter(function (k) { return last.obs[k] > 0.5; })[0];
        label = r.label + "：" + (act === undefined ? "—" : feats[act].zh.split("·").pop());
        // 独热条：每个成员一格，亮格 = AI 看到的取值；白框 = 此刻真实取值
        var cw = bw * 2 / r.ks.length, x0 = vx - bw / 2;
        r.ks.forEach(function (k, n) {
          c.fillStyle = last.obs[k] > 0.5 ? "#9fb4ff" : COL.faint;
          c.fillRect(x0 + n * cw, cy - rowH * 0.32, cw - 1, rowH * 0.64);
          if (delayed && real && real[k] > 0.5 && last.obs[k] < 0.5) {
            c.strokeStyle = COL.real; c.lineWidth = 1; c.strokeRect(x0 + n * cw + 0.5, cy - rowH * 0.32 + 0.5, cw - 2, rowH * 0.64 - 1);
          }
          this.hit.push({kind: "input", k: k, x0: x0 + n * cw, x1: x0 + (n + 1) * cw, y0: y, y1: y + rowH});
        }, this);
      } else {
        var k = r.ks[0], v = last.obs[k];
        label = feats[k].zh;
        c.fillStyle = COL.faint; c.fillRect(vx - bw / 2, cy - rowH * 0.3, bw, rowH * 0.6);
        var vv = Math.max(-1, Math.min(1, v));
        c.fillStyle = vv >= 0 ? "#9fb4ff" : "#ff9fb4";
        c.fillRect(vv >= 0 ? vx : vx + vv * bw / 2, cy - rowH * 0.3, Math.abs(vv) * bw / 2, rowH * 0.6);
        if (delayed && real && Math.abs(real[k] - v) > 1e-4) {      // 此刻真实值（AI 还没看到）
          var rv = Math.max(-1, Math.min(1, real[k]));
          c.fillStyle = COL.real; c.fillRect(vx + rv * bw / 2 - 1, cy - rowH * 0.45, 2, rowH * 0.9);
        }
        this.hit.push({kind: "input", k: k, x0: 0, x1: xInR + 4, y0: y, y1: y + rowH});
      }
      c.fillStyle = hasVal ? COL.text : COL.muted; c.font = fs + "px " + FONT;
      if (!full) label = f0.group.replace("帧数据", "").replace("状态", "") + "·" + label;
      c.fillText(label, 12, cy + fs * 0.36, (r.onehot ? vx - bw / 2 : vx - bw / 2) - 18);
      if (this.opts.attribution && !r.onehot) {
        var at = rowAttr(r) / maxA, aw = 30;
        c.fillStyle = COL.faint; c.fillRect(ax - aw / 2, cy - rowH * 0.3, aw, rowH * 0.6);
        c.fillStyle = at >= 0 ? COL.pos : COL.neg;
        c.fillRect(at >= 0 ? ax : ax + at * aw / 2, cy - rowH * 0.3, Math.abs(at) * aw / 2, rowH * 0.6);
      } else if (this.opts.attribution) {
        var at2 = rowAttr(r) / maxA;
        c.fillStyle = at2 >= 0 ? COL.pos : COL.neg; c.font = "9px " + MONO;
        if (Math.abs(at2) > 0.005) c.fillText(fmt(at2, 1), ax + bw * 0 - 14 + 30, cy + 3);
      }
      c.fillStyle = hasVal ? "#c7cdf0" : "#3a4058";
      c.beginPath(); c.arc(xInR, cy, Math.min(3, rowH * 0.3), 0, Math.PI * 2); c.fill();
      r.ks.forEach(function (k) { inPos[k] = cy; shown.push(k); });
      y += rowH;
    }, this);
    // 动作历史块（自己最近按过什么）
    var hy = Math.min(bottom - 18, y + 8);
    var names = P.hist.map(function (a) { return spec.actions[a]; });
    c.fillStyle = "#6f7aa8"; c.font = "bold 10px " + FONT; c.fillText("自己最近 " + P.nHist + " 次动作（" + nHistDim + " 维独热，合并成一个节点）", 12, hy, xInR - 20);
    c.fillStyle = COL.muted; c.font = "10px " + FONT; c.fillText(names.join(" → ") || "—", 12, hy + 13, xInR - 30);
    var histY = hy + 4;
    c.fillStyle = "#c7cdf0"; c.beginPath(); c.arc(xInR, histY, 3, 0, Math.PI * 2); c.fill();
    c.fillStyle = COL.muted; c.font = "10px " + MONO;
    if (this.opts.attribution) c.fillText(fmt(histAttr / maxA, 1), xInR - 36, histY + 3.5);
    c.fillStyle = COL.muted; c.font = "10px " + FONT;
    c.fillText("AI 看到的值", vx - 26, top + 30 - 3);
    if (this.opts.attribution) c.fillText("归因", ax - 10, top + 30 - 3);
    // ---- 隐藏层 ----
    var nodePos = [], colTop = top + 44, heatH = [];
    for (l = 0; l < L; l++) {
      var colW = Math.min(140, (xOutL - xInR - 40) / L);
      var wl = net.widths[l], colH = bottom - colTop;
      // 热力方阵最多占列高的 35%：宽层用更小的格子
      var cs = Math.max(2, Math.min(7, Math.floor(colW / 16), Math.floor(Math.sqrt((colW - 10) * colH * 0.35 / wl))));
      var perRow = Math.max(8, Math.floor((colW - 10) / cs));
      var rows = Math.ceil(wl / perRow);
      heatH.push(rows * cs);
      var colBottom = bottom - rows * cs - 26;
      var maxK = Math.max(4, Math.floor((colBottom - colTop) / 15));
      var K = Math.min(wl, maxK, 32);
      var imp = ex.importance[l];
      var sel = topIdx(Array.prototype.slice.call(imp), K, function (v) { return Math.abs(v); }).sort(function (a, b) { return a - b; });
      var span = colBottom - colTop, pos = {};
      sel.forEach(function (j, n) { pos[j] = colTop + (K === 1 ? span / 2 : span * n / (K - 1)); });
      nodePos.push({sel: sel, pos: pos, x: hx[l], K: K, w: wl});
      c.fillStyle = COL.text; c.font = "bold 11px " + FONT;
      var narrow = L > 1 && (hx[1] - hx[0]) < 130;
      var t1 = narrow ? "隐藏层 " + (l + 1) + "：" + wl + " 个" : "隐藏层 " + (l + 1) + "：" + wl + " 个神经元";
      c.fillText(t1, hx[l] - c.measureText(t1).width / 2, top + 2);
      c.fillStyle = COL.muted; c.font = "10px " + FONT;
      var t2 = K < wl ? (narrow ? "展开贡献最大的 " + K + " 个" : "展开对当前决策贡献最大的 " + K + " 个") : "全部 " + wl + " 个都展开";
      var t2b = K < wl ? "下方方阵是全部 " + wl + " 个" : "下方方阵同样是全部 " + wl + " 个";
      c.fillText(t2, hx[l] - c.measureText(t2).width / 2, top + 16);
      c.fillText(t2b, hx[l] - c.measureText(t2b).width / 2, top + 30);
      // 全层热力方阵
      var gx0 = hx[l] - perRow * cs / 2, gy0 = bottom - rows * cs - 6, h = fw.acts[l], m = P.masks[l];
      var keys = this._keySet(l);
      for (var j = 0; j < wl; j++) {
        var gx = gx0 + (j % perRow) * cs, gy = gy0 + Math.floor(j / perRow) * cs;
        c.fillStyle = m[j] === 0 ? "#40202a" : actColor(h[j]);
        c.fillRect(gx, gy, cs - 1, cs - 1);
        if (keys[j]) { c.strokeStyle = "#ffd23f"; c.lineWidth = 1; c.strokeRect(gx - 0.5, gy - 0.5, cs, cs); }
        this.hit.push({kind: "neuron", layer: l, j: j, x0: gx, x1: gx + cs, y0: gy, y1: gy + cs});
      }
      c.fillStyle = COL.muted; c.font = "9px " + FONT;
      var t3 = "全部 " + wl + " 个";
      c.fillText(t3, hx[l] - c.measureText(t3).width / 2, gy0 - 4);
    }
    // ---- 连线（贡献 = 前一层激活 × 权重） ----
    var actions = spec.actions, nA = net.nActions, outTop = top + 168;
    var oRowH = Math.min(16, (bottom - outTop) / nA), outList = [];
    for (var q = 0; q < nA; q++) outList.push(q);
    if (oRowH < 11) {
      oRowH = 13;
      var nOut = Math.max(4, Math.floor((bottom - outTop) / oRowH));
      outList = outList.sort(function (x1, x2) { return fw.probs[x2] - fw.probs[x1]; }).slice(0, nOut);
      if (outList.indexOf(last.action) < 0) outList[outList.length - 1] = last.action;
      outList.sort(function (x1, x2) { return x1 - x2; });
    }
    var aPos = function (a) { var r = outList.indexOf(a); return outTop + (r < 0 ? 0 : r) * oRowH + oRowH / 2; };
    if (this.opts.edges) {
      var edges = [];
      var first = nodePos[0], W0 = net.actor.layers[0];
      shown.forEach(function (k) {
        var xk = last.obs[k]; if (xk === 0) return;
        first.sel.forEach(function (j) { edges.push([xInR, inPos[k], first.x, first.pos[j], xk * W0.W[k * W0.nOut + j]]); });
      });
      // 动作历史聚合成一个节点
      first.sel.forEach(function (j) {
        var s = 0; for (var q = nObs; q < last.obs.length; q++) if (last.obs[q]) s += last.obs[q] * W0.W[q * W0.nOut + j];
        if (s) edges.push([xInR, histY, first.x, first.pos[j], s]);
      });
      edges = keepTop(edges, 70);
      for (l = 1; l < L; l++) {
        var A = nodePos[l - 1], B = nodePos[l], WL = net.actor.layers[l], hp = fw.acts[l - 1], e2 = [];
        A.sel.forEach(function (i2) { B.sel.forEach(function (j2) { e2.push([A.x, A.pos[i2], B.x, B.pos[j2], hp[i2] * WL.W[i2 * WL.nOut + j2]]); }); });
        edges = edges.concat(keepTop(e2, 60));
      }
      var Lst = nodePos[L - 1], WO = net.actor.out, hl = fw.acts[L - 1], e3 = [];
      Lst.sel.forEach(function (i3) { e3.push([Lst.x, Lst.pos[i3], xOutL - 4, aPos(last.action), hl[i3] * WO.W[i3 * WO.nOut + last.action]]); });
      edges = edges.concat(keepTop(e3, 24));
      var mx = 1e-9; edges.forEach(function (e) { mx = Math.max(mx, Math.abs(e[4])); });
      edges.forEach(function (e) {
        var t = Math.abs(e[4]) / mx;
        c.strokeStyle = e[4] >= 0 ? "rgba(255,181,71," + (0.08 + 0.7 * t) + ")" : "rgba(74,163,255," + (0.08 + 0.7 * t) + ")";
        c.lineWidth = 0.4 + 2.2 * t;
        c.beginPath(); c.moveTo(e[0], e[1]);
        var mxp = (e[0] + e[2]) / 2; c.bezierCurveTo(mxp, e[1], mxp, e[3], e[2], e[3]); c.stroke();
      });
    }
    // 神经元节点
    nodePos.forEach(function (np, l2) {
      var h = fw.acts[l2], m = P.masks[l2], impl = ex.importance[l2], mxI = 1e-9;
      np.sel.forEach(function (j) { mxI = Math.max(mxI, Math.abs(impl[j])); });
      var r = Math.max(3, Math.min(7, (np.K > 1 ? (np.pos[np.sel[1]] - np.pos[np.sel[0]]) : 14) * 0.38));
      np.sel.forEach(function (j) {
        var x = np.x, yy = np.pos[j];
        c.fillStyle = m[j] === 0 ? "#40202a" : actColor(h[j]);
        c.beginPath(); c.arc(x, yy, r, 0, Math.PI * 2); c.fill();
        c.strokeStyle = Math.abs(impl[j]) / mxI > 0.6 ? "#ffffff" : "#4a5070"; c.lineWidth = 1; c.stroke();
        if (this._keySet(l2)[j]) { c.strokeStyle = "#ffd23f"; c.lineWidth = 2; c.beginPath(); c.arc(x, yy, r + 3, 0, Math.PI * 2); c.stroke(); }
        if (m[j] === 0) {
          c.strokeStyle = COL.cut; c.lineWidth = 1.8;
          c.beginPath(); c.moveTo(x - r, yy - r); c.lineTo(x + r, yy + r); c.moveTo(x + r, yy - r); c.lineTo(x - r, yy + r); c.stroke();
        }
        this.hit.push({kind: "neuron", layer: l2, j: j, x0: x - r - 2, x1: x + r + 2, y0: yy - r - 2, y1: yy + r + 2});
      }, this);
    }, this);
    // ---- 输出层 ----
    // 价值仪表
    c.fillStyle = COL.text; c.font = "bold 11px " + FONT;
    c.fillText("输出 " + nA + " 个动作 + 1 个局势评估", xOutL + 4, top + 2, W - xOutL - 8);
    var gx = (xOutL + W) / 2, gy = top + 58, gr = 30, val = Math.max(-1, Math.min(1, last.value));
    c.lineWidth = 7; c.strokeStyle = COL.faint;
    c.beginPath(); c.arc(gx, gy, gr, Math.PI, 2 * Math.PI); c.stroke();
    c.strokeStyle = val >= 0 ? "#4fd18b" : "#ff6a6a";
    c.beginPath(); c.arc(gx, gy, gr, 1.5 * Math.PI, 1.5 * Math.PI + val * Math.PI / 2, val < 0); c.stroke();
    c.fillStyle = COL.text; c.font = "bold 13px " + MONO; var vt = fmt(last.value);
    c.fillText(vt, gx - c.measureText(vt).width / 2, gy - 6);
    c.fillStyle = COL.muted; c.font = "10px " + FONT;
    var gl = "局势评估（价值头）"; c.fillText(gl, gx - c.measureText(gl).width / 2, gy + 14);
    c.fillText("劣", gx - gr - 16, gy + 4); c.fillText("优", gx + gr + 6, gy + 4);
    // 本回合价值曲线
    var vtz = P.valueTrace, vx0 = xOutL + 6, vw = W - xOutL - 14, vy0 = gy + 26, vh = 40;
    c.strokeStyle = COL.faint; c.lineWidth = 1; c.strokeRect(vx0, vy0, vw, vh);
    c.beginPath(); c.moveTo(vx0, vy0 + vh / 2); c.lineTo(vx0 + vw, vy0 + vh / 2); c.stroke();
    if (vtz.length > 1) {
      var f0 = vtz[0][0], f1 = Math.max(f0 + 1, vtz[vtz.length - 1][0], 600);
      c.strokeStyle = this.color; c.lineWidth = 1.5; c.beginPath();
      vtz.forEach(function (p, n) {
        var xx = vx0 + (p[0] - f0) / (f1 - f0) * vw, yy = vy0 + vh / 2 - Math.max(-1, Math.min(1, p[1])) * vh / 2;
        if (n) c.lineTo(xx, yy); else c.moveTo(xx, yy);
      });
      c.stroke();
    }
    c.fillStyle = COL.muted; c.font = "9px " + FONT; c.fillText("本回合价值曲线", vx0 + 3, vy0 + 10);
    // 动作概率
    var probs = fw.probs, barX = xOutL + Math.min(118, (W - xOutL) * 0.55), barW = W - barX - 34;
    outList.forEach(function (a) {
      var ay = aPos(a), isC = a === last.action;
      if (isC) { c.fillStyle = "rgba(255,210,63,0.16)"; c.fillRect(xOutL, ay - oRowH / 2, W - xOutL - 4, oRowH); }
      c.fillStyle = isC ? COL.chosen : (probs[a] > 0.05 ? COL.text : COL.muted);
      c.font = (isC ? "bold " : "") + Math.max(8, Math.min(11, oRowH - 2)) + "px " + FONT;
      c.fillText((isC ? "▶ " : "") + actions[a], xOutL + 4, ay + 3.5, barX - xOutL - 8);
      c.fillStyle = COL.faint; c.fillRect(barX, ay - oRowH * 0.3, barW, oRowH * 0.6);
      c.fillStyle = isC ? COL.chosen : "#8fa2e8"; c.fillRect(barX, ay - oRowH * 0.3, barW * probs[a], oRowH * 0.6);
      if (probs[a] >= 0.01) { c.fillStyle = COL.muted; c.font = "9px " + MONO; c.fillText(Math.round(probs[a] * 100) + "%", barX + barW + 3, ay + 3); }
    });
    c.fillStyle = COL.muted; c.font = "10px " + FONT;
    c.fillText(outList.length < nA ? "动作概率：列出最高的 " + outList.length + "/" + nA + " 个" : "动作概率：全部 " + nA + " 个", xOutL + 4, outTop - 6);
    // ---- 页脚：归因摘要 ----
    var drivers = topIdx(attr.slice(0, nObs), 4, function (v) { return Math.abs(v); });
    c.fillStyle = COL.panel; c.fillRect(0, bottom + 2, W, footH);
    c.fillStyle = COL.text; c.font = "11px " + FONT;
    var txt = "这次选「" + actions[last.action] + "」（" + Math.round(probs[last.action] * 100) + "%）主要被这些输入推动：" +
      drivers.map(function (k) { return feats[k].zh + " " + fmt(attr[k] / maxA, 1); }).join("，");
    var textW = delayed ? W - 340 : W - 20;
    c.fillText(txt, 10, bottom + 20, textW);
    c.fillStyle = COL.muted; c.font = "10px " + FONT;
    c.fillText("归因方法：" + ex.method + "，对 log π(所选动作) 求导。", 10, bottom + 38, textW);
    c.fillText("这是模型内部的相关性解释（局部线性近似），不是因果结论。点任意神经元可以敲掉它。", 10, bottom + 54, textW);
    if (delayed && real) {   // 并排：AI 此刻看到的（延迟后） vs 此刻真实
      this._mini(last.obs, W - 326, bottom + 8, 156, footH - 14, "AI 看到的（" + Math.round((last.nowFrame - last.seenFrame) * 1000 / 60) + "ms 前）", feats);
      this._mini(real, W - 164, bottom + 8, 156, footH - 14, "此刻真实状态", feats);
    }
    // ---- 悬停提示 ----
    if (this.hover) this._tooltip(this.hover, last, fw, ex, real);
  };
  /* 紧凑但完整的画法：输入按组聚合、每个隐藏层画全层热力方阵、输出只列概率最高的几个动作 + 局势评估。
   * 边框用该玩家的阵营色；点击切到它的单个模式。 */
  BrainView.prototype.drawCompact = function (core, idx) {
    var c = this.c, W = this.cssW, H = this.cssH, P = this.player, ex = this.ex, last = P.last, net = P.net, spec = this.spec, fw = ex.fw;
    var nObs = spec.obs_dim, nIn = net.actor.layers[0].nIn, feats = spec.features;
    c.strokeStyle = this.color; c.lineWidth = 3; c.strokeRect(1.5, 1.5, W - 3, H - 3);
    c.fillStyle = this.color; c.font = "bold 14px " + FONT;
    c.fillText(this.title, 12, 22, W - 150);
    c.fillStyle = COL.muted; c.font = "11px " + FONT;
    var hint = "点击查看完整大脑 ▸"; c.fillText(hint, W - c.measureText(hint).width - 12, 22);
    c.fillStyle = COL.text; c.font = "bold 11.5px " + FONT;
    c.fillText("结构：" + this.structure() + " · 参数 " + net.nParams.toLocaleString(), 12, 40, W - 24);
    var nCut = 0; P.masks.forEach(function (m) { for (var i = 0; i < m.length; i++) if (m[i] === 0) nCut++; });
    if (nCut) { c.fillStyle = COL.cut; c.font = "bold 11px " + FONT; c.fillText("已敲掉 " + nCut + " 个神经元", W - 150, 40); }
    var top = 58, bottom = H - 12, L = net.widths.length;
    var xIn1 = Math.round(W * 0.30), xOut0 = Math.round(W * 0.70);
    // 输入：按组聚合（组内 |值| 的平均 = 活跃度，组内归因之和）
    var attr = ex.attr, maxA = 1e-9, i, k;
    for (i = 0; i < attr.length; i++) maxA = Math.max(maxA, Math.abs(attr[i]));
    var groups = spec.groups.map(function (g) { return {name: g, ks: []}; });
    feats.forEach(function (f, j) { groups[spec.groups.indexOf(f.group)].ks.push(j); });
    var histKs = []; for (k = nObs; k < nIn; k++) histKs.push(k);
    groups.push({name: "最近 " + P.nHist + " 次动作", ks: histKs});
    c.fillStyle = COL.text; c.font = "bold 10.5px " + FONT;
    c.fillText("输入 " + nIn + " 维（按 " + groups.length + " 组聚合）", 12, top + 2, xIn1 - 12);
    var gTop = top + 14, rowH = Math.min(34, (bottom - gTop) / groups.length), maxS = 1e-9;
    groups.forEach(function (g) {
      var a = 0, v = 0; g.ks.forEach(function (j) { a += attr[j]; v += Math.abs(last.obs[j]); });
      g.attr = a; g.act = v / Math.max(1, g.ks.length); g.n = g.ks.length; maxS = Math.max(maxS, Math.abs(a));
    });
    var bw = Math.max(30, (xIn1 - 12) * 0.28), fsz = Math.max(9, Math.min(12, rowH - 8));
    groups.forEach(function (g, n) {
      var cy = gTop + n * rowH + rowH / 2;
      c.fillStyle = COL.text; c.font = fsz + "px " + FONT;
      c.fillText(g.name + "（" + g.n + "）", 12, cy + fsz * 0.35, xIn1 - bw * 2 - 30);
      var bx = xIn1 - bw * 2 - 18;
      c.fillStyle = COL.faint; c.fillRect(bx, cy - rowH * 0.25, bw, rowH * 0.5);
      c.fillStyle = "#9fb4ff"; c.fillRect(bx, cy - rowH * 0.25, bw * Math.min(1, g.act * 3), rowH * 0.5);
      var t = g.attr / maxS, ax = xIn1 - bw / 2 - 10;
      c.fillStyle = COL.faint; c.fillRect(ax - bw / 2, cy - rowH * 0.25, bw, rowH * 0.5);
      c.fillStyle = t >= 0 ? COL.pos : COL.neg;
      c.fillRect(t >= 0 ? ax : ax + t * bw / 2, cy - rowH * 0.25, Math.abs(t) * bw / 2, rowH * 0.5);
      c.fillStyle = "#c7cdf0"; c.beginPath(); c.arc(xIn1 + 4, cy, 2.5, 0, Math.PI * 2); c.fill();
    });
    c.fillStyle = COL.muted; c.font = "9.5px " + FONT;
    c.fillText("活跃度", xIn1 - bw * 2 - 18, gTop - 1); c.fillText("归因", xIn1 - bw - 10, gTop - 1);
    // 隐藏层：全层热力方阵
    var span = xOut0 - xIn1 - 24, colW = span / L;
    for (var l = 0; l < L; l++) {
      var wl = net.widths[l], cx0 = xIn1 + 16 + l * colW, aw = colW - 14, ah = bottom - top - 22;
      var cs = Math.max(2, Math.min(26, Math.floor(Math.sqrt(aw * ah / wl))));   // 小网络的格子不要大得夸张
      while (cs > 2 && Math.ceil(wl / Math.floor(aw / cs)) * cs > ah) cs--;
      var perRow = Math.max(1, Math.floor(aw / cs)), nRows = Math.ceil(wl / perRow);
      var gx0 = cx0 + (aw - perRow * cs) / 2, gy0 = top + 14 + (ah - nRows * cs) / 2, h = fw.acts[l], m = P.masks[l];
      c.fillStyle = COL.text; c.font = "bold 10.5px " + FONT;
      var t1 = "隐藏层 " + (l + 1) + "：" + wl + " 个";
      c.fillText(t1, cx0 + aw / 2 - c.measureText(t1).width / 2, top + 2);
      for (var j = 0; j < wl; j++) {
        c.fillStyle = m[j] === 0 ? "#40202a" : actColor(h[j]);
        c.fillRect(gx0 + (j % perRow) * cs, gy0 + Math.floor(j / perRow) * cs, cs - (cs > 3 ? 1 : 0), cs - (cs > 3 ? 1 : 0));
      }
    }
    // 输出：局势评估 + 概率最高的几个动作
    var ox = xOut0 + 8, ow = W - ox - 12;
    c.fillStyle = COL.text; c.font = "bold 10.5px " + FONT;
    c.fillText("输出 " + net.nActions + " 个动作 + 局势评估", ox, top + 2, ow);
    var val = Math.max(-1, Math.min(1, last.value));
    c.fillStyle = COL.muted; c.font = "10px " + FONT; c.fillText("局势评估", ox, top + 22);
    c.fillStyle = COL.faint; c.fillRect(ox + 56, top + 13, ow - 100, 10);
    c.fillStyle = val >= 0 ? "#4fd18b" : "#ff6a6a";
    var mid = ox + 56 + (ow - 100) / 2; c.fillRect(val >= 0 ? mid : mid + val * (ow - 100) / 2, top + 13, Math.abs(val) * (ow - 100) / 2, 10);
    c.fillStyle = COL.text; c.font = "bold 11px " + MONO; c.fillText(fmt(last.value), ox + ow - 40, top + 22);
    var probs = fw.probs, nTop = Math.max(3, Math.min(8, Math.floor((bottom - top - 44) / 18)));
    var order = topIdx(Array.prototype.slice.call(probs), nTop, function (v) { return v; });
    c.fillStyle = COL.muted; c.font = "10px " + FONT; c.fillText("概率最高的 " + nTop + " 个动作", ox, top + 42);
    var rh = Math.min(20, (bottom - top - 52) / nTop), barX = ox + Math.min(110, ow * 0.5), barW = ow - (barX - ox) - 34;
    order.forEach(function (a, n) {
      var ay = top + 52 + n * rh + rh / 2, isC = a === last.action;
      if (isC) { c.fillStyle = "rgba(255,210,63,0.16)"; c.fillRect(ox - 4, ay - rh / 2, ow + 4, rh); }
      c.fillStyle = isC ? COL.chosen : COL.text; c.font = (isC ? "bold " : "") + Math.min(11, rh - 4) + "px " + FONT;
      c.fillText((isC ? "▶ " : "") + spec.actions[a], ox, ay + 4, barX - ox - 6);
      c.fillStyle = COL.faint; c.fillRect(barX, ay - rh * 0.25, barW, rh * 0.5);
      c.fillStyle = isC ? COL.chosen : "#8fa2e8"; c.fillRect(barX, ay - rh * 0.25, barW * probs[a], rh * 0.5);
      c.fillStyle = COL.muted; c.font = "9px " + MONO; c.fillText(Math.round(probs[a] * 100) + "%", barX + barW + 3, ay + 3);
    });
  };
  // 从观测向量（自己视角、镜像后）画一张小地图：两个角色的位置/高度 + 飞行道具
  BrainView.prototype._mini = function (obs, x0, y0, w, h, label, feats) {
    var c = this.c, ix = this._ix || (this._ix = (function () { var m = {}; feats.forEach(function (f, i) { m[f.key] = i; }); return m; })());
    c.fillStyle = "#0b0e1a"; c.fillRect(x0, y0, w, h);
    c.strokeStyle = COL.faint; c.strokeRect(x0 + 0.5, y0 + 0.5, w - 1, h - 1);
    var gy = y0 + h - 8, X = function (xn) { return x0 + 6 + (xn + 1) / 2 * (w - 12); };
    c.strokeStyle = "#3a4058"; c.beginPath(); c.moveTo(x0 + 4, gy); c.lineTo(x0 + w - 4, gy); c.stroke();
    var me = this.color, op = me === "#7fb0ff" ? "#ff8f87" : "#7fb0ff";
    [["me", me], ["op", op]].forEach(function (s2) {
      var xx = X(obs[ix[s2[0] + ".x"]]), yy = gy - obs[ix[s2[0] + ".y"]] * 100 * (h - 20) / 224 * 1.6;
      var tall = obs[ix[s2[0] + ".holding_down"]] > 0.5 ? 9 : 14;
      c.fillStyle = s2[1]; c.fillRect(xx - 3, yy - tall, 6, tall);
      if (obs[ix[s2[0] + ".proj"]] > 0.5) { c.beginPath(); c.arc(X(obs[ix[s2[0] + ".proj_x"]]), gy - 8, 2.5, 0, Math.PI * 2); c.fill(); }
      if (obs[ix[s2[0] + ".active"]] > 0.5) { c.fillStyle = "#ffffff"; c.fillRect(xx + 3, yy - tall + 2, 5, 2); }
    });
    c.fillStyle = COL.muted; c.font = "9.5px " + FONT; c.fillText(label, x0 + 4, y0 + 11);
  };
  function keepTop(edges, k) {
    edges.sort(function (a, b) { return Math.abs(b[4]) - Math.abs(a[4]); });
    return edges.slice(0, k);
  }
  BrainView.prototype._tooltip = function (h, last, fw, ex, real) {
    var c = this.c, lines = [];
    if (h.kind === "neuron") {
      var m = this.player.masks[h.layer][h.j];
      lines.push("隐藏层 " + (h.layer + 1) + " · 神经元 #" + h.j + (m === 0 ? "（已敲掉）" : ""));
      lines.push("激活 " + fmt(fw.acts[h.layer][h.j]) + " · 对本次决策的贡献 " + fmt(ex.importance[h.layer][h.j], 3));
      var kk = this._keySet(h.layer)[h.j], spec = this.player.net.spec;
      if (kk) lines.push("金框：属于梯度重要度前 " + ((spec.key_info && spec.key_info.k) || "") + " 的神经元");
      var nc = spec.neuron_concepts && spec.neuron_concepts[h.layer + "_" + h.j];
      if (nc && nc.length) lines.push("最相关的游戏概念：" + nc.slice(0, 2).map(function (c) { return c[0] + "（r=" + c[1].toFixed(2) + "）"; }).join("，"));
      lines.push(m === 0 ? "点一下恢复" : "点一下敲掉（激活置零）");
    } else if (h.kind === "input") {
      var f = this.spec.features[h.k];
      lines.push(f.zh + "（" + f.key + "）");
      lines.push("AI 看到的值 " + fmt(last.obs[h.k], 3) + (real && this.player.d > 0 ? " · 此刻真实值 " + fmt(real[h.k], 3) : ""));
      lines.push("归因 " + fmt(ex.attr[h.k], 4));
    }
    c.font = "11px " + FONT;
    var w = 0; lines.forEach(function (s) { w = Math.max(w, c.measureText(s).width); });
    var x = Math.min(this.mouse.x + 12, this.cssW - w - 16), y = Math.min(this.mouse.y + 12, this.cssH - lines.length * 15 - 12);
    c.fillStyle = "rgba(5,6,12,0.92)"; c.fillRect(x, y, w + 12, lines.length * 15 + 8);
    c.fillStyle = "#ffffff"; lines.forEach(function (s, i) { c.fillText(s, x + 6, y + 15 + i * 15); });
  };
  window.ArenaBrainView = BrainView;
})();
