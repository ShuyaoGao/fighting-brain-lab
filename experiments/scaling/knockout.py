"""神经元敲除（定量）+ 线性探针。

对一个中等模型（默认 64×2、人类条件、seed0），逐个把隐藏神经元的激活置零，测它对一组固定对手的得分下降，
找出"关键神经元"；再收集对局中的隐藏层激活，用线性探针（逻辑回归）看各层能不能读出游戏概念，
以及关键神经元和哪些概念最相关。

  python -m experiments.scaling.knockout --model w64_d2_human --seed 0 --games 40 --procs 16

产物：results/scaling/knockout/{_env_stamp.json, knockout.csv, result.json, *.png}
"""
import argparse
import csv
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from common.stamp import write_json, write_stamp  # noqa: E402

OUT = ROOT / "results" / "scaling" / "knockout"
RUNS = ROOT / "runs" / "scaling"


def load(cfg, seed):
    z = np.load(RUNS / cfg / f"seed{seed}" / "snapshots" / "final.npz", allow_pickle=False)
    return {k: z[k] for k in z.files if k != "_meta"}, json.loads(str(z["_meta"]))


def panel_specs(target_cfg, target_seed):
    """固定对手组：同配置的其他种子 + 相邻宽度的 seed0 + 防守反击 CPU。"""
    w = int(target_cfg.split("_")[0][1:])
    specs = []
    for s in (0, 1, 2):
        if s != target_seed and (RUNS / target_cfg / f"seed{s}" / "result.json").exists():
            ww, m = load(target_cfg, s)
            specs.append({"kind": "policy", "name": f"{target_cfg}_s{s}", "weights": ww, "env_cfg": m["env_cfg"]})
    for nw in (w // 2, w * 2):
        cfg = target_cfg.replace(f"w{w}_", f"w{nw}_")
        if (RUNS / cfg / "seed0" / "result.json").exists():
            ww, m = load(cfg, 0)
            specs.append({"kind": "policy", "name": f"{cfg}_s0", "weights": ww, "env_cfg": m["env_cfg"]})
    specs.append({"kind": "scripted", "name": "counter"})
    return specs


def _eval(job):
    from eval.match import play_matches
    key, target, panel, games, seed = job
    scores = []
    for k, opp in enumerate(panel):
        res, outcomes = play_matches(target, opp, n=games, seed=seed + 101 * k)
        scores.append(float(np.mean(outcomes)))
    return key, scores


def masks_for(widths, layer=None, j=None):
    m = [np.ones(w, np.float32) for w in widths]
    if layer is not None:
        m[layer][j] = 0.0
    return m


def collect_activations(w, meta, panel, games=30, seed=0):
    """用 PolicyOpponent 管线对打，记录每次决策时网络看到的观测与各层激活。"""
    from agents.numpy_policy import NumpyPolicy
    from agents.policy_opponent import PolicyOpponent
    from envs.fighting2d.core import FightingCore
    from league.pool import make_opponent
    pol = NumpyPolicy(w)
    rec_obs, rec_acts = [], []
    orig = pol.act

    def rec_act(obs, rng=None, deterministic=False):   # 记录网络每次决策时真正吃进去的观测
        rec_obs.append(np.asarray(obs, np.float32))
        rec_acts.append([h.copy() for h in pol.hidden(obs)])
        return orig(obs, rng=rng, deterministic=deterministic)

    pol.act = rec_act
    cfg = meta["env_cfg"]
    me = PolicyOpponent(pol, frame_skip=cfg["frame_skip"], delay_ms=cfg["delay_ms"], action_history=cfg["action_history"],
             apm=cfg.get("apm"), seed=seed)
    rng = np.random.default_rng(seed)
    for k, spec in enumerate(panel):
        opp = make_opponent(spec, seed=seed + k)
        core = FightingCore(seed=seed + k)
        for g in range(games):
            core.reset(); me.reset(int(rng.integers(1 << 30))); opp.reset(int(rng.integers(1 << 30)))
            side = g % 2
            while not core.done:
                a = me.act(core, side); b = opp.act(core, 1 - side)
                core.step(*((a, b) if side == 0 else (b, a)))
    return np.asarray(rec_obs), [np.asarray([r[l] for r in rec_acts]) for l in range(len(rec_acts[0]))]


def concepts(obs):
    """从网络看到的观测里定义可读的游戏概念（布尔标签）。"""
    from envs.fighting2d.obs_spec import FEATURES
    ix = {f["key"]: i for i, f in enumerate(FEATURES)}
    g = lambda k: obs[:, ix[k]]
    return {
        "对手在出招（发生/判定中）": (g("op.startup") + g("op.active")) > 0.5,
        "对手收招中（可确反）": g("op.recovery") > 0.5,
        "对手在空中": (g("op.state.air") + g("op.state.air_hit")) > 0.5,
        "近身（< 60 像素）": g("rel.dist") * 384 < 60,
        "自己贴墙": g("me.x") < -0.7,
        "对手贴墙": g("op.x") > 0.7,
        "对手飞行道具飞来": (g("op.proj") > 0.5) & (g("op.proj_vx") < 0),
        "自己在受击/防御硬直": (g("me.state.hitstun") + g("me.state.blockstun")) > 0.5,
        "自己血量领先": g("me.hp") > g("op.hp"),
    }


def logistic_probe(X, y, seed=0, l2=1e-2):
    from scipy.optimize import minimize
    rng = np.random.default_rng(seed)
    n = len(y)
    idx = rng.permutation(n)
    tr, te = idx[: int(0.7 * n)], idx[int(0.7 * n):]
    mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-6
    Z = (X - mu) / sd
    Z = np.hstack([Z, np.ones((n, 1))])
    yt = y[tr].astype(float)

    def f(wv):
        z = Z[tr] @ wv
        p = 1 / (1 + np.exp(-z))
        p = np.clip(p, 1e-9, 1 - 1e-9)
        loss = -(yt * np.log(p) + (1 - yt) * np.log(1 - p)).mean() + l2 * (wv[:-1] ** 2).sum()
        g = Z[tr].T @ (p - yt) / len(tr)
        g[:-1] += 2 * l2 * wv[:-1]
        return loss, g

    wv = minimize(f, np.zeros(Z.shape[1]), jac=True, method="L-BFGS-B").x
    pred = (Z[te] @ wv) > 0
    acc = float((pred == y[te]).mean())
    pos = y[te].mean()
    bal = float(0.5 * ((pred[y[te]] == 1).mean() + (pred[~y[te]] == 0).mean())) if 0 < pos < 1 else float("nan")
    return {"test_acc": acc, "majority_baseline": float(max(pos, 1 - pos)), "balanced_acc": bal, "pos_rate": float(y.mean()),
            "n_train": int(len(tr)), "n_test": int(len(te))}


def importance_scores(w, obs, acts):
    """每个隐藏神经元的平均重要度 = mean |∂log π(a)/∂h_j · h_j|（a = 网络在该状态下的最可能动作）。"""
    Ws = [(w[f"W{l}"], w[f"b{l}"]) for l in range(len(acts))]
    Wo = w["Wout"]
    logits = acts[-1] @ Wo + w["bout"]
    p = np.exp(logits - logits.max(1, keepdims=True))
    p /= p.sum(1, keepdims=True)
    a = logits.argmax(1)
    d = -p
    d[np.arange(len(a)), a] += 1.0                  # ∂log π(a)/∂logits
    g = d @ Wo.T                                    # 对最后一层激活的梯度
    imps = [None] * len(acts)
    for l in range(len(acts) - 1, -1, -1):
        h = acts[l]
        imps[l] = np.abs(g * h).mean(0)
        if l > 0:
            g = (g * (1 - h ** 2)) @ Ws[l][0].T
    return imps


def group_masks(widths, members):
    m = masks_for(widths)
    for l, j in members:
        m[l][j] = 0.0
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="w64_d2_human")
    ap.add_argument("--seed", type=int, default=2)
    ap.add_argument("--games", type=int, default=80, help="筛选：每个神经元 × 每个对手的局数")
    ap.add_argument("--confirm-games", type=int, default=300)
    ap.add_argument("--group-games", type=int, default=200)
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--procs", type=int, default=12)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    write_stamp(OUT, {"run": "knockout", "args": vars(a)})
    t0 = time.time()
    w, meta = load(a.model, a.seed)
    nl = len([k for k in w if k.startswith("W") and k != "Wout"])
    widths = [w[f"b{l}"].shape[0] for l in range(nl)]
    panel = panel_specs(a.model, a.seed)
    names = [p.get("name") for p in panel]
    base_spec = {"kind": "policy", "name": "target", "weights": w, "env_cfg": meta["env_cfg"]}
    print(f"目标 {a.model} seed{a.seed}，隐藏层 {widths}，对手组 {names}", flush=True)
    # 1) 状态 + 激活：线性探针 & 重要度
    obs, acts = collect_activations(w, meta, panel, games=24, seed=3)
    imps = importance_scores(w, obs, acts)
    # 2) 逐个敲除筛选
    jobs = [("baseline", dict(base_spec, masks=masks_for(widths)), panel, a.games * 3, 1)]
    for l, wl in enumerate(widths):
        for j in range(wl):
            jobs.append((f"L{l}_{j}", dict(base_spec, masks=masks_for(widths, l, j)), panel, a.games, 1))
    with mp.get_context("spawn").Pool(a.procs) as pool:
        res = dict(pool.imap_unordered(_eval, jobs))
    base = float(np.mean(res["baseline"]))
    rows = []
    for l, wl in enumerate(widths):
        for j in range(wl):
            sc = res[f"L{l}_{j}"]
            rows.append({"layer": l, "neuron": j, "score": float(np.mean(sc)), "drop": float(base - np.mean(sc)),
                         "importance": float(imps[l][j]), **{f"vs_{n}": v for n, v in zip(names, sc)}})
    by_drop = sorted(rows, key=lambda r: -r["drop"])
    by_imp = sorted(rows, key=lambda r: -r["importance"])
    with open(OUT / "knockout.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(by_drop)
    # 3) 复核前 top 个（更多局）
    cj = [("baseline", dict(base_spec, masks=masks_for(widths)), panel, a.confirm_games, 7)]
    for r in by_drop[: a.top]:
        cj.append((f"L{r['layer']}_{r['neuron']}", dict(base_spec, masks=masks_for(widths, r["layer"], r["neuron"])), panel,
                   a.confirm_games, 7))
    # 4) 成组敲除的剂量-反应：按筛选排名 / 按梯度重要度 / 随机（3 次）
    rng = np.random.default_rng(0)
    allidx = [(r["layer"], r["neuron"]) for r in rows]
    groups = {}
    for k in (4, 8, 16, 32):
        groups[f"screen_{k}"] = [(r["layer"], r["neuron"]) for r in by_drop[:k]]
        groups[f"importance_{k}"] = [(r["layer"], r["neuron"]) for r in by_imp[:k]]
        for t in range(3):
            groups[f"random{t}_{k}"] = [allidx[i] for i in rng.choice(len(allidx), size=k, replace=False)]
    for gname, mem in groups.items():
        cj.append((gname, dict(base_spec, masks=group_masks(widths, mem)), panel, a.group_games, 11))
    cj.append(("baseline_g", dict(base_spec, masks=masks_for(widths)), panel, a.group_games * 2, 11))
    with mp.get_context("spawn").Pool(a.procs) as pool:
        cres = dict(pool.imap_unordered(_eval, cj))
    cbase = float(np.mean(cres["baseline"]))
    gbase = float(np.mean(cres["baseline_g"]))
    ks = (4, 8, 16, 32)
    confirm = {"baseline": cbase, "games_per_opponent": a.confirm_games,
               "top": [{"layer": r["layer"], "neuron": r["neuron"], "drop_screen": r["drop"],
                        "drop_confirm": cbase - float(np.mean(cres[f"L{r['layer']}_{r['neuron']}"]))} for r in by_drop[: a.top]]}
    dose = {"baseline": gbase, "games_per_opponent": a.group_games, "k": list(ks),
            "screen": [gbase - float(np.mean(cres[f"screen_{k}"])) for k in ks],
            "importance": [gbase - float(np.mean(cres[f"importance_{k}"])) for k in ks],
            "random_mean": [float(np.mean([gbase - np.mean(cres[f"random{t}_{k}"]) for t in range(3)])) for k in ks],
            "random_each": [[gbase - float(np.mean(cres[f"random{t}_{k}"])) for t in range(3)] for k in ks],
            "members": {g: [[int(l), int(j)] for l, j in m] for g, m in groups.items() if not g.startswith("random")}}
    # 选"关键神经元"：k=8 时按筛选与按重要度两种选法里伤害更大的那一组
    pick = "importance" if dose["importance"][1] >= dose["screen"][1] else "screen"
    key = [{"layer": int(l), "neuron": int(j)} for l, j in groups[f"{pick}_8"]]
    # 5) 线性探针 + 关键神经元与概念的相关
    C = concepts(obs)
    probes = {}
    for cname, y in C.items():
        if y.mean() < 0.02 or y.mean() > 0.98:
            continue
        probes[cname] = {f"layer{l + 1}": logistic_probe(acts[l], y) for l in range(len(acts))}
        probes[cname]["input_obs"] = logistic_probe(obs[:, :90], y)
    key_concepts = []
    for kn in key:
        h = acts[kn["layer"]][:, kn["neuron"]]
        corr = {}
        for cname, y in C.items():
            if 0.02 < y.mean() < 0.98 and h.std() > 1e-6:
                corr[cname] = float(np.corrcoef(h, y.astype(float))[0, 1])
        key_concepts.append({"layer": kn["layer"], "neuron": kn["neuron"],
                             "top_concepts": sorted(corr.items(), key=lambda kv: -abs(kv[1]))[:3],
                             "act_mean": float(h.mean()), "act_sd": float(h.std())})
    from scipy.stats import spearmanr
    rho_imp = spearmanr([r["importance"] for r in rows], [r["drop"] for r in rows])
    result = {"model": f"{a.model}_s{a.seed}", "hidden_widths": widths, "panel": names,
              "screen_games_per_opponent": a.games, "baseline_score_screen": base, "n_neurons": len(rows),
              "drop_distribution": {"mean": float(np.mean([r["drop"] for r in rows])), "sd": float(np.std([r["drop"] for r in rows])),
                                    "max": by_drop[0]["drop"], "n_drop_over_0.05": sum(r["drop"] > 0.05 for r in rows),
                                    "screen_noise_se": float(np.sqrt(0.25 / (a.games * len(panel))) * np.sqrt(2))},
              "top_screen": by_drop[: a.top], "confirm": confirm, "dose_response": dose,
              "key_neurons": {"selection": pick, "members": key, "group_drop_k8": dose[pick][1]},
              "spearman_importance_vs_screen_drop": {"rho": float(rho_imp.statistic), "p": float(rho_imp.pvalue)},
              "probes": probes, "key_neuron_concepts": key_concepts, "n_probe_samples": int(len(obs)),
              "wall_clock_s": round(time.time() - t0, 1),
              "note": "敲除 = 激活置零；重要度 = mean|∂log π/∂h·h|；探针 = 标准化后的 L2 逻辑回归（70/30 划分）；相关不代表因果"}
    write_json(OUT / "result.json", result)
    plot(result, rows)
    print(json.dumps({"baseline": base, "confirm": confirm, "dose": {k: v for k, v in dose.items() if k != "members"},
                      "key": result["key_neurons"]}, ensure_ascii=False, indent=1)[:4000])


def plot(R, rows):
    from experiments.scaling.analyze import setup_mpl, S1, S2, S3, INK, INK2
    plt = setup_mpl()
    fig, ax = plt.subplots(figsize=(7.6, 3.8))
    drops = [r["drop"] for r in sorted(rows, key=lambda r: (r["layer"], r["neuron"]))]
    cols = [S1 if r["layer"] == 0 else S2 for r in sorted(rows, key=lambda r: (r["layer"], r["neuron"]))]
    ax.bar(range(len(drops)), drops, color=cols, width=0.9)
    ax.axhline(0, color=INK2, linewidth=0.8)
    ax.set_xlabel("神经元（蓝 = 第 1 层，橙 = 第 2 层）"); ax.set_ylabel("敲掉后的得分下降")
    ax.set_title(f"逐个敲除 {R['model']} 的隐藏神经元（每个 {R['screen_games_per_opponent']}×{len(R['panel'])} 局）", fontsize=10, color=INK)
    fig.tight_layout(); fig.savefig(OUT / "knockout_bars.png"); plt.close(fig)
    D_ = R["dose_response"]
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    ax.plot(D_["k"], D_["importance"], marker="o", color=S1, label="按梯度重要度挑")
    ax.plot(D_["k"], D_["screen"], marker="s", color=S2, label="按单个敲除筛选挑")
    ax.plot(D_["k"], D_["random_mean"], marker="^", color=INK2, linestyle="--", label="随机挑（3 次平均）")
    for k, each in zip(D_["k"], D_["random_each"]):
        ax.scatter([k] * len(each), each, color=INK2, s=10, alpha=0.5)
    ax.set_xscale("log", base=2)
    ax.set_xticks(D_["k"])
    ax.set_xticklabels([str(k) for k in D_["k"]])
    ax.set_xlabel("一起敲掉的神经元个数（共 %d 个）" % R["n_neurons"])
    ax.set_ylabel("得分下降")
    ax.set_title("成组敲除：挑对的神经元比随机挑伤害更大吗", fontsize=10, color=INK)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "knockout_dose.png")
    plt.close(fig)
    P = R["probes"]
    if P:
        names = list(P)
        L = [k for k in P[names[0]] if k.startswith("layer")] + ["input_obs"]
        fig, ax = plt.subplots(figsize=(7.6, 0.42 * len(names) + 1.4))
        y = np.arange(len(names))
        for k, (lk, col) in enumerate(zip(L, [S1, S2, S3, INK2])):
            ax.barh(y + (k - 1) * 0.22, [P[n][lk]["balanced_acc"] for n in names], height=0.2, color=col,
                    label={"input_obs": "直接用输入（上限参照）"}.get(lk, lk.replace("layer", "隐藏层 ")))
        ax.axvline(0.5, color=INK2, linestyle="--", linewidth=1)
        ax.set_yticks(y); ax.set_yticklabels(names, fontsize=8); ax.set_xlim(0.4, 1.0)
        ax.set_xlabel("线性探针平衡准确率（0.5 = 瞎猜）")
        ax.set_title("各隐藏层能线性读出哪些游戏概念", fontsize=10, color=INK)
        ax.legend(fontsize=8, loc="lower right")
        fig.tight_layout(); fig.savefig(OUT / "probes.png"); plt.close(fig)


if __name__ == "__main__":
    main()
