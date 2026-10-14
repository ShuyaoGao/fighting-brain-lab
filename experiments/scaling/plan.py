"""规模实验的作业清单（单一事实来源）。

  python -m experiments.scaling.plan list
  python -m experiments.scaling.plan run --parallel 3       # 本机作业队列
  python -m experiments.scaling.plan tsp --queue tsp        # 打印 task-spooler 队列命令（Linux 服务器）

设计（结果见 results/scaling/result.json 与 README）：
- 主轴：宽度 {8,16,32,64,128,256,512} × 深度 2 × 3 种子，人类条件（200ms 观测延迟 + APM≤600），自博弈联赛，8M 步；
- 深度变体：宽度 {32,128} × 深度 {1,3} × 3 种子；
- 无限制对照：宽度 {16,64,256} × 深度 2 × 3 种子，0ms、不限 APM；
- 算力对照：宽度 64 深度 2，2M / 4M / 16M 步 × 3 种子（8M 在主轴里）；
- 利用者：对每个宽度的 seed0 最终模型训练 2M 步的 PPO 利用者（256×2），两组：0ms 不限 APM；与目标相同的人类条件。
"""
import argparse
from pathlib import Path

from scripts.jobqueue import Job, ROOT, run_queue

WIDTHS = [8, 16, 32, 64, 128, 256, 512]
SEEDS = [0, 1, 2]
STEPS = 8_000_000
HUMAN = ["--delay-ms", "200", "--apm", "600"]
COMMON = ["--workers", "6", "--num-envs", "32", "--dense-eval-until", "0", "--eval-episodes", "40"]


def device(w):
    """小网络用 CPU 训练（更快，也避免 Windows 上每个 CUDA 上下文占用数 GB 提交内存）；宽网络用 GPU。"""
    return ["--device", "cpu" if w <= 128 else "cuda"]


def cfg_name(w, d, cond, steps=STEPS):
    s = "" if steps == STEPS else f"_{steps // 1_000_000}M"
    return f"w{w}_d{d}_{cond}{s}"


def train_job(w, d, cond, seed, steps=STEPS):
    name = cfg_name(w, d, cond, steps)
    out = Path("runs/scaling") / name / f"seed{seed}"
    argv = ["scripts/train.py", "--mode", "league", "--steps", str(steps), "--seed", str(seed),
            "--hidden", str(w), "--layers", str(d), "--snapshot-every", str(steps // 8),
            "--eval-every", str(max(steps // 4, 500_000)), "--out", out.as_posix(), *COMMON, *device(w)]
    if cond == "human":
        argv += HUMAN
    return Job(f"{name}/seed{seed}", argv, ROOT / out)


def jobs():
    J = []
    for s in SEEDS:
        for w in WIDTHS:
            J.append(train_job(w, 2, "human", s))
    for s in SEEDS:
        for w in (32, 128):
            for d in (1, 3):
                J.append(train_job(w, d, "human", s))
    for s in SEEDS:
        for w in (16, 64, 256):
            J.append(train_job(w, 2, "free", s))
    for s in SEEDS:
        for st in (2_000_000, 4_000_000, 16_000_000):
            J.append(train_job(64, 2, "human", s, st))
    for w in WIDTHS:
        tgt = Path("runs/scaling") / cfg_name(w, 2, "human") / "seed0" / "snapshots" / "final.npz"
        out = Path("runs/scaling_exploit") / f"{cfg_name(w, 2, 'human')}_seed0"
        J.append(Job(f"exploit/{cfg_name(w, 2, 'human')}", [
            "scripts/train.py", "--mode", "single", "--opponent-snapshot", tgt.as_posix(), "--steps", "2000000",
            "--seed", "300", "--hidden", "256", "--layers", "2", "--eval-every", "500000", "--snapshot-every",
            "100000000", "--out", out.as_posix(), *COMMON, *device(256)], ROOT / out, needs=[ROOT / tgt]))
    # 人类条件利用者：和目标同样的 200ms + APM≤600，只比"打法"，不比反应和手速
    # （上面那组不受限的利用者在第 0 步、未训练时就能赢小网络 80–95%，测不出可利用性）
    for w in WIDTHS:
        tgt = Path("runs/scaling") / cfg_name(w, 2, "human") / "seed0" / "snapshots" / "final.npz"
        out = Path("runs/scaling_exploit_human") / f"{cfg_name(w, 2, 'human')}_seed0"
        J.append(Job(f"exploit_h/{cfg_name(w, 2, 'human')}", [
            "scripts/train.py", "--mode", "single", "--opponent-snapshot", tgt.as_posix(), "--steps", "2000000",
            "--seed", "300", "--hidden", "256", "--layers", "2", "--eval-every", "250000", "--snapshot-every",
            "100000000", "--out", out.as_posix(), *COMMON, "--device", "cpu", *HUMAN], ROOT / out, needs=[ROOT / tgt]))
    return J


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "run", "tsp"])
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--queue", default="tsp")
    ap.add_argument("--only", default=None, help="只跑名字里含这个子串的作业")
    a = ap.parse_args()
    J = [j for j in jobs() if a.only is None or a.only in j.name]
    if a.cmd == "list":
        for j in J:
            print(("[done] " if j.done else "       ") + j.name + "  ::  python " + " ".join(j.argv))
        print(f"共 {len(J)} 个作业，已完成 {sum(j.done for j in J)} 个")
    elif a.cmd == "tsp":
        for j in J:
            print(f"{a.queue} .venv/bin/python " + " ".join(j.argv).replace("--workers 6", "--workers 10"))
    else:
        run_queue(J, parallel=a.parallel, log=ROOT / "runs" / "scaling_queue.log")


if __name__ == "__main__":
    main()
