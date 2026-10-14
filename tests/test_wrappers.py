import numpy as np

from envs.fighting2d import Fighting2DEnv
from envs.fighting2d import constants as C
from envs.fighting2d.env import Opponent
from envs.registry import EnvConfig, make_env
from wrappers import (ActionHistory, APMLimit, FrameSkip, MacroActions, ObservationDelay, StickyActions,
                      input_cost, ms_to_frames)
from wrappers.macros import MACROS, N_BASE, expand

E = C.encode_input


class Recorder(Opponent):
    name = "rec"

    def act(self, core, idx):
        return 0


def base(**kw):
    return Fighting2DEnv(opponent=Recorder(), random_side=False, seed=0, **kw)


def test_ms_to_frames():
    assert ms_to_frames(200) == 12 and ms_to_frames(100) == 6 and ms_to_frames(0) == 0


def test_frameskip_tap_semantics_gives_two_presses():
    env = FrameSkip(base(), k=4)
    env.reset(seed=0)
    inputs = []
    orig = env.env.step

    def spy(a):
        inputs.append(a)
        return orig(a)

    env.env.step = spy
    env.step(E(5, C.BTN_L))
    env.step(E(5, C.BTN_L))
    assert inputs == [E(5, C.BTN_L), E(5, 0), E(5, 0), E(5, 0)] * 2
    assert env.unwrapped.core.stats[0]["moves"].get("st_L", 0) >= 1


def test_macro_executes_fireball():
    env = MacroActions(FrameSkip(base(), k=4))
    env.reset(seed=0)
    assert env.action_space.n == N_BASE + len(MACROS)
    env.step(N_BASE + 0)  # 236L
    for _ in range(4):
        env.step(E(5, 0))
    assert env.unwrapped.core.stats[0]["moves"].get("fireball_L") == 1


def test_expand_lengths():
    assert len(expand(3, 4)) == 4
    assert expand(N_BASE + 2, 4)[:3] == MACROS["623L"][:3]
    assert len(expand(N_BASE + 1, 2)) == len(MACROS["236H"])


def test_observation_delay_returns_old_obs():
    d = 5
    raw = base()
    env = ObservationDelay(raw, d)
    o0, _ = env.reset(seed=0)
    history = [o0]
    for t in range(12):
        o, *_ = env.step(E(6, 0))
        history.append(raw.core.observe(0))
        expect = history[max(0, len(history) - 1 - d)]
        np.testing.assert_array_equal(o, expect)


def test_sticky_p1_repeats_previous():
    env = StickyActions(base(), p=1.0, seed=0)
    env.reset(seed=0)
    env.step(E(6, 0))
    assert env.unwrapped.core.f[0].last_input == 0  # 一直沿用初始的中立输入


def test_apm_limit_caps_actions():
    env = APMLimit(base(round_seconds=10), apm=120, burst=2)
    env.reset(seed=0)
    rng = np.random.default_rng(0)
    info = {}
    done = False
    while not done:
        _, _, done, _, info = env.step(int(rng.integers(27)))
    assert info["apm"] <= 120 * 1.05 + 2 * 6
    env2 = APMLimit(base(round_seconds=10), apm=None)
    env2.reset(seed=0)
    done = False
    while not done:
        _, _, done, _, info2 = env2.step(int(rng.integers(27)))
    assert info2["apm"] > 1000


def test_input_cost():
    assert input_cost(E(5, 0), E(5, 0)) == 0
    assert input_cost(E(5, 0), E(6, C.BTN_L)) == 2
    assert input_cost(E(6, C.BTN_L), E(6, C.BTN_L)) == 0


def test_action_history_onehot():
    env = ActionHistory(MacroActions(FrameSkip(base(), 4)), n=3)
    o, _ = env.reset(seed=0)
    assert o.shape[0] == base().observation_space.shape[0] + 3 * env.action_space.n
    o, *_ = env.step(7)
    tail = o[-3 * env.action_space.n:].reshape(3, -1)
    assert tail[0, 7] == 1 and tail[1].sum() == 0


def test_make_env_full_stack_runs_episode():
    cfg = EnvConfig(delay_ms=200, sticky=0.1, apm=300, round_seconds=5)
    env = make_env(cfg, Recorder(), seed=1)
    o, _ = env.reset(seed=1)
    assert env.observation_space.shape == o.shape
    done, steps = False, 0
    while not done:
        o, r, done, _, info = env.step(env.action_space.sample())
        steps += 1
    assert "outcome" in info and "apm" in info
    assert steps <= 5 * 60 // 4 + 2
