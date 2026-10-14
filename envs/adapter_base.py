"""真实游戏适配器的公共部分：把"模拟器 + RAM 地址表"包装成与自带小环境相同的接口。

和 Fighting2DEnv 保持一致的约定（所以 wrappers/、agents/、league/、eval/ 都能直接复用）：
- 一个 step = 一帧；动作 = 27 种相对方向逐帧输入（见 envs/fighting2d/constants.py）；
- 观测 = 从"我"的视角、左右镜像后的 RAM 特征向量；
- 奖励 = (造成伤害 - 受到伤害)/满血 + 回合胜负 ±1；回合结束 terminated=True；
- 结束时 info 里有 outcome / end_reason / opponent，供训练日志与评估统计；
- 双人模式下，对手（PolicyOpponent）通过 `self.view.observe(idx)` 拿到它自己视角的观测。

子类需要实现：_backend_reset()、_backend_step(abs_inputs)、_read_ram() -> RamState。
"""
from dataclasses import dataclass
from typing import List, Optional

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from envs.fighting2d.constants import BTN_H, BTN_L, N_FRAME_INPUTS, decode_input

# 相对方向 -> 绝对方向（朝右时不变，朝左时左右镜像）
_MIRROR = {1: 3, 2: 2, 3: 1, 4: 6, 5: 5, 6: 4, 7: 9, 8: 8, 9: 7}


def to_absolute(code: int, facing_right: bool):
    """统一逐帧输入 -> (绝对数字键盘方向, 按键)。"""
    d, b = decode_input(code)
    return (d if facing_right else _MIRROR[d]), b


def numpad_to_udlr(d: int):
    """绝对数字键盘方向 -> (up, down, left, right) 布尔。"""
    return (d in (7, 8, 9), d in (1, 2, 3), d in (1, 4, 7), d in (3, 6, 9))


@dataclass
class RamState:
    hp: List[float]                       # [P1, P2]
    hp_max: float
    x: Optional[List[float]] = None       # [P1, P2]，没有坐标地址时为 None
    y: Optional[List[float]] = None
    side: Optional[List[int]] = None      # 0=左 1=右（DIAMBRA 直接给）
    timer: Optional[float] = None
    timer_max: float = 99.0
    rounds: Optional[List[int]] = None
    extra: Optional[List[float]] = None   # 游戏特有的、已归一化的附加特征（每个玩家一组，按 [P1..., P2...]）
    round_over: bool = False
    winner: Optional[int] = None          # 0/1/-1，round_over 时有效


class RamView:
    """给对手用的鸭子类型"core"：只提供 observe(idx) 和 frame。"""

    def __init__(self, env):
        self.env = env

    @property
    def frame(self):
        return self.env.frame

    def observe(self, idx):
        return self.env.features(idx)


class ExternalFightingEnv(gym.Env):
    metadata = {"render_modes": ["rgb_array"], "render_fps": 60}
    N_EXTRA = 0

    def __init__(self, me: int = 0, opponent=None, damage_reward: float = 1.0, win_reward: float = 1.0,
                 max_frames: Optional[int] = None):
        super().__init__()
        self.me = me
        self.opponent = opponent           # None = 游戏内置 CPU（1P 模式）
        self.damage_reward = damage_reward
        self.win_reward = win_reward
        self.max_frames = max_frames
        self.view = RamView(self)
        self.action_space = spaces.Discrete(N_FRAME_INPUTS)
        self.observation_space = spaces.Box(-np.inf, np.inf, shape=(self.obs_dim(),), dtype=np.float32)
        self.frame = 0
        self.ram: Optional[RamState] = None

    # ---- 子类实现 ----
    def _backend_reset(self, seed=None):
        raise NotImplementedError

    def _backend_step(self, abs_inputs):
        """abs_inputs: [(numpad, button) for P1, (numpad, button) for P2 或 None]，推进一帧。"""
        raise NotImplementedError

    def _read_ram(self) -> RamState:
        raise NotImplementedError

    def render(self):
        return None

    # ---- 公共逻辑 ----
    @classmethod
    def obs_dim(cls):
        return 9 + 2 * cls.N_EXTRA

    def facing_right(self, idx):
        r = self.ram
        if r.x is not None:
            return r.x[idx] <= r.x[1 - idx]
        if r.side is not None:
            return r.side[idx] == 0
        return idx == 0  # 没有任何位置信息：假定 P1 在左（需要补 RAM 地址！）

    def features(self, idx):
        r = self.ram
        m = 1.0 if self.facing_right(idx) else -1.0
        hp_me, hp_op = r.hp[idx] / r.hp_max, r.hp[1 - idx] / r.hp_max
        if r.x is not None:
            dx = (r.x[1 - idx] - r.x[idx]) * m / 320.0
            xm = r.x[idx] / 320.0
        else:
            dx, xm = 0.0, 0.0
        dy = 0.0 if r.y is None else (r.y[1 - idx] - r.y[idx]) / 100.0
        t = 0.0 if r.timer is None else r.timer / r.timer_max
        rw = [0.0, 0.0] if r.rounds is None else [r.rounds[idx] / 2.0, r.rounds[1 - idx] / 2.0]
        out = [hp_me, hp_op, dx, abs(dx), dy, xm, t, *rw]
        if self.N_EXTRA:
            ex = r.extra or [0.0] * (2 * self.N_EXTRA)
            mine = ex[idx * self.N_EXTRA:(idx + 1) * self.N_EXTRA]
            theirs = ex[(1 - idx) * self.N_EXTRA:(2 - idx) * self.N_EXTRA]
            out += list(mine) + list(theirs)
        return np.asarray(out, dtype=np.float32)

    def set_opponent(self, opponent):
        self.opponent = opponent

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._backend_reset(seed)
        self.frame = 0
        self.ram = self._read_ram()
        if self.opponent is not None:
            self.opponent.reset(None if seed is None else seed + 1)
        return self.features(self.me), {"side": self.me, "opponent": self._opp_name()}

    def _opp_name(self):
        return getattr(self.opponent, "name", "game_cpu") if self.opponent is not None else "game_cpu"

    def step(self, action):
        prev = self.ram
        a_me = to_absolute(int(action), self.facing_right(self.me))
        a_op = None
        if self.opponent is not None:
            a_op = to_absolute(int(self.opponent.act(self.view, 1 - self.me)), self.facing_right(1 - self.me))
        inputs = [a_me, a_op] if self.me == 0 else [a_op, a_me]
        self._backend_step(inputs)
        self.frame += 1
        self.ram = r = self._read_ram()
        dealt = max(0.0, prev.hp[1 - self.me] - r.hp[1 - self.me]) / r.hp_max
        taken = max(0.0, prev.hp[self.me] - r.hp[self.me]) / r.hp_max
        rew = self.damage_reward * (dealt - taken)
        terminated = r.round_over or (self.max_frames is not None and self.frame >= self.max_frames)
        info = {}
        if terminated:
            w = r.winner
            if w is None:  # 超时且后端没给胜负：按血量判
                w = 0 if r.hp[0] > r.hp[1] else (1 if r.hp[1] > r.hp[0] else -1)
            outcome = 0.5 if w == -1 else (1.0 if w == self.me else 0.0)
            rew += self.win_reward * (2 * outcome - 1)
            info = {"outcome": outcome, "end_reason": "ko" if min(r.hp) <= 0 else "timeout",
                    "frames": self.frame, "opponent": self._opp_name()}
        return self.features(self.me), float(rew), terminated, False, info


def button_name(b):
    return {0: None, BTN_L: "L", BTN_H: "H"}[b]
