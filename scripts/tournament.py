"""循环赛 + Bradley–Terry Elo（带 bootstrap 95% CI）。

  # 某次联赛训练的所有快照 + 脚本 CPU，算 Elo 演化
  python scripts/tournament.py --snapshots runs/exp2_league/seed0/snapshots --scripted random greedy counter masher \
      --games 40 --out results/exp2_league/tournament_seed0

  # 多个最终模型交叉对战（延迟消融）
  python scripts/tournament.py --players d0_s0=runs/exp3/d0/seed0/snapshots/final.npz d200_s0=... --games 100 --out ...

产物：_env_stamp.json、games.csv（逐局原始记录）、result.json（Elo、CI、两两得分矩阵）。
"""
import argparse
import csv
import itertools
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from common.stamp import write_json, write_stamp  # noqa: E402
from eval.match import play_matches  # noqa: E402
from league.elo import bootstrap_bt, fit_bradley_terry  # noqa: E402


def load_snapshot(path):
    z = np.load(path, allow_pickle=False)
    w = {k: z[k] for k in z.files if k != "_meta"}
    return w, json.loads(str(z["_meta"]))


def _job(args):
    (na, sa), (nb, sb), games, seed, rs = args
    res, outcomes = play_matches(sa, sb, n=games, seed=seed, round_seconds=rs)
    return na, nb, outcomes, res["apm_a"], res["apm_b"]


def run_tournament(players, games, procs=8, seed=0, round_seconds=30.0, pairs=None):
    """players: [(name, spec)]。返回逐局记录 [(a, b, score_a)] 与每人的平均 APM。"""
    pairs = pairs or list(itertools.combinations(range(len(players)), 2))
    jobs = [(players[i], players[j], games, seed * 100003 + k, round_seconds) for k, (i, j) in enumerate(pairs)]
    recs, apm = [], {}
    with mp.get_context("spawn").Pool(procs) as pool:
        for na, nb, outcomes, apm_a, apm_b in pool.imap_unordered(_job, jobs):
            recs += [(na, nb, o) for o in outcomes]
            apm.setdefault(na, []).append(apm_a)
            apm.setdefault(nb, []).append(apm_b)
    return recs, {k: float(np.mean(v)) for k, v in apm.items()}


def summarize(names, recs, anchor=None, n_boot=200):
    agg = {}
    for a, b, s in recs:
        agg.setdefault((a, b), [0.0, 0])
        agg[(a, b)][0] += s
        agg[(a, b)][1] += 1
    elo = fit_bradley_terry(names, [(a, b, v[0], v[1]) for (a, b), v in agg.items()], anchor=anchor)
    ci = bootstrap_bt(names, recs, anchor=anchor, n_boot=n_boot) if n_boot > 0 else {}
    matrix = {}
    for (a, b), (sc, n) in agg.items():
        matrix.setdefault(a, {})[b] = sc / n
        matrix.setdefault(b, {})[a] = 1 - sc / n
    return elo, ci, matrix


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshots", nargs="*", default=[], help="快照目录（取其中 snap_*.npz 与 final.npz）")
    ap.add_argument("--players", nargs="*", default=[], help="name=path.npz")
    ap.add_argument("--scripted", nargs="*", default=["random", "greedy", "counter", "masher"])
    ap.add_argument("--games", type=int, default=40)
    ap.add_argument("--procs", type=int, default=8)
    ap.add_argument("--anchor", default="random")
    ap.add_argument("--boot", type=int, default=200)
    ap.add_argument("--every", type=int, default=1, help="快照目录里每隔几个取一个")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    write_stamp(out, {"run": "tournament", "args": vars(a)})
    players, meta = [], {}
    for d in a.snapshots:
        d = Path(d)
        files = sorted(d.glob("snap_*.npz"))[::a.every]
        if (d / "final.npz").exists():
            files.append(d / "final.npz")
        for f in files:
            w, m = load_snapshot(f)
            name = f"{d.parent.name}/{f.stem}" if len(a.snapshots) > 1 else f.stem
            players.append((name, {"kind": "policy", "name": name, "weights": w, "env_cfg": m["env_cfg"]}))
            meta[name] = {"global_step": m.get("global_step"), "path": str(f), "delay_ms": m["env_cfg"].get("delay_ms")}
    for p in a.players:
        name, path = p.split("=", 1)
        w, m = load_snapshot(path)
        players.append((name, {"kind": "policy", "name": name, "weights": w, "env_cfg": m["env_cfg"]}))
        meta[name] = {"global_step": m.get("global_step"), "path": path, "delay_ms": m["env_cfg"].get("delay_ms")}
    for s in a.scripted:
        players.append((s, {"kind": "scripted", "name": s}))
        meta[s] = {"scripted": True}
    names = [n for n, _ in players]
    t0 = time.time()
    print(f"{len(players)} 名选手，{len(names) * (len(names) - 1) // 2} 对，每对 {a.games} 局", flush=True)
    recs, apm = run_tournament(players, a.games, a.procs, a.seed)
    with open(out / "games.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["a", "b", "score_a"])
        w.writerows(recs)
    anchor = a.anchor if a.anchor in names else None
    elo, ci, matrix = summarize(names, recs, anchor=anchor, n_boot=a.boot)
    result = {"players": meta, "elo": elo, "elo_ci95": ci, "anchor": anchor, "games_per_pair": a.games,
              "n_games": len(recs), "apm": apm, "score_matrix": matrix, "wall_clock_s": round(time.time() - t0, 1)}
    write_json(out / "result.json", result)
    for n in sorted(names, key=lambda n: -elo[n]):
        c = ci.get(n, [float("nan")] * 2)
        print(f"{n:>28s}  Elo {elo[n]:7.1f}  [{c[0]:7.1f}, {c[1]:7.1f}]  APM {apm.get(n, 0):6.0f}")


if __name__ == "__main__":
    main()
