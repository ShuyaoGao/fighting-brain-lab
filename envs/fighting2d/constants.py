"""自带 2D 格斗小环境的常量。

单位：位置是"像素"（舞台 384 宽，和 CPS/Neo Geo 的 320~384 像素宽量级一致），
时间是"帧"（逻辑 60 FPS，和街机一致）。
"""

FPS = 60
STAGE_W = 384.0
STAGE_H = 224
GROUND_Y = 0.0

MAX_HP = 1000
DEFAULT_ROUND_SECONDS = 30

# 身体尺寸
BODY_HALF_W = 20.0
STAND_H = 90.0
CROUCH_H = 56.0
AIR_HURT = (-18.0, 18.0, 10.0, 80.0)  # 相对脚底 (x0, x1, y0, y1)

# 移动
WALK_F = 2.5
WALK_B = 2.0
JUMP_VY = 11.0
JUMP_VX = 3.0
GRAVITY = 0.75
JUMPSQUAT = 3
LANDING_LAG = 3
KNOCKDOWN_FRAMES = 40
AIR_HIT_KNOCKBACK = 3.0

START_X = (STAGE_W / 2 - 72.0, STAGE_W / 2 + 72.0)

# 输入
INPUT_BUFFER = 4         # 按键缓冲帧数（恢复帧最后几帧按下的键会在可行动时生效）
MOTION_WINDOW = 15       # 指令输入（↓↘→ 等）的判定窗口
THROW_RANGE = 56.0       # 投技判定距离（中心距）
THROW_TECH_WINDOW = 5    # 投技生效时，被投方若在最近 5 帧内按过键则拆投
COMBO_SCALING = 0.1      # 每多一段连击伤害 -10%
MIN_SCALING = 0.3

# 状态
S_IDLE = 0
S_WALK_F = 1
S_WALK_B = 2
S_CROUCH = 3
S_JUMPSQUAT = 4
S_AIR = 5
S_LANDING = 6
S_ATTACK = 7
S_HITSTUN = 8
S_BLOCKSTUN = 9
S_KNOCKDOWN = 10
S_AIR_HIT = 11
S_KO = 12
N_STATES = 13
STATE_NAMES = [
    "idle", "walk_f", "walk_b", "crouch", "jumpsquat", "air", "landing",
    "attack", "hitstun", "blockstun", "knockdown", "air_hit", "ko",
]

# 方向用"数字键盘记法"（相对朝向）：6=前 4=后 2=下 8=上 5=中立
#   7 8 9
#   4 5 6
#   1 2 3
DIRS = (5, 6, 4, 2, 8, 3, 1, 9, 7)
BTN_NONE, BTN_L, BTN_H = 0, 1, 2
N_DIRS = 9
N_BUTTONS = 3
N_FRAME_INPUTS = N_DIRS * N_BUTTONS  # 27 种逐帧输入


def encode_input(numpad_dir: int, button: int) -> int:
    """(相对方向, 按键) -> 0..26 的逐帧输入编号。"""
    return DIRS.index(numpad_dir) * N_BUTTONS + button


def decode_input(code: int):
    return DIRS[code // N_BUTTONS], code % N_BUTTONS
