/* 神经网络推理与解释（纯 JS，无依赖）。与 agents/ppo.py 的 ActorCritic（tanh MLP，actor/critic 分离）一致。
 *
 *   var net = new ArenaBrain.Net(spec);          // spec 由 arena/export.py 导出（真实训练权重）
 *   var r = net.forward(obs, masks);              // {acts:[h1..hL], logits, probs}
 *   net.value(obs)                                // critic 输出：局势评估
 *   net.explain(obs, a, masks, {ig: false})       // 归因：梯度×输入（或积分梯度）、各层神经元重要度
 *
 * masks[l][j] = 0 表示第 l 个隐藏层第 j 个神经元被"敲掉"（激活置零），与 Python 的 NumpyPolicy(masks=...) 一致。
 */
(function (root) {
  "use strict";
  var TBL = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/", LUT = {};
  for (var i = 0; i < 64; i++) LUT[TBL.charAt(i)] = i;
  function b64bytes(s) {
    s = s.replace(/=+$/, "");
    var out = new Uint8Array(Math.floor(s.length * 3 / 4)), j = 0, buf = 0, bits = 0;
    for (var k = 0; k < s.length; k++) {
      buf = ((buf << 6) | LUT[s.charAt(k)]) & 0xffffff; bits += 6;
      if (bits >= 8) { bits -= 8; out[j++] = (buf >> bits) & 255; }
    }
    return out.subarray(0, j);
  }
  function halfToFloat(h) {
    var s = (h & 0x8000) ? -1 : 1, e = (h >> 10) & 0x1f, f = h & 0x3ff;
    if (e === 0) return s * Math.pow(2, -14) * (f / 1024);
    if (e === 31) return f ? NaN : s * Infinity;
    return s * Math.pow(2, e - 15) * (1 + f / 1024);
  }
  function decode(x, dtype) {
    if (typeof x !== "string") return new Float32Array(x);
    var by = b64bytes(x);
    if (dtype === "f16") {
      var n = by.length >> 1, out = new Float32Array(n);
      for (var i = 0; i < n; i++) out[i] = halfToFloat(by[2 * i] | (by[2 * i + 1] << 8));
      return out;
    }
    var buf = new ArrayBuffer(by.length); new Uint8Array(buf).set(by);
    return new Float32Array(buf);
  }
  function mlp(spec, dtype) {
    return {
      layers: spec.layers.map(function (L) { return {W: decode(L.W, dtype), b: decode(L.b, dtype), nIn: L["in"], nOut: L.out}; }),
      out: {W: decode(spec.out.W, dtype), b: decode(spec.out.b, dtype), nIn: spec.out["in"], nOut: spec.out.out}
    };
  }
  // y = x·W + b（W 行主序 nIn×nOut）
  function affine(x, L) {
    var nOut = L.nOut, y = new Float64Array(nOut), W = L.W, i, j;
    for (j = 0; j < nOut; j++) y[j] = L.b[j];
    for (i = 0; i < L.nIn; i++) {
      var xi = x[i]; if (xi === 0) continue;
      var r = i * nOut;
      for (j = 0; j < nOut; j++) y[j] += xi * W[r + j];
    }
    return y;
  }
  // g_in = W·g（反向：对输入的梯度）
  function backAffine(g, L) {
    var nIn = L.nIn, nOut = L.nOut, out = new Float64Array(nIn), W = L.W;
    for (var i = 0; i < nIn; i++) {
      var r = i * nOut, s = 0;
      for (var j = 0; j < nOut; j++) s += W[r + j] * g[j];
      out[i] = s;
    }
    return out;
  }
  function softmax(z) {
    var m = -Infinity, i, n = z.length, p = new Float64Array(n), s = 0;
    for (i = 0; i < n; i++) if (z[i] > m) m = z[i];
    for (i = 0; i < n; i++) { p[i] = Math.exp(z[i] - m); s += p[i]; }
    for (i = 0; i < n; i++) p[i] /= s;
    return p;
  }

  function Net(spec) {
    this.spec = spec;
    var dt = spec.dtype || "f32";
    this.actor = mlp(spec.actor, dt);
    this.critic = spec.critic ? mlp(spec.critic, dt) : null;
    this.widths = this.actor.layers.map(function (L) { return L.nOut; });
    this.obsDim = this.actor.layers[0].nIn;
    this.nActions = this.actor.out.nOut;
    this.nParams = 0;
    var self = this;
    [this.actor].concat(this.critic ? [this.critic] : []).forEach(function (M) {
      M.layers.concat([M.out]).forEach(function (L) { self.nParams += L.W.length + L.b.length; });
    });
  }
  Net.prototype.forward = function (obs, masks) {
    var x = obs, acts = [], A = this.actor;
    for (var l = 0; l < A.layers.length; l++) {
      var z = affine(x, A.layers[l]), m = masks && masks[l];
      for (var j = 0; j < z.length; j++) { z[j] = Math.tanh(z[j]); if (m && m[j] === 0) z[j] = 0; }
      acts.push(z); x = z;
    }
    var logits = affine(x, A.out);
    return {acts: acts, logits: logits, probs: softmax(logits)};
  };
  Net.prototype.value = function (obs) {
    if (!this.critic) return 0;
    var x = obs, C = this.critic;
    for (var l = 0; l < C.layers.length; l++) {
      var z = affine(x, C.layers[l]);
      for (var j = 0; j < z.length; j++) z[j] = Math.tanh(z[j]);
      x = z;
    }
    return affine(x, C.out)[0];
  };
  // 目标 = log π(a|obs)；返回对输入的梯度与各层（激活后）的梯度
  Net.prototype.grads = function (obs, a, masks, fw) {
    fw = fw || this.forward(obs, masks);
    var A = this.actor, L = A.layers.length, d = new Float64Array(this.nActions), i;
    for (i = 0; i < d.length; i++) d[i] = (i === a ? 1 : 0) - fw.probs[i];
    var gh = backAffine(d, A.out), gacts = new Array(L);
    for (var l = L - 1; l >= 0; l--) {
      var h = fw.acts[l], m = masks && masks[l], gz = new Float64Array(h.length);
      gacts[l] = gh;
      for (i = 0; i < h.length; i++) gz[i] = (m && m[i] === 0) ? 0 : gh[i] * (1 - h[i] * h[i]);
      gh = backAffine(gz, A.layers[l]);
    }
    return {gInput: gh, gActs: gacts, fw: fw};
  };
  Net.prototype.explain = function (obs, a, masks, opt) {
    opt = opt || {};
    var g = this.grads(obs, a, masks), n = obs.length, attr = new Float64Array(n), i;
    if (opt.ig) {
      var steps = opt.steps || 16, acc = new Float64Array(n), xs = new Float64Array(n);
      for (var s = 1; s <= steps; s++) {
        var al = s / steps;
        for (i = 0; i < n; i++) xs[i] = obs[i] * al;
        var gs = this.grads(xs, a, masks).gInput;
        for (i = 0; i < n; i++) acc[i] += gs[i];
      }
      for (i = 0; i < n; i++) attr[i] = obs[i] * acc[i] / steps;
    } else {
      for (i = 0; i < n; i++) attr[i] = obs[i] * g.gInput[i];
    }
    // 神经元重要度 = 梯度 × 激活（对 log π(a) 的一阶贡献）
    var imp = g.gActs.map(function (gl, l) {
      var h = g.fw.acts[l], o = new Float64Array(h.length);
      for (var j = 0; j < h.length; j++) o[j] = gl[j] * h[j];
      return o;
    });
    return {attr: attr, importance: imp, fw: g.fw, method: opt.ig ? "积分梯度（基线 = 全零观测）" : "梯度 × 输入"};
  };
  // 第 l 个隐藏层（l = -1 表示输入）到下一层第 j 个单元的连线贡献 = 前一层激活 × 权重
  Net.prototype.edgeContrib = function (prev, layerIdx, j) {
    var L = layerIdx < this.actor.layers.length ? this.actor.layers[layerIdx] : this.actor.out;
    var out = new Float64Array(L.nIn), W = L.W, nOut = L.nOut;
    for (var i = 0; i < L.nIn; i++) out[i] = prev[i] * W[i * nOut + j];
    return out;
  };

  // 用 Net 决策的策略玩家（复现 agents/policy_opponent.py 的管线：延迟、跳帧、宏、动作历史、APM）
  function BrainPlayer(net, cfg, opts) {
    opts = opts || {};
    var F = root.FightRL;
    this.F = F; this.net = net; cfg = cfg || {};
    this.k = cfg.frame_skip || 4;
    this.d = Math.round((cfg.delay_ms || 0) * F.C.FPS / 1000);
    this.nHist = cfg.action_history !== undefined ? cfg.action_history : 4;
    this.visibleOnly = !!cfg.visible_only;
    this.apmRate = cfg.apm ? cfg.apm / 60.0 / F.C.FPS : null;
    this.apmBurst = cfg.apm_burst || 4.0;
    this.rand = opts.rand || Math.random;
    this.deterministic = !!opts.deterministic;
    this.masks = net.widths.map(function (w) { var m = new Float32Array(w); m.fill(1); return m; });
    this.last = null;      // 最近一次决策的完整记录（给大脑面板用）
    this.listeners = [];
    this.reset();
  }
  BrainPlayer.prototype.reset = function () {
    this.buf = []; this.hist = []; this.queue = []; this.fresh = true; this.prevIn = 0; this.tokens = this.apmBurst;
    this.valueTrace = []; this.decisions = 0;
  };
  BrainPlayer.prototype.obsVec = function (raw) {
    var out = raw.slice(), na = this.net.nActions;
    for (var i = 0; i < this.nHist; i++)
      for (var j = 0; j < na; j++) out.push(i < this.hist.length && this.hist[i] === j ? 1.0 : 0.0);
    return out;
  };
  BrainPlayer.prototype.anyMasked = function () {
    return this.masks.some(function (m) { for (var i = 0; i < m.length; i++) if (m[i] === 0) return true; return false; });
  };
  BrainPlayer.prototype.act = function (core, idx) {
    var raw = core.observe(idx, this.visibleOnly);
    if (this.fresh) { for (var i = 0; i <= this.d; i++) this.buf.push({obs: raw, frame: core.frame}); this.fresh = false; }
    else { this.buf.push({obs: raw, frame: core.frame}); if (this.buf.length > this.d + 1) this.buf.shift(); }
    if (this.queue.length === 0) {
      var seen = this.buf[0], obs = this.obsVec(seen.obs);
      var fw = this.net.forward(obs, this.anyMasked() ? this.masks : null);
      var a;
      if (this.deterministic) { a = 0; for (var q = 1; q < fw.probs.length; q++) if (fw.probs[q] > fw.probs[a]) a = q; }
      else {
        var u = this.rand(), acc = 0; a = fw.probs.length - 1;
        for (var q2 = 0; q2 < fw.probs.length; q2++) { acc += fw.probs[q2]; if (u < acc) { a = q2; break; } }
      }
      var v = this.net.value(obs);
      this.valueTrace.push([core.frame, v]);
      this.last = {obs: obs, rawSeen: seen.obs, seenFrame: seen.frame, nowFrame: core.frame, fw: fw, action: a,
                   value: v, decision: ++this.decisions};
      this.queue = this.F.expand(a, this.k);
      if (this.nHist > 0) { this.hist.push(a); if (this.hist.length > this.nHist) this.hist.shift(); }
      for (var li = 0; li < this.listeners.length; li++) this.listeners[li](this.last);
    }
    var inp = this.queue.shift();
    if (this.apmRate !== null) {
      this.tokens = Math.min(this.apmBurst, this.tokens + this.apmRate);
      var dp = this.F.decodeInput(this.prevIn), dc = this.F.decodeInput(inp);
      var cost = (dc[0] !== dp[0] ? 1 : 0) + ((dc[1] !== 0 && dc[1] !== dp[1]) ? 1 : 0);
      if (cost > 0) { if (this.tokens >= cost) this.tokens -= cost; else inp = this.prevIn; }
    }
    this.prevIn = inp;
    return inp;
  };

  root.ArenaBrain = {Net: Net, BrainPlayer: BrainPlayer, decode: decode, halfToFloat: halfToFloat};
})(typeof window !== "undefined" ? window : globalThis);
