"""用 PIL 把 FightingCore 的状态画成 RGB 帧（仅用于看/录像；训练默认不渲染）。"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import constants as C

W, H = int(C.STAGE_W), C.STAGE_H
FLOOR = H - 24  # 地面在屏幕上的 y
P_COLORS = [(70, 130, 230), (225, 70, 70)]
P_LIGHT = [(150, 190, 255), (255, 150, 150)]

_bg = None
_font = None


def _background():
    global _bg
    if _bg is None:
        arr = np.zeros((H, W, 3), dtype=np.uint8)
        top, bot = np.array([28, 30, 52]), np.array([88, 70, 96])
        t = np.linspace(0, 1, FLOOR)[:, None]
        arr[:FLOOR] = (top * (1 - t) + bot * t).astype(np.uint8)[:, None, :]
        arr[FLOOR:] = (60, 52, 44)
        arr[FLOOR, :] = (150, 130, 110)
        _bg = Image.fromarray(arr)
    return _bg


def _get_font():
    global _font
    if _font is None:
        _font = ImageFont.load_default()
    return _font


def _sy(y):
    return FLOOR - y


def render_core(core, show_boxes=False, labels=("P1", "P2"), scale=2):
    img = _background().copy()
    dr = ImageDraw.Draw(img)
    font = _get_font()
    for i, f in enumerate(core.f):
        col = P_COLORS[i]
        s = f.state
        if s in (C.S_HITSTUN, C.S_AIR_HIT):
            col = (255, 255, 255) if (core.frame // 2) % 2 == 0 else P_LIGHT[i]
        elif s == C.S_KO:
            col = (90, 90, 90)
        if s in (C.S_KNOCKDOWN, C.S_KO):
            dr.rectangle([f.x - 40, _sy(f.y + 16), f.x + 40, _sy(f.y)], fill=col)
        else:
            crouch = s == C.S_CROUCH or (f.move is not None and f.move.name.startswith("cr_")) or \
                (s in (C.S_BLOCKSTUN, C.S_HITSTUN) and f.crouching)
            h = C.CROUCH_H if crouch else C.STAND_H
            if f.airborne:
                h = 72
            y0 = f.y + (10 if f.airborne else 0)
            dr.rectangle([f.x - 16, _sy(y0 + h - 20), f.x + 16, _sy(y0)], fill=col)
            hx = f.x + 4 * f.facing
            dr.ellipse([hx - 11, _sy(y0 + h), hx + 11, _sy(y0 + h - 22)], fill=col)
            # 眼睛表示朝向
            ex = hx + 6 * f.facing
            dr.ellipse([ex - 2, _sy(y0 + h - 8), ex + 2, _sy(y0 + h - 12)], fill=(20, 20, 20))
            if s == C.S_BLOCKSTUN or (f.dir_now in (4, 1) and s in (C.S_IDLE, C.S_WALK_B, C.S_CROUCH)):
                gx = f.x + 20 * f.facing
                dr.line([gx, _sy(y0 + h - 10), gx, _sy(y0 + 4)],
                        fill=(255, 230, 80) if s == C.S_BLOCKSTUN else (160, 150, 90), width=3)
            hb = f.active_hitbox()
            m = f.move
            if m is not None and m.hitbox[1] > 0 and f.move_frame > m.startup:
                # 伸出的手脚
                from .core import _world_box
                x0, x1, y0b, y1b = _world_box(f, m.hitbox)
                dr.rectangle([x0, _sy(y1b), x1, _sy(y0b)], fill=P_LIGHT[i] if hb is not None else col)
        if show_boxes:
            for hu in f.hurtboxes():
                dr.rectangle([hu[0], _sy(hu[3]), hu[1], _sy(hu[2])], outline=(60, 220, 90))
            hb = f.active_hitbox()
            if hb is not None:
                dr.rectangle([hb[0], _sy(hb[3]), hb[1], _sy(hb[2])], outline=(255, 40, 40), width=2)
        if f.move is not None:
            dr.text((f.x - 18, _sy(f.y + 110)), f.move.name, fill=(255, 255, 255), font=font)
    for p in core.projs:
        cy = _sy((60))
        dr.ellipse([p.x - 12, cy - 10, p.x + 12, cy + 10], fill=P_LIGHT[p.owner], outline=(255, 255, 255))
    # 血条
    for i, f in enumerate(core.f):
        frac = f.hp / C.MAX_HP
        bw = 150
        if i == 0:
            x0 = 12
            dr.rectangle([x0, 10, x0 + bw, 20], fill=(70, 20, 20))
            dr.rectangle([x0 + bw * (1 - frac), 10, x0 + bw, 20], fill=(240, 200, 40))
            dr.text((x0, 23), labels[0], fill=P_LIGHT[0], font=font)
        else:
            x0 = W - 12 - bw
            dr.rectangle([x0, 10, x0 + bw, 20], fill=(70, 20, 20))
            dr.rectangle([x0, 10, x0 + bw * frac, 20], fill=(240, 200, 40))
            dr.text((x0 + bw - 6 * len(labels[1]), 23), labels[1], fill=P_LIGHT[1], font=font)
        if f.combo >= 2:
            dr.text((W - 90 if i == 0 else 40, 50), f"{f.combo} HITS", fill=(255, 220, 60), font=font)
    secs = int(np.ceil(core.time_left / C.FPS))
    dr.text((W / 2 - 6, 8), f"{secs:02d}", fill=(255, 255, 255), font=font)
    if core.done:
        msg = {0: f"{labels[0]} WINS", 1: f"{labels[1]} WINS", -1: "DRAW"}[core.winner]
        dr.text((W / 2 - 24, 70), msg, fill=(255, 255, 255), font=font)
    if scale != 1:
        img = img.resize((W * scale, H * scale), Image.NEAREST)
    return np.asarray(img)
