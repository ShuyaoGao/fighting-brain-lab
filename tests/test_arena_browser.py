"""用本机无头 Chrome/Edge 跑 arena 页面：加载真实模型、跑完开场进入对战、切换双脑布局、敲掉神经元，
全程不能有 JS 异常。没有浏览器、没有 websocket-client 或没有导出的模型时跳过。"""
import json
from pathlib import Path

import pytest

pytest.importorskip("websocket")
from arena import capture  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "arena" / "web" / "assets" / "gen" / "models" / "index.js"


@pytest.fixture(scope="module")
def browser():
    if not capture.find_browser():
        pytest.skip("没有 Chrome/Edge")
    if not INDEX.exists():
        pytest.skip("先运行 python -m arena.export")
    b = capture.Browser(1600, 900)
    yield b
    b.close()


def test_arena_runs_and_brain_updates(browser):
    b = browser
    b.goto(capture.page_url())
    b.js("ARENA_TEST.manual(true)")
    ids = json.loads(b.js("JSON.stringify(ARENA_MODEL_INDEX.map(function(m){return m.id;}))"))
    assert ids
    b.js("new Promise(function(r){ ARENA_TEST.setModels(%s, %s, r); })" % (json.dumps(ids[0]), json.dumps(ids[-1])))
    b.js("ARENA_TEST.seed(3)")
    st = b.js("ARENA_TEST.step(400); ARENA_TEST.state()")
    assert st["phase"] in ("fight", "ko") and st["frame"] > 200
    assert min(st["decisions"]) > 50
    b.js("ARENA_TEST.setLayout('dual')")
    b.js("ARENA_TEST.knock(1, 0, [0, 1, 2, 3])")
    st2 = b.js("ARENA_TEST.step(200); ARENA_TEST.state()")
    assert st2["frame"] != st["frame"] or st2["phase"] != st["phase"]
    cut = b.js("ARENA_TEST.app.players[1].bp.masks[0].slice(0, 4).reduce(function(a, x){ return a + x; }, 0)")
    assert cut == 0
    b.js("ARENA_TEST.restore()")
    assert b.errors() == []


def test_match_flow_reaches_next_round(browser):
    b = browser
    b.js("ARENA_TEST.seed(5)")
    for _ in range(40):
        st = b.js("ARENA_TEST.step(300); ARENA_TEST.state()")
        if st["round"] >= 2 or sum(st["wins"]) >= 1:
            break
    assert sum(st["wins"]) >= 1 or st["round"] >= 2
    assert b.errors() == []
