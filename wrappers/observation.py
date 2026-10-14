"""观测选择：RAM 特征（默认，小环境直接给；真实游戏从 RAM 地址表读出）或像素帧。"""
import gymnasium as gym
import numpy as np
from gymnasium import spaces
from PIL import Image


class PixelObservation(gym.ObservationWrapper):
    """用 env.render() 的 RGB 帧做观测，缩放 + 可选灰度。配合 FrameStack 使用。"""

    def __init__(self, env, size=(84, 84), grayscale=True):
        super().__init__(env)
        self.size = tuple(size)
        self.grayscale = grayscale
        shape = (self.size[1], self.size[0]) if grayscale else (self.size[1], self.size[0], 3)
        self.observation_space = spaces.Box(0, 255, shape=shape, dtype=np.uint8)

    def observation(self, obs):
        frame = self.env.render()
        img = Image.fromarray(frame)
        if self.grayscale:
            img = img.convert("L")
        img = img.resize(self.size, Image.BILINEAR)
        return np.asarray(img, dtype=np.uint8)


class RamFeatureSelect(gym.ObservationWrapper):
    """从 dict 观测（如 DIAMBRA / retro 的 RAM 变量）里挑选并拼接成向量。"""

    def __init__(self, env, keys, scales=None):
        super().__init__(env)
        self.keys = list(keys)
        self.scales = scales or {}
        self.observation_space = spaces.Box(-np.inf, np.inf, shape=(len(self.keys),), dtype=np.float32)

    def observation(self, obs):
        out = []
        for k in self.keys:
            v = obs
            for part in k.split("."):
                v = v[part]
            out.append(float(np.asarray(v).ravel()[0]) / self.scales.get(k, 1.0))
        return np.asarray(out, dtype=np.float32)
