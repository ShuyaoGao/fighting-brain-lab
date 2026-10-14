from envs.fighting2d import constants as C
from scripts.play_vs_ai import keys_to_input

E = C.encode_input


def test_keys_to_relative_input():
    assert keys_to_input({"right"}, 1) == E(6, 0)          # 朝右按右 = 前
    assert keys_to_input({"right"}, -1) == E(4, 0)         # 朝左按右 = 后（防御）
    assert keys_to_input({"left", "down"}, 1) == E(1, 0)   # 蹲防
    assert keys_to_input({"up", "right", "L"}, 1) == E(9, C.BTN_L)
    assert keys_to_input({"H"}, 1) == E(5, C.BTN_H)
    assert keys_to_input({"left", "right"}, 1) == E(5, 0)
