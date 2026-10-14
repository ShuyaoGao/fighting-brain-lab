"""Gymnasium 接口：

- `Fighting2DEnv`：单智能体视角，一个 step = 一帧，对手（脚本或策略）内嵌在环境里。
  跳帧、反应延迟、APM 限制、指令宏都由 wrappers/ 叠加，和真实游戏适配器共用同一套包装器。
- `Fighting2DDuel`：双人原始接口（自博弈/联赛评估用），step(a0, a1) 同时推进一帧。
"""
from typing import Optional

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from . import constants as C
from .core import OBS_DIM, FightingCore


class Opponent:
    """对手接口：每帧调用一次 act(core, idx) -> 0..26 的逐帧输入。"""

    name = "opponent"

    def reset(self, seed: Optional[int] = None):
        pass

    def act(self, core: FightingCore, idx: int) -> int:  # pragma: no cover - 接口
        raise NotImplementedError


class IdleOpponent(Opponent):
    name = "idle"

    def act(self, core, idx):
        return 0


class Fighting2DEnv(gym.Env):
    metadata = {"render_modes": ["rgb_array"], "render_fps": C.FPS}

    def __init__(self, opponent: Optional[Opponent] = None, round_seconds: float = C.DEFAULT_ROUND_SECONDS,
                 random_side: bool = True, damage_reward: float = 1.0, win_reward: float = 1.0,
                 time_penalty: float = 0.0, obs_type: str = "ram", render_mode: Optional[str] = None,
                 render_scale: int = 2, show_boxes: bool = False, seed: Optional[int] = None,
                 visible_only: bool = False):
        super().__init__()
        self.core = FightingCore(round_seconds=round_seconds, seed=seed)
        self.opponent = opponent if opponent is not None else IdleOpponent()
        self.random_side = random_side
        self.damage_reward = damage_reward
        self.win_reward = win_reward
        self.time_penalty = time_penalty
        self.obs_type = obs_type
        self.render_mode = render_mode
        self.render_scale = render_scale
        self.show_boxes = show_boxes
        self.visible_only = visible_only
        self.me = 0
        self._rng = np.random.default_rng(seed)
        self.action_space = spaces.Discrete(C.N_FRAME_INPUTS)
        if obs_type == "ram":
            self.observation_space = spaces.Box(-np.inf, np.inf, shape=(OBS_DIM,), dtype=np.float32)
        elif obs_type == "pixels":
            self.observation_space = spaces.Box(0, 255, shape=(C.STAGE_H, int(C.STAGE_W), 3), dtype=np.uint8)
        else:
            raise ValueError(obs_type)

    # 对手可以在回合之间更换（联赛用）
    def set_opponent(self, opponent: Opponent):
        self.opponent = opponent

    def _obs(self):
        if self.obs_type == "ram":
            return self.core.observe(self.me, self.visible_only)
        from .render import render_core
        return render_core(self.core, scale=1)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
            self.core.seed(seed)
        self.core.reset()
        self.me = int(self._rng.integers(2)) if self.random_side else 0
        self.opponent.reset(None if seed is None else seed + 1)
        return self._obs(), {"side": self.me, "opponent": getattr(self.opponent, "name", "?")}

    def step(self, action):
        core = self.core
        op_in = self.opponent.act(core, 1 - self.me)
        a = int(action)
        if self.me == 0:
            dealt, taken = core.step(a, op_in)
        else:
            taken, dealt = core.step(op_in, a)
        r = self.damage_reward * (dealt - taken) / C.MAX_HP - self.time_penalty
        info = {}
        terminated = core.done
        if terminated:
            w = core.winner
            outcome = 0.5 if w == -1 else (1.0 if w == self.me else 0.0)
            r += self.win_reward * (2 * outcome - 1)
            info = {
                "outcome": outcome, "end_reason": core.end_reason, "frames": core.frame,
                "hp_me": core.f[self.me].hp, "hp_op": core.f[1 - self.me].hp,
                "stats_me": core.stats[self.me], "stats_op": core.stats[1 - self.me],
                "opponent": getattr(self.opponent, "name", "?"),
            }
        return self._obs(), float(r), terminated, False, info

    def render(self):
        from .render import render_core
        labels = ("AGENT", "CPU") if self.me == 0 else ("CPU", "AGENT")
        return render_core(self.core, show_boxes=self.show_boxes, labels=labels, scale=self.render_scale)


class Fighting2DDuel:
    """双人原始接口（不走 gym），给自博弈评估/录像用。"""

    def __init__(self, round_seconds=C.DEFAULT_ROUND_SECONDS, seed=None):
        self.core = FightingCore(round_seconds=round_seconds, seed=seed)

    def reset(self, seed=None):
        if seed is not None:
            self.core.seed(seed)
        self.core.reset()
        return self.core.observe(0), self.core.observe(1)

    def step(self, a0: int, a1: int):
        d0, d1 = self.core.step(int(a0), int(a1))
        return (self.core.observe(0), self.core.observe(1)), (d0, d1), self.core.done
