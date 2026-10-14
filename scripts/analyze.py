"""实验后处理：跑循环赛 -> 汇总 -> 画图 -> 写 results/*/result.json。

  python scripts/analyze.py exp1          # 对脚本对手的训练曲线
  python scripts/analyze.py exp2          # 联赛快照循环赛 Elo 演化（会跑循环赛）
  python scripts/analyze.py exp3          # 延迟消融：最终模型交叉对战 + 对脚本胜率
  python scripts/analyze.py exp4          # 利用者（exploiter）胜率
  python scripts/analyze.py all

图存 results/figures/*.png；每个实验目录有 result.json（键路径可直接作 claims 的 locator）。
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from common.stamp import write_json, write_stamp  # noqa: E402

RUNS = ROOT / "runs"
RES = ROOT / "results"
FIG = RES / "figures"

# 参考调色板（dataviz 技能 references/palette.md 的前三个分类色，三色全对 CVD 校验通过）
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
BOTS = ["random", "greedy", "counter"]
BOT_CN = {"random": "随机 CPU", "greedy": "贪心进攻 CPU", "counter": "防守反击 CPU", "masher": "乱按基线"}


def setup_mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "WenQuanYi Micro Hei", "DejaVu Sans"],
        "axes.unicode_minus": False, "figure.dpi": 110, "savefig.dpi": 150,
        "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.spines.top": False,
        "axes.spines.right": False, "lines.linewidth": 2.0, "legend.frameon": False,
    })
    return plt


def read_csv(p):
    with open(p, encoding="utf-8") as f:
        return [{k: float(v) for k, v in r.items()} for r in csv.DictReader(f)]


def read_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def style_vs(model_path, opponent, n=40, seed=11):
    """某个快照对指定对手打 n 局的风格指纹：每回合各招式次数、命中、防御、投、APM、KO 率。"""
    from eval.match import play_matches
    from scripts.tournament import load_snapshot
    w, m = load_snapshot(model_path)
    r, _ = play_matches({"kind": "policy", "name": "m", "weights": w, "env_cfg": m["env_cfg"]}, opponent, n=n, seed=seed)
    return {"score": r["score"], "apm": r["apm_a"], "ko_rate": r["ko_rate"],
            "per_round": {k: round(v, 2) for k, v in r["per_round_a"].items()}, "games": n}


# ---------------------------------------------------------------- exp1
def exp1():
    plt = setup_mpl()
    runs = sorted((RUNS / "exp1_scripted").glob("seed*"))
    runs = [r for r in runs if (r / "result.json").exists()]
    if not runs:
        print("exp1: 没有完成的 run")
        return
    out = RES / "exp1_scripted"
    write_stamp(out, {"run": "analyze exp1", "runs": [str(r) for r in runs]})
    curves = {r.name: read_csv(r / "eval_log.csv") for r in runs}
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    summary = {}
    for bot, col in zip(BOTS, (C1, C2, C3)):
        steps = sorted({row["global_step"] for rows in curves.values() for row in rows})
        mat = []
        for rows in curves.values():
            d = {row["global_step"]: row[f"{bot}_score"] for row in rows}
            xs = [row["global_step"] for row in rows]
            ys = [row[f"{bot}_score"] for row in rows]
            mat.append(np.interp(steps, xs, ys))
            ax.plot(np.array(xs) / 1e6, ys, color=col, alpha=0.25, linewidth=1.0)
        mat = np.array(mat)
        mean = mat.mean(0)
        ax.plot(np.array(steps) / 1e6, mean, color=col, label=BOT_CN[bot])
        first = [rows[0][f"{bot}_score"] for rows in curves.values()]
        final = [rows[-1][f"{bot}_score"] for rows in curves.values()]
        # 首次达到 0.9 的步数
        reach = []
        for rows in curves.values():
            hit = [row["global_step"] for row in rows if row[f"{bot}_score"] >= 0.9]
            reach.append(hit[0] if hit else None)
        summary[bot] = {"initial_score_mean": float(np.mean(first)), "final_score_mean": float(np.mean(final)),
                        "final_score_per_seed": final, "steps_to_0.9_per_seed": reach,
                        "final_ci95_per_seed": [[rows[-1][f"{bot}_lo"], rows[-1][f"{bot}_hi"]]
                                                for rows in curves.values()]}
    ax.set_xlabel("训练步数（百万智能体步；1 步 = 4 帧）")
    ax.set_ylabel("胜率（平局记 0.5）")
    ax.set_ylim(-0.02, 1.02)
    ax.set_title(f"PPO 对各脚本 CPU 的胜率随训练变化（{len(runs)} 个种子均值，细线为单种子；每点 100 局）",
                 fontsize=10, color=INK)
    ax.legend(loc="lower right", fontsize=8)
    FIG.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIG / "exp1_winrate_vs_scripted.png")
    plt.close(fig)
    res = {"n_seeds": len(runs), "eval_episodes_per_point": 100, "by_opponent": summary,
           "steps_per_run": json.load(open(runs[0] / "result.json", encoding="utf-8"))["steps"],
           "wall_clock_s_per_run": [json.load(open(r / "result.json", encoding="utf-8"))["wall_clock_s"] for r in runs]}
    res["style_vs_counter"] = {r.name: style_vs(r / "snapshots" / "final.npz", "counter") for r in runs}
    write_json(out / "result.json", res)
    for r in runs:  # 小文件进仓库：评估曲线原始数据
        (out / f"eval_log_{r.name}.csv").write_text((r / "eval_log.csv").read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- exp2
def exp2(games=40, procs=8, rerun=False):
    from scripts.tournament import load_snapshot, run_tournament, summarize
    plt = setup_mpl()
    run = RUNS / "exp2_league" / "seed0"
    out = RES / "exp2_league"
    tj = out / "tournament.json"
    if rerun or not tj.exists():
        if not (run / "result.json").exists():
            print("exp2: run 未完成")
            return
        write_stamp(out, {"run": "analyze exp2 tournament", "games_per_pair": games})
        players, meta = [], {}
        files = sorted((run / "snapshots").glob("snap_*.npz")) + [run / "snapshots" / "final.npz"]
        for f in files:
            w, m = load_snapshot(f)
            players.append((f.stem, {"kind": "policy", "name": f.stem, "weights": w, "env_cfg": m["env_cfg"]}))
            meta[f.stem] = m["global_step"]
        for b in BOTS + ["masher"]:
            players.append((b, {"kind": "scripted", "name": b}))
        recs, apm = run_tournament(players, games, procs=procs, seed=2)
        names = [n for n, _ in players]
        elo, ci, matrix = summarize(names, recs, anchor="random", n_boot=200)
        with open(out / "tournament_games.csv", "w", newline="", encoding="utf-8") as f:
            wr = csv.writer(f)
            wr.writerow(["a", "b", "score_a"])
            wr.writerows(recs)
        write_json(tj, {"elo": elo, "elo_ci95": ci, "steps": meta, "apm": apm, "score_matrix": matrix,
                        "games_per_pair": games, "anchor": "random(=0)"})
    T = json.load(open(tj, encoding="utf-8"))
    elo, ci, steps = T["elo"], T["elo_ci95"], T["steps"]
    snaps = sorted([n for n in steps], key=lambda n: steps[n])
    xs = np.array([steps[n] for n in snaps]) / 1e6
    ys = np.array([elo[n] for n in snaps])
    lo = np.array([ci[n][0] for n in snaps])
    hi = np.array([ci[n][1] for n in snaps])
    online = read_jsonl(run / "train_log.jsonl")
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.fill_between(xs, lo, hi, color=C1, alpha=0.15, linewidth=0)
    ax.plot(xs, ys, color=C1, marker="o", markersize=4, label="联赛快照（循环赛 BT-Elo，95% CI）")
    for b, ls in zip(BOTS + ["masher"], (":", "--", "-.", (0, (1, 3)))):
        ax.axhline(elo[b], color=INK2, linestyle=ls, linewidth=1.0, label=f"{BOT_CN[b]}（{elo[b]:.0f}）")
    ax.set_xlabel("训练步数（百万智能体步）")
    ax.set_ylabel("Elo（随机 CPU = 0）")
    ax.set_title("自博弈联赛：历史快照 Elo 演化（每对 %d 局）" % T["games_per_pair"], fontsize=10, color=INK)
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "exp2_league_elo.png")
    plt.close(fig)
    # 在线 Elo（训练中）单独一张，不和 BT-Elo 共轴
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    xo = [r["global_step"] / 1e6 for r in online if "elo_main_online" in r]
    yo = [r["elo_main_online"] for r in online if "elo_main_online" in r]
    ax.plot(xo, yo, color=C2)
    ax.set_xlabel("训练步数（百万智能体步）")
    ax.set_ylabel("在线 Elo（random 固定 0）")
    ax.set_title("训练中主智能体的在线 Elo（对抗当前对手池，仅看趋势）", fontsize=10, color=INK)
    fig.tight_layout()
    fig.savefig(FIG / "exp2_online_elo.png")
    plt.close(fig)
    # 非传递性：后期快照对早期快照的得分矩阵
    M = T["score_matrix"]
    n = len(snaps)
    mat = np.full((n, n), np.nan)
    for i, a in enumerate(snaps):
        for j, b in enumerate(snaps):
            if a != b and b in M.get(a, {}):
                mat[i, j] = M[a][b]
    fig, ax = plt.subplots(figsize=(6.2, 5.4))
    im = ax.imshow(mat, cmap="RdBu", vmin=0, vmax=1)
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    lab = [f"{steps[s] / 1e6:.1f}M" for s in snaps]
    ax.set_xticklabels(lab, rotation=90, fontsize=6)
    ax.set_yticklabels(lab, fontsize=6)
    ax.grid(False)
    ax.set_xlabel("对手快照")
    ax.set_ylabel("行快照")
    ax.set_title("快照两两得分（行对列；蓝 = 行赢，红 = 行输，0.5 为灰白）", fontsize=9, color=INK)
    fig.colorbar(im, ax=ax, fraction=0.046)
    fig.tight_layout()
    fig.savefig(FIG / "exp2_snapshot_matrix.png")
    plt.close(fig)
    # 非传递三元组计数
    cyc = 0
    for i in range(n):
        for j in range(n):
            for k in range(n):
                if i < j < k:
                    a, b, c = snaps[i], snaps[j], snaps[k]
                    try:
                        if (M[a][b] > .55 and M[b][c] > .55 and M[c][a] > .55) or \
                           (M[a][b] < .45 and M[b][c] < .45 and M[c][a] < .45):
                            cyc += 1
                    except KeyError:
                        pass
    final_vs = {b: M["final"][b] for b in BOTS + ["masher"]}
    # 联赛最终模型 vs 只对脚本 CPU 训练的 exp1 模型（检验"只打 CPU 会过拟合"）
    from eval.match import play_matches
    from scripts.tournament import load_snapshot
    vs_exp1 = {}
    lw, lm = load_snapshot(run / "snapshots" / "final.npz")
    league_spec = {"kind": "policy", "name": "league_final", "weights": lw, "env_cfg": lm["env_cfg"]}
    for f in sorted((RUNS / "exp1_scripted").glob("seed*/snapshots/final.npz")):
        w, m = load_snapshot(f)
        r_, _ = play_matches(league_spec, {"kind": "policy", "name": "exp1", "weights": w, "env_cfg": m["env_cfg"]},
                             n=100, seed=7)
        vs_exp1[f.parent.parent.name] = {"score": r_["score"], "ci95": r_["ci95"], "ko_rate": r_["ko_rate"]}
    res = {"elo_final": elo["final"], "elo_final_ci95": ci["final"], "elo_first_snapshot": elo[snaps[0]],
           "elo_scripted": {b: elo[b] for b in BOTS + ["masher"]}, "n_snapshots": n,
           "max_elo_snapshot": max(snaps, key=lambda s: elo[s]), "max_elo": max(elo[s] for s in snaps),
           "final_score_vs_scripted": final_vs, "intransitive_triples_(>0.55)": cyc,
           "n_triples": n * (n - 1) * (n - 2) // 6, "apm_final": T["apm"].get("final"),
           "league_final_vs_exp1_cpu_trained": vs_exp1,
           "caveat": "胜率接近 0/1 时 BT-Elo 差值被 L2 先验约束、数值不稳定；排序可信，绝对分差不要过度解读"}
    res["style_final_vs_counter"] = style_vs(run / "snapshots" / "final.npz", "counter")
    write_json(out / "result.json", res)
    print(json.dumps(res, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- exp3 (+exp5)
# 组：(键, 显示名, run 目录模板, 颜色)。exp5 = 200ms + APM300 的"人类条件"组，并入同一场交叉对战。
GROUPS = [
    ("d0", "0ms", "exp3_delay/d0/seed{s}", C1),
    ("d100", "100ms", "exp3_delay/d100/seed{s}", C2),
    ("d200", "200ms", "exp3_delay/d200/seed{s}", C3),
    ("human600", "200ms+APM600", "exp5b_human600/seed{s}", "#e87ba4"),
    ("human", "200ms+APM300", "exp5_human/seed{s}", "#eda100"),
]
GLABEL = {g[0]: g[1] for g in GROUPS}
GROUPS_BY_KEY = {g[0]: g[2] for g in GROUPS}
GCOLOR = {g[0]: g[3] for g in GROUPS}


def _group_of(name):
    return name.rsplit("_s", 1)[0]


def exp3(games=100, procs=8, rerun=False):
    from eval.stats import summarize_outcomes
    from scripts.tournament import load_snapshot, run_tournament, summarize
    plt = setup_mpl()
    out = RES / "exp3_delay"
    tj = out / "crossplay.json"
    finals = {}
    for g, _, tmpl, _ in GROUPS:
        for s in range(3):
            f = RUNS / tmpl.format(s=s) / "snapshots" / "final.npz"
            if (f.parent.parent / "result.json").exists():
                finals[f"{g}_s{s}"] = f
    if rerun or not tj.exists():
        if len(finals) < 3:
            print(f"exp3: 只有 {len(finals)} 个完成的模型")
            return
        write_stamp(out, {"run": "analyze exp3 crossplay", "games_per_pair": games, "players": list(finals)})
        players = []
        for n, f in finals.items():
            w, m = load_snapshot(f)
            players.append((n, {"kind": "policy", "name": n, "weights": w, "env_cfg": m["env_cfg"]}))
        for bname in BOTS + ["masher"]:
            players.append((bname, {"kind": "scripted", "name": bname}))
        recs, apm = run_tournament(players, games, procs=procs, seed=3)
        names = [n for n, _ in players]
        elo, ci, matrix = summarize(names, recs, anchor="random", n_boot=300)
        with open(out / "crossplay_games.csv", "w", newline="", encoding="utf-8") as f:
            wr = csv.writer(f)
            wr.writerow(["a", "b", "score_a"])
            wr.writerows(recs)
        write_json(tj, {"elo": elo, "elo_ci95": ci, "apm": apm, "score_matrix": matrix, "games_per_pair": games,
                        "players": {n: str(f) for n, f in finals.items()}})
    T = json.load(open(tj, encoding="utf-8"))
    elo, ci, M = T["elo"], T["elo_ci95"], T["score_matrix"]
    agents = list(T["players"])
    by_g = defaultdict(list)
    for n in agents:
        by_g[_group_of(n)].append(n)
    groups = [g for g, *_ in GROUPS if by_g[g]]
    if not (out / "crossplay_games.csv").exists():
        # 发布版不带逐局原始记录（体积大）；删掉 crossplay.json 后重跑本命令即可重新生成（需要 runs/ 里的模型）
        print("缺少 crossplay_games.csv（逐局原始记录）：删除 results/exp3_delay/crossplay.json 后重跑以重新生成；跳过 exp3 汇总")
        return None
    games_csv = list(csv.DictReader(open(out / "crossplay_games.csv", encoding="utf-8")))
    grp = defaultdict(list)
    for r in games_csv:
        a_, b_ = r["a"], r["b"]
        if a_ in agents and b_ in agents:
            ga, gb = _group_of(a_), _group_of(b_)
            grp[(ga, gb)].append(float(r["score_a"]))
            grp[(gb, ga)].append(1 - float(r["score_a"]))
    head2head = {}
    for ga in groups:
        for gb in groups:
            if grp[(ga, gb)]:
                s_ = summarize_outcomes(grp[(ga, gb)])
                head2head[f"{GLABEL[ga]}_vs_{GLABEL[gb]}"] = {"score": s_["score"], "ci95": s_["ci95"], "n": s_["n"]}
    vs_bots = {GLABEL[g]: {bn: float(np.mean([M[n][bn] for n in by_g[g]])) for bn in BOTS + ["masher"]}
               for g in groups}
    elo_by_g = {GLABEL[g]: {"per_seed": [elo[n] for n in sorted(by_g[g])],
                            "mean": float(np.mean([elo[n] for n in by_g[g]])),
                            "ci95_per_seed": [ci[n] for n in sorted(by_g[g])],
                            "apm_mean": float(np.mean([T["apm"][n] for n in by_g[g]]))} for g in groups}
    # 图 1：各模型 Elo
    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    for i, g in enumerate(groups):
        ns = sorted(by_g[g])
        for j, n in enumerate(ns):
            x = i + (j - 1) * 0.12
            ax.errorbar(x, elo[n], yerr=[[elo[n] - ci[n][0]], [ci[n][1] - elo[n]]], fmt="o", color=GCOLOR[g],
                        markersize=6, capsize=3, linewidth=1.2)
        ax.hlines(np.mean([elo[n] for n in ns]), i - 0.3, i + 0.3, color=GCOLOR[g], linewidth=2.5)
    for bn, ls in zip(BOTS + ["masher"], (":", "--", "-.", (0, (1, 3)))):
        ax.axhline(elo[bn], color=INK2, linestyle=ls, linewidth=1.0, label=f"{BOT_CN[bn]}（{elo[bn]:.0f}）")
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([GLABEL[g].replace("+", "\n+") for g in groups])
    ax.set_xlim(-0.5, len(groups) - 0.1)
    ax.set_ylabel("交叉对战 BT-Elo（随机 CPU = 0）")
    ax.set_xlabel("训练与对战时的反应延迟 / APM 条件")
    ax.set_title("反应延迟消融：最终模型强度（点 = 单种子 ±95% CI，横线 = 组均值）", fontsize=9, color=INK)
    ax.legend(loc="upper right", fontsize=7, title="脚本 CPU 参照线", title_fontsize=7)
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    fig.savefig(FIG / "exp3_delay_elo.png")
    plt.close(fig)
    # 图 2：组间对战
    k = len(groups)
    fig, ax = plt.subplots(figsize=(1.3 * k + 1.8, 1.1 * k + 1.6))
    mat = np.full((k, k), np.nan)
    for i, ga in enumerate(groups):
        for j, gb in enumerate(groups):
            key = f"{GLABEL[ga]}_vs_{GLABEL[gb]}"
            if key in head2head and ga != gb:
                mat[i, j] = head2head[key]["score"]
    im = ax.imshow(mat, cmap="RdBu", vmin=0, vmax=1)
    for i in range(k):
        for j in range(k):
            if not np.isnan(mat[i, j]):
                ax.text(j, i, f"{mat[i, j]:.2f}", ha="center", va="center", fontsize=10,
                        color="white" if abs(mat[i, j] - 0.5) > 0.3 else INK)
    ax.set_xticks(range(k))
    ax.set_yticks(range(k))
    ax.set_xticklabels([GLABEL[g] for g in groups], fontsize=8)
    ax.set_yticklabels([GLABEL[g] for g in groups], fontsize=8)
    ax.set_xlabel("对手组")
    ax.set_ylabel("行组")
    ax.grid(False)
    ax.set_title("组间得分（行对列；每格 = 3×3 个模型对 × %d 局）" % T["games_per_pair"], fontsize=9, color=INK)
    fig.colorbar(im, ax=ax, fraction=0.046)
    fig.tight_layout()
    fig.savefig(FIG / "exp3_delay_head2head.png")
    plt.close(fig)
    res = {"games_per_pair": T["games_per_pair"], "elo_by_group": elo_by_g, "head_to_head": head2head,
           "score_vs_scripted_by_group": vs_bots, "elo_scripted": {bn: elo[bn] for bn in BOTS + ["masher"]},
           "note": "组 200ms+APM300 来自 exp5_human；同一场循环赛，Elo 可直接比较"}
    # 风格指纹：每个最终模型对同一个参照对手（exp2 联赛 10M 步模型）打 40 局，统计每回合招式/防御/投
    style_path = out / "style.json"
    if rerun or not style_path.exists():
        from eval.match import play_matches
        ref_w, ref_m = load_snapshot(RUNS / "exp2_league" / "seed0" / "snapshots" / "final.npz")
        ref = {"kind": "policy", "name": "ref_league10M", "weights": ref_w, "env_cfg": ref_m["env_cfg"]}
        style = {}
        for n, f in T["players"].items():
            w, m = load_snapshot(f)
            r_, _ = play_matches({"kind": "policy", "name": n, "weights": w, "env_cfg": m["env_cfg"]}, ref, n=40, seed=11)
            pr = r_["per_round_a"]
            style[n] = {"score_vs_ref": r_["score"], "apm": r_["apm_a"], "ko_rate": r_["ko_rate"],
                        "per_round": {k: round(v, 2) for k, v in pr.items()}}
        write_json(style_path, {"reference": "runs/exp2_league/seed0/snapshots/final.npz", "games": 40,
                                "players": style})
    res["style_vs_reference"] = json.load(open(style_path, encoding="utf-8"))
    write_json(out / "result.json", res)
    print(json.dumps(res, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- exp4
def exp4():
    plt = setup_mpl()
    out = RES / "exp4_exploit"
    rows = []
    for g, *_ in GROUPS:
        for s in range(3):
            r = RUNS / "exp4_exploit" / f"{g}_seed{s}"
            if (r / "result.json").exists():
                res = json.load(open(r / "result.json", encoding="utf-8"))
                ev = read_csv(r / "eval_log.csv")
                rows.append({"group": g, "seed": s, "final": res["eval"]["target"]["score"],
                             "ci95": res["eval"]["target"]["ci95"], "steps": res["steps"], "long": False,
                             "run_dir": str(r.relative_to(ROOT)).replace("\\", "/"),
                             "exploiter_vs_scripted": {bn: res["eval"][bn]["score"] for bn in BOTS},
                             "curve": [(e["global_step"], e["target_score"]) for e in ev]})
    long_rows = []
    for g, *_ in GROUPS:
        r = RUNS / "exp4b_exploit_long" / f"{g}_seed0"
        if (r / "result.json").exists():
            res = json.load(open(r / "result.json", encoding="utf-8"))
            ev = read_csv(r / "eval_log.csv")
            long_rows.append({"group": g, "seed": 0, "final": res["eval"]["target"]["score"],
                              "ci95": res["eval"]["target"]["ci95"], "steps": res["steps"], "long": True,
                              "run_dir": str(r.relative_to(ROOT)).replace("\\", "/"),
                              "exploiter_vs_scripted": {bn: res["eval"][bn]["score"] for bn in BOTS},
                              "curve": [(e["global_step"], e["target_score"]) for e in ev]})
    if not rows:
        print("exp4: 无数据")
        return
    write_stamp(out, {"run": "analyze exp4"})
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    seen = set()
    for r in rows:
        xs = [c[0] / 1e6 for c in r["curve"]]
        ys = [c[1] for c in r["curve"]]
        lab = f"目标 = {GLABEL[r['group']]} 联赛模型" if r["group"] not in seen else None
        seen.add(r["group"])
        ax.plot(xs, ys, color=GCOLOR[r["group"]], label=lab, alpha=0.9, linewidth=1.5, marker="o", markersize=3)
    ax.axhline(0.5, color=INK2, linestyle="--", linewidth=1.0)
    ax.annotate("0.5：利用者打不赢 = 不可被利用", (0, 0.5), xytext=(2, 3), textcoords="offset points", fontsize=8,
                color=INK2)
    ax.set_ylim(-0.02, 1.02)
    ax.set_xlabel("利用者训练步数（百万智能体步；从零开始、0ms 延迟、不限 APM）")
    ax.set_ylabel("利用者对冻结目标的胜率（每点 60 局）")
    ax.set_title("可被利用性：针对冻结联赛模型训练的 PPO 利用者", fontsize=10, color=INK)
    ax.legend(loc="center right", fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "exp4_exploiter.png")
    plt.close(fig)
    summ = {}
    for g, *_ in GROUPS:
        f = [r["final"] for r in rows if r["group"] == g]
        if f:
            summ[GLABEL[g]] = {"exploiter_final_score_per_seed": f, "mean": float(np.mean(f)),
                               "ci95_per_seed": [r["ci95"] for r in rows if r["group"] == g]}
    if long_rows:
        fig, ax = plt.subplots(figsize=(7.2, 4.0))
        for r in long_rows:
            ax.plot([c[0] / 1e6 for c in r["curve"]], [c[1] for c in r["curve"]], color=GCOLOR[r["group"]],
                    marker="o", markersize=3, linewidth=1.8, label=f"目标 = {GLABEL[r['group']]}（seed0）")
        ax.axhline(0.5, color=INK2, linestyle="--", linewidth=1.0)
        ax.set_ylim(-0.02, 1.02)
        ax.set_xlabel("利用者训练步数（百万智能体步）")
        ax.set_ylabel("利用者对冻结目标的胜率（每点 60 局）")
        ax.set_title("加长到 3M 步的利用者", fontsize=10, color=INK)
        ax.legend(loc="upper left", fontsize=8)
        fig.tight_layout()
        fig.savefig(FIG / "exp4b_exploiter_long.png")
        plt.close(fig)
    long_summ = {GLABEL[r["group"]]: {"final": r["final"], "ci95": r["ci95"], "steps": r["steps"]} for r in long_rows}
    n_exploited = sum(1 for r in rows if r["final"] > 0.5)
    # 案例：不限 APM 的目标里被利用得最狠的那个，利用者与目标各自的招式分布
    case = None
    free = [r for r in rows if r["group"] in ("d0", "d100", "d200")]
    if free:
        from scripts.tournament import load_snapshot
        worst = max(free, key=lambda r: r["final"])
        tdir = RUNS / GROUPS_BY_KEY[worst["group"]].format(s=worst["seed"]) / "snapshots" / "final.npz"
        edir = ROOT / worst["run_dir"] / "snapshots" / "final.npz"
        tw, tm = load_snapshot(tdir)
        ew, em = load_snapshot(edir)
        case = {"target": str(tdir.relative_to(ROOT)).replace("\\", "/"), "exploiter": worst["run_dir"],
                "exploiter_style": style_vs(edir, {"kind": "policy", "name": "t", "weights": tw, "env_cfg": tm["env_cfg"]}),
                "target_style": style_vs(tdir, {"kind": "policy", "name": "e", "weights": ew, "env_cfg": em["env_cfg"]})}
    write_json(out / "result.json", {"by_target_group": summ, "long_3M_seed0": long_summ, "case_most_exploited": case,
                                     "n_targets_1M": len(rows), "n_exploited_over_0.5_at_1M": n_exploited,
                                     "rows": [{k: v for k, v in r.items() if k != "curve"} for r in rows + long_rows]})
    print(json.dumps(summ, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["exp1", "exp2", "exp3", "exp4", "all"])
    ap.add_argument("--rerun", action="store_true")
    ap.add_argument("--procs", type=int, default=8)
    a = ap.parse_args()
    FIG.mkdir(parents=True, exist_ok=True)
    if a.what in ("exp1", "all"):
        exp1()
    if a.what in ("exp2", "all"):
        exp2(procs=a.procs, rerun=a.rerun)
    if a.what in ("exp3", "all"):
        exp3(procs=a.procs, rerun=a.rerun)
    if a.what in ("exp4", "all"):
        exp4()
