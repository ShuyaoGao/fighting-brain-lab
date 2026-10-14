/* 手机竖屏操控区：左下浮动摇杆（8 个方向 + 中间不动，松手回中）、右下 J / K 大圆键、
 * 新手模式下的「气功」「冲天」技能键与「重」切换键。多点触控：摇杆和按键各自跟踪自己的 pointerId，可同时按。
 * 只写 ArenaInput 的 touch 状态（与触屏方向键同一套），不改游戏规则；技能键复用 AI 动作空间里的搓招宏。 */
(function () {
  "use strict";
  function vibrate(ms) { try { if (navigator.vibrate) navigator.vibrate(ms); } catch (e) { /* 不支持时静默 */ } }

  function TouchCtl(root, input, opts) {
    this.root = root; this.input = input; this.opts = opts || {};
    this.zone = root.querySelector("#stick-zone"); this.base = root.querySelector("#stick-base"); this.knob = root.querySelector("#stick-knob");
    this.stickId = null; this.origin = null; this.dir = 5; this.heavy = false; this.bound = [];
    this.R = 52;   // 摇杆半径（CSS px）
    var self = this;
    function on(el, ev, fn, o) { el.addEventListener(ev, fn, o); self.bound.push([el, ev, fn, o]); }
    // 防误触：长按菜单、双击缩放、文字选中
    on(root, "contextmenu", function (e) { e.preventDefault(); });
    on(root, "touchstart", function (e) { if (e.cancelable) e.preventDefault(); }, {passive: false});
    // 保险：所有手指都离开屏幕时，摇杆回中、按键全部松开（防止个别设备丢失某根手指的抬起事件导致按键"粘住"）
    var allUp = function (e) { if (!e.touches || e.touches.length === 0) self.reset(); };
    on(root, "touchend", allUp); on(root, "touchcancel", allUp);
    on(window, "blur", function () { self.reset(); });
    // ---- 浮动摇杆 ----
    on(this.zone, "pointerdown", function (e) {
      if (self.stickId !== null) return;
      self.stickId = e.pointerId;
      try { self.zone.setPointerCapture(e.pointerId); } catch (err) { /* 合成事件可能没有捕获能力 */ }
      var r = self.zone.getBoundingClientRect();
      self.origin = {x: e.clientX, y: e.clientY};
      self.base.classList.add("live");
      self.base.style.left = (e.clientX - r.left) + "px"; self.base.style.top = (e.clientY - r.top) + "px";
      self.knob.style.transition = "none";
      self._move(e.clientX, e.clientY);
      e.preventDefault();
    });
    on(this.zone, "pointermove", function (e) { if (e.pointerId === self.stickId) { self._move(e.clientX, e.clientY); e.preventDefault(); } });
    var end = function (e) { if (e.pointerId === self.stickId) self._release(); };
    on(this.zone, "pointerup", end); on(this.zone, "pointercancel", end); on(this.zone, "lostpointercapture", end);
    // ---- 按键（每个键独立跟踪按下它的手指） ----
    root.querySelectorAll("[data-tk]").forEach(function (btn) {
      var k = btn.getAttribute("data-tk"), pid = null;
      on(btn, "pointerdown", function (e) {
        e.preventDefault(); pid = e.pointerId;
        try { btn.setPointerCapture(e.pointerId); } catch (err) { /* 忽略 */ }
        btn.classList.add("on"); vibrate(8);
        if (k === "L" || k === "H") self.input.touch[k] = true;
        else if (k === "fb" || k === "dp") { if (self.input.enabled) self.input.macro((k === "fb" ? 0 : 2) + (self.heavy ? 1 : 0)); }
        if (self.opts.onPress) self.opts.onPress(k);
      });
      var up = function (e) {
        if (e.pointerId !== pid) return;
        pid = null; btn.classList.remove("on");
        // 很快的轻点也要被游戏读到：按住状态至少保持约 2 帧再松开
        if (k === "L" || k === "H") setTimeout(function () { if (pid === null) self.input.touch[k] = false; }, 34);
      };
      on(btn, "pointerup", up); on(btn, "pointercancel", up); on(btn, "lostpointercapture", up);
    });
    var tog = root.querySelector("#heavy-tog");
    if (tog) on(tog, "pointerdown", function (e) {
      e.preventDefault(); self.heavy = !self.heavy; tog.classList.toggle("on", self.heavy); tog.setAttribute("aria-pressed", self.heavy); vibrate(5);
    });
  }
  TouchCtl.prototype._move = function (x, y) {
    var dx = x - this.origin.x, dy = y - this.origin.y, d = Math.sqrt(dx * dx + dy * dy), R = this.R;
    var k = d > R ? R / d : 1;
    this.knob.style.transform = "translate(" + (dx * k) + "px," + (dy * k) + "px)";
    var dir = 5;
    if (d > R * 0.35) {   // 死区之外：按角度分成 8 个方向（屏幕坐标，y 向下）
      var a = Math.atan2(-dy, dx) * 180 / Math.PI, s = Math.round(((a + 360) % 360) / 45) % 8;
      dir = [6, 9, 8, 7, 4, 1, 2, 3][s];   // 0°=右 45°=右上 90°=上 …（数字键盘记法，绝对方向）
    }
    this._set(dir);
  };
  // 绝对方向（数字键盘：6 = 屏幕右）→ 输入的四个开关；朝向换算由 ArenaInput.code() 完成
  TouchCtl.prototype._set = function (dir) {
    if (dir !== this.dir && dir !== 5) vibrate(4);
    this.dir = dir;
    var t = this.input.touch;
    t.up = dir === 7 || dir === 8 || dir === 9;
    t.down = dir === 1 || dir === 2 || dir === 3;
    t.left = dir === 1 || dir === 4 || dir === 7;
    t.right = dir === 3 || dir === 6 || dir === 9;
    this.root.setAttribute("data-dir", dir);
  };
  TouchCtl.prototype._release = function () {
    this.stickId = null; this._set(5);
    this.knob.style.transition = "transform .12s ease-out"; this.knob.style.transform = "translate(0px,0px)";   // 回中动画
    this.base.classList.remove("live");
  };
  TouchCtl.prototype.reset = function () {
    this._release();
    var t = this.input.touch; t.L = t.H = false;
    this.root.querySelectorAll(".on").forEach(function (b) { if (b.id !== "heavy-tog") b.classList.remove("on"); });
  };
  TouchCtl.prototype.unbind = function () {
    this.bound.forEach(function (b) { b[0].removeEventListener(b[1], b[2], b[3]); });
    this.bound = [];
  };
  window.ArenaTouch = TouchCtl;
})();
