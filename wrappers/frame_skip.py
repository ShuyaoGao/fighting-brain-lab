"""跳帧 + 指令宏 + 动作历史（智能体层包装器）。"""
from collections import deque

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from .macros import MACROS, N_BASE, expand, release


class FrameSkip(gym.Wrapper):
    """一个智能体 step = k 帧（或一段宏序列）。奖励在这些帧上求和。

    step(action) 接受：
      - int：基本输入，tap 语义（按键只按第一帧）；
      - list[int]：逐帧输入序列（由 MacroActions 传入）。
    info 里给出 `frames`（本步实际推进的帧数）和 `inputs`（逐帧输入，用于 APM 统计/回放）。
    """

    def __init__(self, env, k: int = 4, tap: bool = True):
        super().__init__(env)
        self.k = int(k)
        self.tap = tap

    def step(self, action):
        if isinstance(action, (list, tuple)):
            seq = list(action)
            if len(seq) < self.k:
                fill = release(seq[-1]) if self.tap else seq[-1]
                seq = seq + [fill] * (self.k - len(seq))
        else:
            seq = expand(int(action), self.k, tap=self.tap, macros=False)
        total = 0.0
        info = {}
        obs = None
        terminated = truncated = False
        n = 0
        for a in seq:
            obs, r, terminated, truncated, info = self.env.step(a)
            total += r
            n += 1
            if terminated or truncated:
                break
        info = dict(info)
        info["frames"] = n
        return obs, total, terminated, truncated, info


class MacroActions(gym.Wrapper):
    """动作空间 = 27 个基本输入 + 指令宏（必须包在 FrameSkip 外面）。"""

    def __init__(self, env):
        super().__init__(env)
        self._names = list(MACROS)
        self.action_space = spaces.Discrete(N_BASE + len(self._names))

    def step(self, action):
        action = int(action)
        if action >= N_BASE:
            return self.env.step(list(MACROS[self._names[action - N_BASE]]))
        return self.env.step(action)


class ActionHistory(gym.Wrapper):
    """把自己最近 n 个智能体层动作（one-hot）拼到观测后面。

    在有观测延迟时，这相当于"我知道自己刚才按了什么"——人类玩家同样知道。
    """

    def __init__(self, env, n: int = 4):
        super().__init__(env)
        self.n = int(n)
        self.na = int(env.action_space.n)
        low = np.concatenate([env.observation_space.low, np.zeros(self.n * self.na, np.float32)])
        high = np.concatenate([env.observation_space.high, np.ones(self.n * self.na, np.float32)])
        self.observation_space = spaces.Box(low, high, dtype=np.float32)
        self.hist = deque(maxlen=self.n)

    def _aug(self, obs):
        h = np.zeros((self.n, self.na), np.float32)
        for i, a in enumerate(self.hist):
            h[i, a] = 1.0
        return np.concatenate([obs.astype(np.float32), h.ravel()])

    def reset(self, **kw):
        obs, info = self.env.reset(**kw)
        self.hist.clear()
        return self._aug(obs), info

    def step(self, action):
        obs, r, te, tr, info = self.env.step(action)
        self.hist.append(int(action))
        return self._aug(obs), r, te, tr, info
