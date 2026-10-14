"""脚本对手两两对战矩阵（检查难度梯度）。python scripts/bot_matrix.py -n 100"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.match import play_matches  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=100)
    ap.add_argument("--bots", nargs="+", default=["masher", "random", "greedy", "counter"])
    a = ap.parse_args()
    print("row 对 col 的得分（胜=1 平=0.5）")
    print(" " * 9 + "".join(f"{b:>9s}" for b in a.bots))
    for x in a.bots:
        row = []
        for y in a.bots:
            res, _ = play_matches(x, y, n=a.n, seed=1)
            row.append(f"{res['score']:9.2f}")
        print(f"{x:>9s}" + "".join(row))
