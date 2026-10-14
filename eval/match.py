"""对战评估：两个"玩家"（脚本 CPU 或策略快照，统一用 spec 描述）在格斗核心上直接对打。

不走 gym 包装器，省开销；策略玩家用 PolicyOpponent 复现训练时同一条人类条件管线
（tests/test_policy_opponent.py 验证了二者逐帧一致）。
"""
from collections import defaultdict

import numpy as np

from envs.fighting2d.core import FightingCore
from league.pool import make_opponent, spec_name
from wrappers.human import input_cost

from .stats import summarize_outcomes


def play_matches(spec_a, spec_b, n: int = 100, seed: int = 0, round_seconds: float = 30.0,
                 swap_sides: bool = True):
    """A 对 B 打 n 回合（默认左右交替）。返回 A 视角的结果统计。"""
    pa = make_opponent(spec_a, seed=seed * 2 + 1)
    pb = make_opponent(spec_b, seed=seed * 2 + 2)
    core = FightingCore(round_seconds=round_seconds, seed=seed)
    outcomes, kos, hp_diff, apm_a, apm_b = [], [], [], [], []
    stats_a = defaultdict(float)
    rng = np.random.default_rng(seed)
    for ep in range(n):
        side_a = (ep % 2) if swap_sides else 0
        core.reset()
        pa.reset(int(rng.integers(1 << 30)))
        pb.reset(int(rng.integers(1 << 30)))
        prev = [0, 0]
        acts = [0, 0]
        while not core.done:
            ia = pa.act(core, side_a)
            ib = pb.act(core, 1 - side_a)
            ins = (ia, ib) if side_a == 0 else (ib, ia)
            for p in (0, 1):
                acts[p] += input_cost(prev[p], ins[p])
                prev[p] = ins[p]
            core.step(*ins)
        w = core.winner
        outcomes.append(0.5 if w == -1 else (1.0 if w == side_a else 0.0))
        kos.append(core.end_reason == "ko")
        hp_diff.append((core.f[side_a].hp - core.f[1 - side_a].hp) / 1000.0)
        minutes = core.frame / 60.0 / 60.0
        apm_a.append(acts[side_a] / minutes)
        apm_b.append(acts[1 - side_a] / minutes)
        st = core.stats[side_a]
        for k in ("damage", "hits", "blocks", "throws"):
            stats_a[k] += st[k]
        stats_a["max_combo"] = max(stats_a["max_combo"], st["max_combo"])
        for mv, c in st["moves"].items():
            stats_a["move_" + mv] += c
    res = summarize_outcomes(outcomes)
    res.update({
        "a": spec_name(spec_a), "b": spec_name(spec_b), "ko_rate": float(np.mean(kos)),
        "hp_diff_mean": float(np.mean(hp_diff)), "apm_a": float(np.mean(apm_a)), "apm_b": float(np.mean(apm_b)),
        "per_round_a": {k: v / n for k, v in stats_a.items()},
    })
    return res, outcomes
