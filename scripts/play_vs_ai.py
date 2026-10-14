"""人类 vs AI：用键盘和训练好的模型（或脚本 CPU）在自带小环境里对打，并记录战绩。

  python scripts/play_vs_ai.py --ai runs/exp3_delay/d200/seed0/snapshots/final.npz --rounds 5
  python scripts/play_vs_ai.py --ai counter

按键（P1，人类始终在左侧开局）：
  方向  W/A/S/D 或 方向键（A/← = 左，D/→ = 右，W/↑ = 跳，S/↓ = 蹲；按住"远离对手"的方向 = 防御）
  轻攻击 J      重攻击 K      （贴身 前+K = 投；↓↘→+J/K = 气功波；→↓↘+J/K = 冲天拳）
  Esc 退出

每回合结果追加写入 runs/human_matches/<日期>.jsonl（AI 是谁、它的延迟设置、胜负、血量、帧数），
这就是"对人类"这一类评估的原始数据。界面用标准库 tkinter，不需要额外依赖。
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from envs.fighting2d import constants as C  # noqa: E402
from envs.fighting2d.core import FightingCore  # noqa: E402
from envs.fighting2d.render import render_core  # noqa: E402
from league.pool import make_opponent  # noqa: E402
from wrappers.human import input_cost  # noqa: E402

KEYMAP = {"w": "up", "up": "up", "s": "down", "down": "down", "a": "left", "left": "left",
          "d": "right", "right": "right", "j": "L", "k": "H"}


def keys_to_input(held: set, facing: int) -> int:
    """当前按住的键 -> 逐帧输入编号（相对朝向）。facing=1 朝右。"""
    up, down = "up" in held, "down" in held
    left, right = "left" in held, "right" in held
    fwd = right if facing > 0 else left
    back = left if facing > 0 else right
    if fwd and back:
        fwd = back = False
    row = 8 if up else (2 if down else 5)
    if fwd:
        d = {8: 9, 2: 3, 5: 6}[row]
    elif back:
        d = {8: 7, 2: 1, 5: 4}[row]
    else:
        d = row
    b = C.BTN_H if "H" in held else (C.BTN_L if "L" in held else 0)
    return C.encode_input(d, b)


def ai_spec(arg):
    if arg.endswith(".npz"):
        from scripts.tournament import load_snapshot
        w, m = load_snapshot(arg)
        return {"kind": "policy", "name": Path(arg).parent.parent.name + "/" + Path(arg).stem, "weights": w,
                "env_cfg": m["env_cfg"]}, m["env_cfg"]
    return {"kind": "scripted", "name": arg}, {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ai", default="counter")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--player", default="human")
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--boxes", action="store_true")
    ap.add_argument("--smoke", type=float, default=0, help="冒烟测试：N 秒后自动关闭（不记录战绩）")
    a = ap.parse_args()

    import tkinter as tk
    from PIL import Image, ImageTk

    spec, ai_cfg = ai_spec(a.ai)
    ai = make_opponent(spec, seed=int(time.time()))
    core = FightingCore(seed=int(time.time()))
    log_dir = ROOT / "runs" / "human_matches"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{time.strftime('%Y-%m-%d')}.jsonl"

    root = tk.Tk()
    root.title(f"格斗大脑实验台：{a.player} vs {spec.get('name')}")
    label = tk.Label(root)
    label.pack()
    held = set()
    state = {"round": 0, "wins": 0, "photo": None, "next": time.perf_counter(), "prev": 0, "actions": 0}

    def on_key(ev, down):
        k = ev.keysym.lower()
        if k == "escape":
            root.destroy()
            return
        if k in KEYMAP:
            (held.add if down else held.discard)(KEYMAP[k])

    root.bind("<KeyPress>", lambda e: on_key(e, True))
    root.bind("<KeyRelease>", lambda e: on_key(e, False))

    def new_round():
        state["actions"], state["prev"] = 0, 0
        core.reset()
        core.f[0].x, core.f[1].x = C.START_X
        ai.reset(int(time.time()) % (1 << 30))

    def tick():
        if core.done:
            w = core.winner
            rec = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "player": a.player, "ai": spec.get("name"),
                   "ai_delay_ms": ai_cfg.get("delay_ms"), "ai_apm_cap": ai_cfg.get("apm"),
                   "human_won": w == 0, "draw": w == -1, "hp_human": core.f[0].hp, "hp_ai": core.f[1].hp,
                   "frames": core.frame, "end_reason": core.end_reason,
                   "human_apm": state["actions"] / max(core.frame / C.FPS / 60.0, 1e-9)}   # 用来校准 APM 上限
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            state["wins"] += int(w == 0)
            state["round"] += 1
            print(f"第 {state['round']} 回合：{'你赢了' if w == 0 else ('平局' if w == -1 else 'AI 赢了')}"
                  f"（累计 {state['wins']}/{state['round']}）", flush=True)
            if state["round"] >= a.rounds:
                root.after(1500, root.destroy)
                return
            root.after(1500, lambda: (new_round(), tick()))
            return
        human_in = keys_to_input(held, core.f[0].facing)
        state["actions"] += input_cost(state["prev"], human_in)
        state["prev"] = human_in
        ai_in = ai.act(core, 1)
        core.step(human_in, ai_in)
        img = render_core(core, show_boxes=a.boxes, labels=("YOU", "AI"), scale=a.scale)
        state["photo"] = ImageTk.PhotoImage(Image.fromarray(img))
        label.configure(image=state["photo"])
        state["next"] += 1.0 / C.FPS
        delay = max(1, round((state["next"] - time.perf_counter()) * 1000))
        root.after(delay, tick)

    new_round()
    state["next"] = time.perf_counter()
    root.after(500, tick)
    if a.smoke:
        def _close():
            print(f"smoke ok: frame={core.frame}", flush=True)
            root.destroy()
        root.after(int(a.smoke * 1000), _close)
    root.mainloop()
    print(f"战绩已记录到 {log_path}")


if __name__ == "__main__":
    main()
