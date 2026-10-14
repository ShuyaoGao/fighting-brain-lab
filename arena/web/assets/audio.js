/* WebAudio 合成音效（不使用任何外部音频素材）。浏览器要求用户交互后才能出声：第一次点击/按键时 resume。 */
(function () {
  "use strict";
  function Sfx() { this.ctx = null; this.master = null; this.enabled = true; this.noiseBuf = null; }
  Sfx.prototype.ensure = function () {
    if (this.ctx || !this.enabled || this.closed) return this.ctx;
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    try {
      this.ctx = new AC();
      this.master = this.ctx.createGain(); this.master.gain.value = 0.35; this.master.connect(this.ctx.destination);
      var n = this.ctx.sampleRate, buf = this.ctx.createBuffer(1, n, n), d = buf.getChannelData(0);
      for (var i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
      this.noiseBuf = buf;
    } catch (e) { this.ctx = null; }
    return this.ctx;
  };
  Sfx.prototype.resume = function () { if (this.closed) return; var c = this.ensure(); if (c && c.state === "suspended") c.resume(); };
  /* 退出时调用：关闭 AudioContext，之后不再创建 */
  Sfx.prototype.close = function () {
    this.enabled = false; this.closed = true;
    var c = this.ctx; this.ctx = null; this.master = null; this.noiseBuf = null;
    if (c && c.state !== "closed") { try { return c.close(); } catch (e) { /* 忽略 */ } }
    return null;
  };
  Sfx.prototype._env = function (node, t, a, d, peak) {
    node.gain.setValueAtTime(0.0001, t);
    node.gain.exponentialRampToValueAtTime(peak, t + a);
    node.gain.exponentialRampToValueAtTime(0.0001, t + a + d);
  };
  Sfx.prototype._noise = function (t, dur, filterType, freq, q, peak) {
    var c = this.ctx, src = c.createBufferSource(), f = c.createBiquadFilter(), g = c.createGain();
    src.buffer = this.noiseBuf; f.type = filterType; f.frequency.value = freq; f.Q.value = q || 1;
    src.connect(f); f.connect(g); g.connect(this.master);
    this._env(g, t, 0.004, dur, peak); src.start(t); src.stop(t + dur + 0.05);
    return f;
  };
  Sfx.prototype._tone = function (t, type, f0, f1, dur, peak) {
    var c = this.ctx, o = c.createOscillator(), g = c.createGain();
    o.type = type; o.frequency.setValueAtTime(f0, t); o.frequency.exponentialRampToValueAtTime(Math.max(20, f1), t + dur);
    o.connect(g); g.connect(this.master); this._env(g, t, 0.005, dur, peak); o.start(t); o.stop(t + dur + 0.05);
  };
  Sfx.prototype.play = function (fn) {
    if (!this.enabled) return;
    var c = this.ensure(); if (!c || c.state !== "running") return;
    fn.call(this, c.currentTime + 0.005);
  };
  Sfx.prototype.hit = function (heavy) {
    this.play(function (t) {
      this._noise(t, heavy ? 0.16 : 0.08, "lowpass", heavy ? 1800 : 3200, 0.8, heavy ? 0.9 : 0.55);
      this._tone(t, "sine", heavy ? 140 : 220, 50, heavy ? 0.22 : 0.1, heavy ? 0.8 : 0.4);
    });
  };
  Sfx.prototype.block = function () {
    this.play(function (t) { this._noise(t, 0.05, "highpass", 2500, 2, 0.4); this._tone(t, "square", 900, 600, 0.06, 0.12); });
  };
  Sfx.prototype.whoosh = function () { this.play(function (t) { this._noise(t, 0.12, "bandpass", 900, 1.5, 0.18); }); };
  Sfx.prototype.fireball = function () {
    this.play(function (t) { this._tone(t, "sawtooth", 180, 520, 0.25, 0.18); this._noise(t, 0.2, "bandpass", 1400, 3, 0.15); });
  };
  Sfx.prototype.dp = function () { this.play(function (t) { this._tone(t, "square", 260, 900, 0.18, 0.15); }); };
  Sfx.prototype.throwHit = function () { this.play(function (t) { this._tone(t, "triangle", 300, 60, 0.3, 0.6); this._noise(t, 0.2, "lowpass", 900, 1, 0.6); }); };
  Sfx.prototype.ko = function () {
    this.play(function (t) { this._tone(t, "sawtooth", 440, 40, 1.1, 0.35); this._noise(t, 0.6, "lowpass", 600, 0.7, 0.7); });
  };
  Sfx.prototype.beep = function (hi) { this.play(function (t) { this._tone(t, "square", hi ? 1320 : 660, hi ? 1320 : 660, hi ? 0.35 : 0.12, 0.12); }); };
  window.ArenaSfx = Sfx;
})();
