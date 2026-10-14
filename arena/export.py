"""把训练好的模型（actor + critic 真实权重）、观测特征表、动作名导出给浏览器 arena。

  python -m arena.export                 # 导出到 arena/web/assets/gen/（float32）
  python -m arena.export --f16 --out D   # 半精度（发布静态版时减小体积）

每个模型一个 JS 文件（ARENA_REGISTER({...})），按需用 <script> 动态加载，file:// 离线也能用。
"""
import argparse
import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

GEN = ROOT / "arena" / "web" / "assets" / "gen"

LEGACY = [
    ("legacy_league0", "runs/exp2_league/seed0", "0ms 联赛 10M（旧实验，2×256）"),
    ("legacy_d200", "runs/exp3_delay/d200/seed0", "200ms 联赛 6M（旧实验，2×256）"),
    ("legacy_apm300", "runs/exp5_human/seed0", "200ms+APM300 联赛 6M（旧实验，2×256）"),
    ("legacy_cpuonly", "runs/exp1_scripted/seed0", "只打脚本 CPU 2M（旧实验，2×256）"),
]


def b64(a, f16):
    a = np.ascontiguousarray(a, dtype="<f2" if f16 else "<f4")
    return base64.b64encode(a.tobytes()).decode()


def net_spec(state_dict, prefix, f16):
    idx = sorted({int(k.split(".")[1]) for k in state_dict if k.startswith(prefix + ".") and k.endswith("weight")})
    layers = []
    for i in idx:
        W = state_dict[f"{prefix}.{i}.weight"].cpu().numpy().T
        b = state_dict[f"{prefix}.{i}.bias"].cpu().numpy()
        layers.append({"W": b64(W.ravel(), f16), "b": b64(b, f16), "in": int(W.shape[0]), "out": int(W.shape[1])})
    return {"layers": layers[:-1], "out": layers[-1]}


def scaling_elo():
    p = ROOT / "results" / "scaling" / "result.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    return {k: v for k, v in d.get("elo_by_model", {}).items()}


def collect():
    """[(id, run_dir, label)]：规模实验的所有完成 run + 旧实验的代表模型。"""
    out = []
    for rd in sorted((ROOT / "runs" / "scaling").glob("*/seed*")):
        if (rd / "final.pt").exists() and (rd / "result.json").exists():
            cfg = rd.parent.name
            out.append((f"{cfg}_s{rd.name[4:]}", rd, None))
    for mid, rd, label in LEGACY:
        if (ROOT / rd / "final.pt").exists():
            out.append((mid, ROOT / rd, label))
    return out


def describe(mid, rd, label, sd, cfg):
    args = cfg["args"]
    w, d = int(args.get("hidden", 256)), int(args.get("layers", 2))
    env = cfg["env_cfg"]
    human = (env.get("delay_ms") or 0) > 0 or env.get("apm")
    cond = ("人类条件" if human else "无限制")
    cond_detail = f"{int(env.get('delay_ms') or 0)}ms" + (f" + APM≤{int(env['apm'])}" if env.get("apm") else "")
    steps = int(args.get("steps", 0))
    n_actor = sum(v.numel() for k, v in sd.items() if k.startswith("actor."))
    n_critic = sum(v.numel() for k, v in sd.items() if k.startswith("critic."))
    if label is None:
        label = f"{w}×{d} · {cond}（{cond_detail}）· {steps / 1e6:g}M 步 · 种子 {args.get('seed')}"
    return {"id": mid, "label": label, "short": f"{w}x{d}", "width": w, "depth": d, "cond": "human" if human else "free",
            "cond_detail": cond_detail, "seed": int(args.get("seed", 0)), "steps": steps, "params_actor": n_actor,
            "params_total": n_actor + n_critic, "env_cfg": env, "source": str(rd.relative_to(ROOT)).replace("\\", "/"),
            "family": "legacy" if mid.startswith("legacy") else "scaling"}


def export_models(out_dir: Path, f16=False, only=None):
    import torch
    (out_dir / "models").mkdir(parents=True, exist_ok=True)
    elo = scaling_elo()
    keyn = {}
    kop = ROOT / "results" / "scaling" / "knockout" / "result.json"
    if kop.exists():
        k = json.loads(kop.read_text(encoding="utf-8"))
        conc = {(c["layer"], c["neuron"]): c["top_concepts"] for c in k["key_neuron_concepts"]}
        dose = k["dose_response"]
        ncp = kop.parent / "neuron_concepts.json"
        nc = json.loads(ncp.read_text(encoding="utf-8"))["neurons"] if ncp.exists() else {}
        best = lambda l, j: ((nc.get(f"{l}_{j}") or {}).get("top_concepts") or [[None]])[0][0]
        members = dose["members"]["importance_32"]
        keyn[k["model"]] = {"list": [[l, j, dose["importance"][3], best(l, j)] for l, j in members],
                            "info": {"label": "梯度重要度前 32", "k": 32, "group_drop": dose["importance"][3],
                                     "random_drop": dose["random_mean"][3], "baseline": dose["baseline"]},
                            "concepts": {kk: v["top_concepts"] for kk, v in nc.items()}}
    index = []
    for mid, rd, label in collect():
        if only is not None and mid not in only:
            continue
        ck = torch.load(rd / "final.pt", map_location="cpu", weights_only=False)
        sd = ck["state_dict"]
        cfg = json.loads((rd / "config.json").read_text(encoding="utf-8"))
        meta = describe(mid, rd, label, sd, cfg)
        if mid in elo:
            meta["elo"] = elo[mid]
        if mid in keyn:
            meta["key_neurons"] = keyn[mid]["list"]
            meta["key_info"] = keyn[mid]["info"]
            meta["neuron_concepts"] = keyn[mid]["concepts"]
        spec = dict(meta, dtype="f16" if f16 else "f32", actor=net_spec(sd, "actor", f16), critic=net_spec(sd, "critic", f16))
        (out_dir / "models" / f"{mid}.js").write_text("ARENA_REGISTER(" + json.dumps(spec) + ");\n", encoding="utf-8")
        index.append(meta)
    (out_dir / "models" / "index.js").write_text("window.ARENA_MODEL_INDEX = " + json.dumps(index, ensure_ascii=False) + ";\n",
                                                 encoding="utf-8")
    return index


def export_spec(out_dir: Path):
    from envs.fighting2d import constants as C
    from envs.fighting2d.moves import MOVES
    from envs.fighting2d.obs_spec import FEATURES, GROUPS, MOVE_ZH, NAMING, STATE_ZH, action_table
    spec = {"features": FEATURES, "groups": GROUPS, "actions": action_table(), "state_zh": STATE_ZH, "naming": NAMING,
            "move_zh": MOVE_ZH, "moves": [m.name for m in MOVES], "obs_dim": len(FEATURES),
            "history": {"n": 4, "n_actions": len(action_table())}, "fps": C.FPS}
    cred = ROOT / "credits.json"
    if cred.exists():   # 署名配置（页脚用）；空值在页面上显示为 {{KEY}} 占位
        spec["credits"] = {k: v for k, v in json.loads(cred.read_text(encoding="utf-8")).items() if not k.startswith("_")}
        logo = spec["credits"].get("UNIVERSITY_LOGO")
        if logo and (ROOT / logo).is_file():   # 可选校标：复制进页面目录（只有填了路径才会用到）
            import shutil
            out_dir.mkdir(parents=True, exist_ok=True)
            dst = out_dir / ("logo" + (ROOT / logo).suffix.lower())
            shutil.copy(ROOT / logo, dst)
            spec["credits"]["UNIVERSITY_LOGO"] = "assets/gen/" + dst.name
        elif logo:
            print("credits.json 里的 UNIVERSITY_LOGO 文件不存在，页脚只显示文字：", logo)
            spec["credits"]["UNIVERSITY_LOGO"] = ""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "spec.js").write_text("window.ARENA_SPEC = " + json.dumps(spec, ensure_ascii=False) + ";\n", encoding="utf-8")


def export_report(out_dir: Path):
    """实验报告页的数据：全部来自 results/*/result.json。"""
    R = {}
    sc = ROOT / "results" / "scaling" / "result.json"
    if sc.exists():
        R["scaling"] = json.loads(sc.read_text(encoding="utf-8"))
    ko = ROOT / "results" / "scaling" / "knockout" / "result.json"
    if ko.exists():
        k = json.loads(ko.read_text(encoding="utf-8"))
        rows = []
        csvp = ko.parent / "knockout.csv"
        import csv
        with open(csvp, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append({"layer": int(r["layer"]), "neuron": int(r["neuron"]), "drop": float(r["drop"]),
                             "importance": float(r.get("importance", 0) or 0)})
        rows.sort(key=lambda r: (r["layer"], r["neuron"]))
        R["knockout"] = {"model": k["model"], "panel": k["panel"], "rows": rows, "confirm": k["confirm"], "probes": k["probes"],
                         "concepts": {f"{c['layer']}_{c['neuron']}": c["top_concepts"] for c in k["key_neuron_concepts"]},
                         "baseline": k["baseline_score_screen"], "drop_distribution": k["drop_distribution"],
                         "n_probe_samples": k["n_probe_samples"], "games": k["screen_games_per_opponent"],
                         "dose": k.get("dose_response"), "key": k.get("key_neurons"),
                         "rho_importance": k.get("spearman_importance_vs_screen_drop")}
    e3 = ROOT / "results" / "exp3_delay" / "result.json"
    if e3.exists():
        d = json.loads(e3.read_text(encoding="utf-8"))
        R["delay"] = {"elo_by_group": d["elo_by_group"], "head_to_head": d["head_to_head"],
                      "score_vs_scripted_by_group": d["score_vs_scripted_by_group"]}
    e4 = ROOT / "results" / "exp4_exploit" / "result.json"
    if e4.exists():
        d = json.loads(e4.read_text(encoding="utf-8"))
        R["exploit_old"] = {"n_targets_1M": d["n_targets_1M"], "n_exploited": d["n_exploited_over_0.5_at_1M"],
                            "long": d.get("long_3M_seed0")}
    try:   # 早期实验（训练曲线、联赛 Elo 演化）
        from scripts.export_web import export_data
        old = export_data(write=False)
        if "exp1" in old:
            R["exp1"] = old["exp1"]
        if "exp2" in old:
            R["exp2"] = {k: v for k, v in old["exp2"].items() if k != "apm_train"}
    except Exception as e:  # noqa: BLE001
        print("早期实验数据导出失败：", e)
    med = ROOT / "results" / "media" / "media.json"
    if med.exists():
        R["media"] = json.loads(med.read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report_data.js").write_text("window.ARENA_REPORT = " + json.dumps(R, ensure_ascii=False) + ";\n",
                                            encoding="utf-8")
    return R


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(GEN))
    ap.add_argument("--f16", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    export_spec(out)
    export_report(out)
    idx = export_models(out, f16=a.f16)
    size = sum(p.stat().st_size for p in (out / "models").glob("*.js")) / 1e6
    print(f"导出 {len(idx)} 个模型到 {out}（{size:.1f} MB，{'float16' if a.f16 else 'float32'}）")


if __name__ == "__main__":
    main()
