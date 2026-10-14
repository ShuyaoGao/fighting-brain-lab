"""把（numpy 化的）策略包装成逐帧对手，复现训练时智能体看到的同一条"人类条件"管线：
观测延迟 d 帧 -> 每 k 帧决策一次（宏按序列执行完）-> tap 语义 -> 动作历史拼接。

tests/test_policy_opponent.py 用确定性策略验证它和 gym 包装器栈逐帧一致。
"""
from collections import deque
from typing import Optional

import numpy as np

from envs.fighting2d.env import Opponent
from wrappers.macros import expand
from envs.fighting2d.constants import FPS
from wrappers.human import input_cost, ms_to_frames

from .numpy_policy import NumpyPolicy


class PolicyOpponent(Opponent):
    def __init__(self, policy: NumpyPolicy, frame_skip: int = 4, delay_ms: float = 0.0, macros: bool = True,
                 action_history: int = 4, deterministic: bool = False, name: str = "policy",
                 seed: Optional[int] = None, visible_only: bool = False, apm: Optional[float] = None,
                 apm_burst: float = 4.0):
        self.visible_only = visible_only
        self.apm_rate = (apm / 60.0 / FPS) if apm else None   # 与 wrappers.human.APMLimit 相同的令牌桶
        self.apm_burst = float(apm_burst)
        self.policy = policy
        self.k = int(frame_skip)
        self.d = ms_to_frames(delay_ms)
        self.macros = macros
        self.n_hist = int(action_history)
        self.n_actions = policy.n_actions
        self.deterministic = deterministic
        self.name = name
        self.rng = np.random.default_rng(seed)
        self.reset()

    @classmethod
    def from_spec(cls, spec: dict, seed=None):
        cfg = spec.get("env_cfg", {})
        return cls(NumpyPolicy(spec["weights"], spec.get("activation", "tanh"), masks=spec.get("masks")),
                   frame_skip=cfg.get("frame_skip", 4), delay_ms=cfg.get("delay_ms", 0.0),
                   macros=cfg.get("macros", True), action_history=cfg.get("action_history", 4),
                   deterministic=spec.get("deterministic", False), name=spec.get("name", "policy"), seed=seed,
                   visible_only=cfg.get("visible_only", False), apm=cfg.get("apm"))

    def reset(self, seed=None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        self.buf = deque(maxlen=self.d + 1)
        self.hist = deque(maxlen=max(self.n_hist, 1))
        self.queue = []
        self.fresh = True
        self.decisions = 0
        self.prev_in = 0
        self.tokens = self.apm_burst

    def _obs(self, raw):
        if self.n_hist <= 0:
            return raw
        h = np.zeros((self.n_hist, self.n_actions), np.float32)
        for i, a in enumerate(self.hist):
            h[i, a] = 1.0
        return np.concatenate([raw, h.ravel()])

    def act(self, core, idx):
        raw = core.observe(idx, self.visible_only) if self.visible_only else core.observe(idx)
        if self.fresh:
            for _ in range(self.d + 1):
                self.buf.append(raw)
            self.fresh = False
        else:
            self.buf.append(raw)
        if not self.queue:
            obs = self._obs(self.buf[0])
            a = self.policy.act(obs, rng=self.rng, deterministic=self.deterministic)
            self.queue = expand(a, self.k, tap=True, macros=self.macros)
            if self.n_hist > 0:
                self.hist.append(int(a))
            self.decisions += 1
        a = self.queue.pop(0)
        if self.apm_rate is not None:
            self.tokens = min(self.apm_burst, self.tokens + self.apm_rate)
            cost = input_cost(self.prev_in, a)
            if cost > 0:
                if self.tokens >= cost:
                    self.tokens -= cost
                else:
                    a = self.prev_in
        self.prev_in = a
        return a
