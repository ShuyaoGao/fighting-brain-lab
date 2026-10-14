"""浏览器版（arena/web/assets/fight.js）与 Python 核心逐帧对拍。需要 quickjs（pip install quickjs，可选）。"""
import json
from pathlib import Path

import numpy as np
import pytest

quickjs = pytest.importorskip("quickjs")

from agents.numpy_policy import NumpyPolicy  # noqa: E402
from envs.fighting2d.core import FightingCore  # noqa: E402

JS = (Path(__file__).resolve().parents[1] / "arena" / "web" / "assets" / "fight.js").read_text(encoding="utf-8")


def js_ctx():
    ctx = quickjs.Context()
    ctx.eval(JS)
    return ctx


def gen_inputs(seed, n):
    rng = np.random.default_rng(seed)
    out, cur, hold = [], [0, 0], [0, 0]
    for _ in range(n):
        for i in range(2):
            if hold[i] <= 0:
                cur[i] = int(rng.integers(27))
                hold[i] = int(rng.integers(1, 10))
            hold[i] -= 1
        out.append(list(cur))
    # 混入必杀指令
    for t in range(50, n - 10, 97):
        out[t][0], out[t + 1][0], out[t + 2][0] = 9, 15, 4   # ↓ ↘ →+轻（E(2,0)=9, E(3,0)=15, E(6,1)=4）
    return out


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_core_parity(seed):
    ctx = js_ctx()
    n = 3000
    inputs = gen_inputs(seed, n)
    py = FightingCore(round_seconds=60, seed=0, random_start=False)
    py.reset()
    ctx.eval("var core = new FightRL.Core({round_seconds: 60, random_start: false}); var log = [];")
    ctx.eval("var INPUTS = " + json.dumps(inputs) + ";")
    js_states = json.loads(ctx.eval("""
        (function(){
          var out = [];
          for (var t = 0; t < INPUTS.length; t++) {
            if (core.done) break;
            core.step(INPUTS[t][0], INPUTS[t][1]);
            out.push([core.f[0].x, core.f[0].y, core.f[0].hp, core.f[0].state, core.f[1].x, core.f[1].y,
                      core.f[1].hp, core.f[1].state, core.projs.length]);
          }
          return JSON.stringify(out);
        })()"""))
    for t, (a, b) in enumerate(inputs[:len(js_states)]):
        py.step(a, b)
        s = [py.f[0].x, py.f[0].y, py.f[0].hp, py.f[0].state, py.f[1].x, py.f[1].y, py.f[1].hp, py.f[1].state,
             len(py.projs)]
        assert np.allclose(s, js_states[t], atol=1e-9), (t, s, js_states[t])
    o_js = np.array(json.loads(ctx.eval("JSON.stringify(core.observe(0))")))
    np.testing.assert_allclose(py.observe(0), o_js, atol=1e-5)
    o_js = np.array(json.loads(ctx.eval("JSON.stringify(core.observe(1, true))")))
    np.testing.assert_allclose(py.observe(1, visible_only=True), o_js, atol=1e-5)


def test_encoding_matches():
    ctx = js_ctx()
    from envs.fighting2d.constants import encode_input
    for d in (1, 2, 3, 4, 5, 6, 7, 8, 9):
        for b in (0, 1, 2):
            assert ctx.eval(f"FightRL.encodeInput({d},{b})") == encode_input(d, b)


def test_policy_logits_parity():
    ctx = js_ctx()
    rng = np.random.default_rng(0)
    w = {"W0": rng.normal(0, 0.2, (214, 64)).astype(np.float32), "b0": rng.normal(0, 0.1, 64).astype(np.float32),
         "W1": rng.normal(0, 0.2, (64, 64)).astype(np.float32), "b1": rng.normal(0, 0.1, 64).astype(np.float32),
         "Wout": rng.normal(0, 0.5, (64, 31)).astype(np.float32), "bout": np.zeros(31, np.float32)}
    pol = NumpyPolicy(w)
    js_w = {"layers": [{"W": w[f"W{i}"].ravel().tolist(), "b": w[f"b{i}"].tolist(), "in": w[f"W{i}"].shape[0],
                        "out": w[f"W{i}"].shape[1]} for i in range(2)],
            "out": {"W": w["Wout"].ravel().tolist(), "b": w["bout"].tolist(), "in": 64, "out": 31}}
    obs = rng.normal(0, 1, 214).astype(np.float32)
    ctx.eval("var P = new FightRL.Policy(" + json.dumps(js_w) + ");")
    lg = np.array(json.loads(ctx.eval("JSON.stringify(Array.from(P.logits(" + json.dumps(obs.tolist()) + ")))")))
    np.testing.assert_allclose(pol.logits(obs), lg, atol=1e-4)


def test_arena_and_showcase_share_one_core():
    """arena 与展示页用的是同一份 JS 游戏核心（防止两份拷贝悄悄分叉）。"""
    root = Path(__file__).resolve().parents[1]
    if not (root / "showcase" / "assets" / "fight.js").exists():
        pytest.skip("没有旧版展示页 showcase/")
    a = (root / "arena" / "web" / "assets" / "fight.js").read_bytes()
    b = (root / "showcase" / "assets" / "fight.js").read_bytes()
    assert a == b


@pytest.mark.parametrize("seed", [10, 11, 12])
def test_event_and_state_parity_from_random_starts(seed):
    """从随机起始位置开始，逐帧比对双方完整状态（位置/速度/状态/招式帧/硬直/血量/飞行道具）与事件序列。"""
    ctx = js_ctx()
    rng = np.random.default_rng(seed)
    x0, x1 = float(rng.uniform(40, 200)), float(rng.uniform(190, 344))
    inputs = gen_inputs(seed, 2500)
    py = FightingCore(round_seconds=50, seed=0, random_start=False)
    py.reset()
    py.f[0].x, py.f[1].x = x0, x1
    ctx.eval(f"var core = new FightRL.Core({{round_seconds: 50, random_start: false}}); core.f[0].x = {x0}; core.f[1].x = {x1};")
    ctx.eval("var INPUTS = " + json.dumps(inputs) + ";")
    js = json.loads(ctx.eval("""
        (function(){
          var out = [];
          for (var t = 0; t < INPUTS.length && !core.done; t++) {
            core.step(INPUTS[t][0], INPUTS[t][1]);
            out.push({s: core.f.map(function(f){ return [f.x, f.y, f.vx, f.vy, f.state, f.move ? f.move.name : null,
                       f.move_frame, f.stun, f.hp, f.facing, f.combo]; }),
                      p: core.projs.map(function(p){ return [p.owner, p.x]; }),
                      e: core.events.map(function(e){ return e.join(":"); })});
          }
          return JSON.stringify(out);
        })()"""))
    for t, rec in enumerate(js):
        py.step(*inputs[t])
        st = [[f.x, f.y, f.vx, f.vy, f.state, f.move.name if f.move else None, f.move_frame, f.stun, f.hp, f.facing, f.combo]
              for f in py.f]
        assert len(st) == len(rec["s"])
        for a, b in zip(st, rec["s"]):
            assert a[4:] == b[4:], (t, a, b)
            np.testing.assert_allclose(a[:4], b[:4], atol=1e-9)
        assert [[p.owner, p.x] for p in py.projs] == rec["p"] or np.allclose(
            [p.x for p in py.projs], [q[1] for q in rec["p"]])
        assert [":".join(str(x) for x in e) for e in py.events] == rec["e"], (t, py.events, rec["e"])
