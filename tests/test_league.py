import numpy as np

from eval.match import play_matches
from eval.stats import summarize_outcomes, wilson
from league.elo import EloTracker, bootstrap_bt, expected, fit_bradley_terry
from league.pool import OpponentPool, make_opponent


def test_bradley_terry_recovers_ratings():
    rng = np.random.default_rng(0)
    true = {"a": 0.0, "b": 200.0, "c": 400.0, "d": -150.0}
    names = list(true)
    recs, games = [], []
    for i, x in enumerate(names):
        for y in names[i + 1:]:
            p = expected(true[x], true[y])
            wins = rng.binomial(1, p, size=400)
            recs.append((x, y, float(wins.sum()), 400))
            games += [(x, y, float(w)) for w in wins[:60]]
    est = fit_bradley_terry(names, recs, anchor="a")
    for n in names:
        assert abs(est[n] - true[n]) < 45, (n, est[n], true[n])
    ci = bootstrap_bt(names, games, anchor="a", n_boot=30)
    assert ci["a"] == [0.0, 0.0] and ci["c"][0] < ci["c"][1]


def test_online_elo_direction():
    e = EloTracker(fixed={"anchor": 0.0})
    for _ in range(50):
        e.update("x", "anchor", 1.0)
    assert e.r["x"] > 100 and e.r["anchor"] == 0.0


def test_wilson_and_summary():
    lo, hi = wilson(50, 100)
    assert lo < 0.5 < hi
    s = summarize_outcomes([1, 1, 0.5, 0])
    assert s["wins"] == 2 and s["draws"] == 1 and s["losses"] == 1 and abs(s["score"] - 0.625) < 1e-9


def test_pool_samples_by_probability():
    pool = OpponentPool([{"kind": "scripted", "name": "random"}, {"kind": "scripted", "name": "greedy"}],
                        probs=[0.9, 0.1], seed=0)
    names = []
    for _ in range(300):
        pool.reset()
        names.append(pool.name)
    frac = names.count("random") / len(names)
    assert 0.83 < frac < 0.96


def test_scripted_difficulty_gradient():
    """counter（防守反击）应明显强于 random；greedy 应强于 random。"""
    r1, _ = play_matches("counter", "random", n=40, seed=1)
    r2, _ = play_matches("greedy", "random", n=40, seed=1)
    assert r1["score"] > 0.7 and r2["score"] > 0.7


def test_make_opponent_specs():
    assert make_opponent("greedy").name == "greedy"
    assert make_opponent({"kind": "scripted", "name": "counter", "label": "cpu"}).name == "cpu"
