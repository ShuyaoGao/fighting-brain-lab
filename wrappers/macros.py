"""统一动作空间 + 指令宏。

所有适配器（自带小环境 / stable-retro / DIAMBRA）都接受同一套"逐帧输入"：
  0..26 = 9 个相对方向（数字键盘记法，6=前 4=后）× {无, 轻, 重}
在此之上，智能体层动作 = 27 个基本输入 + 若干"指令宏"（必杀技的搓招序列）。

宏动作只是把人类会按的方向序列一次性按出来（↓↘→+拳），不会给 AI 额外的能力；
在 APM 统计里，宏的每一个方向变化和按键都会被计数。
"""
from envs.fighting2d.constants import BTN_H, BTN_L, N_FRAME_INPUTS, decode_input, encode_input

E = encode_input

# 名称 -> 逐帧输入序列
MACROS = {
    "236L": [E(2, 0), E(3, 0), E(6, BTN_L), E(6, 0)],   # 气功波（轻）
    "236H": [E(2, 0), E(3, 0), E(6, BTN_H), E(6, 0)],   # 气功波（重）
    "623L": [E(6, 0), E(2, 0), E(3, BTN_L), E(3, 0)],   # 冲天拳（轻）
    "623H": [E(6, 0), E(2, 0), E(3, BTN_H), E(3, 0)],   # 冲天拳（重）
}
MACRO_NAMES = list(MACROS)
N_BASE = N_FRAME_INPUTS
N_ACTIONS_WITH_MACROS = N_BASE + len(MACROS)


def release(code: int) -> int:
    """同方向、松开按键。"""
    d, _ = decode_input(code)
    return E(d, 0)


def expand(action: int, k: int, tap: bool = True, macros: bool = True):
    """把一个智能体层动作展开成 >=k 帧的逐帧输入序列。

    - 基本输入：tap=True 时只在第一帧按键、其余帧保持方向（这样连续两次"轻拳"是两次独立按键）；
    - 宏：按序列执行，不足 k 帧用最后一帧的方向补齐，超过 k 帧就整段执行完。
    """
    action = int(action)
    if action >= N_BASE:
        if not macros:
            raise ValueError("宏动作未启用")
        seq = list(MACROS[MACRO_NAMES[action - N_BASE]])
    else:
        seq = [action]
    if len(seq) < k:
        fill = release(seq[-1]) if tap else seq[-1]
        seq = seq + [fill] * (k - len(seq))
    return seq


def action_name(action: int) -> str:
    action = int(action)
    if action >= N_BASE:
        return MACRO_NAMES[action - N_BASE]
    d, b = decode_input(action)
    return f"{d}{'' if b == 0 else ('L' if b == BTN_L else 'H')}"
