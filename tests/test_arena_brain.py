"""浏览器大脑面板的数学与真实 torch 模型对拍：前向 logits、critic 价值、对 log π 的输入梯度、
神经元敲除（mask）、积分梯度的完备性、float16 解码。需要 quickjs（可选）。"""
import json
from pathlib import Path

import numpy as np
import pytest
import torch

quickjs = pytest.importorskip("quickjs")

from agents.numpy_policy import NumpyPolicy  # noqa: E402
from agents.ppo import ActorCritic, export_numpy  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "arena" / "web" / "assets"


def make_model(hidden=24, layers=2, seed=0):
    torch.manual_seed(seed)
    m = ActorCritic(214, 31, hidden, layers)
    with torch.no_grad():  # 让输出层不那么平，梯度更有区分度
        m.actor[-1].weight.mul_(80)
    return m


def js_with(model, f16=False):
    from arena.export import net_spec
    sd = model.state_dict()
    spec = {"dtype": "f16" if f16 else "f32", "actor": net_spec(sd, "actor", f16), "critic": net_spec(sd, "critic", f16)}
    ctx = quickjs.Context()
    ctx.eval((ASSETS / "fight.js").read_text(encoding="utf-8"))
    ctx.eval((ASSETS / "brain.js").read_text(encoding="utf-8"))
    ctx.eval("var NET = new ArenaBrain.Net(" + json.dumps(spec) + ");")
    return ctx


def jsarr(ctx, expr):
    return np.array(json.loads(ctx.eval("JSON.stringify(Array.from(" + expr + "))")))


@pytest.mark.parametrize("layers", [1, 2, 3])
def test_forward_value_grad_match_torch(layers):
    m = make_model(layers=layers)
    ctx = js_with(m)
    rng = np.random.default_rng(1)
    obs = rng.normal(0, 1, 214).astype(np.float32)
    ctx.eval("var OBS = " + json.dumps(obs.tolist()) + ";")
    x = torch.tensor(obs, requires_grad=True)
    logits = m.actor(x)
    np.testing.assert_allclose(jsarr(ctx, "NET.forward(OBS).logits"), logits.detach().numpy(), atol=2e-4)
    assert abs(ctx.eval("NET.value(OBS)") - m.value(x).item()) < 2e-4
    a = int(torch.argmax(logits))
    torch.log_softmax(logits, -1)[a].backward()
    g_js = jsarr(ctx, f"NET.grads(OBS, {a}, null).gInput")
    np.testing.assert_allclose(g_js, x.grad.numpy(), atol=2e-4)


def test_masks_match_numpy_policy_and_change_output():
    m = make_model(hidden=16)
    ctx = js_with(m)
    w = export_numpy(m)
    rng = np.random.default_rng(2)
    obs = rng.normal(0, 1, 214).astype(np.float32)
    masks = [np.ones(16, np.float32), np.ones(16, np.float32)]
    masks[0][[1, 5]] = 0
    masks[1][3] = 0
    ctx.eval("var OBS = " + json.dumps(obs.tolist()) + "; var M = " + json.dumps([mm.tolist() for mm in masks]) + ";")
    np.testing.assert_allclose(jsarr(ctx, "NET.forward(OBS, M).logits"), NumpyPolicy(w, masks=masks).logits(obs), atol=2e-4)
    assert not np.allclose(NumpyPolicy(w, masks=masks).logits(obs), NumpyPolicy(w).logits(obs))
    assert all(v == 0 for v in jsarr(ctx, "NET.forward(OBS, M).acts[0]")[[1, 5]])


def test_integrated_gradients_completeness():
    """积分梯度满足完备性：归因之和 ≈ f(x) − f(基线)。"""
    m = make_model(hidden=12)
    ctx = js_with(m)
    rng = np.random.default_rng(3)
    obs = rng.normal(0, 0.5, 214).astype(np.float32)
    ctx.eval("var OBS = " + json.dumps(obs.tolist()) + "; var Z = new Array(214).fill(0);")
    a = int(np.argmax(jsarr(ctx, "NET.forward(OBS).logits")))
    attr = jsarr(ctx, f"NET.explain(OBS, {a}, null, {{ig: true, steps: 64}}).attr")
    lp = lambda e: float(np.log(jsarr(ctx, f"NET.forward({e}).probs")[a]))
    assert abs(attr.sum() - (lp("OBS") - lp("Z"))) < 0.05 * max(1.0, abs(lp("OBS") - lp("Z")))


def test_f16_decode_close_to_f32():
    m = make_model(hidden=20)
    c32, c16 = js_with(m), js_with(m, f16=True)
    obs = np.random.default_rng(4).normal(0, 1, 214).astype(np.float32)
    for c in (c32, c16):
        c.eval("var OBS = " + json.dumps(obs.tolist()) + ";")
    np.testing.assert_allclose(jsarr(c16, "NET.forward(OBS).probs"), jsarr(c32, "NET.forward(OBS).probs"), atol=5e-3)


def test_brain_player_matches_policy_opponent_deterministic():
    """浏览器 BrainPlayer 与 Python PolicyOpponent 在同一局里逐帧给出相同输入（确定性策略）。"""
    from agents.policy_opponent import PolicyOpponent
    from envs.fighting2d.core import FightingCore
    m = make_model(hidden=32)
    w = export_numpy(m)
    ctx = js_with(m)
    cfg = {"frame_skip": 4, "delay_ms": 200, "action_history": 4, "apm": 600}
    py = PolicyOpponent(NumpyPolicy(w), frame_skip=4, delay_ms=200, action_history=4, deterministic=True, apm=600)
    core = FightingCore(round_seconds=10, seed=0, random_start=False)
    core.reset()
    ctx.eval("var P = new ArenaBrain.BrainPlayer(NET, " + json.dumps(cfg) + ", {deterministic: true});"
             "var core = new FightRL.Core({round_seconds: 10, random_start: false});")
    rng = np.random.default_rng(5)
    other = [int(rng.integers(27)) for _ in range(600)]
    ctx.eval("var OTHER = " + json.dumps(other) + "; var OUT = [];"
             "for (var t = 0; t < OTHER.length && !core.done; t++) { var a = P.act(core, 0); OUT.push(a); core.step(a, OTHER[t]); }")
    js_inputs = json.loads(ctx.eval("JSON.stringify(OUT)"))
    py_inputs = []
    for t in range(len(js_inputs)):
        a = py.act(core, 0)
        py_inputs.append(a)
        core.step(a, other[t])
    agree = np.mean(np.array(js_inputs) == np.array(py_inputs))
    assert agree > 0.98, agree   # float32(Python) 与 float64(JS) 在 argmax 近似平局处可能偶发分歧
