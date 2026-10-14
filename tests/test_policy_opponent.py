"""关键一致性：评估/联赛里用的 PolicyOpponent 必须和训练时的 gym 包装器栈逐帧等价，
否则"评估出来的强度"就不是"训练出来的那个智能体"的强度。"""
import numpy as np
import pytest

from agents.numpy_policy import NumpyPolicy
from agents.policy_opponent import PolicyOpponent
from agents.scripted import make_scripted
from envs.fighting2d import FightingCore
from envs.registry import EnvConfig, make_env


def random_policy(obs_dim, n_act, seed=0):
    rng = np.random.default_rng(seed)
    w = {"W0": rng.normal(0, 0.3, (obs_dim, 32)), "b0": rng.normal(0, 0.1, 32),
         "Wout": rng.normal(0, 1.0, (32, n_act)), "bout": rng.normal(0, 0.1, n_act)}
    return NumpyPolicy(w)


@pytest.mark.parametrize("delay_ms,hist,apm", [(0, 0, None), (100, 4, None), (200, 2, None), (200, 4, 300)])
def test_policy_opponent_matches_wrapper_stack(delay_ms, hist, apm):
    seed = 7
    cfg = EnvConfig(delay_ms=delay_ms, action_history=hist, random_side=False, round_seconds=8, apm=apm)
    env = make_env(cfg, make_scripted("greedy", seed=123), seed=seed)
    pol = random_policy(env.observation_space.shape[0], env.action_space.n, seed=1)
    # A) gym 包装器栈
    obs, _ = env.reset(seed=seed)
    done = False
    while not done:
        obs, r, done, _, info = env.step(pol.act(obs, deterministic=True))
    hp_a = (env.unwrapped.core.f[0].hp, env.unwrapped.core.f[1].hp, env.unwrapped.core.frame)
    # B) 直接在核心上跑 PolicyOpponent
    core = FightingCore(round_seconds=8, seed=seed)
    core.seed(seed)
    core.reset()
    me = PolicyOpponent(pol, frame_skip=4, delay_ms=delay_ms, action_history=hist, deterministic=True, apm=apm)
    bot = make_scripted("greedy", seed=123)
    me.reset()
    bot.reset(seed + 1)
    while not core.done:
        a = me.act(core, 0)
        b = bot.act(core, 1)
        core.step(a, b)
    hp_b = (core.f[0].hp, core.f[1].hp, core.frame)
    assert hp_a == hp_b


def test_policy_opponent_matches_with_visible_only():
    seed = 3
    cfg = EnvConfig(delay_ms=100, action_history=4, random_side=False, round_seconds=6, visible_only=True)
    env = make_env(cfg, make_scripted("counter", seed=9), seed=seed)
    pol = random_policy(env.observation_space.shape[0], env.action_space.n, seed=2)
    obs, _ = env.reset(seed=seed)
    done = False
    while not done:
        obs, r, done, _, info = env.step(pol.act(obs, deterministic=True))
    a = (env.unwrapped.core.f[0].hp, env.unwrapped.core.f[1].hp)
    core = FightingCore(round_seconds=6, seed=seed)
    core.seed(seed)
    core.reset()
    me = PolicyOpponent.from_spec({"weights": {"W0": pol.layers[0][0], "b0": pol.layers[0][1],
                                               "Wout": pol.out[0], "bout": pol.out[1]},
                                   "env_cfg": cfg.to_dict(), "deterministic": True})
    bot = make_scripted("counter", seed=9)
    me.reset()
    bot.reset(seed + 1)
    while not core.done:
        core.step(me.act(core, 0), bot.act(core, 1))
    assert a == (core.f[0].hp, core.f[1].hp)
