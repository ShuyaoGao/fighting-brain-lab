"""对手规格（spec）与对手池。

spec 是可 pickle 的小字典：
  {"kind": "scripted", "name": "greedy", "kwargs": {...}}
  {"kind": "policy",   "name": "snap_000123", "weights": {...}, "env_cfg": {...}}
  {"kind": "pool",     "entries": [spec, ...], "probs": [...]}   # 每回合按概率抽一个
"""
from typing import List, Optional

import numpy as np

from envs.fighting2d.env import Opponent


def make_opponent(spec, seed: Optional[int] = None) -> Opponent:
    if isinstance(spec, str):
        spec = {"kind": "scripted", "name": spec}
    kind = spec["kind"]
    if kind == "scripted":
        from agents.scripted import make_scripted
        bot = make_scripted(spec["name"], seed=seed, **spec.get("kwargs", {}))
        if "label" in spec:
            bot.name = spec["label"]
        return bot
    if kind == "policy":
        from agents.policy_opponent import PolicyOpponent
        return PolicyOpponent.from_spec(spec, seed=seed)
    if kind == "pool":
        return OpponentPool(spec["entries"], spec.get("probs"), seed=seed)
    raise ValueError(kind)


def spec_name(spec) -> str:
    if isinstance(spec, str):
        return spec
    return spec.get("label", spec.get("name", spec["kind"]))


class OpponentPool(Opponent):
    """每次 reset 按概率抽一个对手；支持训练中热更新（联赛加入新快照）。"""

    def __init__(self, entries: List[dict], probs=None, seed=None):
        self.rng = np.random.default_rng(seed)
        self._seed = seed
        self.cache = {}
        self.current = None
        self.name = "pool"
        self.set_pool(entries, probs)

    def set_pool(self, entries, probs=None):
        self.entries = list(entries)
        names = {spec_name(e) for e in self.entries}
        self.cache = {k: v for k, v in self.cache.items() if k in names}
        p = np.ones(len(self.entries)) if probs is None else np.asarray(probs, float)
        self.probs = p / p.sum()

    def reset(self, seed=None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        i = int(self.rng.choice(len(self.entries), p=self.probs))
        spec = self.entries[i]
        key = spec_name(spec)
        if key not in self.cache:
            self.cache[key] = make_opponent(spec, seed=int(self.rng.integers(1 << 30)))
        self.current = self.cache[key]
        self.current.reset(int(self.rng.integers(1 << 30)))
        self.name = key

    def act(self, core, idx):
        return self.current.act(core, idx)
