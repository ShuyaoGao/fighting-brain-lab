"""胜率统计：Wilson 置信区间（平局按 0.5 胜计入时用 bootstrap）。"""
import math

import numpy as np


def wilson(wins: float, n: int, z: float = 1.96):
    """Wilson score 区间。wins 可以是含 0.5 的"有效胜场"（近似）。"""
    if n == 0:
        return (float("nan"), float("nan"))
    p = wins / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


def bootstrap_ci(x, n_boot=2000, alpha=0.05, seed=0):
    x = np.asarray(x, float)
    if len(x) == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    means = rng.choice(x, size=(n_boot, len(x)), replace=True).mean(1)
    return (float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2)))


def summarize_outcomes(outcomes):
    """outcomes: 1=胜, 0.5=平, 0=负。返回胜率（平局算半场）和 95% CI。"""
    o = np.asarray(outcomes, float)
    n = len(o)
    wins = float((o == 1).sum())
    draws = float((o == 0.5).sum())
    score = float(o.mean()) if n else float("nan")
    lo, hi = wilson(wins + 0.5 * draws, n)
    return {"n": n, "wins": int(wins), "draws": int(draws), "losses": int(n - wins - draws),
            "score": score, "ci95": [lo, hi]}
