"""把 AI 限制到"人类条件"的逐帧包装器（必须包在 FrameSkip 里面，即直接包基础环境）。

- ObservationDelay：反应延迟。智能体看到的是 d 帧之前的画面/状态（60FPS 下 12 帧 = 200ms）。
- StickyActions：以概率 p 本帧沿用上一帧的输入（模拟手指的不精确，Machado et al. 2018 的 ALE 做法）。
- APMLimit：令牌桶限制每分钟操作数（方向变化 + 新按键各算 1 次），同时统计实际 APM。
"""
from collections import deque
from typing import Optional

import gymnasium as gym
import numpy as np

from envs.fighting2d.constants import FPS, decode_input


def ms_to_frames(ms: float, fps: int = FPS) -> int:
    return int(round(ms * fps / 1000.0))


class ObservationDelay(gym.Wrapper):
    def __init__(self, env, delay_frames: int = 12):
        super().__init__(env)
        self.d = int(delay_frames)
        self.buf = deque(maxlen=self.d + 1)

    def reset(self, **kw):
        obs, info = self.env.reset(**kw)
        self.buf.clear()
        for _ in range(self.d + 1):
            self.buf.append(obs)
        return self.buf[0], info

    def step(self, action):
        obs, r, te, tr, info = self.env.step(action)
        self.buf.append(obs)
        return self.buf[0], r, te, tr, info


class StickyActions(gym.Wrapper):
    def __init__(self, env, p: float = 0.25, seed: Optional[int] = None):
        super().__init__(env)
        self.p = float(p)
        self.rng = np.random.default_rng(seed)
        self.prev = 0

    def reset(self, **kw):
        self.prev = 0
        return self.env.reset(**kw)

    def step(self, action):
        a = int(action)
        if self.p > 0 and self.rng.random() < self.p:
            a = self.prev
        self.prev = a
        return self.env.step(a)


def input_cost(prev: int, cur: int) -> int:
    """一次逐帧输入相对上一帧的"操作数"：方向变化 1 + 新按下的键 1。"""
    pd, pb = decode_input(prev)
    cd, cb = decode_input(cur)
    return int(cd != pd) + int(cb != 0 and cb != pb)


class APMLimit(gym.Wrapper):
    """apm=None 时只统计不限制。episode 结束时 info['apm'] 给出实际 APM。"""

    def __init__(self, env, apm: Optional[float] = 300.0, burst: float = 4.0, fps: int = FPS):
        super().__init__(env)
        self.apm = apm
        self.burst = float(burst)
        self.rate = (apm / 60.0 / fps) if apm else None
        self.fps = fps

    def reset(self, **kw):
        self.prev = 0
        self.tokens = self.burst
        self.actions = 0
        self.frames = 0
        self.blocked = 0
        return self.env.reset(**kw)

    def step(self, action):
        a = int(action)
        cost = input_cost(self.prev, a)
        if self.rate is not None:
            self.tokens = min(self.burst, self.tokens + self.rate)
            if cost > 0:
                if self.tokens >= cost:
                    self.tokens -= cost
                else:
                    a, cost = self.prev, 0
                    self.blocked += 1
        self.actions += cost
        self.frames += 1
        self.prev = a
        obs, r, te, tr, info = self.env.step(a)
        if te or tr:
            info = dict(info)
            info["apm"] = self.actions / max(self.frames / self.fps / 60.0, 1e-9)
            info["apm_blocked_frames"] = self.blocked
        return obs, r, te, tr, info
