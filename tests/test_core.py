"""格斗核心的机制测试：命中/防御/上下段/飞行道具/无敌/投技/拆投/连段/结束条件/观测对称性。"""
import numpy as np
import pytest

from envs.fighting2d import FightingCore
from envs.fighting2d import constants as C

E = C.encode_input
N = E(5, 0)


def make(x0=150.0, x1=200.0):
    c = FightingCore(seed=0, random_start=False)
    c.reset()
    c.f[0].x, c.f[1].x = x0, x1
    return c


def run(c, seq0, seq1=None, n=None):
    seq1 = seq1 or []
    n = n or max(len(seq0), len(seq1))
    for i in range(n):
        a = seq0[i] if i < len(seq0) else (seq0[-1] if seq0 else N)
        b = seq1[i] if i < len(seq1) else (seq1[-1] if seq1 else N)
        c.step(a, b)
        if c.done:
            break


def test_jab_hits_idle_opponent():
    c = make()
    run(c, [E(5, C.BTN_L)] + [N] * 6, [N] * 7)
    assert c.f[1].hp == C.MAX_HP - 30
    assert c.f[1].state == C.S_HITSTUN


def test_stand_block_stops_mid_but_not_low():
    c = make()
    run(c, [E(5, C.BTN_L)] + [N] * 6, [E(4, 0)] * 7)
    assert c.f[1].hp == C.MAX_HP and c.f[1].state == C.S_BLOCKSTUN
    c = make()
    run(c, [E(2, C.BTN_L)] + [E(2, 0)] * 6, [E(4, 0)] * 7)
    assert c.f[1].hp == C.MAX_HP - 25  # 下段打站防


def test_crouch_block_stops_low_but_not_jump_attack():
    c = make()
    run(c, [E(2, C.BTN_L)] + [E(2, 0)] * 6, [E(1, 0)] * 7)
    assert c.f[1].hp == C.MAX_HP
    # 跳入重攻击（上段）打蹲防
    c = make(120.0, 200.0)
    seq = [E(9, 0)] * 2 + [N] * 12 + [E(5, C.BTN_H)] + [N] * 25
    run(c, seq, [E(1, 0)] * len(seq))
    assert c.f[1].hp < C.MAX_HP


def test_fireball_motion_spawns_single_projectile():
    c = make(100.0, 300.0)
    run(c, [E(2, 0), E(3, 0), E(6, C.BTN_L)] + [N] * 14, [N] * 17)
    assert len(c.projs) == 1 and c.f[0].proj is not None
    # 已有飞行道具时再搓不会出第二发（变成普通技）
    run(c, [E(2, 0), E(3, 0), E(6, C.BTN_L)] + [N] * 14, [N] * 17)
    assert len(c.projs) <= 1


def test_fireball_hits_and_chips_when_blocked():
    c = make(100.0, 300.0)
    run(c, [E(2, 0), E(3, 0), E(6, C.BTN_H)] + [N] * 60, [N] * 63)
    assert c.f[1].hp == C.MAX_HP - 60
    c = make(100.0, 300.0)
    run(c, [E(2, 0), E(3, 0), E(6, C.BTN_H)] + [N] * 60, [E(4, 0)] * 63)
    assert c.f[1].hp == C.MAX_HP - 10  # 削血


def test_dp_is_invulnerable_on_startup():
    c = make(150.0, 190.0)
    # P1 出轻拳（第 5 帧有判定），P0 在第 3 帧完成冲天拳指令 -> 无敌期间对拳免疫并打中对手
    seq0 = [E(6, 0), E(2, 0), E(3, C.BTN_L)] + [N] * 30
    seq1 = [N, N, E(5, C.BTN_L)] + [N] * 30
    run(c, seq0, seq1)
    assert c.f[0].hp == C.MAX_HP
    assert c.f[1].hp < C.MAX_HP


def test_throw_and_tech():
    c = make(150.0, 190.0)
    run(c, [E(6, C.BTN_H)] + [N] * 10, [E(4, 0)] * 11)
    assert c.f[1].hp == C.MAX_HP - 110 and c.f[1].state == C.S_KNOCKDOWN
    c = make(150.0, 190.0)
    run(c, [E(6, C.BTN_H)] + [N] * 10, [E(1, 0), E(1, C.BTN_L)] + [E(1, 0)] * 9)
    assert c.f[1].hp == C.MAX_HP  # 拆投（或轻拳先打到）
    assert c.stats[1]["techs"] + c.stats[1]["hits"] >= 1


def test_link_combo_and_scaling():
    c = make(150.0, 195.0)
    # 轻拳 -> 收招最后几帧预输入（按键缓冲 4 帧）-> 再轻拳（+5 有利，4 帧发生，能连上）
    seq = [E(5, C.BTN_L)] + [N] * 11 + [E(5, C.BTN_L)] + [N] * 10
    run(c, seq, [N] * len(seq))
    assert c.stats[0]["max_combo"] == 2
    assert c.f[1].hp == C.MAX_HP - 30 - 27  # 第二段 -10%


def test_cancel_into_special():
    c = make(150.0, 195.0)
    seq = [E(2, C.BTN_L), E(2, 0), E(2, 0), E(2, 0), E(2, 0), E(3, 0), E(6, C.BTN_H)] + [N] * 40
    run(c, seq, [N] * len(seq))
    assert c.stats[0]["cancels"] == 1
    assert c.stats[0]["moves"].get("fireball_H") == 1


def test_timeout_winner_by_hp():
    c = FightingCore(round_seconds=1, seed=0, random_start=False)
    c.reset()
    c.f[0].x, c.f[1].x = 150.0, 190.0
    run(c, [E(5, C.BTN_L)] + [N] * 100, [N] * 101)
    assert c.done and c.end_reason == "timeout" and c.winner == 0


def test_ko():
    c = make()
    c.f[1].hp = 20
    run(c, [E(5, C.BTN_L)] + [N] * 6, [N] * 7)
    assert c.done and c.end_reason == "ko" and c.winner == 0


def test_observation_mirror_symmetry():
    c = make(150.0, 230.0)
    o0 = c.observe(0)
    c2 = make(384 - 230.0, 384 - 150.0)
    o1 = c2.observe(1)
    np.testing.assert_allclose(o0, o1, atol=1e-6)


def test_determinism():
    def play(seed):
        c = FightingCore(seed=seed)
        rng = np.random.default_rng(seed)
        while not c.done:
            c.step(int(rng.integers(27)), int(rng.integers(27)))
        return c.f[0].hp, c.f[1].hp, c.frame

    assert play(3) == play(3)


@pytest.mark.parametrize("seed", range(5))
def test_random_play_invariants(seed):
    c = FightingCore(seed=seed)
    rng = np.random.default_rng(seed)
    while not c.done:
        c.step(int(rng.integers(27)), int(rng.integers(27)))
        for f in c.f:
            assert C.BODY_HALF_W - 1e-6 <= f.x <= C.STAGE_W - C.BODY_HALF_W + 1e-6
            assert f.y >= 0
            assert 0 <= f.hp <= C.MAX_HP
    assert c.winner in (0, 1, -1)


def test_visible_only_masks_hidden_counters():
    from envs.fighting2d.core import HIDDEN_IDX
    c = make()
    run(c, [E(5, C.BTN_L)] + [N] * 3, [N] * 4)
    full, vis = c.observe(0), c.observe(0, visible_only=True)
    assert full[HIDDEN_IDX].any() and not vis[HIDDEN_IDX].any()
    keep = np.ones(len(full), bool)
    keep[HIDDEN_IDX] = False
    np.testing.assert_array_equal(full[keep], vis[keep])
