"""保证可视化用的特征名与 core.observe 的实际定义逐维对应。"""
import numpy as np

from envs.fighting2d.core import OBS_DIM, FightingCore
from envs.fighting2d.obs_spec import EXTRACTORS, FEATURES, NAMING, action_table


def test_feature_count_matches_obs_dim():
    assert len(FEATURES) == OBS_DIM == len(EXTRACTORS)
    assert len({f["key"] for f in FEATURES}) == OBS_DIM


def test_every_feature_matches_observe_on_random_play():
    rng = np.random.default_rng(0)
    checked = np.zeros(OBS_DIM, bool)
    for seed in range(6):
        c = FightingCore(seed=seed)
        hold = [0, 0]
        cur = [0, 0]
        while not c.done:
            for i in range(2):
                if hold[i] <= 0:
                    cur[i] = int(rng.integers(27))
                    hold[i] = int(rng.integers(1, 10))
                hold[i] -= 1
            c.step(*cur)
            if c.frame % 7 == 0:
                for p in (0, 1):
                    obs = c.observe(p)
                    ref = np.array([f(c, p) for f in EXTRACTORS], dtype=np.float32)
                    np.testing.assert_allclose(obs, ref, atol=1e-6, err_msg=f"frame {c.frame} p{p}")
                    checked |= np.abs(obs) > 1e-9
    # 绝大多数维度在随机对局里都出现过非零值（确实被比对到了）
    assert checked.mean() > 0.85, [FEATURES[i]["key"] for i in np.where(~checked)[0]]


def test_action_names():
    names = action_table()
    # 招式显示名来自 envs/fighting2d/naming.json
    assert len(names) == 31 and names[0] == "不动" and names[-1] == NAMING["specials"]["dp"] + "（重）"
    assert len(set(names)) == 31
