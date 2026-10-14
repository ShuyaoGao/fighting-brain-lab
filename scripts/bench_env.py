"""测环境吞吐（智能体步/秒），用于决定 num_envs / workers。

  python scripts/bench_env.py --workers 0 8 12 --num-envs 32 64
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from common.vec_env import make_vec_env  # noqa: E402
from envs.registry import EnvConfig, EnvFactory  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, nargs="+", default=[0, 8])
    ap.add_argument("--num-envs", type=int, nargs="+", default=[32])
    ap.add_argument("--delay-ms", type=float, default=0)
    ap.add_argument("--steps", type=int, default=300)
    a = ap.parse_args()
    cfg = EnvConfig(delay_ms=a.delay_ms)
    opp = {"kind": "pool", "entries": [{"kind": "scripted", "name": s} for s in ["random", "greedy", "counter"]]}
    for ne in a.num_envs:
        for w in a.workers:
            v = make_vec_env([EnvFactory(cfg, opp, seed=i) for i in range(ne)], w)
            v.reset(seed=0)
            t = time.perf_counter()
            for _ in range(a.steps):
                v.step(np.random.randint(0, v.action_space.n, ne))
            sps = ne * a.steps / (time.perf_counter() - t)
            print(f"num_envs={ne:3d} workers={w:2d}  agent_steps/s={sps:8.0f}  frames/s={sps * cfg.frame_skip:9.0f}")
            v.close()
