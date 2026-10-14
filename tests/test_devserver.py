"""python -m arena 的本地服务不残留：/shutdown 立即退出；心跳超时自动退出。"""
import threading
import time
import urllib.request

import arena.__main__ as dev
from arena.capture import free_port


def _start(tmp_path, monkeypatch, timeout=None, grace=None):
    if timeout is not None:
        monkeypatch.setattr(dev, "HEARTBEAT_TIMEOUT", timeout)
    if grace is not None:
        monkeypatch.setattr(dev, "FIRST_BEAT_GRACE", grace)
    (tmp_path / "index.html").write_text("<p>ok</p>", encoding="utf-8")
    port = free_port()
    th = threading.Thread(target=dev.serve, args=(tmp_path, port, None), daemon=True)
    th.start()
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html", timeout=1).read()
            break
        except Exception:
            time.sleep(0.05)
    return port, th


def _post(port, path):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=b"", method="POST")
    return urllib.request.urlopen(req, timeout=2).status


def test_shutdown_endpoint_stops_server(tmp_path, monkeypatch):
    port, th = _start(tmp_path, monkeypatch)
    assert _post(port, "/heartbeat") == 204
    assert _post(port, "/shutdown") == 204
    th.join(timeout=5)
    assert not th.is_alive()


def test_heartbeat_timeout_stops_server(tmp_path, monkeypatch):
    port, th = _start(tmp_path, monkeypatch, timeout=1.5, grace=30)
    assert _post(port, "/heartbeat") == 204
    time.sleep(0.8)
    assert th.is_alive()          # 心跳还新鲜
    th.join(timeout=6)            # 之后不再发心跳：超时退出
    assert not th.is_alive()


def test_page_exit_button_stops_dev_server(monkeypatch):
    """真实页面：通过本地服务打开 → 页面自动发心跳 → 点「退出」→ 服务退出、页面显示结束页。"""
    import json

    import pytest
    pytest.importorskip("websocket")
    from pathlib import Path

    from arena import build, capture
    root = Path(__file__).resolve().parents[1]
    if not capture.find_browser() or not (root / "arena" / "web" / "assets" / "gen" / "models" / "index.js").exists():
        pytest.skip("没有 Chrome/Edge 或没有导出的模型")
    page = build.build_local()
    port = free_port()
    th = threading.Thread(target=dev.serve, args=(page.parent, port, None), daemon=True)
    th.start()
    b = capture.Browser(1366, 768)
    try:
        b.goto(f"http://127.0.0.1:{port}/index.html?nohelp")
        st = b.js("ARENA_TEST.exitState()")
        assert st["beat"] is True and st["stopped"] is False
        b.js("ARENA_TEST.shutdown()")
        th.join(timeout=8)
        assert not th.is_alive(), "退出按钮应关闭本地服务"
        time.sleep(0.4)
        assert "已停止运行" in (b.js("document.body.innerText") or "")
        assert json.dumps(b.js("ARENA_TEST.exitState()"))
    finally:
        b.close()
