"""实验清单（单一事实来源）。本机按"车道"串行跑，或打印成 Linux 服务器上 task-spooler 的提交命令。

  python scripts/experiments.py list
  python scripts/experiments.py run --lane 1          # 本机：跑第 1 车道（串行）
  python scripts/experiments.py tsp --queue tsp       # 打印 task-spooler 提交命令（每条进队列串行跑）
  python scripts/experiments.py run --only exp4       # 只跑名字含 exp4 的

车道：1、2 = exp1/exp2/exp3；4 = exp5（人类条件：200ms + APM 300）；
3 = exp4（利用者 / exploitability），依赖 exp3、exp5 的 final.npz，最后跑。
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

COMMON = "--workers 6 --num-envs 32"


def experiments():
    E = []
    for s in range(3):
        E.append(("exp1_scripted", 1, f"--mode scripted --steps 2000000 --seed {s} --eval-every 250000 "
                  f"--eval-episodes 100 --out runs/exp1_scripted/seed{s}"))
    E.append(("exp2_league", 2, "--mode league --steps 10000000 --seed 0 --snapshot-every 500000 "
              "--eval-every 500000 --eval-episodes 60 --out runs/exp2_league/seed0"))
    lane_of = {(0, 0): 1, (0, 1): 1, (0, 2): 1, (100, 0): 2, (100, 1): 2, (100, 2): 2,
               (200, 0): 2, (200, 1): 1, (200, 2): 1}
    for d in (0, 100, 200):
        for s in range(3):
            E.append(("exp3_delay", lane_of[(d, s)],
                      f"--mode league --steps 6000000 --seed {s} --delay-ms {d} --snapshot-every 500000 "
                      f"--eval-every 1000000 --dense-eval-until 0 --eval-episodes 60 "
                      f"--out runs/exp3_delay/d{d}/seed{s}"))
    # exp5："人类条件"组合 = 200ms 反应延迟 + APM 上限 300（AlphaStar 约 22 次/5 秒 ≈ 264 APM 作参照；
    # 格斗游戏人类 APM 没有找到可靠来源 [未核实]）
    for s in range(3):
        E.append(("exp5_human", 4,
                  f"--mode league --steps 6000000 --seed {s} --delay-ms 200 --apm 300 --snapshot-every 500000 "
                  f"--eval-every 1000000 --dense-eval-until 0 --eval-episodes 60 --out runs/exp5_human/seed{s}"))
    # exp5b：APM 上限放宽到 600（令牌桶容量同为 4），看 APM 约束的"拐点"
    for s in range(3):
        E.append(("exp5b_human600", 5,
                  f"--mode league --steps 6000000 --seed {s} --delay-ms 200 --apm 600 --snapshot-every 500000 "
                  f"--eval-every 1000000 --dense-eval-until 0 --eval-episodes 60 --out runs/exp5b_human600/seed{s}"))
    targets = [(f"d{d}_seed{s}", f"runs/exp3_delay/d{d}/seed{s}") for d in (0, 100, 200) for s in range(3)]
    targets += [(f"human_seed{s}", f"runs/exp5_human/seed{s}") for s in range(3)]
    for i, (name, tdir) in enumerate(targets):
        s = i % 3
        E.append(("exp4_exploit", 3,
                  f"--mode single --opponent-snapshot {tdir}/snapshots/final.npz "
                  f"--steps 1000000 --seed {100 + s} --eval-every 250000 --dense-eval-until 0 --eval-episodes 60 "
                  f"--snapshot-every 100000000 --out runs/exp4_exploit/{name}"))
    # exp4b：更长的利用者（3M 步）只打每组的 seed0，看 1M 步时没被利用的模型多给预算后会不会被利用
    long_targets = [("d0", "runs/exp3_delay/d0/seed0"), ("d100", "runs/exp3_delay/d100/seed0"),
                    ("d200", "runs/exp3_delay/d200/seed0"), ("human600", "runs/exp5b_human600/seed0"),
                    ("human", "runs/exp5_human/seed0")]
    for i, (name, tdir) in enumerate(long_targets):
        E.append(("exp4b_exploit_long", 6 + i % 2,
                  f"--mode single --opponent-snapshot {tdir}/snapshots/final.npz "
                  f"--steps 3000000 --seed 200 --eval-every 500000 --dense-eval-until 0 --eval-episodes 60 "
                  f"--snapshot-every 100000000 --out runs/exp4b_exploit_long/{name}_seed0"))
    return E


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "run", "tsp"])
    ap.add_argument("--lane", type=int, default=None)
    ap.add_argument("--only", default=None)
    ap.add_argument("--queue", default="tsp")
    ap.add_argument("--skip-done", action="store_true", default=True)
    a = ap.parse_args()
    exps = [e for e in experiments() if (a.lane is None or e[1] == a.lane) and (a.only is None or a.only in e[0])]
    for name, lane, args in exps:
        full = f"scripts/train.py {args} {COMMON}"
        out = ROOT / args.split("--out ")[1].split()[0]
        if a.cmd == "list":
            print(f"[lane {lane}] {name}: {full}")
        elif a.cmd == "tsp":
            print(f"{a.queue} .venv/bin/python {full.replace('--workers 6', '--workers 10')}")
        else:
            if a.skip_done and (out / "result.json").exists():
                print(f"跳过（已完成）: {out}")
                continue
            out.mkdir(parents=True, exist_ok=True)
            print(f"==> {full}", flush=True)
            with open(out / "stdout.log", "w", encoding="utf-8") as f:
                rc = subprocess.call([PY, *full.split()], cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
            print(f"    exit={rc}", flush=True)


if __name__ == "__main__":
    main()
