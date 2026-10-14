"""stable-retro 适配器（Linux/macOS；Windows 只能 WSL2）。

  pip install stable-retro          # 新版 import 名是 stable_retro，老版是 retro，这里两个都试
  python -m stable_retro.import /path/to/your/roms   # 导入你自己合法拥有的 ROM（按哈希匹配）

游戏差异全部放在 envs/game_specs/<name>.json：
  game / state_1p / state_2p / buttons（统一的 L、H 映射到手柄键名）/ ram（info 变量名）/ hp_max
本模块不含任何 ROM，也不会下载 ROM。
"""
import json
from pathlib import Path
from typing import Optional

import numpy as np

from .adapter_base import ExternalFightingEnv, RamState, numpad_to_udlr

SPEC_DIR = Path(__file__).resolve().parent / "game_specs"


def load_spec(name_or_path):
    p = Path(name_or_path)
    if not p.suffix:
        p = SPEC_DIR / f"{name_or_path}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def import_retro():
    try:
        import stable_retro as retro  # stable-retro >= 1.0
    except ImportError:
        import retro  # 旧版 stable-retro / gym-retro
    return retro


class RetroFightingEnv(ExternalFightingEnv):
    """spec: game_specs 里的名字或 json 路径；two_player=True 时用 2P 存档，对手由 opponent 控制。"""

    def __init__(self, spec, opponent=None, two_player: Optional[bool] = None, me: int = 0,
                 damage_reward=1.0, win_reward=1.0, max_frames=None, render_mode=None, retro_module=None,
                 **make_kwargs):
        self.spec = load_spec(spec) if isinstance(spec, (str, Path)) else spec
        self.two_player = (opponent is not None) if two_player is None else two_player
        self._retro = retro_module or import_retro()
        state = self.spec.get("state_2p" if self.two_player else "state_1p")
        kw = dict(game=self.spec["game"], players=2 if self.two_player else 1)
        if state:
            kw["state"] = state
        kw.update(make_kwargs)
        if render_mode:
            kw["render_mode"] = render_mode
        self.retro_env = self._retro.make(**kw)
        self.buttons = list(getattr(self.retro_env.unwrapped, "buttons", self.retro_env.buttons))
        self._last_info = {}
        self._last_obs = None
        self._backend_done = False
        super().__init__(me=me, opponent=opponent, damage_reward=damage_reward, win_reward=win_reward,
                         max_frames=max_frames)

    # 统一输入 -> 手柄按键数组
    def _pad(self, abs_input):
        arr = np.zeros(len(self.buttons), dtype=np.int8)
        if abs_input is None:
            return arr
        d, b = abs_input
        up, down, left, right = numpad_to_udlr(d)
        for name, on in (("UP", up), ("DOWN", down), ("LEFT", left), ("RIGHT", right)):
            if on and name in self.buttons:
                arr[self.buttons.index(name)] = 1
        if b:
            for name in self.spec["buttons"]["L" if b == 1 else "H"]:
                arr[self.buttons.index(name)] = 1
        return arr

    def _backend_reset(self, seed=None):
        obs, info = self.retro_env.reset(seed=seed)
        self._last_obs, self._last_info = obs, info or {}
        self._backend_done = False
        if not self._last_info:
            # 部分版本 reset 不返回 info：空推一帧拿到 RAM 变量
            self._backend_step([(5, 0), (5, 0)])

    def _backend_step(self, abs_inputs):
        if self.two_player:
            act = np.concatenate([self._pad(abs_inputs[0]), self._pad(abs_inputs[1])])
        else:
            act = self._pad(abs_inputs[self.me])
        obs, rew, terminated, truncated, info = self.retro_env.step(act)
        self._last_obs, self._last_info = obs, info
        self._backend_done = bool(terminated or truncated)

    def _var(self, key):
        return float(self._last_info[key]) if key in self._last_info else None

    def _read_ram(self) -> RamState:
        ram = self.spec["ram"]
        hp = [self._var(ram["hp"][0]) or 0.0, self._var(ram["hp"][1]) or 0.0]
        x = [self._var(k) for k in ram["x"]] if ram.get("x") else None
        y = [self._var(k) for k in ram["y"]] if ram.get("y") else None
        rounds = [int(self._var(k) or 0) for k in ram["rounds"]] if ram.get("rounds") else None
        timer = self._var(ram["timer"]) if ram.get("timer") else None
        hp_ko = self.spec.get("hp_ko", 0)
        over = self._backend_done or min(hp) <= hp_ko or (timer is not None and timer <= 0 and self.frame > 0)
        winner = None
        if over:
            winner = 0 if hp[0] > hp[1] else (1 if hp[1] > hp[0] else -1)
        return RamState(hp=hp, hp_max=float(self.spec["hp_max"]), x=x, y=y, timer=timer,
                        timer_max=float(self.spec.get("timer_max", 99)), rounds=rounds,
                        round_over=over, winner=winner)

    def render(self):
        return self._last_obs

    def close(self):
        self.retro_env.close()
