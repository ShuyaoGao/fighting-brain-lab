"""纯 Python 的 2D 格斗游戏逻辑核心（不依赖 ROM，不依赖 numpy 以外的库）。

`FightingCore.step(input_p1, input_p2)` 推进一帧（60 FPS 逻辑帧）。
输入是 0..26 的逐帧输入编号（9 个相对方向 × {无, 轻, 重}），见 constants.encode_input。

设计要点（刻意和街机格斗一致）：
- 帧数据驱动：发生/持续/收招、受击硬直/防御硬直，所以有"确反"、"有利帧"、"连段"这些概念；
- 攻击判定框/受击框分离，出招时伸出的手脚也是受击框（挥空会被打）；
- 按住后 = 防御，站防挡中段+上段(跳攻)，蹲防挡中段+下段；投技不能防；
- 必杀技要搓指令（↓↘→+拳 = 气功波，→↓↘+拳 = 冲天拳），可在普通技命中/被防后取消；
- 连段伤害递减，飞行道具互相抵消，倒地有起身无敌，版边推挤转移给攻击方。
"""
from collections import deque

import numpy as np

from . import constants as C
from .moves import MOVES, MOVE_BY_NAME, N_MOVES, PROJ_HALF_W, PROJ_Y0, PROJ_Y1

_ACTIONABLE = (C.S_IDLE, C.S_WALK_F, C.S_WALK_B, C.S_CROUCH)
_THROW_IMMUNE = (C.S_HITSTUN, C.S_BLOCKSTUN, C.S_KNOCKDOWN, C.S_KO, C.S_AIR, C.S_AIR_HIT)
_DIR_DECODE = [C.decode_input(i) for i in range(C.N_FRAME_INPUTS)]

M_ST_L = MOVE_BY_NAME["st_L"]
M_ST_H = MOVE_BY_NAME["st_H"]
M_CR_L = MOVE_BY_NAME["cr_L"]
M_CR_H = MOVE_BY_NAME["cr_H"]
M_J_L = MOVE_BY_NAME["j_L"]
M_J_H = MOVE_BY_NAME["j_H"]
M_THROW = MOVE_BY_NAME["throw"]
M_FB = (None, MOVE_BY_NAME["fireball_L"], MOVE_BY_NAME["fireball_H"])
M_DP = (None, MOVE_BY_NAME["dp_L"], MOVE_BY_NAME["dp_H"])


class Projectile:
    __slots__ = ("owner", "x", "vx", "damage", "hitstun", "blockstun", "chip")

    def __init__(self, owner, x, vx, damage, hitstun, blockstun, chip):
        self.owner, self.x, self.vx = owner, x, vx
        self.damage, self.hitstun, self.blockstun, self.chip = damage, hitstun, blockstun, chip


class Fighter:
    __slots__ = (
        "idx", "x", "y", "vx", "vy", "facing", "hp", "state", "stun", "move", "move_frame",
        "move_done", "move_contact", "push_v", "dir_hist", "prev_btn", "buf_btn", "buf_left",
        "proj", "combo", "air_used", "jump_vx", "dir_now", "last_input", "last_press",
    )

    def __init__(self, idx, x, facing):
        self.idx = idx
        self.x, self.y, self.vx, self.vy = float(x), 0.0, 0.0, 0.0
        self.facing = facing
        self.hp = C.MAX_HP
        self.state = C.S_IDLE
        self.stun = 0
        self.move = None
        self.move_frame = 0
        self.move_done = False      # 本招已经判定过一次（每招只打一次）
        self.move_contact = False   # 本招命中或被防（用于必杀取消）
        self.push_v = 0.0
        self.dir_hist = deque([5] * C.MOTION_WINDOW, maxlen=C.MOTION_WINDOW)
        self.prev_btn = 0
        self.buf_btn = 0
        self.buf_left = 0
        self.proj = None
        self.combo = 0
        self.air_used = False
        self.jump_vx = 0.0
        self.dir_now = 5
        self.last_input = 0
        self.last_press = -999      # 最近一次"新按键"的帧号（拆投用）

    # ---- 便捷属性 ----
    @property
    def airborne(self):
        return self.state in (C.S_AIR, C.S_AIR_HIT)

    @property
    def crouching(self):
        return self.dir_now in (1, 2, 3)

    def invulnerable(self):
        if self.state in (C.S_KNOCKDOWN, C.S_KO):
            return True
        m = self.move
        if m is not None and m.invuln[1] > 0:
            return m.invuln[0] <= self.move_frame <= m.invuln[1]
        return False

    def can_act(self):
        return self.state in _ACTIONABLE

    def hurtboxes(self):
        """世界坐标受击框列表 [(x0,x1,y0,y1), ...]。"""
        if self.invulnerable():
            return ()
        x, y = self.x, self.y
        if self.airborne:
            a = C.AIR_HURT
            boxes = [(x + a[0], x + a[1], y + a[2], y + a[3])]
        elif self.state == C.S_CROUCH or (self.state in (C.S_BLOCKSTUN, C.S_HITSTUN) and self.crouching) \
                or (self.move is not None and self.move.name in ("cr_L", "cr_H")):
            boxes = [(x - C.BODY_HALF_W - 2, x + C.BODY_HALF_W + 2, 0.0, C.CROUCH_H)]
        else:
            boxes = [(x - C.BODY_HALF_W, x + C.BODY_HALF_W, 0.0, C.STAND_H)]
        m = self.move
        if m is not None and m.hitbox[1] > 0 and self.move_frame > m.startup:
            # 出招伸出的手脚：持续和收招阶段都可被打（挥空可被惩罚）
            bx = (m.hitbox[0], m.hitbox[1] - 6, m.hitbox[2], m.hitbox[3])
            boxes.append(_world_box(self, bx))
        return boxes

    def active_hitbox(self):
        m = self.move
        if m is None or self.move_done or m.hitbox[1] <= 0:
            return None
        if m.startup < self.move_frame <= m.startup + m.active:
            return _world_box(self, m.hitbox)
        return None


def _world_box(f, box):
    x0, x1, y0, y1 = box
    if f.facing > 0:
        return (f.x + x0, f.x + x1, f.y + y0, f.y + y1)
    return (f.x - x1, f.x - x0, f.y + y0, f.y + y1)


def _overlap(a, b):
    return a[0] < b[1] and b[0] < a[1] and a[2] < b[3] and b[2] < a[3]


def _motion(hist, seq, tail=5):
    """在方向历史里按顺序找指令 seq（例如 (2,3,6)），最后一个方向须在最近 tail 帧内。"""
    n = len(hist)
    i = n - 1
    stop = n - tail
    # 找最后一个方向
    while i >= stop and hist[i] != seq[-1]:
        i -= 1
    if i < stop:
        return False
    for d in reversed(seq[:-1]):
        i -= 1
        while i >= 0 and hist[i] != d:
            i -= 1
        if i < 0:
            return False
    return True


class FightingCore:
    """双人格斗逻辑。所有坐标/状态都可以直接读（相当于街机的 RAM）。"""

    def __init__(self, round_seconds=C.DEFAULT_ROUND_SECONDS, seed=None, random_start=True):
        self.round_frames = int(round_seconds * C.FPS)
        self.random_start = random_start
        self.rng = np.random.default_rng(seed)
        self.reset()

    def seed(self, seed):
        self.rng = np.random.default_rng(seed)

    def reset(self):
        x0, x1 = C.START_X
        if self.random_start:
            shift = float(self.rng.uniform(-60, 60))
            gap = float(self.rng.uniform(-30, 40))
            x0, x1 = x0 + shift - gap / 2, x1 + shift + gap / 2
        self.f = [Fighter(0, x0, 1), Fighter(1, x1, -1)]
        self.projs = []
        self.frame = 0
        self.done = False
        self.winner = None  # 0 / 1 / -1(平局)
        self.events = []    # 本帧事件（用于统计/渲染）
        self.stats = [_new_stats(), _new_stats()]
        return self

    # ------------------------------------------------------------------
    def step(self, in0: int, in1: int):
        """推进一帧。返回 (dmg_dealt_by_p0, dmg_dealt_by_p1)。"""
        if self.done:
            return 0, 0
        self.events = []
        f0, f1 = self.f
        hp_before = (f0.hp, f1.hp)
        self._ingest(f0, in0)
        self._ingest(f1, in1)
        self._tick(f0)
        self._tick(f1)
        self._decide(f0, f1)
        self._decide(f1, f0)
        self._physics(f0)
        self._physics(f1)
        self._separate_and_face(f0, f1)
        self._update_projectiles()
        self._resolve_hits(f0, f1)
        self.frame += 1
        self._check_end()
        return hp_before[1] - f1.hp, hp_before[0] - f0.hp

    # ------------------------------------------------------------------
    def _ingest(self, f, code):
        d, b = _DIR_DECODE[code]
        f.last_input = code
        f.dir_now = d
        f.dir_hist.append(d)
        if b and b != f.prev_btn:
            f.buf_btn, f.buf_left = b, C.INPUT_BUFFER
            f.last_press = self.frame
        elif f.buf_left > 0:
            f.buf_left -= 1
            if f.buf_left == 0:
                f.buf_btn = 0
        f.prev_btn = b

    def _tick(self, f):
        s = f.state
        if f.move is not None:
            f.move_frame += 1
            if f.move_frame > f.move.total:
                air = f.move.air
                f.move = None
                f.move_frame = 0
                if not air and s == C.S_ATTACK:
                    f.state = C.S_IDLE
        if s in (C.S_HITSTUN, C.S_BLOCKSTUN, C.S_KNOCKDOWN, C.S_LANDING):
            f.stun -= 1
            if f.stun <= 0:
                f.state = C.S_IDLE
                f.stun = 0
        elif s == C.S_JUMPSQUAT:
            f.stun -= 1
            if f.stun <= 0:
                f.state = C.S_AIR
                f.vy = C.JUMP_VY
                f.vx = f.jump_vx
                f.y = 0.01
                f.air_used = False
        # 连段计数 = 自己当前吃了几段连击；一旦脱离受击状态就清零
        if f.state != C.S_HITSTUN and f.state != C.S_AIR_HIT:
            f.combo = 0

    def _take_button(self, f):
        b = f.buf_btn
        f.buf_btn, f.buf_left = 0, 0
        return b

    def _start_move(self, f, m):
        f.move = m
        f.move_frame = 1
        f.move_done = False
        f.move_contact = False
        if not m.air:
            f.state = C.S_ATTACK
        st = self.stats[f.idx]
        st["moves"][m.name] = st["moves"].get(m.name, 0) + 1

    def _special_from_motion(self, f, b):
        if _motion(f.dir_hist, (6, 2, 3)):
            return M_DP[b]
        if _motion(f.dir_hist, (2, 3, 6)) and f.proj is None:
            return M_FB[b]
        return None

    def _decide(self, f, opp):
        s = f.state
        if s in _ACTIONABLE:
            if f.buf_btn:
                b = self._take_button(f)
                m = self._special_from_motion(f, b)
                if m is None:
                    d = f.dir_now
                    if b == C.BTN_H and d == 6 and abs(opp.x - f.x) <= C.THROW_RANGE and not opp.airborne:
                        m = M_THROW
                    elif d in (1, 2, 3):
                        m = M_CR_L if b == C.BTN_L else M_CR_H
                    else:
                        m = M_ST_L if b == C.BTN_L else M_ST_H
                f.vx = 0.0
                self._start_move(f, m)
                return
            d = f.dir_now
            if d in (7, 8, 9):
                f.state = C.S_JUMPSQUAT
                f.stun = C.JUMPSQUAT
                f.jump_vx = {7: -1, 8: 0, 9: 1}[d] * C.JUMP_VX * f.facing
                f.vx = 0.0
            elif d in (1, 2, 3):
                f.state = C.S_CROUCH
            elif d == 6:
                f.state = C.S_WALK_F
            elif d == 4:
                f.state = C.S_WALK_B
            else:
                f.state = C.S_IDLE
        elif s == C.S_ATTACK and f.move is not None and f.move.cancelable and f.move_contact \
                and f.buf_btn and f.move_frame <= f.move.startup + f.move.active + 8:
            m = self._special_from_motion(f, f.buf_btn)
            if m is not None:
                self._take_button(f)
                self.events.append(("cancel", f.idx))
                self.stats[f.idx]["cancels"] += 1
                self._start_move(f, m)
        elif s == C.S_AIR and f.move is None and not f.air_used and f.buf_btn:
            b = self._take_button(f)
            f.air_used = True
            self._start_move(f, M_J_L if b == C.BTN_L else M_J_H)

    def _physics(self, f):
        s = f.state
        if s == C.S_WALK_F:
            f.x += C.WALK_F * f.facing
        elif s == C.S_WALK_B:
            f.x -= C.WALK_B * f.facing
        elif s in (C.S_AIR, C.S_AIR_HIT):
            f.x += f.vx
            f.y += f.vy
            f.vy -= C.GRAVITY
            if f.y <= 0.0:
                f.y, f.vy, f.vx = 0.0, 0.0, 0.0
                if s == C.S_AIR:
                    f.state = C.S_LANDING
                    f.stun = C.LANDING_LAG
                    f.move = None
                    f.move_frame = 0
                else:
                    f.state = C.S_KNOCKDOWN
                    f.stun = C.KNOCKDOWN_FRAMES
                    f.move = None
        if f.push_v != 0.0 and not f.airborne:
            f.x += f.push_v
            f.push_v *= 0.75
            if abs(f.push_v) < 0.2:
                f.push_v = 0.0
        lo, hi = C.BODY_HALF_W, C.STAGE_W - C.BODY_HALF_W
        if f.x < lo:
            f.x = lo
        elif f.x > hi:
            f.x = hi

    def _separate_and_face(self, a, b):
        lo, hi = C.BODY_HALF_W, C.STAGE_W - C.BODY_HALF_W
        if abs(a.y - b.y) < 60.0:
            dx = b.x - a.x
            min_d = 2 * C.BODY_HALF_W
            if abs(dx) < min_d:
                sgn = 1.0 if (dx > 0 or (dx == 0 and a.facing > 0)) else -1.0
                over = (min_d - abs(dx)) / 2
                a.x -= sgn * over
                b.x += sgn * over
                # 版边：被墙挡住的一方不动，另一方被整段推开
                if a.x < lo:
                    b.x += lo - a.x
                    a.x = lo
                elif a.x > hi:
                    b.x -= a.x - hi
                    a.x = hi
                if b.x < lo:
                    a.x += lo - b.x
                    b.x = lo
                elif b.x > hi:
                    a.x -= b.x - hi
                    b.x = hi
        for f, o in ((a, b), (b, a)):
            if f.state in _ACTIONABLE or f.state == C.S_LANDING:
                if o.x > f.x + 0.5:
                    f.facing = 1
                elif o.x < f.x - 0.5:
                    f.facing = -1

    def _update_projectiles(self):
        alive = []
        for p in self.projs:
            p.x += p.vx
            if -PROJ_HALF_W <= p.x <= C.STAGE_W + PROJ_HALF_W:
                alive.append(p)
            else:
                self.f[p.owner].proj = None
        # 互相抵消
        if len(alive) == 2 and alive[0].owner != alive[1].owner and abs(alive[0].x - alive[1].x) < 2 * PROJ_HALF_W:
            for p in alive:
                self.f[p.owner].proj = None
            self.events.append(("proj_clash", -1))
            alive = []
        self.projs = alive

    # ------------------------------------------------------------------
    def _can_block(self, d, level):
        if d.state in (C.S_IDLE, C.S_WALK_F, C.S_WALK_B, C.S_CROUCH):
            if d.dir_now not in (4, 1):
                return False
        elif d.state != C.S_BLOCKSTUN:
            return False
        crouch = d.dir_now in (1, 2, 3)
        if level == "low" and not crouch:
            return False
        if level == "high" and crouch:
            return False
        return True

    def _resolve_hits(self, f0, f1):
        pending = []
        for a, d in ((f0, f1), (f1, f0)):
            m = a.move
            if m is None:
                continue
            if m.throw:
                if a.move_frame == m.startup + 1 and not a.move_done:
                    a.move_done = True
                    ok = (abs(d.x - a.x) <= C.THROW_RANGE and d.state not in _THROW_IMMUNE
                          and not d.invulnerable() and d.state != C.S_JUMPSQUAT
                          and not (d.move is not None and d.move.throw and d.move_frame <= d.move.startup + 1))
                    if ok and d.last_press >= self.frame - C.THROW_TECH_WINDOW:
                        # 拆投：被投方在最近几帧内按了键 -> 双方弹开，都不受伤
                        self.events.append(("throw_tech", d.idx))
                        self.stats[d.idx]["techs"] += 1
                        for f_ in (a, d):
                            f_.move, f_.move_frame, f_.state = None, 0, C.S_IDLE
                        sgn = 1.0 if d.x >= a.x else -1.0
                        a.push_v, d.push_v = -sgn * 6.0, sgn * 6.0
                    elif ok:
                        pending.append(("throw", a, d, m))
                    elif d.move is not None and d.move.throw:
                        self.events.append(("throw_tech", a.idx))
                continue
            if m.projectile is not None:
                if a.move_frame == m.startup + 1 and not a.move_done and a.proj is None:
                    a.move_done = True
                    spd, dmg, hs, bs, chip = m.projectile
                    p = Projectile(a.idx, a.x + a.facing * 30.0, spd * a.facing, dmg, hs, bs, chip)
                    a.proj = p
                    self.projs.append(p)
                continue
            hb = a.active_hitbox()
            if hb is None:
                continue
            for hu in d.hurtboxes():
                if _overlap(hb, hu):
                    pending.append(("melee", a, d, m))
                    a.move_done = True
                    break
        for p in list(self.projs):
            d = self.f[1 - p.owner]
            pbox = (p.x - PROJ_HALF_W, p.x + PROJ_HALF_W, PROJ_Y0, PROJ_Y1)
            for hu in d.hurtboxes():
                if _overlap(pbox, hu):
                    pending.append(("proj", self.f[p.owner], d, p))
                    self.projs.remove(p)
                    self.f[p.owner].proj = None
                    break
        for kind, a, d, src in pending:
            self._apply_hit(kind, a, d, src)

    def _apply_hit(self, kind, a, d, src):
        st_a, st_d = self.stats[a.idx], self.stats[d.idx]
        if kind == "throw":
            dmg = src.damage
            d.hp -= dmg
            d.state, d.stun = C.S_KNOCKDOWN, C.KNOCKDOWN_FRAMES
            d.move = None
            d.push_v = a.facing * 6.0
            st_a["throws"] += 1
            st_a["damage"] += dmg
            self.events.append(("throw", a.idx))
            self._ko_check(d)
            return
        if kind == "proj":
            dmg, hs, bs, chip, level = src.damage, src.hitstun, src.blockstun, src.chip, "mid"
            push_hit, push_block, kd = 4.0, 5.0, False
            direction = 1.0 if src.vx > 0 else -1.0
        else:
            m = src
            dmg, hs, bs, chip, level = m.damage, m.hitstun, m.blockstun, m.chip, m.level
            push_hit, push_block, kd = m.push_hit, m.push_block, m.knockdown
            direction = float(a.facing)
            a.move_contact = True
        if not d.airborne and self._can_block(d, level):
            d.state, d.stun = C.S_BLOCKSTUN, bs
            d.move = None
            d.hp -= chip
            st_a["damage"] += chip
            st_d["blocks"] += 1
            self._push(a, d, direction * push_block, kind)
            self.events.append(("block", d.idx))
            self._ko_check(d)
            return
        in_combo = d.state in (C.S_HITSTUN, C.S_AIR_HIT)
        d.combo = d.combo + 1 if in_combo else 1
        scale = max(C.MIN_SCALING, 1.0 - C.COMBO_SCALING * (d.combo - 1))
        dmg = int(round(dmg * scale))
        d.hp -= dmg
        st_a["damage"] += dmg
        st_a["hits"] += 1
        st_a["max_combo"] = max(st_a["max_combo"], d.combo)
        d.move = None
        d.move_frame = 0
        if d.airborne or d.state == C.S_JUMPSQUAT:
            d.state = C.S_AIR_HIT
            d.vx = direction * C.AIR_HIT_KNOCKBACK
            d.vy = max(d.vy, 4.0)
            d.y = max(d.y, 0.01)
        elif kd:
            d.state, d.stun = C.S_KNOCKDOWN, C.KNOCKDOWN_FRAMES
            self._push(a, d, direction * push_hit * 1.5, kind)
        else:
            d.state, d.stun = C.S_HITSTUN, hs
            self._push(a, d, direction * push_hit, kind)
        self.events.append(("hit", a.idx, d.combo))
        self._ko_check(d)

    def _push(self, a, d, v, kind):
        lo, hi = C.BODY_HALF_W + 2, C.STAGE_W - C.BODY_HALF_W - 2
        at_wall = (v > 0 and d.x >= hi) or (v < 0 and d.x <= lo)
        if at_wall and kind != "proj" and not a.airborne:
            a.push_v = -v
        else:
            d.push_v = v

    def _ko_check(self, d):
        if d.hp <= 0:
            d.hp = 0
            d.state = C.S_KO
            d.move = None

    def _check_end(self):
        f0, f1 = self.f
        ko0, ko1 = f0.hp <= 0, f1.hp <= 0
        if ko0 or ko1:
            self.done = True
            self.winner = -1 if (ko0 and ko1) else (1 if ko0 else 0)
            self.end_reason = "ko"
        elif self.frame >= self.round_frames:
            self.done = True
            self.winner = 0 if f0.hp > f1.hp else (1 if f1.hp > f0.hp else -1)
            self.end_reason = "timeout"

    # ------------------------------------------------------------------
    @property
    def time_left(self):
        return max(0, self.round_frames - self.frame)

    def observe(self, p: int, visible_only: bool = False) -> np.ndarray:
        """玩家 p 视角的"RAM 特征"观测（左右镜像到"自己朝右"）。

        visible_only=True 时把人类在屏幕上看不到的精确量置零：招式进度百分比、剩余硬直帧数、无敌标志
        （招式种类和"发生/持续/收招"三段动画仍保留，因为看动画就能分辨）。"""
        me, op = self.f[p], self.f[1 - p]
        m = float(me.facing)
        cx = C.STAGE_W / 2
        out = []
        for q in (me, op):
            out += _fighter_feats(q, m, cx)
        out += [
            (op.x - me.x) * m / C.STAGE_W,
            (op.y - me.y) / 100.0,
            self.time_left / self.round_frames,
            abs(op.x - me.x) / C.STAGE_W,
        ]
        arr = np.asarray(out, dtype=np.float32)
        if visible_only:
            arr[HIDDEN_IDX] = 0.0
        return arr

    def view(self, p: int) -> dict:
        """脚本对手用的结构化视角（等价于读 RAM）。"""
        me, op = self.f[p], self.f[1 - p]
        return {"me": me, "op": op, "projs": self.projs, "frame": self.frame,
                "time_left": self.time_left, "dist": abs(op.x - me.x)}


OBS_PER_FIGHTER = 6 + C.N_STATES + N_MOVES + 4 + 6 + 3
OBS_DIM = 2 * OBS_PER_FIGHTER + 4
# 每个角色特征里"屏幕上看不到"的量：招式进度(phase)、剩余硬直(stun)、无敌标志(invuln)
_PHASE = 6 + C.N_STATES + N_MOVES
_HIDDEN_LOCAL = (_PHASE, _PHASE + 4, _PHASE + 5)
HIDDEN_IDX = np.array([k * OBS_PER_FIGHTER + i for k in (0, 1) for i in _HIDDEN_LOCAL])


def _fighter_feats(q, m, cx):
    st = [0.0] * C.N_STATES
    st[q.state] = 1.0
    mv = [0.0] * N_MOVES
    phase = startup = active = recov = 0.0
    if q.move is not None:
        mm = q.move
        mv[mm.idx] = 1.0
        phase = q.move_frame / mm.total
        if q.move_frame <= mm.startup:
            startup = 1.0
        elif q.move_frame <= mm.startup + mm.active:
            active = 1.0
        else:
            recov = 1.0
    p = q.proj
    return [
        (q.x - cx) * m / cx, q.y / 100.0, q.vx * m / 6.0, q.vy / 12.0, q.facing * m, q.hp / C.MAX_HP,
        *st, *mv,
        phase, startup, active, recov,
        q.stun / 30.0, 1.0 if q.invulnerable() else 0.0, 1.0 if q.can_act() else 0.0,
        1.0 if q.dir_now in (4, 1) else 0.0, 1.0 if q.dir_now in (1, 2, 3) else 0.0, min(q.combo, 10) / 10.0,
        1.0 if p is not None else 0.0,
        ((p.x - cx) * m / cx) if p is not None else 0.0,
        (p.vx * m / 6.0) if p is not None else 0.0,
    ]


def _new_stats():
    return {"damage": 0, "hits": 0, "blocks": 0, "throws": 0, "techs": 0, "cancels": 0, "max_combo": 0, "moves": {}}
