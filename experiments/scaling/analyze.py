"""规模实验分析：全体循环赛 BT-Elo、Elo vs 参数量、对脚本 CPU、利用者、算力对照。

  python -m experiments.scaling.analyze tournament --games 30 --procs 16   # 跑循环赛（耗时）
  python -m experiments.scaling.analyze report                             # 汇总 + 出图 + result.json

产物：results/scaling/{_env_stamp.json, games.csv, tournament.json, result.json, *.png}
"""
import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from common.stamp import write_json, write_stamp  # noqa: E402

RUNS = ROOT / "runs" / "scaling"
OUT = ROOT / "results" / "scaling"
BOTS = ["random", "greedy", "counter", "masher"]
BOT_CN = {"random": "随机 CPU", "greedy": "贪心进攻 CPU", "counter": "防守反击 CPU", "masher": "乱按基线"}
# 参考调色板（dataviz 技能的分类色，前三色全对 CVD 校验通过）
S1, S2, S3, S4 = "#2a78d6", "#eb6834", "#1baf7a", "#c98500"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def load_snapshot(path):
    z = np.load(path, allow_pickle=False)
    return {k: z[k] for k in z.files if k != "_meta"}, json.loads(str(z["_meta"]))


def models():
    """所有完成的规模实验模型：id -> 元信息。"""
    out = {}
    for rd in sorted(RUNS.glob("*/seed*")):
        if not (rd / "result.json").exists():
            continue
        cfg = json.loads((rd / "config.json").read_text(encoding="utf-8"))
        a = cfg["args"]
        name = rd.parent.name
        w, d = int(a["hidden"]), int(a.get("layers", 2))
        obs_dim, n_act = 214, 31
        n_actor = obs_dim * w + w + (d - 1) * (w * w + w) + w * n_act + n_act
        out[f"{name}_s{rd.name[4:]}"] = {
            "config": name, "seed": int(a["seed"]), "width": w, "depth": d, "steps": int(a["steps"]),
            "cond": "free" if not cfg["env_cfg"].get("apm") else "human", "params_actor": n_actor,
            "snapshot": str((rd / "snapshots" / "final.npz").relative_to(ROOT)).replace("\\", "/"),
            "wall_clock_s": json.loads((rd / "result.json").read_text(encoding="utf-8"))["wall_clock_s"]}
    return out


def setup_mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"], "axes.unicode_minus": False,
        "figure.dpi": 110, "savefig.dpi": 160, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
        "ytick.color": INK2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.spines.top": False,
        "axes.spines.right": False, "lines.linewidth": 2.0, "legend.frameon": False})
    return plt


# ------------------------------------------------------------------ 循环赛
def cmd_tournament(a):
    from scripts.tournament import run_tournament, summarize
    M = models()
    players = []
    for mid, m in M.items():
        w, meta = load_snapshot(ROOT / m["snapshot"])
        players.append((mid, {"kind": "policy", "name": mid, "weights": w, "env_cfg": meta["env_cfg"]}))
    for b in BOTS:
        players.append((b, {"kind": "scripted", "name": b}))
    OUT.mkdir(parents=True, exist_ok=True)
    write_stamp(OUT, {"run": "scaling tournament", "games_per_pair": a.games, "n_players": len(players)})
    print(f"{len(players)} 名选手，{len(players) * (len(players) - 1) // 2} 对，每对 {a.games} 局", flush=True)
    recs, apm = run_tournament(players, a.games, procs=a.procs, seed=11)
    names = [n for n, _ in players]
    elo, ci, matrix = summarize(names, recs, anchor="random", n_boot=a.boot)
    with open(OUT / "games.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["a", "b", "score_a"])
        wr.writerows(recs)
    write_json(OUT / "tournament.json", {"elo": elo, "elo_ci95": ci, "apm": apm, "score_matrix": matrix,
                                         "games_per_pair": a.games, "models": M})
    print("完成")


# ------------------------------------------------------------------ 汇总与出图
def group_stats(vals):
    v = np.asarray(vals, float)
    if len(v) == 0:
        return None
    se = v.std(ddof=1) / math.sqrt(len(v)) if len(v) > 1 else float("nan")
    from scipy.stats import t as tdist
    tq = float(tdist.ppf(0.975, len(v) - 1)) if len(v) > 1 else float("nan")
    return {"mean": float(v.mean()), "sd": float(v.std(ddof=1)) if len(v) > 1 else 0.0, "se": se,
            "ci95": [float(v.mean() - tq * se), float(v.mean() + tq * se)] if len(v) > 1 else None,
            "ci_method": "t 分布（种子间）",
            "n": int(len(v)), "values": [float(x) for x in v]}


def exploiter_results(base="scaling_exploit"):
    out = {}
    for rd in sorted((ROOT / "runs" / base).glob("*_seed0")):
        if (rd / "result.json").exists():
            r = json.loads((rd / "result.json").read_text(encoding="utf-8"))
            ev = []
            with open(rd / "eval_log.csv", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    ev.append([float(row["global_step"]), float(row["target_score"])])
            first = next((st for st, sc in ev if sc >= 0.5), None)
            out[rd.name.replace("_seed0", "")] = {"final": r["eval"]["target"]["score"], "ci95": r["eval"]["target"]["ci95"],
                                                  "curve": ev, "score_at_step0": ev[0][1] if ev else None,
                                                  "first_eval_step_over_0.5": first,
                                                  "env_cfg": {k: r["env_cfg"].get(k) for k in ("delay_ms", "apm")}}
    return out


def cmd_report(a):
    plt = setup_mpl()
    T = json.loads((OUT / "tournament.json").read_text(encoding="utf-8"))
    M, elo, ci, matrix = T["models"], T["elo"], T["elo_ci95"], T["score_matrix"]
    by_cfg = defaultdict(list)
    for mid, m in M.items():
        by_cfg[m["config"]].append(mid)

    def cfg_stats(cfg):
        ids = by_cfg.get(cfg, [])
        return {"elo": group_stats([elo[i] for i in ids]),
                "vs_scripted": {b: group_stats([matrix[i][b] for i in ids]) for b in BOTS},
                "apm": group_stats([T["apm"][i] for i in ids]),
                "params_actor": M[ids[0]]["params_actor"] if ids else None, "seeds": sorted(M[i]["seed"] for i in ids)}

    widths = [8, 16, 32, 64, 128, 256, 512]
    main = {w: cfg_stats(f"w{w}_d2_human") for w in widths}
    depth = {f"w{w}_d{d}": cfg_stats(f"w{w}_d{d}_human") for w in (32, 128) for d in (1, 2, 3)}
    free = {w: cfg_stats(f"w{w}_d2_free") for w in (16, 64, 256)}
    compute = {s: cfg_stats("w64_d2_human" + ("" if s == 8 else f"_{s}M")) for s in (2, 4, 8, 16)}
    expl_free = exploiter_results("scaling_exploit")
    expl_h = exploiter_results("scaling_exploit_human")
    # 宽度与 Elo 的秩相关（种子级别）
    from scipy.stats import spearmanr
    xs, ys = [], []
    for w in widths:
        for i in by_cfg.get(f"w{w}_d2_human", []):
            xs.append(M[i]["params_actor"]); ys.append(elo[i])
    rho = spearmanr(xs, ys) if len(xs) > 3 else None
    # 大网络 vs 小网络的直接对战（同条件，组 vs 组）
    def head2head(ca, cb):
        sc = [matrix[i][j] for i in by_cfg.get(ca, []) for j in by_cfg.get(cb, []) if j in matrix.get(i, {})]
        return float(np.mean(sc)) if sc else None
    h2h = {f"w{wa}_vs_w{wb}": head2head(f"w{wa}_d2_human", f"w{wb}_d2_human") for wa in widths for wb in widths if wa != wb}
    free_vs_human = {f"free_w{wf}_vs_human_w{wh}": head2head(f"w{wf}_d2_free", f"w{wh}_d2_human")
                     for wf in (16, 64, 256) for wh in widths}
    # 训练算力代理：策略参数量 × 训练步数（前向/反向 FLOPs 大致与之成正比；只用于同一族内比较）
    compute_proxy = {}
    for cfg, ids in by_cfg.items():
        m = M[ids[0]]
        compute_proxy[cfg] = {"params_actor": m["params_actor"], "steps": m["steps"],
                              "params_x_steps_1e9": m["params_actor"] * m["steps"] / 1e9,
                              "elo_mean": float(np.mean([elo[i] for i in ids]))}
    res = {"conditions": {"human": "200ms 观测延迟 + APM≤600（令牌桶容量 4），帧跳 4", "free": "0ms、不限 APM"},
           "budget_steps": 8_000_000, "games_per_pair": T["games_per_pair"], "anchor": "random=0",
           "width_axis": {str(w): main[w] for w in widths}, "depth_variants": depth,
           "free_controls": {str(w): free[w] for w in free}, "compute_control_w64": {str(s): compute[s] for s in compute},
           "exploiters_2M": expl_h, "exploiters_2M_note": "利用者与目标同为人类条件（200ms + APM≤600），256×2，2M 步，从零训练只打一个冻结目标（seed0）",
           "exploiters_2M_free": expl_free,
           "exploiters_2M_free_note": "0ms、不限 APM 的利用者：未训练（第 0 步）就能赢 8–32 宽的目标 80–95%，500k 步全部 100%，测的是条件不对等而不是可利用性",
           "spearman_params_vs_elo_seedlevel": None if rho is None else
           {"rho": float(rho.statistic), "p": float(rho.pvalue), "n": len(xs)},
           "head_to_head_width": h2h, "head_to_head_free_vs_human": free_vs_human, "compute_proxy": compute_proxy,
           "elo_by_model": {i: elo[i] for i in M}, "elo_ci95_by_model": {i: ci[i] for i in M},
           "elo_scripted": {b: elo[b] for b in BOTS}}
    write_json(OUT / "result.json", res)
    figs(plt, res, M, elo, ci)
    print(json.dumps({k: v for k, v in res.items() if k in ("spearman_params_vs_elo_seedlevel",)}, ensure_ascii=False))
    for w in widths:
        s = main[w]["elo"]
        if s:
            print(f"w{w:>3}: Elo {s['mean']:7.1f} ± {s['sd']:6.1f}  (n={s['n']})  vs counter {main[w]['vs_scripted']['counter']['mean']:.2f}")


def figs(plt, R, M, elo, ci):
    widths = [8, 16, 32, 64, 128, 256, 512]
    # 1) Elo vs 参数量
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    xs, ms, lo, hi = [], [], [], []
    for w in widths:
        s = R["width_axis"][str(w)]
        if not s["elo"]:
            continue
        p = s["params_actor"]
        for v in s["elo"]["values"]:
            ax.scatter(p, v, color=S1, alpha=0.35, s=18, zorder=2)
        xs.append(p); ms.append(s["elo"]["mean"])
        lo.append(s["elo"]["mean"] - (s["elo"]["ci95"][0] if s["elo"]["ci95"] else s["elo"]["mean"]))
        hi.append((s["elo"]["ci95"][1] if s["elo"]["ci95"] else s["elo"]["mean"]) - s["elo"]["mean"])
        ax.annotate(f"{w}", (p, s["elo"]["mean"]), xytext=(5, -12), textcoords="offset points", fontsize=8, color=INK2)
    ax.errorbar(xs, ms, yerr=[lo, hi], color=S1, marker="o", capsize=3, label="宽度轴（深度 2，人类条件）", zorder=3)
    for key, mk in (("w32_d1", "v"), ("w32_d3", "^"), ("w128_d1", "v"), ("w128_d3", "^")):
        s = R["depth_variants"].get(key)
        if s and s["elo"]:
            ax.errorbar([s["params_actor"]], [s["elo"]["mean"]], yerr=[[s["elo"]["mean"] - s["elo"]["ci95"][0]], [s["elo"]["ci95"][1] - s["elo"]["mean"]]]
                        if s["elo"]["ci95"] else None, color=S2, marker=mk, capsize=3, linestyle="none",
                        label="深度 1（▼）/ 3（▲）" if key == "w32_d1" else None, zorder=3)
    fx, fy = [], []
    for w, s in R["free_controls"].items():
        if s["elo"]:
            fx.append(s["params_actor"]); fy.append(s["elo"]["mean"])
    if fx:
        ax.plot(fx, fy, color=S3, marker="s", linestyle="--", label="无限制对照（0ms、不限 APM）", zorder=3)
    bv = list(R["elo_scripted"].values())
    ax.axhspan(min(bv), max(bv), color=INK2, alpha=0.12, lw=0, label="脚本 CPU 区间")
    ax.set_xscale("log")
    ax.set_xlabel("策略网络参数量（对数轴）")
    ax.set_ylabel("循环赛 BT-Elo（随机 CPU = 0）")
    ax.set_title("网络大小 vs 对抗强度（8M 步自博弈联赛；点 = 单种子，误差棒 = 种子间 95% CI，t 分布）", fontsize=9.5, color=INK)
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout(); fig.savefig(OUT / "elo_vs_params.png"); plt.close(fig)
    # 2) 对脚本 CPU 胜率 vs 参数量
    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    for b, col in zip(["random", "greedy", "counter"], (S1, S2, S3)):
        px, py = [], []
        for w in widths:
            s = R["width_axis"][str(w)]
            if s["elo"]:
                px.append(s["params_actor"]); py.append(s["vs_scripted"][b]["mean"])
        ax.plot(px, py, marker="o", color=col, label=BOT_CN[b])
    ax.set_xscale("log"); ax.set_ylim(-0.02, 1.02)
    ax.set_xlabel("策略网络参数量（对数轴）"); ax.set_ylabel("胜率（3 种子均值）")
    ax.set_title("人类条件下各大小网络对脚本 CPU 的胜率", fontsize=10, color=INK)
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout(); fig.savefig(OUT / "vs_scripted_vs_params.png"); plt.close(fig)
    # 3) 利用者
    E = R["exploiters_2M"]
    if E:
        import matplotlib as mpl
        fig, ax = plt.subplots(figsize=(7.6, 4.2))
        cmap = mpl.colormaps["viridis"]
        for i, w in enumerate(widths):
            k = f"w{w}_d2_human"
            if k in E and E[k]["curve"]:
                c = cmap(i / (len(widths) - 1) * 0.9)
                xs_ = [p[0] / 1e6 for p in E[k]["curve"]]; ys_ = [p[1] for p in E[k]["curve"]]
                ax.plot(xs_, ys_, marker="o", ms=3.5, color=c, label=f"目标 {w}×2")
        ax.axhline(0.5, color=INK2, linestyle="--", linewidth=1)
        ax.set_ylim(-0.02, 1.02); ax.set_xlim(0, 2.05)
        ax.set_xlabel("利用者训练步数（百万）"); ax.set_ylabel("利用者对目标的胜率（每点 40 局）")
        ax.set_title("同样是人类条件的利用者，针对每个大小的模型训练 2M 步", fontsize=10, color=INK)
        ax.legend(fontsize=7.5, ncol=4, loc="lower right")
        fig.tight_layout(); fig.savefig(OUT / "exploiter_vs_params.png"); plt.close(fig)
    # 4) 算力对照
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    sx, sy_, el, eh = [], [], [], []
    for s in ("2", "4", "8", "16"):
        st = R["compute_control_w64"][s]
        if st["elo"]:
            for v in st["elo"]["values"]:
                ax.scatter(int(s), v, color=S4, alpha=0.35, s=18)
            sx.append(int(s)); sy_.append(st["elo"]["mean"])
            el.append(st["elo"]["mean"] - (st["elo"]["ci95"][0] if st["elo"]["ci95"] else st["elo"]["mean"]))
            eh.append((st["elo"]["ci95"][1] if st["elo"]["ci95"] else st["elo"]["mean"]) - st["elo"]["mean"])
    if sx:
        ax.errorbar(sx, sy_, yerr=[el, eh], color=S4, marker="o", capsize=3)
    for w, col, ls in ((128, INK2, ":"), (256, S1, "--")):
        st = R["width_axis"][str(w)]["elo"]
        if st:
            ax.axhline(st["mean"], color=col, linestyle=ls, linewidth=1)
            ax.text(2.05, st["mean"] + 12, f"{w}×2 · 8M 步", fontsize=8, color=col)
    ax.set_xscale("log", base=2); ax.set_xticks([2, 4, 8, 16]); ax.set_xticklabels(["2M", "4M", "8M", "16M"])
    ax.set_xlabel("训练步数（同一网络：64×2）"); ax.set_ylabel("循环赛 BT-Elo")
    ax.set_title("算力对照：参数量不变，只加训练步数", fontsize=10, color=INK)
    fig.tight_layout(); fig.savefig(OUT / "compute_control.png"); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["tournament", "report"])
    ap.add_argument("--games", type=int, default=30)
    ap.add_argument("--procs", type=int, default=16)
    ap.add_argument("--boot", type=int, default=200)
    a = ap.parse_args()
    {"tournament": cmd_tournament, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    main()
