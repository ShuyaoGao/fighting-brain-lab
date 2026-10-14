"""观测向量（core.observe）每一维的名称、中文标签、分组，以及独立实现的取值函数。

tests/test_obs_spec.py 用随机对局逐维比对 `core.observe(p)` 与这里的取值函数，保证可视化里显示的
特征名称和模型实际吃进去的数一一对应。改 core.observe 时必须同步改这里，否则测试会失败。
"""
import json
from pathlib import Path

from . import constants as C
from .moves import MOVES


def load_naming():
    """招式名称与角色配色的唯一来源：envs/fighting2d/naming.json（{fireball}/{dp} 替换成 specials 里的名字）。"""
    raw = json.loads((Path(__file__).with_name("naming.json")).read_text(encoding="utf-8"))
    sp = raw["specials"]
    fmt = (lambda t: t.format(**sp))
    return {"specials": sp, "moves": {k: fmt(v) for k, v in raw["moves"].items()},
            "macros": {k: fmt(v) for k, v in raw["macros"].items()}, "characters": raw["characters"]}


NAMING = load_naming()
STATE_ZH = ["站立", "前走", "后退", "下蹲", "起跳", "空中", "落地", "出招", "受击硬直", "防御硬直", "倒地", "空中受击", "KO"]
MOVE_ZH = NAMING["moves"]

GROUPS = ["自身状态", "自身帧数据", "对手状态", "对手帧数据", "飞行道具", "相对距离"]


def _phase(q):
    m = q.move
    if m is None:
        return 0.0, 0.0, 0.0, 0.0
    ph = q.move_frame / m.total
    if q.move_frame <= m.startup:
        return ph, 1.0, 0.0, 0.0
    if q.move_frame <= m.startup + m.active:
        return ph, 0.0, 1.0, 0.0
    return ph, 0.0, 0.0, 1.0


def _fighter_specs(side):
    """side = 'me' 或 'op'。取值函数签名 f(core, p) -> float。"""
    zh = "自身" if side == "me" else "对手"
    st_group, fd_group = (zh + "状态", zh + "帧数据")
    cx = C.STAGE_W / 2

    def q(core, p):
        return core.f[p] if side == "me" else core.f[1 - p]

    def mir(core, p):
        return float(core.f[p].facing)

    S = [
        (f"{side}.x", f"{zh}水平位置", st_group, lambda c, p: (q(c, p).x - cx) * mir(c, p) / cx),
        (f"{side}.y", f"{zh}高度", st_group, lambda c, p: q(c, p).y / 100.0),
        (f"{side}.vx", f"{zh}水平速度", st_group, lambda c, p: q(c, p).vx * mir(c, p) / 6.0),
        (f"{side}.vy", f"{zh}垂直速度", st_group, lambda c, p: q(c, p).vy / 12.0),
        (f"{side}.facing", f"{zh}朝向", st_group, lambda c, p: q(c, p).facing * mir(c, p)),
        (f"{side}.hp", f"{zh}血量", st_group, lambda c, p: q(c, p).hp / C.MAX_HP),
    ]
    for i, name in enumerate(C.STATE_NAMES):
        S.append((f"{side}.state.{name}", f"{zh}·{STATE_ZH[i]}", st_group,
                  (lambda i: lambda c, p: 1.0 if q(c, p).state == i else 0.0)(i)))
    for m in MOVES:
        S.append((f"{side}.move.{m.name}", f"{zh}招式·{MOVE_ZH[m.name]}", fd_group,
                  (lambda idx: lambda c, p: 1.0 if (q(c, p).move is not None and q(c, p).move.idx == idx) else 0.0)(m.idx)))
    S += [
        (f"{side}.move_phase", f"{zh}招式进度", fd_group, lambda c, p: _phase(q(c, p))[0]),
        (f"{side}.startup", f"{zh}发生中", fd_group, lambda c, p: _phase(q(c, p))[1]),
        (f"{side}.active", f"{zh}判定中", fd_group, lambda c, p: _phase(q(c, p))[2]),
        (f"{side}.recovery", f"{zh}收招中", fd_group, lambda c, p: _phase(q(c, p))[3]),
        (f"{side}.stun", f"{zh}剩余硬直", fd_group, lambda c, p: q(c, p).stun / 30.0),
        (f"{side}.invuln", f"{zh}无敌", fd_group, lambda c, p: 1.0 if q(c, p).invulnerable() else 0.0),
        (f"{side}.can_act", f"{zh}可行动", fd_group, lambda c, p: 1.0 if q(c, p).can_act() else 0.0),
        (f"{side}.holding_back", f"{zh}按后（防御姿态）", st_group, lambda c, p: 1.0 if q(c, p).dir_now in (4, 1) else 0.0),
        (f"{side}.holding_down", f"{zh}按下（蹲）", st_group, lambda c, p: 1.0 if q(c, p).dir_now in (1, 2, 3) else 0.0),
        (f"{side}.combo", f"{zh}被连段数", fd_group, lambda c, p: min(q(c, p).combo, 10) / 10.0),
        (f"{side}.proj", f"{zh}飞行道具在场", "飞行道具", lambda c, p: 1.0 if q(c, p).proj is not None else 0.0),
        (f"{side}.proj_x", f"{zh}飞行道具位置", "飞行道具",
         lambda c, p: ((q(c, p).proj.x - cx) * mir(c, p) / cx) if q(c, p).proj is not None else 0.0),
        (f"{side}.proj_vx", f"{zh}飞行道具速度", "飞行道具",
         lambda c, p: (q(c, p).proj.vx * mir(c, p) / 6.0) if q(c, p).proj is not None else 0.0),
    ]
    return S


def _global_specs():
    return [
        ("rel.dx", "对手在前方的距离（带方向）", "相对距离",
         lambda c, p: (c.f[1 - p].x - c.f[p].x) * c.f[p].facing / C.STAGE_W),
        ("rel.dy", "高度差", "相对距离", lambda c, p: (c.f[1 - p].y - c.f[p].y) / 100.0),
        ("rel.time_left", "回合剩余时间", "相对距离", lambda c, p: c.time_left / c.round_frames),
        ("rel.dist", "距离", "相对距离", lambda c, p: abs(c.f[1 - p].x - c.f[p].x) / C.STAGE_W),
    ]


SPECS = _fighter_specs("me") + _fighter_specs("op") + _global_specs()
FEATURES = [{"key": k, "zh": z, "group": g} for k, z, g, _ in SPECS]
EXTRACTORS = [f for *_, f in SPECS]


def feature_table():
    return [dict(i=i, **f) for i, f in enumerate(FEATURES)]


# ---- 动作名称 ----
DIR_ZH = {5: "不动", 6: "前进", 4: "后退（站防）", 2: "下蹲", 8: "垂直跳", 3: "前蹲", 1: "蹲防", 9: "前跳", 7: "后跳"}
BTN_ZH = {0: "", 1: " + 轻", 2: " + 重"}
MACRO_ZH = NAMING["macros"]


def action_zh(a: int) -> str:
    from wrappers.macros import MACRO_NAMES, N_BASE
    a = int(a)
    if a >= N_BASE:
        return MACRO_ZH[MACRO_NAMES[a - N_BASE]]
    d, b = C.decode_input(a)
    return DIR_ZH[d] + BTN_ZH[b]


def action_table():
    from wrappers.macros import N_ACTIONS_WITH_MACROS
    return [action_zh(a) for a in range(N_ACTIONS_WITH_MACROS)]
