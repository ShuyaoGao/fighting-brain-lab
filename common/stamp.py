"""留痕：每次训练/评估都落 _env_stamp.json（什么机器、什么环境、什么代码版本、什么参数）。"""
import json
import os
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _git(*args):
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return None


def env_stamp(extra=None) -> dict:
    d = {
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "argv": sys.argv,
        "cpu_count": os.cpu_count(),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
    }
    for mod in ("numpy", "gymnasium", "torch", "scipy", "matplotlib"):
        try:
            m = __import__(mod)
            d[f"{mod}_version"] = getattr(m, "__version__", "?")
        except Exception:
            d[f"{mod}_version"] = None
    try:
        import torch
        d["cuda_available"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            d["cuda_device"] = torch.cuda.get_device_name(0)
            d["torch_cuda"] = torch.version.cuda
    except Exception:
        pass
    if extra:
        d.update(extra)
    return d


def write_stamp(run_dir, extra=None):
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    stamp = env_stamp(extra)
    (run_dir / "_env_stamp.json").write_text(json.dumps(stamp, indent=2, ensure_ascii=False, default=str),
                                              encoding="utf-8")
    return stamp


class JsonlLogger:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(self.path, "a", encoding="utf-8")

    def log(self, rec: dict):
        self.f.write(json.dumps(rec, ensure_ascii=False, default=_default) + "\n")
        self.f.flush()

    def close(self):
        self.f.close()


def _default(o):
    try:
        import numpy as np
        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
    except Exception:
        pass
    return str(o)


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=_default), encoding="utf-8")
