/* 人类输入：键盘（WASD/方向键 + J/K）与手柄（Gamepad API：左摇杆/十字键 + A/X 轻、B/Y 重）。
 * 输出与 Python 版 scripts/play_vs_ai.py 一致的"相对朝向"逐帧输入编号。
 *
 * 简易搓招（新手模式，默认开）：U = 气功波、I = 冲天拳，按住 Shift 放重版本；手柄 LB / RB 同理。
 * 实现方式是把 AI 动作空间里同一个"搓招宏"（↓↘→+攻击 / →↓↘+攻击，4 帧）原样按出来，
 * 不是直接生成招式；所以方向变化和按键照样计入手速，和 AI 的条件一致。 */
(function () {
  "use strict";
  var F = window.FightRL;
  var KEYS = {w: "up", arrowup: "up", s: "down", arrowdown: "down", a: "left", arrowleft: "left", d: "right", arrowright: "right",
    j: "L", z: "L", k: "H", x: "H"};
  var EASY = {u: 0, i: 2};   // F.MACROS 下标：0/1 = 气功波轻/重，2/3 = 冲天拳轻/重
  function Input() {
    this.held = {}; this.pad = {}; this.touch = {}; this.enabled = false; this.padName = null;
    this.easy = true; this.queue = []; this.macroTag = null; this.lastMacro = null; this.padPrev = {};
  }
  Input.prototype.bind = function (target) {
    var self = this;
    function on(e, v) {
      if (!self.enabled) return;
      var tag = (e.target && e.target.tagName) || "";
      if (tag === "SELECT" || tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      var key = (e.key || "").toLowerCase();
      if (v && !e.repeat && EASY[key] !== undefined) {
        if (self.easy) { self.macro(EASY[key] + (e.shiftKey ? 1 : 0)); e.preventDefault(); }
        else if (self.onEasyOff) self.onEasyOff();
        return;
      }
      var k = KEYS[key];
      if (k) { self.held[k] = v; e.preventDefault(); }
    }
    this._h = {
      keydown: function (e) { on(e, true); }, keyup: function (e) { on(e, false); },
      blur: function () { self.held = {}; },
      gamepadconnected: function (e) { self.padName = e.gamepad.id; },
      gamepaddisconnected: function () { self.padName = null; }
    };
    this._target = target;
    target.addEventListener("keydown", this._h.keydown);
    target.addEventListener("keyup", this._h.keyup);
    window.addEventListener("blur", this._h.blur);
    window.addEventListener("gamepadconnected", this._h.gamepadconnected);
    window.addEventListener("gamepaddisconnected", this._h.gamepaddisconnected);
  };
  /* 退出时调用：断开键盘与手柄监听，之后不再轮询手柄 */
  Input.prototype.unbind = function () {
    if (!this._h) return;
    this._target.removeEventListener("keydown", this._h.keydown);
    this._target.removeEventListener("keyup", this._h.keyup);
    window.removeEventListener("blur", this._h.blur);
    window.removeEventListener("gamepadconnected", this._h.gamepadconnected);
    window.removeEventListener("gamepaddisconnected", this._h.gamepaddisconnected);
    this._h = null; this.enabled = false; this.stopped = true; this.queue = []; this.held = {};
  };
  /* 排入一个搓招宏（与 AI 的宏动作完全相同的逐帧输入） */
  Input.prototype.macro = function (idx) {
    if (this.queue.length) return;
    this.queue = F.MACROS[idx].slice();
    this.macroTag = F.MACRO_NAMES[idx];
  };
  Input.prototype.pollPad = function () {
    this.pad = {};
    if (this.stopped) return;
    var gps = navigator.getGamepads ? navigator.getGamepads() : [];
    for (var i = 0; i < gps.length; i++) {
      var g = gps[i]; if (!g) continue;
      var b = function (k) { return g.buttons[k] && g.buttons[k].pressed; };
      var ax = g.axes[0] || 0, ay = g.axes[1] || 0;
      this.pad.left = b(14) || ax < -0.45; this.pad.right = b(15) || ax > 0.45;
      this.pad.up = b(12) || ay < -0.55; this.pad.down = b(13) || ay > 0.55;
      this.pad.L = b(0) || b(2); this.pad.H = b(1) || b(3);
      var lb = b(4), rb = b(5);
      if (this.enabled && this.easy) {
        if (lb && !this.padPrev.lb) this.macro(this.pad.H ? 1 : 0);
        if (rb && !this.padPrev.rb) this.macro(this.pad.H ? 3 : 2);
      }
      this.padPrev = {lb: lb, rb: rb};
      this.padName = g.id;
      break;
    }
  };
  Input.prototype.code = function (facing) {
    this.pollPad();
    this.lastMacro = null;
    if (this.queue.length) {   // 搓招宏优先：逐帧按出 ↓↘→+攻击（相对朝向编码，和 AI 一样）
      var c = this.queue.shift();
      this.lastMacro = this.macroTag;
      return c;
    }
    var k = this.held, p = this.pad, t = this.touch;
    var up = k.up || p.up || t.up, down = k.down || p.down || t.down, left = k.left || p.left || t.left, right = k.right || p.right || t.right;
    var fwd = facing > 0 ? right : left, back = facing > 0 ? left : right;
    if (fwd && back) fwd = back = false;
    var row = up ? 8 : (down ? 2 : 5), d;
    if (fwd) d = {8: 9, 2: 3, 5: 6}[row]; else if (back) d = {8: 7, 2: 1, 5: 4}[row]; else d = row;
    var btn = (k.H || p.H || t.H) ? 2 : ((k.L || p.L || t.L) ? 1 : 0);
    return F.encodeInput(d, btn);
  };
  window.ArenaInput = Input;
})();
