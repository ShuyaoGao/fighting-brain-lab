"""招式表（帧数据）。

帧约定：招式第 1 帧开始计数；1..startup 为发生前，startup+1..startup+active 为持续（有攻击判定），
之后 recovery 帧为收招硬直。总帧数 = startup + active + recovery。

判定框坐标：相对角色脚底中心、按朝向翻转，(前向 x0, 前向 x1, 高度 y0, 高度 y1)。
判定层级 level：
  mid  —— 站防、蹲防都能挡
  low  —— 只能蹲防（下段）
  high —— 只能站防（中段/跳攻，"overhead"）
"""
from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass(frozen=True)
class Move:
    name: str
    startup: int
    active: int
    recovery: int
    damage: int = 0
    hitstun: int = 0
    blockstun: int = 0
    level: str = "mid"
    hitbox: Tuple[float, float, float, float] = (0, 0, 0, 0)
    push_hit: float = 4.0
    push_block: float = 5.0
    knockdown: bool = False
    cancelable: bool = False        # 命中/被防后可用必杀技取消
    chip: int = 0                   # 被防时的削血
    air: bool = False
    invuln: Tuple[int, int] = (0, 0)  # 无敌帧区间 [a, b]（含），(0,0) 表示无
    projectile: Optional[Tuple[float, int, int, int, int]] = None  # (速度, 伤害, 硬直, 防御硬直, 削血)
    throw: bool = False
    special: bool = False
    idx: int = field(default=0, compare=False)

    @property
    def total(self) -> int:
        return self.startup + self.active + self.recovery


_MOVES = [
    Move("st_L", 4, 3, 7, damage=30, hitstun=15, blockstun=11, level="mid",
         hitbox=(15, 55, 55, 75), push_hit=3.0, push_block=4.0, cancelable=True),
    Move("st_H", 8, 4, 18, damage=80, hitstun=20, blockstun=16, level="mid",
         hitbox=(15, 82, 50, 80), push_hit=5.0, push_block=6.0, cancelable=True),
    Move("cr_L", 4, 2, 7, damage=25, hitstun=14, blockstun=10, level="low",
         hitbox=(15, 55, 5, 25), push_hit=3.0, push_block=4.0, cancelable=True),
    Move("cr_H", 9, 4, 22, damage=70, hitstun=0, blockstun=14, level="low",
         hitbox=(15, 88, 0, 18), push_hit=4.0, push_block=6.0, knockdown=True),
    Move("j_L", 4, 8, 4, damage=40, hitstun=15, blockstun=10, level="high",
         hitbox=(5, 45, -5, 30), push_hit=2.0, push_block=3.0, air=True),
    Move("j_H", 7, 6, 6, damage=70, hitstun=20, blockstun=14, level="high",
         hitbox=(5, 58, -10, 25), push_hit=3.0, push_block=4.0, air=True),
    Move("throw", 3, 1, 20, damage=110, knockdown=True, throw=True),
    Move("fireball_L", 12, 1, 30, projectile=(4.0, 60, 20, 16, 10), special=True),
    Move("fireball_H", 12, 1, 30, projectile=(6.5, 60, 20, 16, 10), special=True),
    Move("dp_L", 3, 8, 28, damage=90, hitstun=0, blockstun=18, level="mid",
         hitbox=(5, 42, 30, 125), push_hit=2.0, push_block=3.0, knockdown=True,
         invuln=(1, 6), special=True),
    Move("dp_H", 4, 8, 36, damage=120, hitstun=0, blockstun=18, level="mid",
         hitbox=(5, 45, 30, 135), push_hit=2.0, push_block=3.0, knockdown=True,
         invuln=(1, 9), special=True),
]

MOVES = tuple(Move(**{**m.__dict__, "idx": i}) for i, m in enumerate(_MOVES))
MOVE_BY_NAME = {m.name: m for m in MOVES}
N_MOVES = len(MOVES)

# 飞行道具的判定框（相对道具中心）
PROJ_HALF_W = 12.0
PROJ_Y0, PROJ_Y1 = 48.0, 72.0
