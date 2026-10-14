"""真实游戏适配器的测试桩：用假的 stable_retro / diambra.arena 模块验证
"统一动作 -> 手柄按键"映射、朝向镜像、RAM -> 奖励/回合结束、双人模式对手接入、与包装器栈的兼容性。
真实游戏需要 ROM + Linux（retro）或 Docker（DIAMBRA），建议在 Linux 服务器上跑。"""
import types

import numpy as np

from envs.adapter_base import to_absolute
from envs.diambra_adapter import DiambraFightingEnv
from envs.fighting2d import constants as C
from envs.registry import EnvConfig, wrap_env
from envs.retro_adapter import RetroFightingEnv, load_spec

E = C.encode_input
GENESIS = ["B", "A", "MODE", "START", "UP", "DOWN", "LEFT", "RIGHT", "C", "Y", "X", "Z"]


class FakeRetroEnv:
    """玩家 1 每按一次 A，对手掉 10 血；x 坐标随左右移动。"""

    def __init__(self, players):
        self.players = players
        self.buttons = GENESIS
        self.unwrapped = self
        self.log = []

    def reset(self, seed=None):
        self.hp = [100, 100]
        self.x = [100, 200]
        self.t = 0
        return np.zeros((4, 4, 3), np.uint8), self._info()

    def _info(self):
        return {"health": self.hp[0], "enemy_health": self.hp[1], "x_position": self.x[0],
                "enemy_x_position": self.x[1], "y_position": 0, "enemy_y_position": 0,
                "rounds_won": 0, "enemy_rounds_won": 0}

    def step(self, act):
        act = np.asarray(act)
        self.log.append(act.copy())
        n = len(GENESIS)
        for p in range(self.players):
            a = act[p * n:(p + 1) * n]
            if a[GENESIS.index("A")]:
                self.hp[1 - p] = max(0, self.hp[1 - p] - 10)
            self.x[p] += int(a[GENESIS.index("RIGHT")]) - int(a[GENESIS.index("LEFT")])
        self.t += 1
        return np.zeros((4, 4, 3), np.uint8), 0.0, False, False, self._info()

    def close(self):
        pass


fake_retro = types.SimpleNamespace(make=lambda game, players=1, state=None, **kw: FakeRetroEnv(players))


def test_relative_to_absolute_mirror():
    assert to_absolute(E(6, 1), True) == (6, 1)
    assert to_absolute(E(6, 1), False) == (4, 1)
    assert to_absolute(E(3, 0), False) == (1, 0)


def test_retro_button_mapping_and_reward():
    env = RetroFightingEnv("mk2_genesis", retro_module=fake_retro, two_player=False)
    obs, _ = env.reset(seed=0)
    assert obs.shape == env.observation_space.shape
    o, r, done, _, info = env.step(E(6, C.BTN_L))  # 朝右：前 = RIGHT，L = A
    pad = env.retro_env.log[-1]
    assert pad[GENESIS.index("RIGHT")] == 1 and pad[GENESIS.index("A")] == 1 and pad[GENESIS.index("LEFT")] == 0
    assert np.isclose(r, 10 / 120)
    for _ in range(20):
        o, r, done, _, info = env.step(E(5, C.BTN_L))
        if done:
            break
    assert done and info["outcome"] == 1.0 and info["end_reason"] == "ko"


def test_retro_two_player_with_policy_opponent_view():
    class Opp:
        name = "fake_opp"

        def reset(self, seed=None):
            pass

        def act(self, core, idx):
            obs = core.observe(idx)  # PolicyOpponent 的用法：对手视角的观测
            assert obs.shape[0] == 9
            return E(6, 0)  # 对手"向前" = 朝左走

    env = RetroFightingEnv("mk2_genesis", opponent=Opp(), retro_module=fake_retro)
    env.reset(seed=0)
    env.step(E(5, 0))
    pad = env.retro_env.log[-1]
    n = len(GENESIS)
    assert pad[n + GENESIS.index("LEFT")] == 1  # P2 在右边，"前"是左


def test_retro_works_under_wrapper_stack():
    env = wrap_env(RetroFightingEnv("mk2_genesis", retro_module=fake_retro, two_player=False),
                   EnvConfig(game="retro", delay_ms=100))
    o, _ = env.reset(seed=0)
    o2, r, d, _, info = env.step(env.action_space.n - 1)  # 宏 623H
    assert o2.shape == o.shape


# ---------------- DIAMBRA ----------------
class FakeDiambraEnv:
    def __init__(self, two_player):
        self.two = two_player
        self.acts = []

    def _obs(self):
        return {"frame": np.zeros((4, 4, 3)), "stage": np.array([1]), "timer": np.array([60]),
                "P1": {"health": np.array([self.hp[0]]), "side": np.array([0]), "wins": np.array([0])},
                "P2": {"health": np.array([self.hp[1]]), "side": np.array([1]), "wins": np.array([0])}}

    def reset(self, seed=None, options=None):
        self.hp = [125, 125]
        return self._obs(), {}

    def step(self, act):
        self.acts.append(act)
        a0 = act["agent_0"] if self.two else act
        if a0[1] != 0:
            self.hp[1] -= 25
        done = self.hp[1] <= 0
        return self._obs(), 0.0, False, False, {"round_done": done}

    def close(self):
        pass


class _Settings:
    pass


def make_fake_arena():
    ns = types.SimpleNamespace()
    ns.EnvironmentSettings = _Settings
    ns.EnvironmentSettingsMultiAgent = _Settings
    ns.SpaceTypes = types.SimpleNamespace(MULTI_DISCRETE="MULTI_DISCRETE", DISCRETE="DISCRETE")
    ns.Roles = types.SimpleNamespace(P1="P1", P2="P2")
    ns.made = []

    def make(game, settings, **kw):
        assert settings.step_ratio == 1
        e = FakeDiambraEnv(two_player=not hasattr(settings, "role"))
        ns.made.append((game, settings, e))
        return e

    ns.make = make
    return ns


def test_diambra_mapping_and_round_end():
    arena = make_fake_arena()
    env = DiambraFightingEnv("samsh5sp_diambra", arena_module=arena)
    env.reset(seed=0)
    o, r, d, _, info = env.step(E(9, C.BTN_H))  # 朝右：前上 = 右上(4)，H = 5（强斩）
    assert env.denv.acts[-1] == [4, 5]
    assert np.isclose(r, 25 / 125)
    for _ in range(10):
        o, r, d, _, info = env.step(E(5, C.BTN_L))
        if d:
            break
    assert d and info["outcome"] == 1.0
    assert load_spec("samsh5sp_diambra")["hp_max"] == 125


def test_diambra_two_player_dict_actions():
    arena = make_fake_arena()

    class Opp:
        name = "o"

        def reset(self, seed=None):
            pass

        def act(self, core, idx):
            return E(6, 0)

    env = DiambraFightingEnv("kof98umh_diambra", opponent=Opp(), arena_module=arena)
    env.reset(seed=0)
    env.step(E(4, 0))
    a = env.denv.acts[-1]
    assert a["agent_0"] == [1, 0]   # P1 朝右，后 = 左(1)
    assert a["agent_1"] == [1, 0]   # P2 朝左，前 = 左(1)


def test_ppo_end_to_end_on_retro_backend_with_fake_module(monkeypatch):
    """--game retro --mode cpu 的整条链路：EnvFactory -> 包装器栈 -> 向量环境 -> PPO 更新。"""
    import sys

    from agents.ppo import PPOConfig, PPOTrainer
    from common.vec_env import SyncVecEnv
    from envs.registry import EnvFactory

    fake_mod = types.ModuleType("stable_retro")
    fake_mod.make = lambda game, players=1, state=None, **kw: FakeRetroEnv(players)
    monkeypatch.setitem(sys.modules, "stable_retro", fake_mod)
    cfg = EnvConfig(game="retro", game_id="mk2_genesis")
    venv = SyncVecEnv([EnvFactory(cfg, None, seed=i) for i in range(2)])
    tr = PPOTrainer(venv, PPOConfig(total_steps=256, num_envs=2, n_steps=64, n_minibatches=2, hidden=32))
    tr.train()
    assert tr.global_step == 256
    assert len(tr.episodes) > 0 and "outcome" in tr.episodes[0]
