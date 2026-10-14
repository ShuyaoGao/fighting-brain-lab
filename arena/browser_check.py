"""免安装版（play/index.html，file:// 打开）的跨浏览器验收：Chrome、Edge（Chromium 内核，走 DevTools 协议）。

  python -m arena.browser_check                 # 两个浏览器 × 1920×1080 / 1366×768
  python -m arena.browser_check --page arena/web/index.html

逐项检查：打开（首次弹出操作说明、Esc 关闭、本地字体已加载）、观战（双脑、AI 决策）、布局（无横向滚动、游戏画面在首屏）、
双脑/单脑切换、神经元敲除（按钮）、我来打（真实键盘事件移动）、手搓气功波（↓↘→+J 逐帧按键）、
新手键（U 气功波、Shift+I 重冲天拳）、练习模式（任务打勾）。结果写到 release/browser_check.json，截图在 release/browser_check/。
只测本机已安装、系统签名过的浏览器；Firefox 与 Safari 记为"未测"（Safari 需要在真实 Mac 上确认）。
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from arena import capture  # noqa: E402

KEY = {"a": 65, "d": 68, "w": 87, "s": 83, "j": 74, "k": 75, "u": 85, "i": 73, "h": 72, "escape": 27, "shift": 16}
BROWSERS = {"Chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "Edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"}


class Check:
    def __init__(self, b):
        self.b, self.rows = b, []

    def key(self, k, down, shift=False):
        name = {"escape": "Escape", "shift": "Shift"}.get(k, k.upper() if shift else k)
        code = {"escape": "Escape", "shift": "ShiftLeft"}.get(k, "Key" + k.upper())
        self.b.call("Input.dispatchKeyEvent", {"type": "keyDown" if down else "keyUp", "key": name, "code": code,
                                               "windowsVirtualKeyCode": KEY[k], "nativeVirtualKeyCode": KEY[k],
                                               "modifiers": 8 if shift else 0})

    def tap(self, k, shift=False):
        self.key(k, True, shift)
        self.key(k, False, shift)

    def click(self, selector):
        r = self.b.js("(function(){var e=document.querySelector(%s); if(!e) return null; e.scrollIntoView({block:'center'});"
                      "var r=e.getBoundingClientRect(); return [r.left+r.width/2, r.top+r.height/2];})()" % json.dumps(selector))
        if not r:
            raise RuntimeError("找不到元素 " + selector)
        for t in ("mousePressed", "mouseReleased"):
            self.b.call("Input.dispatchMouseEvent", {"type": t, "x": r[0], "y": r[1], "button": "left", "clickCount": 1})
        time.sleep(0.15)

    def st(self):
        return self.b.js("ARENA_TEST.state()")

    def step(self, n=1):
        return self.b.js(f"ARENA_TEST.step({n})")

    def ok(self, name, cond, detail=""):
        self.rows.append({"item": name, "pass": bool(cond), "detail": detail})
        return cond


def wait(b, expr, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if b.js(expr):
                return True
        except Exception:
            pass
        time.sleep(0.15)
    return False


def run_one(exe, url, W, H, shots):
    b = capture.Browser(W, H, exe=exe)
    c = Check(b)
    try:
        b.call("Page.navigate", {"url": url})
        c.ok("打开页面（file://）", wait(b, "window.ARENA_TEST && ARENA_TEST.state().ready"))
        c.ok("首次打开弹出操作说明", c.st()["help"])
        fonts = b.js("document.fonts.check(\"16px 'Noto Sans SC'\") && document.fonts.check(\"10px 'Press Start 2P'\")")
        c.ok("本地字体（不依赖网络）", fonts)
        foot = b.js("document.getElementById('credits').innerText") or ""
        c.ok("页脚显示署名与许可证", "Shuyao Gao" in foot and "MIT" in foot and "CC BY 4.0" in foot, " / ".join(foot.splitlines())[:120])
        (shots / f"{W}x{H}_0_help.png").write_bytes(b.shot())
        c.tap("escape")
        c.ok("Esc 关闭说明", not c.st()["help"])
        c.tap("h")
        c.ok("H 键再次打开说明", c.st()["help"])
        c.tap("h")
        b.js("ARENA_TEST.manual(true)")
        # 观战
        st = c.st()
        c.ok("默认观战（两个 AI）", st["mode"] == "watch" and all(p not in ("human", "dummy") for p in st["players"]), str(st["players"]))
        b.js("ARENA_TEST.seed(5)")
        c.step(400)
        st = c.st()
        c.ok("AI 自动对打（决策在进行）", min(st["decisions"]) > 20, str(st["decisions"]))
        br = b.js("ARENA_TEST.brains()")
        c.ok("「全部」模式：两颗大脑在右栏上下堆叠（紧凑画法）", len(br) == 2 and all(x["mode"] == "compact" and x["w"] > 300 and x["h"] > 150 for x in br)
             and br[0]["w"] == br[1]["w"], json.dumps([[x["side"], x["mode"], x["w"], x["h"]] for x in br]))
        # 结构式里的数字必须和实际模型一致（输入 = 观测 + 动作历史，隐藏层宽度来自模型索引）
        ok_struct, detail = True, []
        for x in br:
            m = b.js("(function(){var id=ARENA_TEST.state().players[%d]; var m=ARENA_MODEL_INDEX.filter(function(q){return q.id===id;})[0];"
                     "return {w:m.width, d:m.depth, obs:ARENA_SPEC.obs_dim, nh:m.env_cfg.action_history, na:ARENA_SPEC.actions.length};})()" % x["side"])
            exp_in = m["obs"] + m["nh"] * m["na"]
            want = "输入 %d → %s → 输出 %d 个动作 + 1 个局势评估" % (exp_in, " → ".join("隐藏 %d" % m["w"] for _ in range(m["d"])), m["na"])
            ok_struct &= x["structure"] == want and x["nIn"] == exp_in and x["widths"] == [m["w"]] * m["d"]
            detail.append(x["structure"])
        c.ok("结构式数字与模型一致", ok_struct, " | ".join(detail))
        lay = b.js("(function(){var g=document.getElementById('game').getBoundingClientRect(), r=document.querySelector('.brains').getBoundingClientRect();"
                   "return {sw: document.documentElement.scrollWidth, iw: innerWidth, gtop: g.top, gbot: g.bottom, gw: g.width, ih: innerHeight,"
                   " gr: g.right, bl: r.left, bw: r.width, bh: r.height};})()")
        c.ok("左右两栏：左边游戏、右边大脑占满高度", lay["gr"] <= lay["bl"] and lay["bh"] >= lay["ih"] * 0.75, json.dumps(lay))
        c.ok("无横向滚动条", lay["sw"] <= lay["iw"] + 1, f"scrollWidth={lay['sw']} innerWidth={lay['iw']}")
        c.ok("游戏画面完整在首屏", lay["gtop"] >= 0 and lay["gbot"] <= lay["ih"] and lay["gw"] >= 300, json.dumps(lay))
        (shots / f"{W}x{H}_1_watch.png").write_bytes(b.shot())
        b.js("ARENA_TEST.seed(5)"); c.step(200)
        c.click("#brain-stack canvas")   # 点「全部」里的第一个大脑 → 切到它的单个模式
        c.step(2)
        br = b.js("ARENA_TEST.brains()")
        c.ok("点「全部」里的大脑切到单个模式", len(br) == 1 and br[0]["mode"] == "full" and br[0]["side"] == 0, json.dumps(br)[:160])
        c.click("button[data-bv='1']"); c.step(2)
        br = b.js("ARENA_TEST.brains()")
        c.ok("顶部切换「P2 大脑」", len(br) == 1 and br[0]["side"] == 1 and br[0]["h"] >= lay["ih"] * 0.7, json.dumps(br)[:160])
        (shots / f"{W}x{H}_1b_single.png").write_bytes(b.shot())
        c.click("button[data-bv='all']"); c.step(2)
        w0 = b.js("document.querySelector('.brains').getBoundingClientRect().width")
        c.click("#bigmode"); c.step(2)
        w1 = b.js("document.querySelector('.brains').getBoundingClientRect().width")
        c.ok("大屏模式：右栏变宽（约 55% → 65%）", w1 > w0 * 1.12 and abs(w1 / (lay["iw"] - 32) - 0.65) < 0.05, f"{w0:.0f} → {w1:.0f}")
        (shots / f"{W}x{H}_1c_big.png").write_bytes(b.shot())
        c.click("#bigmode"); c.step(2)
        c.click("#cut-rand")
        n = b.js("ARENA_TEST.cuts()")
        c.click("#cut-reset")
        c.ok("神经元敲除（随机 25% → 全部恢复）", n > 0 and b.js("ARENA_TEST.cuts()") == 0, f"敲掉 {n} 个")
        # 我来打
        c.ok("没有多余的「我来打」大按钮", not b.js("!!document.getElementById('cta')"))
        c.click("button[data-mode=play]")
        wait(b, "ARENA_TEST.state().ready && ARENA_TEST.state().players[0]==='human'")
        st = c.st()
        c.ok("「我来打」切到人机对战", st["mode"] == "play" and st["players"][0] == "human", str(st["players"]))
        b.js("ARENA_TEST.seed(9)"); b.js("ARENA_TEST.skipIntro()")
        x0 = c.st()["x"][0]
        c.key("d", True); c.step(30); c.key("d", False); c.step(2)
        x1 = c.st()["x"][0]
        c.ok("键盘：按住 D 前进", x1 > x0 + 20, f"x {x0:.0f} → {x1:.0f}")
        (shots / f"{W}x{H}_2_play.png").write_bytes(b.shot())
        # 练习模式
        c.click("button[data-mode=practice]")
        wait(b, "ARENA_TEST.state().mode==='practice'")
        b.js("ARENA_TEST.seed(3)")
        c.key("d", True); c.step(40); c.key("d", False)
        c.key("w", True); c.step(3); c.key("w", False); c.step(60)
        t = c.st()["tasks"] or {}
        c.ok("练习模式：前进、跳 自动打勾", t.get("walkF") and t.get("jump"), json.dumps(t))
        # 必杀技输入在练习模式里测（木桩站着不动，结果确定）
        c.step(60)
        # 手搓气功波：↓ ↘ →+J（P1 在左、朝右）
        seq = [({"s"}, 3), ({"s", "d"}, 3), ({"d"}, 2), ({"d", "j"}, 2), (set(), 2)]
        held, got = set(), None
        for keys, n in seq:
            for k in keys - held: c.key(k, True)
            for k in held - keys: c.key(k, False)
            held = keys
            for _ in range(n):
                c.step(1)
                m = c.st()["moves"][0]
                if m and m.startswith("fireball"): got = got or m
        for _ in range(6):
            c.step(1); m = c.st()["moves"][0]
            if m and m.startswith("fireball"): got = got or m
        c.ok("手搓 ↓↘→+J 放出气功波", got == "fireball_L", str(got))
        c.ok("搓招成功提示「✓」", "✓" in (c.st()["flash"] or ""), c.st()["flash"])
        c.step(150)
        c.tap("u"); got = None
        for _ in range(8):
            c.step(1); m = c.st()["moves"][0]
            if m and m.startswith("fireball"): got = got or m
        c.ok("新手键 U → 轻气功波", got == "fireball_L", str(got))
        c.step(150)
        c.key("shift", True); c.tap("i", shift=True); c.key("shift", False); got = None
        for _ in range(8):
            c.step(1); m = c.st()["moves"][0]
            if m and m.startswith("dp"): got = got or m
        c.ok("新手键 Shift+I → 重冲天拳", got == "dp_H", str(got))
        # 搓错时的提示：↓ → +J（少了 ↘）
        c.step(120)
        for keys, n in [({"s"}, 3), ({"d"}, 3), ({"d", "j"}, 2), (set(), 10)]:
            for k in keys - held: c.key(k, True)
            for k in held - keys: c.key(k, False)
            held = keys; c.step(n)
        c.ok("搓错时提示差在哪（少了 ↘）", "少了" in (c.st()["flash"] or ""), c.st()["flash"])
        t = c.st()["tasks"] or {}
        c.ok("练习模式：气功波、冲天拳任务打勾", t.get("fireball") and t.get("dp"), json.dumps(t))
        (shots / f"{W}x{H}_3_practice.png").write_bytes(b.shot())
        errs = b.errors()
        c.ok("没有脚本错误", not errs, "; ".join(errs)[:300])
        # 退出：停止主循环、定时器、音效、手柄监听，释放模型，显示结束页
        b.js("ARENA_TEST.manual(false)"); time.sleep(0.3)
        c.click("#exit-btn"); time.sleep(0.8)
        es = b.js("window.ARENA_TEST ? ARENA_TEST.exitState() : null")
        ended = b.js("!!document.getElementById('ended') && document.getElementById('ended').innerText.indexOf('已停止运行') >= 0")
        c.ok("退出：主循环停止、音效关闭、心跳停止，显示结束页", es and es["stopped"] and not es["raf"] and not es["beat"]
             and es["audio"] in ("closed", "none", "closing") and ended, json.dumps(es))
    except Exception as e:  # noqa: BLE001
        c.ok("流程中断", False, str(e)[:300])
    finally:
        b.close()
    return c.rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", default=str(ROOT / "play" / "index.html"))
    a = ap.parse_args()
    url = Path(a.page).resolve().as_uri()
    out = ROOT / "release"
    shots = out / "browser_check"
    shots.mkdir(parents=True, exist_ok=True)
    res = {"page": Path(a.page).name, "results": {}}
    for name, exe in BROWSERS.items():
        if not Path(exe).exists():
            res["results"][name] = "未安装"
            continue
        for W, H in ((1920, 1080), (1366, 768)):
            d = shots / name
            d.mkdir(exist_ok=True)
            rows = run_one(exe, url, W, H, d)
            res["results"][f"{name} {W}x{H}"] = rows
            bad = [r for r in rows if not r["pass"]]
            print(f"{name} {W}x{H}: {len(rows) - len(bad)}/{len(rows)} 通过" + ("" if not bad else "；失败：" + "；".join(r["item"] + "（" + r["detail"] + "）" for r in bad)))
    res["results"]["Firefox"] = "未测（本机没有安装 Firefox）"
    res["results"]["Safari"] = "未测：需要在真实 Mac 上确认"
    (out / "browser_check.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


if __name__ == "__main__":
    main()
