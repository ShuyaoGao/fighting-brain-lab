"""每个隐藏神经元与游戏概念的相关（给实验台的悬停提示用），以及按梯度重要度的排名。

  python -m experiments.scaling.neuron_concepts --model w64_d2_human --seed 2
产物：results/scaling/knockout/neuron_concepts.json
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from common.stamp import write_json  # noqa: E402
from experiments.scaling.knockout import OUT, collect_activations, concepts, importance_scores, load, panel_specs  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="w64_d2_human")
    ap.add_argument("--seed", type=int, default=2)
    a = ap.parse_args()
    w, meta = load(a.model, a.seed)
    obs, acts = collect_activations(w, meta, panel_specs(a.model, a.seed), games=24, seed=3)
    C = concepts(obs)
    imps = importance_scores(w, obs, acts)
    out = {}
    for l, A in enumerate(acts):
        for j in range(A.shape[1]):
            h = A[:, j]
            corr = {}
            for cname, y in C.items():
                if 0.02 < y.mean() < 0.98 and h.std() > 1e-6:
                    corr[cname] = float(np.corrcoef(h, y.astype(float))[0, 1])
            out[f"{l}_{j}"] = {"importance": float(imps[l][j]),
                               "top_concepts": sorted(corr.items(), key=lambda kv: -abs(kv[1]))[:3]}
    write_json(OUT / "neuron_concepts.json", {"model": f"{a.model}_s{a.seed}", "n_samples": int(len(obs)), "neurons": out,
                                             "note": "皮尔逊相关；相关不代表因果"})
    print("ok", len(out))
