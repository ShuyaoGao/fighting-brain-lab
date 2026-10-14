"""免安装版 play/index.html（file:// 打开）的端到端验收：用本机 Chrome/Edge 在 1366×768 下走一遍
说明浮层、本地字体、页脚署名、观战、双脑/单脑、敲除、我来打、键盘、手搓与新手键必杀技、练习任务。
没有 play/（先运行 python -m arena.build --release）、没有浏览器或 websocket-client 时跳过。"""
from pathlib import Path

import pytest

pytest.importorskip("websocket")
from arena import browser_check, capture  # noqa: E402

PLAY = Path(__file__).resolve().parents[1] / "play" / "index.html"


def test_play_release_end_to_end(tmp_path):
    if not PLAY.exists():
        pytest.skip("先运行 python -m arena.build --release")
    exe = capture.find_browser()
    if not exe:
        pytest.skip("没有 Chrome/Edge")
    rows = browser_check.run_one(exe, PLAY.resolve().as_uri(), 1366, 768, tmp_path)
    bad = [r["item"] + "：" + r["detail"] for r in rows if not r["pass"]]
    assert not bad, bad
    assert len(rows) >= 20
