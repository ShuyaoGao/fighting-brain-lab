"""极简向量化环境：同步（进程内）和多进程两种，接口一致。

- 回合结束时立即自动 reset（同一步返回新回合的初始观测），结束信息放在 infos[i] 里；
- 多进程版每个 worker 跑一组环境，摊薄进程间通信开销（Windows spawn / Linux fork 都能用）。
"""
import multiprocessing as mp
from typing import Callable, List

import numpy as np


def _clean_info(info):
    out = {}
    for k, v in info.items():
        if isinstance(v, (int, float, str, bool, np.integer, np.floating)):
            out[k] = v.item() if hasattr(v, "item") else v
        elif isinstance(v, dict):
            out[k] = {kk: (vv if not isinstance(vv, dict) else dict(vv)) for kk, vv in v.items()}
    return out


class SyncVecEnv:
    def __init__(self, env_fns: List[Callable]):
        self.envs = [fn() for fn in env_fns]
        self.num_envs = len(self.envs)
        self.observation_space = self.envs[0].observation_space
        self.action_space = self.envs[0].action_space

    def reset(self, seed=None):
        obs = []
        for i, e in enumerate(self.envs):
            o, _ = e.reset(seed=None if seed is None else seed + i)
            obs.append(o)
        return np.stack(obs)

    def step(self, actions):
        obs, rews, dones, infos = [], [], [], []
        for e, a in zip(self.envs, actions):
            o, r, te, tr, info = e.step(int(a))
            d = te or tr
            if d:
                infos.append(_clean_info(info))
                o, _ = e.reset()
            else:
                infos.append(None)
            obs.append(o)
            rews.append(r)
            dones.append(d)
        return np.stack(obs), np.asarray(rews, np.float32), np.asarray(dones, bool), infos

    def call_opponent(self, method, *args):
        for e in self.envs:
            getattr(e.unwrapped.opponent, method)(*args)

    def close(self):
        for e in self.envs:
            e.close()


def _worker(conn, env_fns):
    venv = SyncVecEnv(env_fns)
    try:
        while True:
            cmd, data = conn.recv()
            if cmd == "step":
                conn.send(venv.step(data))
            elif cmd == "reset":
                conn.send(venv.reset(data))
            elif cmd == "call_opponent":
                venv.call_opponent(data[0], *data[1])
                conn.send(True)
            elif cmd == "spaces":
                conn.send((venv.observation_space, venv.action_space))
            elif cmd == "close":
                venv.close()
                conn.send(True)
                break
    except (EOFError, KeyboardInterrupt):
        pass


class SubprocVecEnv:
    def __init__(self, env_fns: List[Callable], n_workers: int = 4):
        n_workers = max(1, min(n_workers, len(env_fns)))
        chunks = np.array_split(np.arange(len(env_fns)), n_workers)
        ctx = mp.get_context("spawn")
        self.conns, self.procs, self.slices = [], [], []
        for ch in chunks:
            a, b = ctx.Pipe()
            p = ctx.Process(target=_worker, args=(b, [env_fns[i] for i in ch]), daemon=True)
            p.start()
            self.conns.append(a)
            self.procs.append(p)
            self.slices.append((int(ch[0]), int(ch[-1]) + 1))
        self.num_envs = len(env_fns)
        self.conns[0].send(("spaces", None))
        self.observation_space, self.action_space = self.conns[0].recv()

    def reset(self, seed=None):
        for (lo, _), c in zip(self.slices, self.conns):
            c.send(("reset", None if seed is None else seed + lo))
        return np.concatenate([c.recv() for c in self.conns])

    def step(self, actions):
        for (lo, hi), c in zip(self.slices, self.conns):
            c.send(("step", actions[lo:hi]))
        res = [c.recv() for c in self.conns]
        obs = np.concatenate([r[0] for r in res])
        rews = np.concatenate([r[1] for r in res])
        dones = np.concatenate([r[2] for r in res])
        infos = [i for r in res for i in r[3]]
        return obs, rews, dones, infos

    def call_opponent(self, method, *args):
        for c in self.conns:
            c.send(("call_opponent", (method, args)))
        for c in self.conns:
            c.recv()

    def close(self):
        for c in self.conns:
            try:
                c.send(("close", None))
                c.recv()
            except Exception:
                pass
        for p in self.procs:
            p.join(timeout=5)


def make_vec_env(env_fns, n_workers=0):
    return SyncVecEnv(env_fns) if n_workers <= 0 else SubprocVecEnv(env_fns, n_workers)
