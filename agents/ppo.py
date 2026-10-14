"""CleanRL 风格的 PPO（单文件、可读、无隐藏魔法），离散动作 + MLP。

- 训练默认用 CPU（小 MLP 在 CPU 上比 GPU 快，且不占共享显存）；可 --device cuda。
- 每次 update 往 train_log.jsonl 落一行；回调里做评估、存快照（联赛）。
- 策略可导出成 numpy 权重（见 export_numpy），对手池和评估都用 numpy 前向。
"""
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass

import numpy as np
import torch
import torch.nn as nn
from torch.distributions import Categorical


@dataclass
class PPOConfig:
    total_steps: int = 2_000_000
    num_envs: int = 32
    n_steps: int = 128
    lr: float = 2.5e-4
    anneal_lr: bool = True
    gamma: float = 0.99
    gae_lambda: float = 0.95
    n_epochs: int = 4
    n_minibatches: int = 8
    clip: float = 0.2
    ent_coef: float = 0.01
    vf_coef: float = 0.5
    max_grad_norm: float = 0.5
    target_kl: float = 0.0       # >0 时早停
    hidden: int = 256
    n_layers: int = 2
    device: str = "cpu"
    torch_threads: int = 4
    seed: int = 0

    @property
    def batch_size(self):
        return self.num_envs * self.n_steps


def _layer(i, o, std=np.sqrt(2), bias=0.0):
    lin = nn.Linear(i, o)
    nn.init.orthogonal_(lin.weight, std)
    nn.init.constant_(lin.bias, bias)
    return lin


class ActorCritic(nn.Module):
    def __init__(self, obs_dim, n_actions, hidden=256, n_layers=2):
        super().__init__()

        def mlp(out, out_std):
            layers, d = [], obs_dim
            for _ in range(n_layers):
                layers += [_layer(d, hidden), nn.Tanh()]
                d = hidden
            layers.append(_layer(d, out, out_std))
            return nn.Sequential(*layers)

        self.actor = mlp(n_actions, 0.01)
        self.critic = mlp(1, 1.0)
        self.obs_dim, self.n_actions, self.hidden, self.n_layers = obs_dim, n_actions, hidden, n_layers

    def value(self, x):
        return self.critic(x).squeeze(-1)

    def act(self, x, action=None):
        logits = self.actor(x)
        dist = Categorical(logits=logits)
        if action is None:
            action = dist.sample()
        return action, dist.log_prob(action), dist.entropy(), self.value(x)


def export_numpy(model: ActorCritic) -> dict:
    """actor 权重 -> {"W0","b0",...,"Wout","bout"}（W 形状 in×out），给 NumpyPolicy 用。"""
    lins = [m for m in model.actor if isinstance(m, nn.Linear)]
    w = {}
    for i, lin in enumerate(lins[:-1]):
        w[f"W{i}"] = lin.weight.detach().cpu().numpy().T.copy()
        w[f"b{i}"] = lin.bias.detach().cpu().numpy().copy()
    w["Wout"] = lins[-1].weight.detach().cpu().numpy().T.copy()
    w["bout"] = lins[-1].bias.detach().cpu().numpy().copy()
    return w


def save_checkpoint(path, model, cfg: PPOConfig, env_cfg: dict, extra=None):
    torch.save({"state_dict": model.state_dict(), "obs_dim": model.obs_dim, "n_actions": model.n_actions,
                "hidden": model.hidden, "n_layers": model.n_layers, "ppo_cfg": asdict(cfg),
                "env_cfg": env_cfg, "extra": extra or {}}, path)


def load_checkpoint(path, device="cpu"):
    ck = torch.load(path, map_location=device, weights_only=False)
    model = ActorCritic(ck["obs_dim"], ck["n_actions"], ck["hidden"], ck["n_layers"])
    model.load_state_dict(ck["state_dict"])
    return model, ck


class PPOTrainer:
    def __init__(self, venv, cfg: PPOConfig, logger=None, model: ActorCritic = None):
        self.venv = venv
        self.cfg = cfg
        torch.manual_seed(cfg.seed)
        torch.set_num_threads(cfg.torch_threads)
        self.device = torch.device(cfg.device)
        obs_dim = venv.observation_space.shape[0]
        n_act = venv.action_space.n
        self.model = (model or ActorCritic(obs_dim, n_act, cfg.hidden, cfg.n_layers)).to(self.device)
        self.opt = torch.optim.Adam(self.model.parameters(), lr=cfg.lr, eps=1e-5)
        self.logger = logger
        self.global_step = 0
        self.episodes = deque(maxlen=400)   # 最近回合的结束信息
        self.callbacks = []

    def add_callback(self, fn):
        """fn(trainer, update_idx) ，每次 update 之后调用。"""
        self.callbacks.append(fn)

    def train(self):
        cfg, dev = self.cfg, self.device
        N, T = cfg.num_envs, cfg.n_steps
        obs_dim = self.venv.observation_space.shape[0]
        b_obs = torch.zeros((T, N, obs_dim), device=dev)
        b_act = torch.zeros((T, N), dtype=torch.long, device=dev)
        b_logp = torch.zeros((T, N), device=dev)
        b_rew = torch.zeros((T, N), device=dev)
        b_done = torch.zeros((T, N), device=dev)
        b_val = torch.zeros((T, N), device=dev)

        next_obs = torch.as_tensor(self.venv.reset(seed=cfg.seed), device=dev)
        next_done = torch.zeros(N, device=dev)
        n_updates = max(1, cfg.total_steps // cfg.batch_size)
        t_start = time.time()
        for upd in range(1, n_updates + 1):
            if cfg.anneal_lr:
                self.opt.param_groups[0]["lr"] = cfg.lr * (1.0 - (upd - 1.0) / n_updates)
            t0 = time.time()
            ep_infos = []
            for t in range(T):
                self.global_step += N
                b_obs[t] = next_obs
                b_done[t] = next_done
                with torch.no_grad():
                    a, logp, _, v = self.model.act(next_obs)
                b_act[t], b_logp[t], b_val[t] = a, logp, v
                o, r, d, infos = self.venv.step(a.cpu().numpy())
                b_rew[t] = torch.as_tensor(r, device=dev)
                next_obs = torch.as_tensor(o, device=dev)
                next_done = torch.as_tensor(d, dtype=torch.float32, device=dev)
                for inf in infos:
                    if inf is not None:
                        ep_infos.append(inf)
                        self.episodes.append(inf)
            t_roll = time.time() - t0
            # GAE
            with torch.no_grad():
                next_v = self.model.value(next_obs)
                adv = torch.zeros_like(b_rew)
                last = 0
                for t in reversed(range(T)):
                    nonterm = 1.0 - (next_done if t == T - 1 else b_done[t + 1])
                    nv = next_v if t == T - 1 else b_val[t + 1]
                    delta = b_rew[t] + cfg.gamma * nv * nonterm - b_val[t]
                    last = delta + cfg.gamma * cfg.gae_lambda * nonterm * last
                    adv[t] = last
                ret = adv + b_val
            f_obs, f_act, f_logp = b_obs.reshape(-1, obs_dim), b_act.reshape(-1), b_logp.reshape(-1)
            f_adv, f_ret, f_val = adv.reshape(-1), ret.reshape(-1), b_val.reshape(-1)
            B = cfg.batch_size
            mb = B // cfg.n_minibatches
            stats = defaultdict(list)
            for ep in range(cfg.n_epochs):
                perm = torch.randperm(B, device=dev)
                for s in range(0, B, mb):
                    idx = perm[s:s + mb]
                    _, newlogp, ent, newv = self.model.act(f_obs[idx], f_act[idx])
                    ratio = (newlogp - f_logp[idx]).exp()
                    a_mb = f_adv[idx]
                    a_mb = (a_mb - a_mb.mean()) / (a_mb.std() + 1e-8)
                    pg = torch.max(-a_mb * ratio, -a_mb * ratio.clamp(1 - cfg.clip, 1 + cfg.clip)).mean()
                    v_clip = f_val[idx] + (newv - f_val[idx]).clamp(-cfg.clip, cfg.clip)
                    vl = 0.5 * torch.max((newv - f_ret[idx]) ** 2, (v_clip - f_ret[idx]) ** 2).mean()
                    loss = pg - cfg.ent_coef * ent.mean() + cfg.vf_coef * vl
                    self.opt.zero_grad()
                    loss.backward()
                    nn.utils.clip_grad_norm_(self.model.parameters(), cfg.max_grad_norm)
                    self.opt.step()
                    with torch.no_grad():
                        lr_ = (newlogp - f_logp[idx])
                        stats["approx_kl"].append(((ratio - 1) - lr_).mean().item())
                        stats["clipfrac"].append(((ratio - 1).abs() > cfg.clip).float().mean().item())
                    stats["pg_loss"].append(pg.item())
                    stats["v_loss"].append(vl.item())
                    stats["entropy"].append(ent.mean().item())
                if cfg.target_kl > 0 and np.mean(stats["approx_kl"][-cfg.n_minibatches:]) > cfg.target_kl:
                    break
            var_y = f_ret.var().item()
            ev = float("nan") if var_y == 0 else 1 - (f_ret - f_val).var().item() / var_y
            rec = {
                "update": upd, "global_step": self.global_step,
                "sps": int(N * T / max(time.time() - t0, 1e-9)), "rollout_s": round(t_roll, 3),
                "elapsed_s": round(time.time() - t_start, 1), "lr": self.opt.param_groups[0]["lr"],
                "explained_var": ev, **{k: float(np.mean(v)) for k, v in stats.items()},
            }
            rec.update(summarize_episodes(ep_infos))
            self.last_record = rec
            for fn in self.callbacks:
                extra = fn(self, upd)
                if isinstance(extra, dict):
                    rec.update(extra)
            if self.logger is not None:
                self.logger.log(rec)
        return self.model


def summarize_episodes(infos):
    if not infos:
        return {"episodes": 0}
    out = {"episodes": len(infos)}
    oc = [i["outcome"] for i in infos if "outcome" in i]
    if oc:
        out["win_rate_train"] = float(np.mean(oc))
    by = defaultdict(list)
    for i in infos:
        if "opponent" in i and "outcome" in i:
            by[i["opponent"]].append(i["outcome"])
    out["train_outcomes_by_opp"] = {k: [float(np.mean(v)), len(v)] for k, v in by.items()}
    apm = [i["apm"] for i in infos if "apm" in i]
    if apm:
        out["apm_mean"] = float(np.mean(apm))
    ko = [i.get("end_reason") == "ko" for i in infos]
    out["ko_rate"] = float(np.mean(ko))
    return out
