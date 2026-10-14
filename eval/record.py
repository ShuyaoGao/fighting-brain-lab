"""录对局：gif（小，适合进仓库）或 mp4（需要 imageio-ffmpeg，放 gitignore 的 videos/）。"""
from pathlib import Path

import numpy as np
from PIL import Image

from envs.fighting2d.core import FightingCore
from envs.fighting2d.render import render_core
from league.pool import make_opponent, spec_name


def record_match(spec_a, spec_b, path, seed=0, side_a=0, round_seconds=30.0, every=3, scale=1,
                 max_seconds=None, show_boxes=False, hold_end_frames=20, labels=None):
    pa = make_opponent(spec_a, seed=seed * 2 + 1)
    pb = make_opponent(spec_b, seed=seed * 2 + 2)
    core = FightingCore(round_seconds=round_seconds, seed=seed)
    core.reset()
    pa.reset(seed + 11)
    pb.reset(seed + 12)
    la, lb = labels or (spec_name(spec_a), spec_name(spec_b))
    lab = (la, lb) if side_a == 0 else (lb, la)
    frames = []
    while not core.done:
        ia = pa.act(core, side_a)
        ib = pb.act(core, 1 - side_a)
        core.step(*((ia, ib) if side_a == 0 else (ib, ia)))
        if core.frame % every == 0:
            frames.append(render_core(core, show_boxes=show_boxes, labels=lab, scale=scale))
        if max_seconds is not None and core.frame >= max_seconds * 60:
            break
    end = render_core(core, show_boxes=show_boxes, labels=lab, scale=scale)
    frames += [end] * hold_end_frames
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fps = 60 / every
    if path.suffix == ".gif":
        imgs = [Image.fromarray(f).convert("P", palette=Image.ADAPTIVE, colors=64) for f in frames]
        imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=int(1000 / fps), loop=0,
                     optimize=True)
    else:
        import imageio.v2 as imageio
        imageio.mimwrite(path, frames, fps=fps, macro_block_size=1)
    w = core.winner
    return {"path": str(path), "winner": None if w is None else (["P1", "P2", "draw"][w if w >= 0 else 2]),
            "a_side": side_a, "a_won": w == side_a, "frames": core.frame,
            "hp": [core.f[0].hp, core.f[1].hp], "end_reason": getattr(core, "end_reason", None)}
