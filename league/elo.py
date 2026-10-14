"""Elo 评分：在线更新（训练中看趋势）+ Bradley–Terry 最大似然拟合（循环赛后的正式评分）。"""
import math
from collections import defaultdict

import numpy as np
from scipy.optimize import minimize

ELO_SCALE = 400.0 / math.log(10.0)  # Elo 分差 = ELO_SCALE * logit 差


def expected(ra, rb):
    return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))


class EloTracker:
    """在线 Elo。fixed 里的玩家（如脚本锚点）分数不变。"""

    def __init__(self, k=16.0, init=1000.0, fixed=None):
        self.k = k
        self.init = init
        self.r = defaultdict(lambda: init)
        self.fixed = dict(fixed or {})
        for n, v in self.fixed.items():
            self.r[n] = v
        self.games = defaultdict(int)

    def update(self, a, b, score_a):
        ea = expected(self.r[a], self.r[b])
        if a not in self.fixed:
            self.r[a] += self.k * (score_a - ea)
        if b not in self.fixed:
            self.r[b] += self.k * ((1 - score_a) - (1 - ea))
        self.games[a] += 1
        self.games[b] += 1

    def ratings(self):
        return dict(self.r)


def fit_bradley_terry(names, results, anchor=None, anchor_value=0.0, l2=1e-3):
    """results: [(a, b, score_a_total, n_games), ...]，平局按 0.5 计入 score。
    返回 {name: elo}，anchor 的分数固定为 anchor_value（默认均值 0）。"""
    idx = {n: i for i, n in enumerate(names)}
    A = np.array([idx[r[0]] for r in results])
    Bi = np.array([idx[r[1]] for r in results])
    S = np.array([r[2] for r in results], float)
    N = np.array([r[3] for r in results], float)

    def nll(theta):
        d = theta[A] - theta[Bi]
        p = 1 / (1 + np.exp(-d))
        p = np.clip(p, 1e-9, 1 - 1e-9)
        ll = S * np.log(p) + (N - S) * np.log(1 - p)
        g = np.zeros_like(theta)
        resid = S - N * p
        np.add.at(g, A, resid)
        np.add.at(g, Bi, -resid)
        return -ll.sum() + l2 * (theta ** 2).sum(), -g + 2 * l2 * theta

    res = minimize(nll, np.zeros(len(names)), jac=True, method="L-BFGS-B")
    theta = res.x
    elo = theta * ELO_SCALE
    if anchor is not None:
        elo = elo - elo[idx[anchor]] + anchor_value
    else:
        elo = elo - elo.mean() + anchor_value
    return {n: float(elo[idx[n]]) for n in names}


def bootstrap_bt(names, game_records, anchor=None, n_boot=200, seed=0):
    """game_records: [(a, b, score_a)] 逐局记录。按局重采样，返回每人 Elo 的 95% 区间。"""
    rng = np.random.default_rng(seed)
    recs = list(game_records)
    samples = defaultdict(list)
    for _ in range(n_boot):
        pick = rng.integers(len(recs), size=len(recs))
        agg = defaultdict(lambda: [0.0, 0])
        for i in pick:
            a, b, s = recs[i]
            agg[(a, b)][0] += s
            agg[(a, b)][1] += 1
        r = fit_bradley_terry(names, [(a, b, v[0], v[1]) for (a, b), v in agg.items()], anchor=anchor)
        for n, v in r.items():
            samples[n].append(v)
    return {n: [float(np.quantile(v, 0.025)), float(np.quantile(v, 0.975))] for n, v in samples.items()}
