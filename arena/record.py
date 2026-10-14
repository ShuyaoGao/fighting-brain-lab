"""录制双屏演示（无头浏览器逐帧截图 → mp4 + gif），场景都是确定性的（固定随机种子）。

  python -m arena.record --all
  python -m arena.record --scenario big_vs_small

产物：results/media/<场景>.gif（进仓库）与 videos/<场景>.mp4（gitignore），以及 results/media/media.json。
"人类 vs AI"场景里的人类按键由脚本模拟（CDP 键盘事件），录像里如实标注。
"""
import argparse
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from arena import capture  # noqa: E402

MEDIA = ROOT / "results" / "media"
VIDEOS = ROOT / "videos"
KEYCODES = {"a": 65, "d": 68, "w": 87, "s": 83, "j": 74, "k": 75}


def best_ids():
    idx = json.loads((ROOT / "arena" / "web" / "assets" / "gen" / "models" / "index.js").read_text(encoding="utf-8")
                     .split("=", 1)[1].rstrip().rstrip(";"))
    ids = {m["id"] for m in idx}
    return ids


def human_script():
    """模拟一个普通玩家：前进、轻拳、蹲防、搓气功波、跳入重攻击、后退防御、贴身投……循环。[(帧数, 按住的键)]"""
    seq = [(36, "d"), (3, "dj"), (9, ""), (3, "j"), (12, ""), (30, "as"), (4, "s"), (4, "sd"), (3, "dj"), (24, ""),
           (8, "wd"), (14, ""), (3, "k"), (20, ""), (40, "a"), (20, "d"), (3, "dk"), (18, ""), (4, "d"), (4, "s"),
           (4, "sd"), (3, "sdk"), (30, ""), (24, "as")]
    return seq


SCENARIOS = {
    "human_vs_ai": {"title": "人类 vs AI（按键由脚本模拟）", "layout": "single", "side": 1, "seconds": 14,
                    "desc": "P1 由脚本模拟的键盘输入操作，P2 是人类条件（200ms 反应 + APM≤600）训练的 256×2 网络；右侧实时显示 P2 的大脑。"},
    "big_vs_small": {"title": "大网络 vs 小网络（双脑）", "layout": "dual", "side": 1, "seconds": 14,
                     "desc": "P1 = 512×2，P2 = 8×2，都是人类条件、8M 步联赛训练；下方并排显示两颗大脑。"},
    "knockout": {"title": "敲掉神经元前后", "layout": "single", "side": 1, "seconds": 16,
                 "desc": "P1 = 256×2，P2 = 64×2 种子 2（做过敲除实验的模型）。前 8 秒正常，第 8 秒敲掉梯度重要度前 32 的神经元（128 个里的 1/4，红叉）。单局只是演示；统计上按重要度敲 32 个和随机敲 32 个伤害相近（见敲除一节）。"},
}


def pick_models(name, ids):
    def first(*cands):
        for c in cands:
            if c in ids:
                return c
        return sorted(ids)[0]
    if name == "human_vs_ai":
        return [first("w256_d2_human_s0", "legacy_d200"), first("w256_d2_human_s0", "legacy_d200")]
    if name == "big_vs_small":
        return [first("w512_d2_human_s0", "legacy_league0"), first("w8_d2_human_s0", "legacy_apm300")]
    return [first("w256_d2_human_s0", "legacy_d200"), first("w64_d2_human_s2", "legacy_league0")]


def key_event(b, key, down):
    b.call("Input.dispatchKeyEvent", {"type": "keyDown" if down else "keyUp", "key": key, "code": "Key" + key.upper(),
                                      "windowsVirtualKeyCode": KEYCODES[key], "nativeVirtualKeyCode": KEYCODES[key]})


def record(name, fps=20, scale=0.5, gif_scale=0.24, gif_fps=6, seed=11):
    sc = SCENARIOS[name]
    ids = best_ids()
    models = pick_models(name, ids)
    b = capture.Browser(1920, 1080)
    frames = []
    try:
        b.goto(capture.page_url(hash_="dual" if sc["layout"] == "dual" else ""))
        capture.prepare(b, models, sc["layout"], sc["side"], seed)
        b.js("ARENA_TEST.setOpt('sound', false)")
        if name == "human_vs_ai":
            b.js("ARENA_TEST.humanP1(true)")
            b.js(f"ARENA_TEST.seed({seed})")
        b.js("ARENA_TEST.skipIntro()")
        per = max(1, round(60 / fps))
        total = int(sc["seconds"] * fps)
        script, held, t_script, si = human_script(), set(), 0, 0
        for k in range(total):
            if name == "human_vs_ai":
                # 按脚本切换按住的键
                while t_script <= k * per:
                    dur, keys = script[si % len(script)]
                    want = set(keys)
                    for key in held - want:
                        key_event(b, key, False)
                    for key in want - held:
                        key_event(b, key, True)
                    held = want
                    t_script += dur
                    si += 1
                if k == 0:
                    b.js("ARENA_TEST.caption('P1 的按键由脚本模拟')")
                if k == fps * 3:
                    b.js("ARENA_TEST.caption('')")
            if name == "knockout":
                if k == 0:
                    b.js("ARENA_TEST.caption('P2：正常的 64×2 网络')")
                if k == fps * 8:
                    b.js("ARENA_TEST.cutKeys(); ARENA_TEST.caption('P2 已敲掉 32 个神经元（单局演示，统计结论见报告）')")
            b.js(f"ARENA_TEST.step({per})")
            frames.append(Image.open(io.BytesIO(b.shot())).convert("RGB"))
        errs = b.errors()
        state = b.js("ARENA_TEST.state()")
    finally:
        b.close()
    VIDEOS.mkdir(exist_ok=True)
    MEDIA.mkdir(parents=True, exist_ok=True)
    import imageio.v2 as imageio
    mp4 = VIDEOS / f"{name}.mp4"
    imageio.mimwrite(mp4, [np.asarray(f.resize((int(f.width * scale), int(f.height * scale)), Image.LANCZOS)) for f in frames],
                     fps=fps, macro_block_size=1, quality=6)
    step = max(1, fps // gif_fps)
    g = [f.resize((int(f.width * gif_scale), int(f.height * gif_scale)), Image.LANCZOS).convert("P", palette=Image.ADAPTIVE, colors=48)
         for f in frames[::step]]
    gif = MEDIA / f"{name}.gif"
    g[0].save(gif, save_all=True, append_images=g[1:], duration=int(1000 / gif_fps), loop=0, optimize=True)
    # 一张代表性截图（全分辨率，用于幻灯片）
    still = MEDIA / f"{name}.png"
    frames[len(frames) // 2].save(still)
    info = {"name": name, "title": sc["title"], "desc": sc["desc"], "models": models, "gif": gif.name, "mp4": mp4.name,
            "png": still.name, "seconds": sc["seconds"], "fps": fps, "errors": errs, "final_state": state,
            "gif_mb": round(gif.stat().st_size / 1e6, 2), "mp4_mb": round(mp4.stat().st_size / 1e6, 2)}
    print(json.dumps(info, ensure_ascii=False))
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", choices=list(SCENARIOS))
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    names = list(SCENARIOS) if a.all else [a.scenario]
    meta_p = MEDIA / "media.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    for n in names:
        meta[n] = record(n)
    MEDIA.mkdir(parents=True, exist_ok=True)
    meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
