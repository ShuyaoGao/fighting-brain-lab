"""打包：把 core.js 和 ui.js 内联进 index.src.html，生成单文件 duel/index.html。

GitHub Pages 直接发布这个文件；下载后双击也能玩（不联网时字体换成系统字体）。
用法：python duel/src/build.py
"""
import pathlib

src = pathlib.Path(__file__).parent
html = (src / "index.src.html").read_text(encoding="utf-8")
html = html.replace("/*CORE*/", (src / "core.js").read_text(encoding="utf-8"))
html = html.replace("/*UI*/", (src / "ui.js").read_text(encoding="utf-8"))
out = src.parent / "index.html"
out.write_text(html, encoding="utf-8")
print("built", out, len(html), "bytes")
