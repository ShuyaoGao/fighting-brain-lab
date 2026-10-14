"""用本机已安装的 Chrome/Edge（无头模式 + DevTools 协议）驱动 arena：截图、逐帧录像、无头冒烟测试。
不安装任何浏览器；只依赖 websocket-client（纯 Python）。

  python -m arena.capture shot  --out shot.png [--layout dual] [--frames 300]
  python -m arena.capture video --out demo.mp4 --scenario human_vs_ai --seconds 20
"""
import argparse
import base64
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BROWSERS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"]


def find_browser():
    for b in BROWSERS:
        if os.path.exists(b):
            return b
    return shutil.which("chrome") or shutil.which("msedge") or shutil.which("chromium")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Browser:
    def __init__(self, width=1920, height=1080, dpr=1.0, exe=None):
        import websocket
        exe = exe or find_browser()
        if not exe:
            raise RuntimeError("找不到 Chrome/Edge")
        self.port = free_port()
        self.prof = tempfile.mkdtemp(prefix="arena_cdp_")
        self.proc = subprocess.Popen([exe, "--headless=new", f"--remote-debugging-port={self.port}",
                                      f"--user-data-dir={self.prof}", f"--window-size={width},{height}",
                                      "--hide-scrollbars", "--mute-audio", "--no-first-run", "--disable-gpu",
                                      f"--force-device-scale-factor={dpr}", "about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws_url = None
        for _ in range(100):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/list", timeout=1).read())
                pages = [t for t in tabs if t.get("type") == "page"]
                if pages:
                    ws_url = pages[0]["webSocketDebuggerUrl"]
                    break
            except Exception:
                time.sleep(0.1)
        if not ws_url:
            self.close()
            raise RuntimeError("浏览器调试端口没有响应")
        self.ws = websocket.create_connection(ws_url, timeout=60, suppress_origin=True)
        self.mid = 0
        self.events = []
        self.call("Runtime.enable")
        self.call("Page.enable")
        self.call("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": dpr,
                                                         "mobile": False})

    def call(self, method, params=None):
        self.mid += 1
        mid = self.mid
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
            self.events.append(msg)

    def goto(self, url, wait_js="window.ARENA_TEST && ARENA_TEST.state().ready", timeout=30):
        self.call("Page.navigate", {"url": url})
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                if self.js(wait_js):
                    return True
            except Exception:
                pass
            time.sleep(0.2)
        raise RuntimeError("页面没有就绪：" + url)

    def js(self, expr):
        r = self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in r:
            raise RuntimeError(json.dumps(r["exceptionDetails"], ensure_ascii=False)[:800])
        return r.get("result", {}).get("value")

    def errors(self):
        out = []
        for e in self.events:
            if e.get("method") == "Runtime.exceptionThrown":
                out.append(e["params"]["exceptionDetails"].get("exception", {}).get("description", "exception"))
            if e.get("method") == "Runtime.consoleAPICalled" and e["params"]["type"] == "error":
                out.append(" ".join(str(a.get("value", a.get("description", ""))) for a in e["params"]["args"]))
        return out

    def shot(self, clip=None):
        p = {"format": "png"}
        if clip:
            p["clip"] = dict(clip, scale=1)
        return base64.b64decode(self.call("Page.captureScreenshot", p)["data"])

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            pass
        shutil.rmtree(self.prof, ignore_errors=True)


def page_url(dist=False, hash_=""):
    from arena import build
    p = build.build_local() if not dist else (ROOT / "arena" / "dist" / "index.html")
    return p.resolve().as_uri() + "?nohelp" + (("#" + hash_) if hash_ else "")


def prepare(b, models=None, layout="single", side=1, seed=7, human=False):
    b.js("ARENA_TEST.manual(true)")
    if models:
        b.js("new Promise(function(r){ ARENA_TEST.setModels(%s, %s, r); })" % (json.dumps(models[0]), json.dumps(models[1])))
    b.js(f"ARENA_TEST.setLayout({json.dumps(layout)}, {side})")
    b.js(f"ARENA_TEST.seed({seed})")
    time.sleep(0.3)


def cmd_shot(a):
    b = Browser(a.width, a.height)
    try:
        b.goto(page_url(hash_="dual" if a.layout == "dual" else ""))
        prepare(b, a.models, a.layout, a.side, a.seed)
        b.js(f"ARENA_TEST.step({a.frames})")
        Path(a.out).write_bytes(b.shot())
        print("截图：", a.out, "状态：", b.js("JSON.stringify(ARENA_TEST.state())"), "错误：", b.errors())
    finally:
        b.close()


def cmd_video(a):
    import imageio.v2 as imageio
    from PIL import Image
    b = Browser(a.width, a.height)
    frames = []
    try:
        b.goto(page_url(hash_="dual" if a.layout == "dual" else ""))
        prepare(b, a.models, a.layout, a.side, a.seed)
        if a.knock:
            spec = json.loads(a.knock)
            b.js("ARENA_TEST.step(%d)" % spec.get("after", 0))
        total = int(a.seconds * a.fps)
        per = max(1, round(60 / a.fps))
        for k in range(total):
            if a.knock and k == spec.get("at", -1):
                b.js("ARENA_TEST.knock(%d, %d, %s)" % (spec["side"], spec["layer"], json.dumps(spec["neurons"])))
            b.js(f"ARENA_TEST.step({per})")
            img = Image.open(io.BytesIO(b.shot())).convert("RGB")
            if a.scale != 1:
                img = img.resize((int(img.width * a.scale), int(img.height * a.scale)), Image.LANCZOS)
            frames.append(img)
        print("错误：", b.errors())
    finally:
        b.close()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix == ".gif":
        pal = [f.convert("P", palette=Image.ADAPTIVE, colors=128) for f in frames]
        pal[0].save(out, save_all=True, append_images=pal[1:], duration=int(1000 / a.fps), loop=0, optimize=True)
    else:
        imageio.mimwrite(out, [__import__("numpy").asarray(f) for f in frames], fps=a.fps, macro_block_size=1, quality=8)
    print("视频：", out, len(frames), "帧")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["shot", "video"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--layout", default="single")
    ap.add_argument("--side", type=int, default=1)
    ap.add_argument("--models", nargs=2, default=None)
    ap.add_argument("--frames", type=int, default=240)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--fps", type=int, default=20)
    ap.add_argument("--scale", type=float, default=0.5)
    ap.add_argument("--knock", default=None, help='JSON：{"after":帧, "at":第几张, "side":1, "layer":0, "neurons":[...]}')
    a = ap.parse_args()
    {"shot": cmd_shot, "video": cmd_video}[a.cmd](a)


if __name__ == "__main__":
    main()
