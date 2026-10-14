"""把 PyTorch 策略导出成纯 numpy 前向（对手池/评估用：快、无需 torch、可在任何进程里跑）。"""
import numpy as np


class NumpyPolicy:
    def __init__(self, weights: dict, activation: str = "tanh", masks=None):
        # weights: {"W0","b0","W1","b1",...,"Wout","bout"}，W 形状 (in, out)
        self.layers = []
        i = 0
        while f"W{i}" in weights:
            self.layers.append((np.asarray(weights[f"W{i}"], np.float32), np.asarray(weights[f"b{i}"], np.float32)))
            i += 1
        self.out = (np.asarray(weights["Wout"], np.float32), np.asarray(weights["bout"], np.float32))
        self.act_fn = np.tanh if activation == "tanh" else (lambda x: np.maximum(x, 0))
        self.obs_dim = self.layers[0][0].shape[0]
        self.n_actions = self.out[0].shape[1]
        # masks[l][j] = 0：把第 l 个隐藏层的第 j 个神经元"敲掉"（激活置零），用于敲除实验
        self.masks = None if masks is None else [None if m is None else np.asarray(m, np.float32) for m in masks]

    def hidden(self, obs):
        """返回各隐藏层激活（已应用 mask），线性探针用。"""
        x = np.asarray(obs, np.float32)
        acts = []
        for l, (W, b) in enumerate(self.layers):
            x = self.act_fn(x @ W + b)
            if self.masks is not None and l < len(self.masks) and self.masks[l] is not None:
                x = x * self.masks[l]
            acts.append(x)
        return acts

    def logits(self, obs):
        x = np.asarray(obs, np.float32)
        for l, (W, b) in enumerate(self.layers):
            x = self.act_fn(x @ W + b)
            if self.masks is not None and l < len(self.masks) and self.masks[l] is not None:
                x = x * self.masks[l]
        return x @ self.out[0] + self.out[1]

    def act(self, obs, rng=None, deterministic=False):
        lg = self.logits(obs)
        if deterministic or rng is None:
            return int(np.argmax(lg)) if lg.ndim == 1 else np.argmax(lg, -1)
        lg = lg - lg.max(-1, keepdims=True)
        p = np.exp(lg)
        p /= p.sum(-1, keepdims=True)
        if p.ndim == 1:
            return int(rng.choice(len(p), p=p))
        u = rng.random((p.shape[0], 1))
        return (p.cumsum(-1) > u).argmax(-1)
