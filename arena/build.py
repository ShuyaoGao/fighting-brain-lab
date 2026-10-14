"""生成 arena 的可运行页面。

- 本地版：arena/web/index.html（加上 <!doctype> 骨架，双击或 python -m arena 打开）
- 发布版：arena/dist/（不带骨架、只包含选定模型、可选 float16），用于 Artifact 发布或拷到任何静态服务器
- 免安装版：play/（完整 HTML、精选模型 float16、字体与录像都在本地，双击 index.html 即可，也能直接放 GitHub Pages）
  和 release/格斗大脑实验台-v<版本>.zip（同一份内容打包，用于挂到 GitHub Release）

  python -m arena.build --release
"""
import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
WEB = ROOT / "arena" / "web"
DIST = ROOT / "arena" / "dist"

SKELETON = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
{head}
</head>
<body>
{body}
</body>
</html>
"""


def split_page(src: str):
    """page.html 把 <title>/<meta>/<link>/<style> 放在最前面；其余是 body。"""
    cut = src.index("</style>") + len("</style>")
    return src[:cut], src[cut:]


def page_source():
    src = (WEB / "page.html").read_text(encoding="utf-8")
    return src.replace("<!--REPORT-->", (WEB / "report_section.html").read_text(encoding="utf-8"))


def sync_media(assets_dir: Path):
    """把录像转成网页用的轻量版本：mp4 降码率（quality 4），海报 png → jpg。源文件在 videos/ 与 results/media/。"""
    import json
    med = ROOT / "results" / "media" / "media.json"
    if not med.exists():
        return 0
    out = assets_dir / "media"
    out.mkdir(parents=True, exist_ok=True)
    meta = json.loads(med.read_text(encoding="utf-8"))
    n = 0
    for m in meta.values():
        src, dst = ROOT / "videos" / m["mp4"], out / m["mp4"]
        if src.exists() and (not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime):
            import imageio.v2 as imageio
            r = imageio.get_reader(src)
            frames, fps = [f for f in r], r.get_meta_data()["fps"]
            r.close()
            imageio.mimwrite(dst, frames, fps=fps, macro_block_size=1, quality=4)
        png = ROOT / "results" / "media" / m["png"]
        if png.exists():
            from PIL import Image
            im = Image.open(png).convert("RGB")
            im.thumbnail((960, 960))
            im.save(out / (Path(m["png"]).stem + ".jpg"), quality=82)
        n += 1
    return n


def build_local():
    sync_media(WEB / "assets")
    try:
        from arena import fonts
        fonts.build()
    except Exception as e:  # noqa: BLE001
        print("字体打包跳过：", e)
    src = page_source()
    head, body = split_page(src)
    (WEB / "index.html").write_text(SKELETON.format(head=head, body=body), encoding="utf-8")
    return WEB / "index.html"


def build_dist(models=None, f16=True, limit_mb=12.0):
    from arena.export import export_models, export_spec
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "assets" / "gen").mkdir(parents=True)
    for f in (WEB / "assets").glob("*.js"):
        shutil.copy(f, DIST / "assets" / f.name)
    (DIST / "index.html").write_text(page_source(), encoding="utf-8")
    sync_media(DIST / "assets")
    export_spec(DIST / "assets" / "gen")
    from arena.export import export_report
    export_report(DIST / "assets" / "gen")
    idx = export_models(DIST / "assets" / "gen", f16=f16, only=set(models) if models else None)
    total = sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file()) / 1e6
    print(f"dist：{len(idx)} 个模型，共 {total:.1f} MB（{'float16' if f16 else 'float32'}）")
    if total > limit_mb:
        print(f"警告：超过 {limit_mb} MB，请减少模型")
    return DIST, idx, total


# 免安装发布包里的模型：人类条件 7 个宽度（种子 0）+ 敲除实验对象（64×2 种子 2）+ 无限制 3 个 + 旧实验 2 个
RELEASE_MODELS = ["w8_d2_human_s0", "w16_d2_human_s0", "w32_d2_human_s0", "w64_d2_human_s0", "w128_d2_human_s0",
                  "w256_d2_human_s0", "w512_d2_human_s0", "w64_d2_human_s2",
                  "w16_d2_free_s0", "w64_d2_free_s0", "w256_d2_free_s0", "legacy_d200", "legacy_league0"]
PLAY = ROOT / "play"
RELEASE = ROOT / "release"
REDIRECT = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>开始游戏</title>
<meta http-equiv="refresh" content="0; url=index.html"></head>
<body style="background:#0a0c16;color:#e6e9f8;font-family:sans-serif;padding:24px">
<p>正在打开格斗大脑实验台…… 没有自动跳转就点 <a style="color:#ffd23f" href="index.html">index.html</a>。</p>
<script>location.replace("index.html");</script></body></html>
"""
README_TXT = """格斗大脑实验台 v{version}（免安装版）
==================================

怎么打开
  双击 index.html（或「开始游戏.html」），用 Chrome / Edge / Firefox / Safari 打开即可。
  不需要安装 Python，不需要联网；模型、字体、录像都在 assets/ 目录里。
  如果双击后是用记事本之类打开的：右键 index.html →「打开方式」→ 选一个浏览器。

三种玩法
  观战：两个神经网络对打，右侧（手机上在游戏下方）实时显示它们的「大脑」。
  我来打：你操作蓝色 P1。对手分新手 / 普通 / 困难 / 无限制四档。
  练习：对手是木桩，任务清单逐项打勾。
  手机上也能打开：默认观战，往下滑看大脑；想亲手玩会出现虚拟按键。
  按 H 或右上角「?」随时打开操作说明。

键位
  A / D 移动  W 跳  S 蹲  按住「后」= 防御   J 轻攻击  K 重攻击
  新手模式（默认开）：U 气功波  I 冲天拳  按住 Shift 放重版本

署名与许可证
  {author} · {univ_en} · {univ_ko}
  代码：MIT License；文档、图表与教学素材：CC BY 4.0
  字体：Noto Sans SC、ZCOOL QingKe HuangYou、Press Start 2P、JetBrains Mono（SIL Open Font License 1.1，见 assets/fonts/）
  代码由 Claude Code 辅助编写，经作者审阅。
"""


def build_release(models=None, version=None, zip_limit_mb=15.0):
    """生成 play/ 与 release/*.zip（完整 HTML 骨架、float16 模型、本地字体与录像）。"""
    import json
    import zipfile
    from arena import fonts
    from arena.export import export_models, export_report, export_spec
    cred = json.loads((ROOT / "credits.json").read_text(encoding="utf-8")) if (ROOT / "credits.json").exists() else {}
    version = version or cred.get("VERSION") or "1.0"
    if PLAY.exists():
        shutil.rmtree(PLAY)
    gen = PLAY / "assets" / "gen"
    gen.mkdir(parents=True)
    for f in (WEB / "assets").glob("*.js"):
        if f.name != "fonts.js":
            shutil.copy(f, PLAY / "assets" / f.name)
    sync_media(PLAY / "assets")
    export_spec(gen)
    export_report(gen)
    idx = export_models(gen, f16=True, only=set(models or RELEASE_MODELS))
    fonts.build(out=PLAY / "assets" / "fonts.js", license_dir=PLAY / "assets" / "fonts",
                extra=[gen / "spec.js", gen / "report_data.js", gen / "models" / "index.js"])
    head, body = split_page(page_source())
    (PLAY / "index.html").write_text(SKELETON.format(head=head, body=body), encoding="utf-8")
    (PLAY / "开始游戏.html").write_text(REDIRECT, encoding="utf-8")
    v = (lambda k: cred.get(k) or "{{" + k + "}}")
    (PLAY / "使用说明.txt").write_text(README_TXT.format(version=version, author=v("AUTHOR_EN"), univ_en=v("UNIVERSITY_EN"),
                                                         univ_ko=v("UNIVERSITY_KO")), encoding="utf-8")
    RELEASE.mkdir(exist_ok=True)
    name = f"格斗大脑实验台-v{version}"
    zp = RELEASE / f"{name}.zip"
    if zp.exists():
        zp.unlink()
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(PLAY.rglob("*")):
            if p.is_file():
                z.write(p, f"{name}/{p.relative_to(PLAY).as_posix()}")
    raw = sum(p.stat().st_size for p in PLAY.rglob("*") if p.is_file()) / 1e6
    zmb = zp.stat().st_size / 1e6
    print(f"play/：{len(idx)} 个模型，{raw:.1f} MB；{zp.relative_to(ROOT)}：{zmb:.1f} MB")
    if zmb > zip_limit_mb:
        print(f"警告：zip 超过 {zip_limit_mb} MB")
    return PLAY, zp, raw, zmb


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", action="store_true", help="生成 play/ 与 release/*.zip（免安装版）")
    ap.add_argument("--dist", action="store_true")
    ap.add_argument("--f32", action="store_true")
    ap.add_argument("--models", nargs="*", default=None)
    a = ap.parse_args()
    print(build_local())
    if a.dist:
        build_dist(a.models, f16=not a.f32)
    if a.release:
        build_release(a.models)
