# 第三方组件与许可证

本仓库的代码（Python、JavaScript、HTML/CSS、构建脚本）全部由本项目编写，**没有拷贝或内嵌第三方源代码**；网页端不使用任何第三方 JavaScript 库（游戏核心、神经网络推理、图表、音效都是自己写的，音效用 WebAudio 实时合成，不含音频素材）。仓库里唯一随附的第三方作品是下面列出的开源字体。仓库不包含任何游戏 ROM 或外部数据集；网页里的模型权重由本项目训练得到。

## 随网页分发的字体（play/assets/fonts.js）

构建时（`arena/fonts.py`）从 Google Fonts 的开源仓库下载，按页面实际用到的字符取子集，以 data URI 打包。许可证全文随包附在 `play/assets/fonts/`。

| 字体 | 用途 | 许可证 |
|---|---|---|
| Noto Sans SC | 正文 | SIL Open Font License 1.1 |
| ZCOOL QingKe HuangYou（站酷庆科黄油体） | 标题 | SIL Open Font License 1.1 |
| Press Start 2P | 游戏画面 HUD | SIL Open Font License 1.1 |
| JetBrains Mono | 数字与等宽文字 | SIL Open Font License 1.1 |

`docs/code_map.html` 在线加载 Google Fonts（Chakra Petch、Noto Sans SC、JetBrains Mono，均为 SIL OFL 1.1）；离线时退回系统字体。

## Python 依赖（requirements.txt，不随仓库分发，由使用者自行安装）

版本为作者测试时的版本；许可证取自各包发布的元数据。

| 包 | 测试版本 | 许可证 | 用途 |
|---|---|---|---|
| torch | 2.11.0 | BSD-3-Clause | PPO 训练 |
| numpy | 2.5.3 | BSD-3-Clause（及其内含组件的 0BSD / MIT / Zlib / CC0-1.0） | 数值计算 |
| gymnasium | 1.4.0 | MIT | 环境接口 |
| scipy | 1.18.1 | BSD-3-Clause | 统计检验 |
| matplotlib | 3.11.2 | Matplotlib License（PSF 风格） | 出图 |
| fonttools | 4.63.0 | MIT | 字体子集 |
| pillow | 12.3.0 | MIT-CMU（HPND） | 图像处理 |
| imageio | 2.38.0 | BSD-2-Clause | 录像 |
| imageio-ffmpeg | 0.6.0 | BSD-2-Clause（平台安装包内含 FFmpeg 可执行文件，FFmpeg 本身为 LGPL/GPL） | mp4 编码 |
| pytest | 9.1.1 | MIT | 测试 |
| quickjs（可选） | 1.19.4 | MIT（内嵌 QuickJS，MIT） | JS 与 Python 逐帧对拍测试 |
| websocket-client（可选） | 1.9.2 | Apache-2.0 | 驱动本机 Chrome/Edge 做截图、录像、浏览器测试 |
| stable-retro（可选，未安装测试） | — | MIT | 真实游戏适配器（Linux/macOS） |
| diambra-arena（可选，未安装测试） | — | 见其项目页（未核实） | 真实游戏适配器（需要 Docker） |

## 外部工具与浏览器

浏览器测试与录像使用本机已安装的 Google Chrome / Microsoft Edge（通过 DevTools 协议），不随仓库分发。
