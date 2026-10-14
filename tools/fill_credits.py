"""用 credits.json 统一替换仓库里的 {{KEY}} 占位（系列名、案例编号、GitHub 用户名、仓库名……），并更新 play/ 页脚。

  python tools/fill_credits.py            # 替换并报告还剩哪些占位
  python tools/fill_credits.py --check    # 只检查，不改文件

credits.json 里值为空字符串的键保持占位不变；页面页脚在值为空时显示 {{KEY}}。
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIX = {".md", ".cff", ".txt", ".html", ".js", ".json", ".py", ".toml", ".yml", ".yaml", ""}
SKIP_DIRS = {".git", ".venv", "runs", "release", ".cache", "__pycache__", "node_modules"}
PAT = re.compile(r"\{\{([A-Z_]+)\}\}")


def files():
    for p in ROOT.rglob("*"):
        if p.is_file() and not (set(p.relative_to(ROOT).parts) & SKIP_DIRS) and p.suffix in TEXT_SUFFIX:
            if p.name in ("credits.json", "fill_credits.py") or p.name.startswith("_") or p.stat().st_size > 3_000_000:
                continue
            yield p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    cred = {k: v for k, v in json.loads((ROOT / "credits.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}
    filled = {k: str(v) for k, v in cred.items() if str(v).strip()}
    left = {}
    changed = 0
    for p in files():
        try:
            s = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        t = PAT.sub(lambda m: filled.get(m.group(1), m.group(0)), s)
        for k in PAT.findall(t):
            left.setdefault(k, set()).add(str(p.relative_to(ROOT)))
        if t != s and not a.check:
            p.write_text(t, encoding="utf-8")
            changed += 1
    # play/ 页脚读 spec.js 里的 credits
    spec = ROOT / "play" / "assets" / "gen" / "spec.js"
    if spec.exists() and not a.check:
        s = spec.read_text(encoding="utf-8")
        head, body = s.split("=", 1)
        obj = json.loads(body.strip().rstrip(";"))
        keep_logo = (obj.get("credits") or {}).get("UNIVERSITY_LOGO", "")
        obj["credits"] = dict(cred, UNIVERSITY_LOGO=keep_logo)   # 校标图片需要重新构建 play/ 才会被复制进去
        if cred.get("UNIVERSITY_LOGO") and not keep_logo:
            print("提示：UNIVERSITY_LOGO 需要在源仓库运行 python -m arena.build --release 重新构建 play/ 后才会显示")
        spec.write_text(head + "= " + json.dumps(obj, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(("检查" if a.check else "已替换") + f"：{changed} 个文件")
    for k, where in sorted(left.items()):
        print(f"  仍是占位 {{{{{k}}}}}：{len(where)} 个文件（{', '.join(sorted(where)[:4])}{' …' if len(where) > 4 else ''}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
