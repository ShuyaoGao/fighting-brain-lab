"""把网页用到的字体打包到本地：下载开源字体（SIL OFL 1.1）→ 按页面实际用到的字符取子集 → 生成 assets/fonts.js。

fonts.js 用 data: URI 注入 @font-face，所以离线、file:// 双击打开都能用，不依赖 Google Fonts。
原始字体缓存在 .cache/fonts/（gitignore）；第一次构建需要联网下载，之后离线也能重建。
没有网络、也没有缓存时，页面退回系统字体（微软雅黑 / 苹方），功能不受影响。

  python -m arena.fonts            # 生成 arena/web/assets/fonts.js
"""
import base64
import hashlib
import io
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "arena" / "web"
CACHE = ROOT / ".cache" / "fonts"
GF = "https://github.com/google/fonts/raw/main/ofl/"

# 家族名, 文件, 下载路径, 许可证路径, CSS 字重, 字符集（"page" = 页面用到的全部字符，"ascii" = 只要 ASCII 与少量符号）
FONTS = [
    ("Noto Sans SC", "NotoSansSC.ttf", "notosanssc/NotoSansSC%5Bwght%5D.ttf", "notosanssc/OFL.txt", "100 900", "page"),
    ("ZCOOL QingKe HuangYou", "ZCOOLQingKeHuangYou-Regular.ttf", "zcoolqingkehuangyou/ZCOOLQingKeHuangYou-Regular.ttf",
     "zcoolqingkehuangyou/OFL.txt", "400", "page"),
    ("Press Start 2P", "PressStart2P-Regular.ttf", "pressstart2p/PressStart2P-Regular.ttf", "pressstart2p/OFL.txt", "400", "ascii"),
    ("JetBrains Mono", "JetBrainsMono.ttf", "jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf", "jetbrainsmono/OFL.txt", "100 800", "ascii"),
]
EXTRA = "←↑→↓↖↗↘↙·×≤≥±–—…“”‘’「」『』《》（）【】，。、；：？！％＋－／～✓✗▶▸◂■□●○★☆"


def fetch(rel, dest):
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print("下载", rel)
    with urllib.request.urlopen(GF + rel, timeout=120) as r:
        dest.write_bytes(r.read())
    return dest


def page_chars(extra=()):
    files = list(extra) + [WEB / "page.html", WEB / "report_section.html", ROOT / "envs" / "fighting2d" / "naming.json", ROOT / "credits.json"]
    files += [p for p in (WEB / "assets").glob("*.js") if p.name != "fonts.js"]
    files += [WEB / "assets" / "gen" / n for n in ("spec.js", "report_data.js")]
    files += [WEB / "assets" / "gen" / "models" / "index.js"]
    text = "".join(p.read_text(encoding="utf-8") for p in files if p.exists())
    chars = {c for c in text if ord(c) >= 0x80}
    chars |= {chr(i) for i in range(0x20, 0x7F)} | set(EXTRA)
    return "".join(sorted(chars))


def subset(src, chars):
    from fontTools import subset as fts
    opts = fts.Options()
    opts.flavor = "woff"            # woff（zlib）不需要 brotli 扩展
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    font = fts.load_font(str(src), opts)
    sub = fts.Subsetter(opts)
    sub.populate(text=chars)
    sub.subset(font)
    buf = io.BytesIO()
    fts.save_font(font, buf, opts)
    return buf.getvalue()


def build(out=WEB / "assets" / "fonts.js", license_dir=WEB / "assets" / "fonts", extra=()):
    chars_page = page_chars(extra)
    chars_ascii = "".join(chr(i) for i in range(0x20, 0x7F)) + EXTRA
    key = hashlib.sha256((chars_page + json.dumps(FONTS)).encode("utf-8")).hexdigest()[:16]
    stamp = CACHE / ("fonts_" + key + ".js")
    license_dir.mkdir(parents=True, exist_ok=True)
    try:
        for fam, fn, rel, lic, *_ in FONTS:
            fetch(rel, CACHE / fn)
            fetch(lic, CACHE / ("OFL-" + fn.split(".")[0].split("-")[0] + ".txt"))
    except Exception as e:  # noqa: BLE001
        print("字体下载失败（页面将使用系统字体）：", e)
        if not out.exists():
            out.write_text("/* 字体未打包：构建时无法下载，页面使用系统字体 */\n", encoding="utf-8")
        return out
    for fam, fn, *_ in FONTS:   # 许可证随字体一起分发（OFL 要求）
        src = CACHE / ("OFL-" + fn.split(".")[0].split("-")[0] + ".txt")
        (license_dir / ("OFL-" + fam.replace(" ", "") + ".txt")).write_bytes(src.read_bytes())
    if stamp.exists():
        out.write_bytes(stamp.read_bytes())
        return out
    css = []
    sizes = {}
    for fam, fn, rel, lic, weight, cs in FONTS:
        data = subset(CACHE / fn, chars_page if cs == "page" else chars_ascii)
        sizes[fam] = len(data)
        css.append("@font-face{font-family:'%s';src:url(data:font/woff;base64,%s) format('woff');font-weight:%s;font-style:normal;font-display:swap}"
                   % (fam, base64.b64encode(data).decode(), weight))
    js = ("/* 由 arena/fonts.py 生成：开源字体（SIL OFL 1.1，许可证见 assets/fonts/）按页面用到的字符取的子集 */\n"
          "(function(){var s=document.createElement('style');s.textContent=" + json.dumps("".join(css)) + ";document.head.appendChild(s);})();\n")
    out.write_text(js, encoding="utf-8")
    stamp.write_text(js, encoding="utf-8")
    print("fonts.js：%d 个字符，%s，共 %.2f MB" % (len(chars_page), ", ".join("%s %.0f KB" % (k, v / 1024) for k, v in sizes.items()),
                                                 out.stat().st_size / 1e6))
    return out


if __name__ == "__main__":
    sys.exit(0 if build() else 1)
