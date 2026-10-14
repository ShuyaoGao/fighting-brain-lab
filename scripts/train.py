"""训练入口（本机和 GPU 服务器通用）。

示例：
  # 对脚本 CPU 混合池训练，定期评估对各脚本对手的胜率
  python scripts/train.py --mode scripted --steps 3000000 --out runs/exp1/seed0 --seed 0

  # 自博弈联赛（历史快照池 + 脚本锚点）
  python scripts/train.py --mode league --steps 6000000 --out runs/league/seed0

  # 反应延迟 200ms
  python scripts/train.py --mode league --delay-ms 200 --out runs/delay200/seed0

产物（out 目录）：_env_stamp.json、config.json、train_log.jsonl、eval_log.csv、snapshots/*.npz、
final.pt、result.json。
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from common.stamp import JsonlLogger, write_json, write_stamp  # noqa: E402
from common.vec_env import make_vec_env  # noqa: E402
from envs.registry import EnvConfig, EnvFactory  # noqa: E402
from eval.match import play_matches  # noqa: E402
from league.elo import EloTracker  # noqa: E402

# 注意：torch 只在 main() 里导入。Windows 用 spawn 启动环境子进程时会重新执行本文件顶层，
# 顶层导入 torch 会让每个子进程多占几百 MB 提交内存（曾导致 WinError 1450）。

SCRIPTED = ["random", "greedy", "counter"]


def scripted_spec(name):
    return {"kind": "scripted", "name": name}


def policy_spec(name, weights, env_cfg, deterministic=False):
    return {"kind": "policy", "name": name, "weights": weights, "env_cfg": env_cfg, "deterministic": deterministic}


def save_snapshot(path, weights, meta):
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **weights, _meta=json.dumps(meta))


def load_snapshot(path):
    z = np.load(path, allow_pickle=False)
    w = {k: z[k] for k in z.files if k != "_meta"}
    meta = json.loads(str(z["_meta"]))
    return w, meta


class League:
    """历史快照对手池 + PFSP 风格加权采样 + 在线 Elo。"""

    def __init__(self, env_cfg, scripted_frac=0.25, max_pool=40, pfsp_power=1.5, scripted=None):
        self.env_cfg = env_cfg
        self.scripted = list(SCRIPTED if scripted is None else scripted)
        self.scripted_frac = scripted_frac if self.scripted else 0.0
        self.max_pool = max_pool
        self.pfsp_power = pfsp_power
        self.snaps = []            # [(name, weights)]
        self.results = {}          # name -> [score_sum, n]
        self.elo = EloTracker(k=12.0, fixed={"random": 0.0})

    def add(self, name, weights):
        self.snaps.append((name, weights))
        if len(self.snaps) > self.max_pool:
            # 保留最早的一个（多样性）和较新的，删掉中间最老的
            del self.snaps[1]

    def record(self, opp, outcome):
        r = self.results.setdefault(opp, [0.0, 0])
        r[0] += outcome
        r[1] += 1
        self.elo.update("main", opp, outcome)

    def pool_spec(self):
        entries, probs = [], []
        for s in self.scripted:
            entries.append(scripted_spec(s))
            probs.append(self.scripted_frac / len(self.scripted))
        if self.snaps:
            ws = []
            for name, w in self.snaps:
                sc, n = self.results.get(name, [0.5, 1])
                winrate = (sc + 0.5) / (n + 1)          # 平滑
                ws.append((1 - winrate) ** self.pfsp_power + 0.05)
            ws = np.asarray(ws)
            ws = ws / ws.sum() * (1 - self.scripted_frac)
            for (name, w), p in zip(self.snaps, ws):
                entries.append(policy_spec(name, w, self.env_cfg))
                probs.append(float(p))
        else:
            probs = [1 / len(self.scripted)] * len(self.scripted)
        return {"kind": "pool", "entries": entries, "probs": probs}


def main():
    global PPOConfig, PPOTrainer, export_numpy, save_checkpoint
    from agents.ppo import PPOConfig, PPOTrainer, export_numpy, save_checkpoint
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["scripted", "league", "single", "cpu"], default="scripted",
                    help="cpu = 真实游戏的内置 CPU 当对手（1P 存档）")
    ap.add_argument("--game", default="fighting2d", choices=["fighting2d", "retro", "diambra"])
    ap.add_argument("--game-id", default="", help="真实游戏：envs/game_specs 里的配置名，如 mk2_genesis")
    ap.add_argument("--opponent", default="greedy", help="mode=single 时的唯一对手（脚本名）")
    ap.add_argument("--opponent-snapshot", default=None,
                    help="mode=single 时改用一个冻结的策略快照(.npz)做对手 —— 用来训练'利用者'(exploiter)")
    ap.add_argument("--steps", type=int, default=3_000_000)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--num-envs", type=int, default=32)
    ap.add_argument("--n-steps", type=int, default=128)
    ap.add_argument("--workers", type=int, default=8, help="0 = 进程内同步")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--torch-threads", type=int, default=4)
    ap.add_argument("--lr", type=float, default=2.5e-4)
    ap.add_argument("--ent-coef", type=float, default=0.01)
    ap.add_argument("--hidden", type=int, default=256)
    ap.add_argument("--layers", type=int, default=2, help="隐藏层层数（actor 与 critic 相同）")
    ap.add_argument("--frame-skip", type=int, default=4)
    ap.add_argument("--delay-ms", type=float, default=0.0)
    ap.add_argument("--sticky", type=float, default=0.0)
    ap.add_argument("--apm", type=float, default=None)
    ap.add_argument("--round-seconds", type=float, default=30.0)
    ap.add_argument("--visible-only", action="store_true", help="观测只含人类屏幕可见信息")
    ap.add_argument("--eval-every", type=int, default=250_000, help="每多少智能体步评估一次")
    ap.add_argument("--eval-episodes", type=int, default=100)
    ap.add_argument("--dense-eval-until", type=int, default=500_000, help="此步数之前用更密的评估间隔")
    ap.add_argument("--dense-eval-every", type=int, default=62_500)
    ap.add_argument("--snapshot-every", type=int, default=250_000)
    ap.add_argument("--scripted-frac", type=float, default=0.25)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    env_cfg = EnvConfig(game=args.game, game_id=args.game_id, frame_skip=args.frame_skip, delay_ms=args.delay_ms,
                        sticky=args.sticky, apm=args.apm, round_seconds=args.round_seconds,
                        visible_only=args.visible_only)
    external = args.game != "fighting2d"   # 真实游戏：没有脚本 CPU，评估只看训练回合结果
    ppo_cfg = PPOConfig(total_steps=args.steps, num_envs=args.num_envs, n_steps=args.n_steps, lr=args.lr,
                        ent_coef=args.ent_coef, hidden=args.hidden, n_layers=args.layers, device=args.device,
                        torch_threads=args.torch_threads, seed=args.seed)
    config = {"args": vars(args), "env_cfg": env_cfg.to_dict(), "ppo_cfg": ppo_cfg.__dict__}
    write_json(out / "config.json", config)
    write_stamp(out, {"run": "train", "config": config})

    league = League(env_cfg.to_dict(), scripted_frac=args.scripted_frac,
                    scripted=[] if external else None) if args.mode == "league" else None
    if external and args.mode in ("scripted",):
        raise SystemExit("真实游戏没有脚本 CPU：用 --mode cpu（打游戏内置 CPU）或 --mode league（需要 2P 存档）")
    if args.mode == "cpu":
        opp = None
    elif args.mode == "scripted":
        opp = {"kind": "pool", "entries": [scripted_spec(s) for s in SCRIPTED], "probs": None}
    elif args.mode == "single":
        if args.opponent_snapshot:
            tw, tmeta = load_snapshot(args.opponent_snapshot)
            opp = policy_spec("target", tw, tmeta["env_cfg"])
        else:
            opp = scripted_spec(args.opponent)
    else:
        if external:  # 没有脚本锚点：先放一个随机初始化策略当第 0 个快照
            from agents.ppo import ActorCritic
            from envs.registry import make_env
            probe = make_env(env_cfg, None)
            m0 = ActorCritic(probe.observation_space.shape[0], probe.action_space.n, args.hidden, args.layers)
            probe.close()
            league.add("snap_000", export_numpy(m0))
        opp = league.pool_spec()
    fns = [EnvFactory(env_cfg, opp, seed=args.seed * 1000 + i) for i in range(args.num_envs)]
    venv = make_vec_env(fns, args.workers)

    logger = JsonlLogger(out / "train_log.jsonl")
    trainer = PPOTrainer(venv, ppo_cfg, logger=logger)
    eval_targets = [] if external else [(s_, scripted_spec(s_)) for s_ in SCRIPTED]
    if args.mode == "single" and args.opponent_snapshot:
        eval_targets.append(("target", opp))
    eval_names = [n for n, _ in eval_targets]
    eval_csv = out / "eval_log.csv"
    eval_rows = []
    state = {"next_eval": 0, "next_snap": args.snapshot_every, "snap_i": 0, "t0": time.time()}

    def evaluate(tr, final=False):
        w = export_numpy(tr.model)
        me = policy_spec("agent", w, env_cfg.to_dict())
        row = {"global_step": tr.global_step, "frames": tr.global_step * args.frame_skip,
               "elapsed_s": round(time.time() - state["t0"], 1)}
        for s, spec in eval_targets:
            res, _ = play_matches(me, spec, n=args.eval_episodes, seed=10_000 + tr.global_step % 997,
                                  round_seconds=args.round_seconds)
            row[f"{s}_score"] = res["score"]
            row[f"{s}_lo"], row[f"{s}_hi"] = res["ci95"]
            row[f"{s}_ko"] = res["ko_rate"]
            row[f"{s}_apm"] = res["apm_a"]
        eval_rows.append(row)
        with open(eval_csv, "w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=list(row.keys()))
            wr.writeheader()
            wr.writerows(eval_rows)
        return row

    def callback(tr, upd):
        extra = {"frames": tr.global_step * args.frame_skip}
        if tr.global_step >= state["next_eval"]:
            row = evaluate(tr)
            state["next_eval"] += (args.dense_eval_every if tr.global_step < args.dense_eval_until
                                   else args.eval_every)
            extra["eval"] = row
            print(f"[{tr.global_step:>9d}] sps={tr.last_record['sps']} " +
                  " ".join(f"{s}={row[s + '_score']:.2f}" for s in eval_names), flush=True)
        if league is not None:
            # 用训练回合结果更新联赛统计
            for name, (score, n) in tr.last_record.get("train_outcomes_by_opp", {}).items():
                for _ in range(n):
                    league.record(name, score)
            if tr.global_step >= state["next_snap"]:
                state["snap_i"] += 1
                name = f"snap_{state['snap_i']:03d}"
                w = export_numpy(tr.model)
                league.add(name, w)
                save_snapshot(out / "snapshots" / f"{name}.npz", w,
                              {"name": name, "global_step": tr.global_step, "env_cfg": env_cfg.to_dict()})
                league.elo.r[name] = league.elo.r["main"]
                tr.venv.call_opponent("set_pool", league.pool_spec()["entries"], league.pool_spec()["probs"])
                state["next_snap"] += args.snapshot_every
            extra["elo_main_online"] = league.elo.r["main"]
            extra["pool_size"] = len(league.snaps)
        elif args.mode != "league" and tr.global_step >= state["next_snap"]:
            state["snap_i"] += 1
            name = f"snap_{state['snap_i']:03d}"
            save_snapshot(out / "snapshots" / f"{name}.npz", export_numpy(tr.model),
                          {"name": name, "global_step": tr.global_step, "env_cfg": env_cfg.to_dict()})
            state["next_snap"] += args.snapshot_every
        return extra

    trainer.add_callback(callback)
    t0 = time.time()
    try:
        trainer.train()
    finally:
        venv.close()
    final_row = evaluate(trainer, final=True)
    save_checkpoint(out / "final.pt", trainer.model, ppo_cfg, env_cfg.to_dict())
    w = export_numpy(trainer.model)
    save_snapshot(out / "snapshots" / "final.npz", w,
                  {"name": "final", "global_step": trainer.global_step, "env_cfg": env_cfg.to_dict()})
    result = {
        "mode": args.mode, "seed": args.seed, "steps": trainer.global_step,
        "frames": trainer.global_step * args.frame_skip,
        "game_hours": trainer.global_step * args.frame_skip / 60 / 3600,
        "wall_clock_s": round(time.time() - t0, 1), "env_cfg": env_cfg.to_dict(),
        "final_eval": final_row,
        "eval": {s: {"score": final_row[f"{s}_score"], "ci95": [final_row[f"{s}_lo"], final_row[f"{s}_hi"]]}
                 for s in eval_names},
    }
    if league is not None:
        result["online_elo"] = league.elo.ratings()
        result["pool"] = [n for n, _ in league.snaps]
    write_json(out / "result.json", result)
    logger.close()
    print(json.dumps(result["eval"], ensure_ascii=False))


if __name__ == "__main__":
    main()
