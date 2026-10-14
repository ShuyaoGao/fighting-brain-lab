"""一条命令启动格斗大脑实验台：导出模型 -> 生成页面 -> 本地 HTTP 服务 -> 打开浏览器。

  python -m arena                 # 默认端口 8765
  python -m arena --no-export     # 跳过导出（模型没变时更快）
  python -m arena --no-browser --port 9000

本地服务不会在后台残留：
- 页面右上角「退出」会调用 POST /shutdown，服务随即退出；
- 页面每 5 秒发一次心跳（/heartbeat）；超过 30 秒没收到心跳（标签页已关闭）服务自动退出；
- 也可以在终端按 Ctrl+C。
离线版（play/ 或双击 index.html）是纯静态网页，没有任何服务进程，关掉标签页就全部结束。
"""
import argparse
import functools
import http.server
import socketserver
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

HEARTBEAT_TIMEOUT = 30.0     # 秒：超过这么久没有心跳就退出
FIRST_BEAT_GRACE = 120.0     # 秒：启动后等第一次心跳（浏览器打开、模型加载）的宽限


class Handler(http.server.SimpleHTTPRequestHandler):
    server_ref = None

    def log_message(self, fmt, *args):   # 安静一些：只打印错误
        if args and str(args[1]).startswith(("4", "5")):
            super().log_message(fmt, *args)

    def _ok(self):
        self.send_response(204)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _route(self):
        srv = self.server
        if self.path.startswith("/heartbeat"):
            srv.last_beat = time.time()
            self._ok()
            return True
        if self.path.startswith("/shutdown"):
            self._ok()
            print("页面请求退出：本地服务关闭。")
            threading.Thread(target=srv.shutdown, daemon=True).start()
            return True
        return False

    def do_POST(self):
        if not self._route():
            self.send_error(404)

    def do_GET(self):
        if not self._route():
            super().do_GET()


def watchdog(srv):
    """心跳超时就关闭服务。"""
    while not srv.stopped:
        time.sleep(1.0)
        now = time.time()
        if srv.last_beat is None:
            if now - srv.started > FIRST_BEAT_GRACE:
                print(f"{FIRST_BEAT_GRACE:.0f} 秒内没有页面连接：本地服务关闭。")
                srv.shutdown()
                return
        elif now - srv.last_beat > HEARTBEAT_TIMEOUT:
            print(f"{HEARTBEAT_TIMEOUT:.0f} 秒没有收到页面心跳（标签页已关闭）：本地服务关闭。")
            srv.shutdown()
            return


def serve(directory, port, open_url=None):
    handler = functools.partial(Handler, directory=str(directory))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", port), handler) as httpd:
        httpd.daemon_threads = True
        httpd.started, httpd.last_beat, httpd.stopped = time.time(), None, False
        threading.Thread(target=watchdog, args=(httpd,), daemon=True).start()
        if open_url:
            threading.Timer(0.6, lambda: webbrowser.open(open_url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            httpd.stopped = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-export", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--layout", choices=["single", "dual"], default="dual", help="大脑面板：single = 单个，dual = 全部")
    a = ap.parse_args()
    from arena import build, export
    if not a.no_export:
        export.export_spec(export.GEN)
        export.export_report(export.GEN)
        idx = export.export_models(export.GEN)
        print(f"已导出 {len(idx)} 个模型")
    page = build.build_local()
    url = f"http://127.0.0.1:{a.port}/index.html" + ("#single" if a.layout == "single" else "")
    print(f"格斗大脑实验台：{url}（页面右上角「退出」或 Ctrl+C 结束；关掉标签页 30 秒后服务自动退出）")
    serve(page.parent, a.port, None if a.no_browser else url)


if __name__ == "__main__":
    main()
