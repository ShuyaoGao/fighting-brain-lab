"""统一的环境工厂：同一份 EnvConfig 可以生成自带小环境 / stable-retro / DIAMBRA 的环境，
并叠上同一套"人类条件"包装器。训练脚本只和这里打交道。"""
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

from wrappers import (ActionHistory, APMLimit, FrameSkip, MacroActions, ObservationDelay, PixelObservation,
                      StickyActions, ms_to_frames)


@dataclass
class EnvConfig:
    game: str = "fighting2d"          # fighting2d | retro | diambra
    game_id: str = ""                  # retro: 例如 "SamuraiShodown-Genesis"；diambra: 例如 "samsh5sp"
    game_kwargs: Dict[str, Any] = field(default_factory=dict)
    round_seconds: float = 30.0
    frame_skip: int = 4                # 60FPS 下 4 帧 = 每秒 15 次决策
    delay_ms: float = 0.0              # 观测延迟（反应时间）
    sticky: float = 0.0                # 粘滞动作概率
    apm: Optional[float] = None        # None = 不限制（但仍统计实际 APM）
    macros: bool = True                # 是否提供必杀技指令宏
    action_history: int = 4            # 观测里拼接最近 n 个自己的动作
    obs: str = "ram"                   # ram | pixels
    visible_only: bool = False         # 只给人类在屏幕上看得到的信息（去掉精确帧计数、无敌标志）
    damage_reward: float = 1.0
    win_reward: float = 1.0
    random_side: bool = True

    @property
    def delay_frames(self) -> int:
        return ms_to_frames(self.delay_ms)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def make_base_env(cfg: EnvConfig, opponent=None, seed: Optional[int] = None, render_mode=None):
    if cfg.game == "fighting2d":
        from envs.fighting2d import Fighting2DEnv
        return Fighting2DEnv(opponent=opponent, round_seconds=cfg.round_seconds, random_side=cfg.random_side,
                             damage_reward=cfg.damage_reward, win_reward=cfg.win_reward,
                             obs_type="ram", render_mode=render_mode, seed=seed, visible_only=cfg.visible_only,
                             **cfg.game_kwargs)
    if cfg.game == "retro":
        from envs.retro_adapter import RetroFightingEnv
        return RetroFightingEnv(cfg.game_id, opponent=opponent, damage_reward=cfg.damage_reward,
                                win_reward=cfg.win_reward, **cfg.game_kwargs)
    if cfg.game == "diambra":
        from envs.diambra_adapter import DiambraFightingEnv
        return DiambraFightingEnv(cfg.game_id, opponent=opponent, damage_reward=cfg.damage_reward,
                                  win_reward=cfg.win_reward, seed=seed, **cfg.game_kwargs)
    raise ValueError(f"未知 game: {cfg.game}")


def wrap_env(env, cfg: EnvConfig, seed: Optional[int] = None):
    """顺序（内 -> 外）：APM 统计/限制 -> 粘滞 -> 观测延迟 -> 跳帧 -> 宏 -> 动作历史 [-> 像素]"""
    env = APMLimit(env, apm=cfg.apm)
    if cfg.sticky > 0:
        env = StickyActions(env, cfg.sticky, seed=seed)
    if cfg.delay_frames > 0:
        env = ObservationDelay(env, cfg.delay_frames)
    env = FrameSkip(env, cfg.frame_skip)
    if cfg.macros:
        env = MacroActions(env)
    if cfg.obs == "pixels":
        env = PixelObservation(env)
    elif cfg.action_history > 0:
        env = ActionHistory(env, cfg.action_history)
    return env


def make_env(cfg: EnvConfig, opponent=None, seed: Optional[int] = None, render_mode=None):
    return wrap_env(make_base_env(cfg, opponent, seed, render_mode), cfg, seed)


class EnvFactory:
    """可 pickle 的环境构造器（Windows 多进程 spawn 需要）。opponent_spec 见 league.pool.make_opponent。"""

    def __init__(self, cfg: EnvConfig, opponent_spec=None, seed: int = 0):
        self.cfg_dict = cfg.to_dict()
        self.opponent_spec = opponent_spec
        self.seed = seed

    def __call__(self):
        from league.pool import make_opponent
        cfg = EnvConfig.from_dict(self.cfg_dict)
        opp = make_opponent(self.opponent_spec, seed=self.seed + 7919) if self.opponent_spec is not None else None
        return make_env(cfg, opp, seed=self.seed)
