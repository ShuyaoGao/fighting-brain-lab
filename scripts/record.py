"""录对局 gif/mp4。

  python scripts/record.py --a runs/exp2_league/seed0/snapshots/final.npz --b counter --out results/gifs/league_vs_counter.gif
  python scripts/record.py --preset          # 录 results/gifs/ 下的代表性对局（需要实验已跑完）

--a/--b 可以是脚本 CPU 名（random/greedy/counter/masher）或快照 .npz 路径。
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.stamp import write_json, write_stamp  # noqa: E402
from eval.record import record_match  # noqa: E402
from scripts.tournament import load_snapshot  # noqa: E402


def spec_of(s, label=None):
    if s.endswith(".npz"):
        w, m = load_snapshot(ROOT / s if not Path(s).is_absolute() else s)
        return {"kind": "policy", "name": label or Path(s).stem, "weights": w, "env_cfg": m["env_cfg"]}
    return {"kind": "scripted", "name": s, "label": label or s}


PRESETS = [
    ("exp1_agent_vs_counter.gif", "runs/exp1_scripted/seed0/snapshots/final.npz", "counter", "PPO-vsCPU", "CPU-counter"),
    ("league_final_vs_greedy.gif", "runs/exp2_league/seed0/snapshots/final.npz", "greedy", "LEAGUE", "CPU-greedy"),
    ("league_final_vs_early.gif", "runs/exp2_league/seed0/snapshots/final.npz",
     "runs/exp2_league/seed0/snapshots/snap_001.npz", "LEAGUE-10M", "LEAGUE-0.5M"),
    ("delay200_vs_delay0.gif", "runs/exp3_delay/d200/seed0/snapshots/final.npz",
     "runs/exp3_delay/d0/seed0/snapshots/final.npz", "AI-200ms", "AI-0ms"),
    ("exploiter_vs_league.gif", "runs/exp4_exploit/d100_seed1/snapshots/final.npz",
     "runs/exp3_delay/d100/seed1/snapshots/final.npz", "EXPLOITER", "AI-100ms"),
    ("apm300_vs_200ms.gif", "runs/exp5_human/seed0/snapshots/final.npz",
     "runs/exp3_delay/d200/seed0/snapshots/final.npz", "AI-APM300", "AI-200ms"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a")
    ap.add_argument("--b")
    ap.add_argument("--out")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--every", type=int, default=3)
    ap.add_argument("--scale", type=int, default=1)
    ap.add_argument("--boxes", action="store_true", help="画出攻击判定框/受击框")
    ap.add_argument("--preset", action="store_true")
    a = ap.parse_args()
    if a.preset:
        out_dir = ROOT / "results" / "gifs"
        write_stamp(out_dir, {"run": "record presets"})
        meta = {}
        for fn, sa, sb, la, lb in PRESETS:
            if any(s.endswith(".npz") and not (ROOT / s).exists() for s in (sa, sb)):
                print("跳过（缺快照）:", fn)
                continue
            info = record_match(spec_of(sa, la), spec_of(sb, lb), out_dir / fn, seed=a.seed, every=a.every,
                                scale=a.scale, labels=(la, lb))
            meta[fn] = {**info, "a": sa, "b": sb}
            print(fn, info)
        write_json(out_dir / "gifs.json", meta)
        return
    info = record_match(spec_of(a.a), spec_of(a.b), a.out, seed=a.seed, every=a.every, scale=a.scale,
                        show_boxes=a.boxes)
    print(json.dumps(info, ensure_ascii=False))


if __name__ == "__main__":
    main()
