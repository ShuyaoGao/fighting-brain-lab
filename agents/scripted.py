"""脚本化对手（相当于街机里的 CPU）。

都通过读"RAM 状态"（core 的结构化视角）决策，带可配置的反应延迟和失误率，
避免出现"帧级完美反应、根本打不动"的 CPU。
所有方向都用相对朝向的数字键盘记法：6=前、4=后、2=下、1=后下（蹲防）……

- RandomBot           随机按键（持续若干帧），偶尔搓必杀
- GreedyBot           贪心进攻：能打就打、贴身投、跳入，不防御
- CounterBot          防守反击：看招防御（区分上下段）、对空冲天拳、确反挥空/被防的大硬直招
- 另外提供 make_scripted(name) 工厂
"""
from collections import deque
from typing import Optional

import numpy as np

from envs.fighting2d import constants as C
from envs.fighting2d.env import Opponent

E = C.encode_input


def _phase(f):
    m = f.move
    if m is None:
        return None, 0
    if f.move_frame <= m.startup:
        return "startup", m.total - f.move_frame
    if f.move_frame <= m.startup + m.active:
        return "active", m.total - f.move_frame
    return "recovery", m.total - f.move_frame


def snapshot(core, idx):
    """把对局状态压成一个小字典（脚本 CPU 的"感知"）。"""
    me, op = core.f[idx], core.f[1 - idx]
    ph, left = _phase(op)
    rel = (op.x - me.x) * me.facing  # >0 表示对手在我前方
    incoming = None
    incoming_v = 0.0
    for p in core.projs:
        if p.owner != idx:
            d = (p.x - me.x)
            if d * p.vx < 0:  # 正朝我飞来
                incoming = abs(d)
                incoming_v = abs(p.vx)
    return {
        "dist": abs(op.x - me.x), "rel": rel, "op_state": op.state, "op_move": op.move.name if op.move else None,
        "op_level": op.move.level if op.move else None, "op_phase": ph, "op_left": left,
        "op_air": op.airborne, "op_y": op.y, "op_vy": op.vy, "op_can_act": op.can_act(),
        "op_stun": op.stun, "op_blocking": op.dir_now in (4, 1) and op.can_act(),
        "op_throw_ok": op.state not in (C.S_HITSTUN, C.S_BLOCKSTUN, C.S_KNOCKDOWN, C.S_AIR, C.S_AIR_HIT),
        "incoming": incoming, "incoming_v": incoming_v, "my_proj": me.proj is not None,
        "my_back_wall": (me.x - C.BODY_HALF_W) if me.facing > 0 else (C.STAGE_W - C.BODY_HALF_W - me.x),
    }


class ScriptedBot(Opponent):
    """带反应延迟 + 动作队列的脚本 CPU 基类。"""

    name = "scripted"

    def __init__(self, reaction_frames: int = 10, mistake_rate: float = 0.03, seed: Optional[int] = None):
        self.reaction = reaction_frames
        self.mistake = mistake_rate
        self.rng = np.random.default_rng(seed)
        self.reset(seed)

    def reset(self, seed=None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        self.hist = deque(maxlen=max(1, self.reaction + 1))
        self.queue = []
        self.hold = 0

    def act(self, core, idx):
        self.hist.append(snapshot(core, idx))
        seen = self.hist[0]  # reaction 帧之前的世界
        me = core.f[idx]
        if self.queue:
            return self.queue.pop(0)
        if self.rng.random() < self.mistake:
            return int(self.rng.integers(C.N_FRAME_INPUTS))
        return self.decide(seen, me, core)

    def decide(self, s, me, core):  # pragma: no cover
        raise NotImplementedError

    # 常用的指令序列
    def press(self, d, b, hold_dir_frames=0):
        seq = [E(d, b)] + [E(d, 0)] * hold_dir_frames
        self.queue = seq[1:]
        return seq[0]

    def motion(self, dirs, b, tail=2):
        seq = [E(d, 0) for d in dirs[:-1]] + [E(dirs[-1], b)] + [E(dirs[-1], 0)] * tail
        self.queue = seq[1:]
        return seq[0]

    def fireball(self, b=C.BTN_L):
        return self.motion((2, 3, 6), b)

    def dp(self, b=C.BTN_H):
        return self.motion((6, 2, 3), b)


class RandomBot(ScriptedBot):
    name = "random"

    def __init__(self, seed=None, **kw):
        super().__init__(reaction_frames=0, mistake_rate=0.0, seed=seed)

    def decide(self, s, me, core):
        if self.rng.random() < 0.02:
            return self.fireball(int(self.rng.integers(1, 3))) if self.rng.random() < 0.5 else self.dp(int(self.rng.integers(1, 3)))
        a = int(self.rng.integers(C.N_FRAME_INPUTS))
        n = int(self.rng.integers(3, 12))
        d, _ = C.decode_input(a)
        self.queue = [a] + [E(d, 0)] * (n - 1)
        return self.queue.pop(0)


class GreedyBot(ScriptedBot):
    """贪心进攻型：只看眼前收益，能打就打，从不主动防御。"""

    name = "greedy"

    def __init__(self, seed=None, reaction_frames=8, mistake_rate=0.03):
        super().__init__(reaction_frames=reaction_frames, mistake_rate=mistake_rate, seed=seed)

    def decide(self, s, me, core):
        r = self.rng.random()
        if not me.can_act():
            # 在出招中：命中了就取消接必杀（连段）
            if me.move is not None and me.move.cancelable and me.move_contact:
                return self.fireball(C.BTN_H) if s["dist"] > 45 else self.dp(C.BTN_L)
            return E(6, 0)
        dist = s["dist"]
        if s["op_state"] in (C.S_HITSTUN,) and dist < 60:
            return self.press(6, C.BTN_L, 2)
        if dist <= 50:
            if r < 0.30 and s["op_throw_ok"]:
                return self.press(6, C.BTN_H, 3)
            if r < 0.65:
                return self.press(5, C.BTN_L, 3)
            if r < 0.85:
                return self.press(2, C.BTN_L, 3)
            return self.press(5, C.BTN_H, 6)
        if dist <= 85:
            if r < 0.35:
                return self.press(5, C.BTN_H, 6)
            if r < 0.55:
                return self.press(2, C.BTN_H, 6)
            return E(6, 0)
        if r < 0.04 and dist < 200:
            # 前跳 + 下落时重攻击
            self.queue = [E(9, 0)] * 2 + [E(5, 0)] * 14 + [E(5, C.BTN_H)] + [E(5, 0)] * 12
            return E(9, 0)
        if r < 0.07 and not s["my_proj"]:
            return self.fireball(C.BTN_L)
        return E(6, 0)


class CounterBot(ScriptedBot):
    """防守反击型：默认蹲防（挡中/下段），看到跳入就对空冲天拳或站防，
    看到对手收招硬直就按剩余帧数选确反招式，贴身偶尔蹲轻拳（打断 + 拆投）或投。

    注意：概率参数是"每帧风险率"（hazard），反应延迟 reaction_frames 帧内看到的都是旧画面。
    """

    name = "counter"

    def __init__(self, seed=None, reaction_frames=10, mistake_rate=0.005, anti_air_rate=0.7, punish_rate=0.9,
                 reversal_rate=0.25, close_jab_hazard=0.04, throw_hazard=0.02, fireball_hazard=0.02,
                 poke_hazard=0.03):
        self.poke_hazard = poke_hazard
        self.anti_air_rate = anti_air_rate
        self.punish_rate = punish_rate
        self.reversal_rate = reversal_rate
        self.close_jab_hazard = close_jab_hazard
        self.throw_hazard = throw_hazard
        self.fireball_hazard = fireball_hazard
        super().__init__(reaction_frames=reaction_frames, mistake_rate=mistake_rate, seed=seed)

    def reset(self, seed=None):
        super().reset(seed)
        self.prev_state = C.S_IDLE
        self.aa_choice = None   # 对当前这次跳跃是否对空（每次跳跃只掷一次骰子）
        self.punish_choice = None
        self.jump_choice = None  # 对当前这发飞行道具是否跳过去

    def act(self, core, idx):
        a = super().act(core, idx)
        self.prev_state = core.f[idx].state
        return a

    def decide(self, s, me, core):
        r = self.rng.random()
        dist = s["dist"]
        if not s["op_air"]:
            self.aa_choice = None
        if s["op_phase"] != "recovery":
            self.punish_choice = None
        if not me.can_act():
            if me.move is not None and me.move.cancelable and me.move_contact:
                return self.fireball(C.BTN_L)
            return E(4, 0) if s["op_air"] else E(1, 0)
        # 0) 防御硬直/倒地起身后对手贴身 -> 无敌冲天拳反击（reversal）
        if self.prev_state in (C.S_BLOCKSTUN, C.S_KNOCKDOWN) and dist < 70:
            if self.rng.random() < self.reversal_rate:
                return self.dp(C.BTN_L)
        # 1) 对空：对手跳过来
        if s["op_air"] and s["op_state"] == C.S_AIR and dist < 110 and s["rel"] > 0:
            if self.aa_choice is None:
                self.aa_choice = self.rng.random() < self.anti_air_rate
            if self.aa_choice and s["op_vy"] < 3 and dist < 95:
                return self.dp(C.BTN_H)
            return E(4, 0)
        # 2) 确反：按"现在还剩多少收招帧"选招（看到的是 reaction 帧前的画面）
        if s["op_phase"] == "recovery":
            left_now = s["op_left"] - self.reaction
            if self.punish_choice is None:
                self.punish_choice = self.rng.random() < self.punish_rate
            if self.punish_choice:
                if left_now >= 5 and dist < 55:
                    return self.press(5, C.BTN_L, 1)        # 轻拳确反，命中后取消接波
                if left_now >= 9 and dist < 85:
                    return self.press(5, C.BTN_H, 2)
                if left_now >= 10 and dist < 100:
                    return self.press(2, C.BTN_H, 2)
                if left_now >= 14 and dist < 170:
                    return E(6, 0)                          # 走上去确反（下一帧再判断距离）
        # 3) 贴身：偶尔蹲轻拳（打断连打 + 顺带拆投），对手在防御时偶尔投
        if dist < 60:
            if r < self.close_jab_hazard:
                return self.press(1, C.BTN_L, 1)
            if r < self.close_jab_hazard + self.throw_hazard and s["op_throw_ok"] and s["op_blocking"]:
                return self.press(6, C.BTN_H, 2)
        # 3.5) 中距离对手没在出招：偶尔用重拳/扫腿戳（footsies）
        if 70 < dist < 90 and s["op_phase"] is None and not s["op_air"] and r < self.poke_hazard:
            return self.press(5, C.BTN_H, 2) if r < self.poke_hazard / 2 else self.press(2, C.BTN_H, 2)
        # 4) 飞行道具：防住；慢速波偶尔跳过去反打
        if s["incoming"] is not None and s["incoming"] < 220:
            if self.jump_choice is None:
                self.jump_choice = s["incoming_v"] < 5 and self.rng.random() < 0.35
            if self.jump_choice and 70 < s["incoming"] < 120:
                self.jump_choice = False
                self.queue = [E(9, 0)] * 2 + [E(5, 0)] * 16 + [E(5, C.BTN_H)] + [E(5, 0)] * 10
                return E(9, 0)
            return E(1, 0)
        self.jump_choice = None
        if s["op_move"] in ("fireball_L", "fireball_H") and s["op_phase"] == "startup":
            return E(1, 0)
        # 5) 远距离：偶尔对波，否则慢慢走近（光蹲防会被削血磨死）
        if dist > 170:
            if me.proj is None and r < self.fireball_hazard:
                return self.fireball(C.BTN_L if r < self.fireball_hazard / 2 else C.BTN_H)
            return E(6, 0)
        # 默认：对手在空中站防，否则蹲防
        return E(4, 0) if s["op_air"] else E(1, 0)


class MasherBot(ScriptedBot):
    """"乱按"基线：每 4 帧均匀随机选一个智能体层动作（含必杀宏），等价于未训练的 PPO 策略。"""

    name = "masher"

    def __init__(self, seed=None, frame_skip=4, **kw):
        self.k = frame_skip
        super().__init__(reaction_frames=0, mistake_rate=0.0, seed=seed)

    def decide(self, s, me, core):
        from wrappers.macros import N_ACTIONS_WITH_MACROS, expand
        seq = expand(int(self.rng.integers(N_ACTIONS_WITH_MACROS)), self.k)
        self.queue = seq[1:]
        return seq[0]


SCRIPTED = {"random": RandomBot, "greedy": GreedyBot, "counter": CounterBot, "masher": MasherBot}


def make_scripted(name: str, seed=None, **kw) -> ScriptedBot:
    return SCRIPTED[name](seed=seed, **kw)
