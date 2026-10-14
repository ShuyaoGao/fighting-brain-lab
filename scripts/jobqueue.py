"""极简本地作业队列：最多 P 个作业并行，跑完一个补一个；已有 result.json 的作业跳过；可声明依赖文件。

用法（Python）：
    from scripts.jobqueue import Job, run_queue
    run_queue([Job(name, argv, out_dir, needs=[path, ...]), ...], parallel=3, log=Path("runs/queue.log"))

Linux 服务器上的等价做法：每个作业一条 `tsp python ...`（task-spooler 队列）。
"""
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Job:
    name: str
    argv: List[str]
    out: Path
    needs: List[Path] = field(default_factory=list)

    @property
    def done(self):
        return (self.out / "result.json").exists()

    def ready(self):
        return all(Path(p).exists() for p in self.needs)

    @property
    def busy(self):
        """别的进程正在跑（训练日志在最近 3 分钟内有更新）——避免两个队列重复启动同一作业。"""
        log = self.out / "train_log.jsonl"
        return (not self.done) and log.exists() and time.time() - log.stat().st_mtime < 180


def run_queue(jobs: List[Job], parallel: int = 3, log: Path = None, poll: float = 5.0):
    pending = [j for j in jobs if not j.done]
    running = []
    logf = open(log, "a", encoding="utf-8") if log else None

    def say(msg):
        line = time.strftime("%H:%M:%S ") + msg
        print(line, flush=True)
        if logf:
            logf.write(line + "\n")
            logf.flush()

    say(f"队列：共 {len(jobs)} 个，待跑 {len(pending)} 个，并行 {parallel}")
    while pending or running:
        for j, p, f in list(running):
            rc = p.poll()
            if rc is not None:
                f.close()
                running.remove((j, p, f))
                say(f"完成 {j.name} exit={rc}" + ("" if j.done else "（没有 result.json！）"))
        pending = [j for j in pending if not j.done]
        # 并行上限把"别的队列正在跑的作业"也算进去
        while len(running) + sum(1 for j in pending if j.busy) < parallel:
            nxt = next((j for j in pending if j.ready() and not j.busy), None)
            if nxt is None:
                break
            pending.remove(nxt)
            nxt.out.mkdir(parents=True, exist_ok=True)
            f = open(nxt.out / "stdout.log", "w", encoding="utf-8")
            p = subprocess.Popen([sys.executable, *nxt.argv], cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
            running.append((nxt, p, f))
            say(f"启动 {nxt.name}")
        if pending and not running and not any(j.ready() or j.busy for j in pending):
            say("剩余作业的依赖永远不会满足：" + ", ".join(j.name for j in pending))
            break
        time.sleep(poll)
    say("队列结束")
