"""DIAMBRA Arena 适配器（需要 Docker + DIAMBRA 账号 + 你自己的 ROM；建议在 Linux 服务器上运行）。

  pip install diambra diambra-arena
  diambra arena check-roms /abs/path/samsh5sp.zip        # 校验 ROM 的 sha256
  diambra run -r /abs/path/roms python scripts/train.py ...  # diambra CLI 负责拉起引擎容器

设置：step_ratio=1（一步一帧，与本项目的包装器一致）、MULTI_DISCRETE 动作 [移动 9, 攻击 N]。
DIAMBRA 移动编号（官方文档各游戏页一致）：0 无, 1 左, 2 左上, 3 上, 4 右上, 5 右, 6 右下, 7 下, 8 左下。
观测里自带 RAM 状态：P1/P2 的 health、side、wins、character，以及 timer、stage。
"""
from typing import Optional

import numpy as np

from .adapter_base import ExternalFightingEnv, RamState
from .retro_adapter import load_spec

# 绝对数字键盘方向 -> DIAMBRA 移动编号
NUMPAD_TO_DIAMBRA = {5: 0, 4: 1, 7: 2, 8: 3, 9: 4, 6: 5, 3: 6, 2: 7, 1: 8}


def _num(v):
    """DIAMBRA 的 RAM 值可能是标量或 shape (1,) 的数组。"""
    return float(np.asarray(v).ravel()[0])


def import_diambra():
    import diambra.arena as arena
    return arena


class DiambraFightingEnv(ExternalFightingEnv):
    N_EXTRA = 0

    def __init__(self, spec, opponent=None, me: int = 0, damage_reward=1.0, win_reward=1.0, seed=None,
                 difficulty: Optional[int] = None, characters=None, arena_module=None, max_frames=None,
                 episode: str = "round"):
        self.spec = load_spec(spec) if isinstance(spec, str) else spec
        self.arena = arena_module or import_diambra()
        self.two_player = opponent is not None
        self.episode = episode
        Settings = self.arena.EnvironmentSettingsMultiAgent if self.two_player else self.arena.EnvironmentSettings
        st = Settings()
        st.step_ratio = 1
        st.action_space = self._space_type("MULTI_DISCRETE")
        st.frame_shape = tuple(self.spec.get("frame_shape", (0, 0, 0)))
        if not self.two_player:
            st.role = self._role("P1" if me == 0 else "P2")
        if difficulty is not None and not self.two_player:
            st.difficulty = difficulty
        if characters is not None:
            st.characters = characters
        self.denv = self.arena.make(self.spec["game"], st)
        self._obs = None
        self._info = {}
        self._done = False
        super().__init__(me=me, opponent=opponent, damage_reward=damage_reward, win_reward=win_reward,
                         max_frames=max_frames)

    def _space_type(self, name):
        st = getattr(self.arena, "SpaceTypes", None)
        return getattr(st, name) if st is not None else name

    def _role(self, name):
        roles = getattr(self.arena, "Roles", None)
        return getattr(roles, name) if roles is not None else name

    def _act(self, abs_input):
        if abs_input is None:
            return [0, 0]
        d, b = abs_input
        attack = 0 if b == 0 else self.spec["attacks"]["L" if b == 1 else "H"]
        return [NUMPAD_TO_DIAMBRA[d], attack]

    def _backend_reset(self, seed=None):
        self._obs, self._info = self.denv.reset(seed=seed)
        self._done = False

    def _backend_step(self, abs_inputs):
        if self.two_player:
            act = {"agent_0": self._act(abs_inputs[0]), "agent_1": self._act(abs_inputs[1])}
        else:
            act = self._act(abs_inputs[self.me])
        self._obs, _, terminated, truncated, self._info = self.denv.step(act)
        done_key = {"round": "round_done", "stage": "stage_done", "game": "game_done"}[self.episode]
        self._done = bool(terminated or truncated or self._info.get(done_key, False))

    def _read_ram(self) -> RamState:
        o = self._obs
        p = [o["P1"], o["P2"]]
        hp = [_num(p[0]["health"]), _num(p[1]["health"])]
        side = [int(_num(p[0]["side"])), int(_num(p[1]["side"]))]
        wins = [int(_num(p[0]["wins"])), int(_num(p[1]["wins"]))]
        winner = None
        if self._done:
            winner = 0 if hp[0] > hp[1] else (1 if hp[1] > hp[0] else -1)
        return RamState(hp=hp, hp_max=float(self.spec["hp_max"]), side=side, rounds=wins,
                        timer=_num(o.get("timer", 0)), timer_max=float(self.spec.get("timer_max", 99)),
                        round_over=self._done, winner=winner)

    def render(self):
        return None if self._obs is None else self._obs.get("frame")

    def close(self):
        self.denv.close()
