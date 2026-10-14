# 格斗游戏强化学习生态调研（LANDSCAPE）

- 核实日期：2026-10-07
- 核实方式：GitHub REST API（仓库最近推送时间、release、目录树、源码文件原文）、PyPI JSON API、arXiv API、Crossref / OpenAlex（DOI）、官方文档页面原文、论文 PDF 全文检索。
- 标记约定：
  - 无标记：已对照一手来源（官方仓库、官方文档、论文原文）核实。
  - `[部分核实]`：只有二手来源（新闻、搜索摘要、预测市场页面），或一手来源只覆盖了其中一部分。
  - `[未核实]`：没有找到可靠来源，**不要当成事实引用**。
- "最近推送"指 GitHub `pushed_at` 字段，即任意分支最后一次 push 的时间，可能只是依赖机器人的提交。

---

## 0. 结论速览

1. **想直接拿街机 ROM + 现成 RAM 状态**：DIAMBRA Arena 最省事。9 款游戏，双人模式，观测里自带 health/side/wins 等 RAM 状态。代价有三条：必须装 Docker；许可证禁止商用和衍生作品分发；仓库自 2024-06 以后没有新提交。
2. **想要开源、可改、能自己加游戏**：stable-retro（MIT，2026-09 仍有提交，最新 v1.0.1）。已集成约 30 款格斗游戏，主要是 Genesis/SNES 家用机移植版，街机版只有 `MortalKombat2-Arcade-v0`（FBNeo 核心）一款。**PyPI 只发 Linux x86_64 和 macOS arm64 的 wheel，Windows 官方只支持 WSL2**，所以 Linux（例如 Ubuntu GPU 服务器）是天然的运行平台。
3. **想研究"人类反应延迟下的公平对战"**：FootsiesGym（2026-07 新出，自带 `action_delay` 参数，默认 8 帧）和 FightingICE（已知 15 帧状态延迟）是现成的带延迟环境。
4. **"RL 一定无敌"不成立**。已有证据：
   - Firoiu 2017：无延迟（2 帧 ≈ 33ms）的 Melee 智能体能赢职业选手；
   - Firoiu 2018：延迟加到人类水平（12～14 帧）后，标准方法性能骤降，加了预测模型也没赢下英国头号选手；
   - FightLadder 2024：所有自博弈/联赛训练出的街霸智能体，都能被 PPO 训练出的"利用者"和人类用简单套路稳定击败；
   - KataGo 对抗策略 2022：超人围棋 AI 同样能被针对性击穿。
5. **可信路线**：先把观测延迟（约 200～250ms，即 12～15 帧）和动作频率限制到人类水平，再用联赛训练，最后同时报告三类成绩：对脚本 AI、对人类、对专门训练的利用者。

---

## 1. 总览表

| 项目 | 类型 | 支持游戏 | 平台要求 | 维护状态（截至 2026-10-07） | 对本项目的用处 | URL |
|---|---|---|---|---|---|---|
| DIAMBRA Arena | 环境平台（街机 ROM） | 9 款：doapp、sfiii3n、tektagt、umk3、samsh5sp、kof98umh、mvsc、xmvsf、soulclbr | Docker Desktop 必需；Linux/Windows/macOS；用户自备 ROM，sha256 校验 | PyPI `diambra-arena` 2.2.7（2024-04-30）；仓库最近推送 2024-06-11；此后无提交 | 最快拿到带 RAM 状态的街机格斗环境，原生 2P | https://docs.diambra.ai/ ，https://github.com/diambra/arena |
| stable-retro | 通用复古游戏 RL 环境（Farama） | 1000+ 游戏，约 30 款格斗（见 §2.2） | Linux（推荐 Ubuntu 24.04）、macOS；Windows 仅 WSL2；Python 3.10–3.14 | v1.0.1（2026-06-25）；最近推送 2026-09-17；活跃 | 开源可改；`data.json` 定义 RAM 变量；支持 `players=2` | https://github.com/Farama-Foundation/stable-retro |
| MAMEToolkit | MAME 封装 | 理论上任意 MAME 游戏；内置 SF3 3rd Strike 环境 | 仅 Linux（依赖 Linux FIFO 管道） | PyPI 1.1.0（2019-12-08）；最近推送 2020-01-10；**已停更** | 参考其 Lua 读内存思路；不建议直接用 | https://github.com/M-J-Murray/MAMEToolkit |
| FightingICE / DareFightingICE | 学术竞赛平台（Java） | 自有 2D 格斗游戏（素材来自 *The Rumble Fish 2*） | Java + LWJGL（Win/Linux/macOS arm64 原生库）；Docker 镜像；Python 接口 `pyftg` | release v7.1（2026-04-18）；最近推送 2026-09-14；`pyftg` 2.3（2025-02-05）；IEEE CoG 2026 仍在办赛 | 有 15 帧延迟和音频赛道的学术基准 | https://github.com/TeamFightingICE/FightingICE ，https://www.ice.ci.ritsumei.ac.jp/~ftgaic/ |
| FootsiesGym | 极简格斗基准 | HiFight 的 FOOTSIES | Linux、macOS（Rosetta）；**Windows 不支持** | PyPI `footsies-gym` 1.0.0（2026-07-08）；最近推送 2026-10-04 | 自带 `action_delay`，适合研究延迟和自博弈 | https://github.com/como-research/FootsiesGym ，arXiv:2607.06514 |
| FightLadder | 竞争性 MARL 基准 + 代码 | SF II（Genesis）、SF III（街机）、Fatal Fury 2（Genesis）、Mortal Kombat（Genesis）、KOF '97（Neo Geo） | 基于 gym-retro/stable-retro 与 MAMEToolkit | ICML 2024；仓库最近推送 2024-07-23（MIT） | 联赛/PSRO 基线和可被利用性评估方法 | https://github.com/wenzhe-li/FightLadder ，arXiv:2406.02081 |
| linyiLYi/street-fighter-ai | 单项目（SF2 + PPO） | SF2 Special Champion Edition（Genesis） | OpenAI gym-retro（不是 stable-retro）+ SB3，Python 3.8.10，Windows 11 测试 | 最近推送 2024-05-14；约 6.5k star；Apache-2.0 | 奖励设计和"过拟合单一存档"的反面教材 | https://github.com/linyiLYi/street-fighter-ai |
| slippi-ai（Phillip II） | Melee AI（模仿学习 + RL） | Super Smash Bros. Melee | Slippi Dolphin；Python 3.12/3.13 | 最近推送 2026-10-06；活跃 | 目前最接近"人类延迟下与顶尖选手对战"的公开系统 | https://github.com/vladfi1/slippi-ai |
| MAME 本体 | 模拟器 | 街机全集 | 全平台 | 最新 0.289（2026-07-30） | Lua API 读 RAM（§4） | https://docs.mamedev.org/luascript/ |
| Ikemen GO | 开源格斗引擎（兼容 MUGEN 素材） | MUGEN 角色 | 全平台 | 最近推送 2026-10-07；活跃 | 可做自有引擎；**没有找到官方 RL 接口** | https://github.com/ikemen-engine/Ikemen-GO |

---

## 2. 环境与工具详解

### 2.1 DIAMBRA Arena

来源：https://docs.diambra.ai/ ，https://docs.diambra.ai/envs/games/ ，https://github.com/diambra/arena ，论文 arXiv:2210.10595（Palmas，2022）。

**支持的游戏（以 docs.diambra.ai 为准，共 9 款）**。sha256 已用页面原始 HTML 逐一比对：

| 游戏 | Game ID | ROM 文件名 | SHA256 | 难度 | 备注 |
|---|---|---|---|---|---|
| Dead Or Alive ++ | `doapp` | `doapp.zip` | `d95855c7d8596a90f0b8ca15725686567d767a9a3f93a8896b489a160e705c4e` | 1–4 | 11 名角色 |
| Street Fighter III 3rd Strike | `sfiii3n` | `sfiii3n.zip` | `7239b5eb005488db22ace477501c574e9420c0ab70aeeb0795dfeb474284d416` | 1–8 | 20 名角色（可选 19） |
| Tekken Tag Tournament | `tektagt` | `tektagt.zip`（由 `tektagtac.zip` 改名） | `57be777eae0ee9e1c035a64da4c0e7cb7112259ccebe64e7e97029ac7f01b168` | 1–9 | 双角色槽 |
| Ultimate Mortal Kombat 3 | `umk3` | `umk3.zip`（由 `umk3r10.zip` 改名） | `f48216ad82f78cb86e9c07d2507be347f904f4b5ae354a85ae7c34d969d265af` | 1–5 | 26 名（可选 22） |
| Samurai Showdown 5 Special | `samsh5sp` | `samsh5sp.zip` | `adf33d8a02f3d900b4aa95e62fb21d9278fb920b179665b12a489bd39a6c103d` | 1–8 | 28 名 |
| The King of Fighters '98 UMH | `kof98umh` | `kof98umh.zip` | `beb7bdea87137832f5f6d731fd1abd0350c0cd6b6b2d57cab2bedbac24fe8d0a` | 1–8 | 45 名（可选 43），三人队 |
| Marvel VS Capcom | `mvsc` | `mvsc.zip`，另需 `qsound_hle.zip` | `6f63627cc37c554f74e8bf07b21730fa7f85511c7d5d07449850be98dde91da8` | 1–8 | |
| X-Men VS Street Fighter | `xmvsf` | `xmvsf.zip`，另需 `qsound_hle.zip` | `833aa46af63a3ad87f69ce2bacd85a4445f35a50e3aff4f793f069b205b51c60` | 1–8 | |
| Soul Calibur | `soulclbr` | `soulclbr.zip` | `a07a1a19995d582b56f2865783c5d7adb7acb9a6ad995a26fc7c4cfecd821817` | 1–8 | |

文档称每款游戏都做过大量测试，保证单人模式可以无 bug 打通；"many more to come soon" 的说法在仓库停更后已不可信。

**运行要求**
- **Docker 必需**。官方安装步骤第一条就是装 Docker Desktop（Linux / Windows / macOS），模拟引擎以容器形式运行，Python 包通过网络与容器通信。
- Windows 支持：文档原文 "supports all major Operating Systems (Linux, Windows and MacOS)"；Windows 10 "N" 版可能缺 Media Feature Pack 导致 `cv2` DLL 报错。命令行工具 `diambra` 0.0.20（PyPI，2025-01-24）有 `win_amd64` wheel。
- 必须在官网免费注册。
- **ROM 用户自备**，用 `diambra arena check-roms /abs/path/romFile.zip` 校验，输出 "Correct ROM file for ..., sha256 = ..." 才算通过；`diambra arena list-roms` 列出所有游戏的 ROM 要求。

**Python API**：文档原文 "Python API fully compliant with OpenAI Gym/Gymnasium format"。原生对接 Stable-Baselines3（文档测试 2.1.*）和 Ray RLlib（2.7.*）。动作空间可选 `DISCRETE` 或 `MULTI_DISCRETE`（以 sfiii3n 为例：Discrete 18，MultiDiscrete 为 9 个移动 × 10 个攻击）。`step_ratio`（1–6）控制每步推进的帧数，`frame_shape` 控制缩放和灰度。

**多智能体 / 双人**：支持。设置 `n_players=2` 后，动作空间变为字典，键为 `agent_0` / `agent_1`。官方定位里写明可用于 competitive multi-agent、self-play、human-agent。

**RAM 状态（观测的一部分）**
- 全局：`frame`、`stage`、`timer`
- 每个玩家（`P1` / `P2` 键下）：`side`（0 左 1 右）、`wins`、`character`、`health`
- 游戏特有，例如 sfiii3n 有 `stun_bar`、`stunned`、`super_bar`、`super_type`、`super_count`、`super_max`；umk3 有 aggressor bar；samsh5sp 有怒气、武器状态；tektagt/mvsc/xmvsf 有双角色血量和当前出场角色。

**许可证**：仓库 `LICENSE.txt` 是 DIAMBRA 自定义许可（PyPI 标为 "Custom"，GitHub 识别为 NOASSERTION）。条款要点：
- 禁止未经书面许可的商业使用，包括办比赛、以服务形式提供、制作可商业化的内容；
- 禁止未经许可分发衍生作品。

**对本项目**：做学术实验没问题。但如果要把训练好的智能体做成公开服务或直播内容，需要先读许可证；仓库已停更两年多，Docker 镜像未来能否拉取存在风险 `[未核实镜像当前可用性]`。官网"竞赛平台 / 排行榜"目前是否还在运营 `[未核实]`。

### 2.2 stable-retro（Farama-Foundation/stable-retro）

来源：https://github.com/Farama-Foundation/stable-retro （README、`docs/supported_games.md`、`docs/integration.md`、`stable_retro/retro_env.py`、目录树），PyPI `stable-retro`。

**当前状态**：最新 release v1.0.1（2026-06-25），之前依次是 v1.0.0（2026-04-07）和 v0.9.9（2026-02-15）。最近提交 2026-09-17。MIT 许可，各模拟器核心另有许可，见 `LICENSES.md`。注意：**集成数据目录已从 `retro/data/stable` 改为 `stable_retro/data/stable`**，共 1009 个 stable、56 个 experimental、6 个 contrib 集成。

**平台**
- PyPI 1.0.1 wheel 只有 `manylinux x86_64` 和 `macosx arm64`（cp310–cp314），**没有 Windows wheel**。
- README "Supported specs" 写的是 "Windows 10, 11 (via WSL2)"。README 里的模拟器表虽然给 Windows 列打了勾，但那只是核心能编译，官方安装路径是 WSL2（`docs/linux_installation.md` 里有 WSL2 指南）。
- 推荐 Ubuntu 24.04，Python 3.10–3.14，CPU 需支持 SSE3。
- 新增模拟核心：N64、NDS、Saturn、Dreamcast（仅 Linux 且需硬件渲染）、Arcade（FBNeo，macOS 不支持）。

**已集成的格斗游戏**。逐个检查 `stable_retro/data/stable` 目录名，按"1v1 对战格斗"标准人工筛选，不含清版动作和拳击：

| 平台 | 集成名 |
|---|---|
| Genesis | `StreetFighterIISpecialChampionEdition-Genesis-v0`、`MortalKombat-Genesis-v0`、`MortalKombatII-Genesis-v0`、`MortalKombat3-Genesis-v0`、`SamuraiShodown-Genesis-v0`、`FatalFury-Genesis-v0`、`FatalFury2-Genesis-v0`、`ArtOfFighting-Genesis-v0`、`WorldHeroes-Genesis-v0`、`ClayFighter-Genesis-v0`、`VirtuaFighter2-Genesis-v0`、`TeenageMutantNinjaTurtlesTournamentFighters-Genesis-v0`、`JusticeLeagueTaskForce-Genesis-v0`、`ShaqFu-Genesis-v0`、`FightingMasters-Genesis-v0`、`KaGeKiFistsOfSteel-Genesis-v0`、`DeadlyMoves-Genesis-v0`、`PowerAthlete-Genesis-v0`、`StreetSmart-Genesis-v0`、`PitFighter-Genesis-v0`、`RiseOfTheRobots-Genesis-v0`、`CyborgJustice-Genesis-v0`、`KingOfTheMonsters2-Genesis-v0` |
| SNES | `ArtOfFighting-Snes-v0`、`KingOfTheMonsters2-Snes-v0`、`BattleMasterKyuukyokuNoSenshiTachi-Snes-v0` |
| 其他家用机 | `MortalKombat-SCD-v0`（Sega CD）、`VirtuaFighter-32x-v0`、`VirtuaFighter2-Saturn-v0`、`MortalKombatTrilogy-N64-v0`、`UltimateMortalKombatM5-NintendoDS-v0`、`StreetFighter3rdStrike-Dreamcast-v0`（需 Linux 硬件渲染和 BIOS）、`TeenageMutantNinjaTurtlesTournamentFighters-Nes-v0`、`UrbanChampion-Nes-v0`、`PitFighter-Sms-v0`、`BattleArenaToshinden-GameBoy-v0` |
| 街机（FBNeo） | `MortalKombat2-Arcade-v0`（唯一的街机格斗集成） |

- README 的营销表格把 "King of Fighters '98" 列为 Fighters 示例，但**目录树里没有任何 KOF 集成**（2026-10-07 检查），以目录为准。
- 各集成的 RAM 变量丰富程度差别很大：
  - `StreetFighterIISpecialChampionEdition-Genesis-v0` 的 `data.json` 只有 `health`、`enemy_health`、`matches_won`、`enemy_matches_won`、`score`、`continuetimer`，**没有坐标**。默认 `scenario.json` 以 `score` 为奖励、`continuetimer==10` 为结束条件，只带一个存档 `Champion.Level1.RyuVsGuile.state`。
  - `MortalKombatII-Genesis-v0` 有双方 `x_position` / `y_position`、`health`、`rounds_won`，有 30 多个存档，其中包括 `Level1.LiuKangVsJax.2P.state`（双人存档）。
  - `MortalKombat2-Arcade-v0` 有 `p1_health`、`p2_health`、`round`。

**添加新游戏**（`docs/integration.md`）
- 每个集成目录包含 `data.json`（RAM 变量：`address` + `type`，如 `>u2`、`|d1`、`>i2`，类型含字节序、有无符号、BCD）、`scenario.json`（由变量组合出奖励和结束条件，可限制动作组合 `actions`、裁剪 `crop`）、`metadata.json`（默认存档）、`rom.sha`（ROM 哈希，多数来自 No-Intro SHA-1）以及 `.state` 存档。
- 用 Integration UI 搜索内存变量和制作存档。文档里 Windows/Mac 版 Integration UI 的链接还是 "TODO"，实际需要从源码构建。
- 用 `python3 -m retro.import <rom目录>` 按哈希导入 ROM；自定义集成放到 `custom_integrations`，配合 `inttype=retro.data.Integrations.ALL` 加载。
- 复杂奖励可以写 `script.lua`。

**双人**：支持。`RetroEnv(players=2)` 会把动作空间扩成双人（MultiBinary 为 `num_buttons*players`，Discrete 为 `combos**players`）；`multi_rewards` 可返回每个玩家各自的奖励；`metadata.json` 可通过 `default_player_state` 为不同人数指定存档；示例见 `stable_retro/examples/trivial_random_agent_multiplayer.py`。前提是该游戏有双人存档，并且 `data.json` 里有 P2 的变量。

### 2.3 MAMEToolkit（M-J-Murray/MAMEToolkit）

来源：https://github.com/M-J-Murray/MAMEToolkit README；PyPI `MAMEToolkit`。

- **功能**：把 MAME 包装成 Python 环境，每步返回帧（NumPy）和指定内存地址的值，并能向输入端口发送动作。依赖作者修改过的 MAME（https://github.com/M-J-Murray/mame），改动包括扩展 Lua console 以导出帧数据、关闭开机警告。
- **维护状态**：PyPI 1.1.0（2019-12-08），最近推送 2020-01-10，GPL-2.0。**近 7 年无更新，视为停更**。
- **平台**：README 原文 "currently available on Linux systems"，"Other operating systems will not work, as the library relies heavily on linux fifo pipes"。无头服务器需要 Xvfb。
- **内置街霸环境**：Street Fighter III 3rd Strike（Japan 990608, NO CD），MAME ID `sfiii3n`。示例内存地址如 `winsP1 = Address('0x02011383','u8')`、`healthP1 = Address('0x02068D0B','s8')`；仓库附带 `sf_environment/Environment.py` 和 `Steps.py`，用来跳过标题和选人界面。
- **读 RAM 的方式**：用户提供 `{名字: Address(十六进制地址, 类型)}`，工具通过修改版 MAME 的 Lua console 每帧读取并回传。README 建议用 MAME 调试器的 cheat 搜索功能（`cheatinit` / `cheatnext`）定位地址。
- `frame_ratio` 默认 3，即 60fps 下每 3 帧给智能体 1 帧（20fps）。作者报告单个随机智能体约 600% 实时速度，8 个 hogwild 约 300%；一个 5 层 ConvNet 训练 2200 局后，平均闯关从第 2 关提升到第 5 关。
- **对本项目**：思路可借鉴，但应改用新版 MAME 自带的 Lua API（§4）重写，不要依赖 2019 年的 MAME 分支。

### 2.4 FightingICE / DareFightingICE（立命馆大学 ICE Lab）

来源：https://github.com/TeamFightingICE/FightingICE ，https://github.com/TeamFightingICE/FightingICE/tree/master/DareFightingICE ，https://www.ice.ci.ritsumei.ac.jp/~ftgaic/index-R.html ，arXiv:2203.01556、arXiv:2403.02687。

- **引擎**：Java 2D 格斗游戏，图形用 LWJGL 3.3.3（带 Windows amd64 / Linux amd64、arm64 / macOS arm64 原生库），通信用 gRPC + protobuf。提供 Docker 一键启动 `ghcr.io/teamfightingice/fightingice`。
- **Python 接口**：`pyftg`（PyPI 2.3，2025-02-05，MIT）。早年另有 Py4J 和 OpenAI Gym 接口（官网写 2019-07-08 更新）。
- **当前状态**：release v7.1（2026-04-18），最近推送 2026-09-14，仍在维护。
- **15 帧延迟**：DareFightingICE 文档提到 15 帧延迟机制，用于 "achieving fairness in DareFightingICE agents evaluation"。即 AI 拿到的游戏状态有 15 帧（约 250ms）滞后，这是本领域最早的内建"人类化延迟"之一。
- **竞赛历史**：
  - 2013–2021 名为 Fighting Game AI Competition；
  - 2022 起改为 DareFightingICE，在 IEEE CoG 举办，含"音效设计"和"只靠声音的盲 AI"两个赛道；2022、2023 两个赛道属同一比赛，2024 起拆成两个独立比赛；
  - **2025**：AI 赛道第 1 名 Pythunder（Eita Aoki），第 2 名 Mana Ropé 25（Katsuki Ohto），第 3 名为官方基线 BlindAI `[部分核实：来自检索摘要，对应官方结果页未逐条打开]`；
  - **2026**：AI 赛道改为 **DareFightingICE LLM AI Competition**，要求用 LLM（提示工程或微调，模型 ≤7B）驱动实时格斗智能体。官方结果页列出第 1 名 Team Iconic（立命馆），第 2 名 Llama BakaCirno（北京交通大学），第 3 名 MambaGPT（立命馆）。音效设计赛第 1 名为 Re-Classica（Musa Khan）。"≤7B" 这一限制来自检索摘要 `[部分核实]`。
- **对本项目**：游戏本身不是商业街机游戏，但学术圈有长期基线（MCTS、BlindAI 等），带延迟和音频输入，适合做"公平对战"的对照实验。

### 2.5 Footsies 类环境

- **FOOTSIES（HiFight）**：Unity 制作的极简 2D 格斗游戏，只保留立回（neutral）的博弈。仓库 https://github.com/hifight/Footsies ，GPL-3.0，最近推送 2020-05-13。
- **FootsiesGym（como-research）**：https://github.com/como-research/FootsiesGym ，论文 arXiv:2607.06514（McDonald, Tsang, Kerr，2026-07-07 提交），"A Fighting Game Benchmark for Two-Player Zero-Sum Imperfect-Information Games"。
  - PyPI `footsies-gym` 1.0.0（2026-07-08），最近推送 2026-10-04，GPL-3.0。
  - 架构：Python 环境通过 gRPC 驱动 Unity 游戏服务器，支持向量化（单服务器批量推进 N 局）。首次使用时自动下载二进制并校验 SHA256。
  - **平台：Linux、macOS（Rosetta）；README 原文 "Windows is not supported"**。
  - 关键参数：`frame_skip=4`（默认），**`action_delay=8` 帧（默认，"simulates reaction time"）**；动作空间 `Discrete(6)`，开启蓄力特殊技时为 `Discrete(9)`；观测为 88 维向量，非对称：双方都能看到自己的私有信息，看不到对方的，因此是不完全信息博弈。
  - 接口是多智能体 dict 风格（`env.agents`、`terminateds`/`truncateds`），文档未直接写明属于 PettingZoo 还是 RLlib MultiAgentEnv `[未核实]`。
- **Ray RLlib 的 Footsies 自博弈示例**（`self_play_footsies.py` / `multi_agent_footsies_ppo.py`）：只在第三方 Ray 发行包镜像（gemfury）中见到。2026-10-07 在 ray-project/ray 主分支对应路径查询返回 404，可能已移动或删除 `[部分核实]`。
- 其他小型复刻（如 `Brogolem35/botsies`、`martinhoT/footsies-agents`）星数很少，没有逐一核实。

### 2.6 linyiLYi/street-fighter-ai

来源：https://github.com/linyiLYi/street-fighter-ai （README、README_CN、`main/train.py`、`main/street_fighter_custom_wrapper.py`）。

- **框架更正**：项目用的是 **OpenAI gym-retro**（Python 3.8.10 + Stable-Baselines3），不是 stable-retro；在 Windows 11 上测试，附带 `Gym Retro Integration.exe`。
- **算法**：SB3 `PPO("CnnPolicy")`，`NUM_ENV=16`（SubprocVecEnv），`n_steps=512`，`batch_size=512`，`n_epochs=4`，`gamma=0.94`，学习率从 2.5e-4 线性衰减到 2.5e-6，clip 从 0.15 线性衰减到 0.025。代码里 `total_timesteps=int(100000000)`，但公开的检查点只有 2.0M / 2.5M / 3.0M / 7.0M 步。
- **观测**：每个环境步重复同一动作 **6 帧**（`num_step_frames=6`）。保留最近 9 帧，每帧 2 倍下采样到 100×128，再从第 3、6、9 帧各取 R、G、B 一个通道，拼成一张 (100,128,3) 图像。只用像素决策，RAM 只用来算奖励。
- **奖励**：只读 `agent_hp` / `enemy_hp`（满血 176）。
  - 对局中：`3 × 对手掉血 − 自己掉血`；
  - 输了：`−176^((对手剩余血+1)/177)`；
  - 赢了：`3 × 176^((自己剩余血+1)/177)`；
  - 整体乘 0.001 归一化。系数 3 的作用是抑制"怂"（cowardice），README 引用了 CoG 2022 论文 *Mitigating Cowardice for Reinforcement Learning* 的 penalty decay 思路。
- **训练场景**：**只用一个存档** `Champion.Level12.RyuVsBison`（最高难度最终关，隆对拜森）。
- **过拟合说明（作者原话）**：README 明说 "achieves a 100% win rate in the first round of the final level (overfitting occurs)"：
  - 2.0M 步：刚开始过拟合，有泛化能力但不强；
  - 2.5M 步：默认模型，泛化较好，有较大概率打通最终关；
  - 3.0M 步：第一轮胜率接近 100%，泛化能力弱；
  - 7.0M 步：完全过拟合，第一轮 100% 胜率，几乎不泛化。
- **结论**：这是"对固定 CPU、固定存档的过拟合"，**不能**当作"RL 能打赢人类"的证据。

### 2.7 其他开源（只列能查到仓库的；均为小型个人或课程项目，没有逐一验证可运行性）

| 仓库 | 内容 | 最近推送 |
|---|---|---|
| M-J-Murray/SFAgents | MAMEToolkit 上的 SF3 ConvNet 智能体 | 2020-01 |
| corbosiny/AIVO-StreetFigherReinforcementLearning | SF 训练环境 | 2023-03 |
| rpeixe/gym-exploring-combos | 在 Street Fighter Alpha 3 中用 RL 探索连段 | 2025-04 |
| BrunoMarcato/MortalKombatAI | gym-retro 上的 MK | 2024-05 |
| RielFox/umk3_environment | UMK3（Rev 1.2）街机环境 | 2020-07 |
| Ibrahim-Benkhedda/Kane-vs-Abel-MortalKombat2 | MK2 上比较行为树和 DRL | 2025-03 |
| Lexer04/Samurai-Shodown-with-Reinforcement-Learning-PPO | 侍魂上双智能体 PPO 对打 | 2024-05 |
| bq6613753-ops/Mugen-AI | MUGEN 上的 RL | 2026-03 |
| acht7111020/DRL-playing-2.5D-fighting-game | ICIP 2018，Little Fighter 2（论文 arXiv:1805.02070） | 2020-06 |

- 按 "fightingRL" 和 "ikemen reinforcement learning" 检索 GitHub 均无结果。**Ikemen GO 本体活跃，但没有找到成型的 RL 环境封装** `[未核实是否存在非公开或未索引的项目]`。

---

## 3. 学术工作

### 3.1 Blade & Soul 职业级格斗 AI（NCSOFT）

- Oh, Rho, Moon, Son, Lee, Chung. *Creating Pro-Level AI for a Real-Time Fighting Game Using Deep Reinforcement Learning*。**arXiv:1904.03821**；**IEEE Transactions on Games 14(2):212–220, 2022 卷（OpenAlex 记为 2021 年在线发表），DOI: 10.1109/TG.2021.3049539**（已用 OpenAlex 核实）。
- 方法：
  - LSTM 智能体每 **0.1 秒**决策一次；状态只包含"人类在对局中能看到的信息"（HP、SP、距离、离墙距离、剩余时间等）；
  - **自博弈课程**：用三维奖励塑形（时间惩罚、HP 相关项、距离惩罚）分别训练出 aggressive、balanced、defensive 三种风格，放进共享对手池互相对练；
  - **data skipping**：跳过大量被动的 no-op 数据，提高样本效率和探索。
- **公平性设置（关键）**：原文 "We applied an average of 230 ms of delay for the decision of an AI to be reflected in the game ... This amount of delay corresponds to the average reaction time of professional players in BAB"。职业选手和 AI 固定同一职业（Destroyer）、同一技能树。
- 结果：
  - 摘要：对 5 名职业选手**总胜率 62%**（预测试加正式赛）；
  - 2018 B&S 世界锦标赛 Blind Match 中赢了 7 场里的 3 场；
  - aggressive 风格在预测试和现场都击败了全部职业选手。作者认为一个原因是 aggressive 智能体持续进攻，不给人类喘息时间。

### 3.2 FightLadder（ICML 2024）

- Li, Ding, Karten, Jin（普林斯顿）。**arXiv:2406.02081**（2024-06-04 提交，v2 于 06-24），ICML 2024。代码 https://github.com/wenzhe-li/FightLadder （MIT），项目页 https://sites.google.com/view/fightladder/home 。
- 支持游戏：Street Fighter II（Genesis）、Street Fighter III（街机）、Fatal Fury 2（Genesis）、Mortal Kombat（Genesis）、The King of Fighters '97（Neo Geo）；底层基于 gym-retro 和 MAMEToolkit 一类模拟器接口。默认每步帧数 8（Genesis 类）或 3（街机类），帧堆叠 12 或 9。
- 发现：
  - **单人**：课程学习加 PPO 训练 20 个 epoch（每个 epoch 10M 步）后，对每个 CPU 角色胜率接近 1，通关整个游戏的胜率超过 0.6，作者称其超过了玩过几小时的人类；加入硬编码必杀技表**没有**显著提升。
  - **双人**：实现了 IPPO、FSP、PSRO 和 AlphaStar 式联赛（主智能体、主利用者、联赛利用者）。联赛和 PSRO 的 Elo 更高，但 **PPO 利用者最终能以超过 0.5 的胜率击败所有基线算法训练出的策略**，原文 "none of these algorithms can result in the exact Nash equilibrium policies, or even close to it"。
  - **人类做利用者**："some simple strategies (e.g., defensive posture combined with low kicks at proper timing) could still defeat them rather consistently"。
  - 结论："both single-agent RL and human players are capable of exploiting all agents learned by current widely adopted algorithms"。

### 3.3 Firoiu 等：Melee 与"人类反应延迟"

- **Firoiu, Whitney, Tenenbaum (2017)**，**arXiv:1702.06230**。arXiv v3 标题为 *Beating the World's Best at Super Smash Bros. with Deep Reinforcement Learning*，PDF 正文标题带 "Melee"。
  - 先对内置 AI 训练，作者称效果"连低水平竞技玩家都构不成挑战"；改为自博弈约两周后，带到两场大型赛事，"performed favorably against all professional players who were willing to face it"，结论里写超过了 10 名高排名人类选手。
  - **自己承认的主要缺陷**："they play with unrealistic reaction speed: 2 frames (33ms), compared to over 200ms for humans"。
  - 延迟实验：用"前 k+1 帧加动作"做输入，延迟 2 或 4 帧时仍能训练出较强智能体，**到 6–10 帧附近性能急剧下降**。
- **Firoiu, Ju, Tenenbaum (2018)**，*At Human Speed: Deep Reinforcement Learning with Action Delay*，**arXiv:1810.07286**。
  - 引用 Jain et al. 2015：普通人视觉反应约 250ms。在 60Hz 下，**15 帧 ≈ 普通人，12 帧被视为人类可达的下限**。
  - 发现标准 IMPALA 随延迟增加迅速掉性能；提出用神经预测模型"抵消"延迟（预测步数 p 等于延迟 d 时最好）。
  - 对英国头号选手 Professor Pro（国际排名第 41），在每 2 帧决策一次的条件下，延迟 6 步和 7 步分别相当于 12 帧和 14 帧（约 200ms 和 233ms）。表 1 结果：
    - 不带预测的 (6,0)：0 胜 6 负；
    - (6,6)：3 胜 5 负；
    - (7,7)：2 胜 5 负。
  - 作者原话 "our predictive agents were not ultimately victorious, they did come close"。
  - 该文还指出 APM 问题：frame skip 为 2 的 RL 智能体约 1800 APM，星际职业选手很少超过 400。

### 3.4 Phillip / slippi-ai（vladfi1）

- https://github.com/vladfi1/slippi-ai （MIT；最近推送 2026-10-06，仍在活跃开发）。这是 Phillip 的后继：**先在 Slippi 回放上做行为克隆，再用自博弈 RL 精炼**。接口基于 libmelee（vladfi1/libmelee 最近推送 2026-08-17）。
- README 原文："Due to phillip's high delay (18+ frames) and buffer donation, it should feel like playing locally at up to 300ms ping"。也就是说，**当前公开对战版本带 18 帧以上（约 300ms）延迟**，比 Firoiu 2018 的 12–14 帧还长。
- README 列出与 Zain、aMSa、Cody、Moky、Aklo 等顶尖选手的对战录像。具体比分（如 Moky 先 10 局 10–3 负于 Phillip，Zain 先 5 局 5–3 胜 Phillip）只见于 Manifold 预测市场页面，该市场"2025 年是否有人类在 Bo5 中击败 Phillip"按"否"结算 `[部分核实：二手来源，无一手比赛记录]`。
- 意义：这是"人类级延迟 + 模仿学习先验 + RL"路线下，目前最接近与顶尖人类五五开甚至占优的公开系统。但它依赖大规模人类回放数据，街机老游戏不具备这个条件。

### 3.5 限制反应时间 / APM 的先例

| 系统 | 来源 | 限制设置 |
|---|---|---|
| **GT Sophy**（Sony AI） | Wurman et al., *Outracing champion Gran Turismo drivers with deep reinforcement learning*, Nature 602:223–228 (2022)，**DOI: 10.1038/s41586-021-04357-7** | 决策频率 **10Hz**（Sony AI 博客："decision cycle, 0.1s ... at 10Hz"）。"自然反应 23–30ms" 以及"人为加 100/200/250ms 延迟后的表现"这两条只在二手摘要中见到 `[部分核实，未读到 Nature 原文]` |
| **AlphaStar**（DeepMind） | Vinyals et al., *Grandmaster level in StarCraft II using multi-agent reinforcement learning*, Nature 575:350–354 (2019)，**DOI: 10.1038/s41586-019-1724-z** | DeepMind 博客原文："capped at a max of 22 agent actions per 5 seconds"（一个智能体动作最多计 3 次游戏内 APM）；通过镜头界面观察；Battle.net 排名高于 99.8% 的活跃玩家，三族均达宗师。2019-01 演示版"平均 APM 约 280、观测到动作平均延迟约 350ms"只有新闻转述 `[部分核实]`。另外，5 秒窗口内可以集中爆发操作，这一点在社区有争议 |
| **OpenAI Five** | OpenAI et al., *Dota 2 with Large Scale Deep Reinforcement Learning*, **arXiv:1912.06680** | 每 4 帧决策一次（7.5 次/秒），观测与动作异步错开一步；论文附录 L："reaction time randomly distributed between 5 and 8 frames (167ms to 267ms)"，正文写平均 **217ms**，并引用人类视觉反应约 250ms |
| **B&S（NCSOFT）** | 见 §3.1 | 平均 **230ms** 决策生效延迟 |
| **Firoiu 2018 / Phillip** | 见 §3.3、§3.4 | 12–14 帧 / 18 帧以上 |
| **FightingICE / FootsiesGym** | 见 §2.4、§2.5 | 15 帧状态延迟 / 默认 8 帧动作延迟 |

### 3.6 对抗策略与可被利用性

- **Gleave et al. (2019)**，*Adversarial Policies: Attacking Deep Reinforcement Learning*，**arXiv:1905.10615**（ICLR 2020）。在仿真人形机器人零和博弈中，针对自博弈训练出的"受害者"，训练出的对抗策略看起来像在乱动，却能稳定获胜：它们通过制造"自然但对抗"的观测，诱使受害网络犯错。
- **Wang et al. (2022/2023)**，*Adversarial Policies Beat Superhuman Go AIs*，**arXiv:2211.00241**（ICML 2023）。对超人设置下的 KataGo 胜率 **超过 97%**；对抗者并不擅长下棋，而是诱导 KataGo 犯严重错误；攻击能零样本迁移到其他超人围棋 AI；**人类专家学会后无需算法辅助也能稳定击败超人 AI**；即使对 KataGo 做了针对性对抗训练，核心漏洞仍然存在。
- 对格斗游戏的含义：FightLadder（§3.2）在街霸上直接复现了同类现象。"对 CPU 胜率高"和"对人类胜率高"都**不等于**不可被利用。

### 3.7 自博弈与联赛

- **PSRO**：Lanctot et al., *A Unified Game-Theoretic Approach to Multiagent Reinforcement Learning*，**arXiv:1711.00832**（NIPS 2017）。指出独立 RL 会过拟合训练中遇到的对手（提出 joint-policy correlation 指标）；PSRO 对策略混合求近似最优反应，并用经验博弈论元求解器选择对手。它统一了 InRL、迭代最优反应、double oracle 和虚拟博弈。
- **AlphaStar League**：主智能体加两类利用者（main exploiter 和 league exploiter）。利用者"focus on helping the main agent grow stronger by exposing its flaws"，用来缓解自博弈的遗忘和循环克制问题（DeepMind 博客与 Nature 论文）。FightLadder 在街霸上实现了这一结构，并给出 Elo 和可被利用性评估。

### 3.8 其他格斗游戏 RL 论文（已在 arXiv 核实存在）

- Palmas, *DIAMBRA Arena: a New Reinforcement Learning Platform for Research and Experimentation*，**arXiv:2210.10595**。
- Li et al., *Deep Reinforcement Learning for Playing 2.5D Fighting Games*，**arXiv:1805.02070**（ICIP 2018，Little Fighter 2）。
- Halina & Guzdial, *Diversity-based Deep Reinforcement Learning Towards Multidimensional Difficulty for Fighting Game AI*，**arXiv:2211.02759**（EXAG 2022）。
- Zhang et al., *Advancing DRL Agents in Commercial Fighting Games: Training, Integration, and Agent-Human Alignment*，**arXiv:2406.01103**（ICML 2024）。系统名 Shūkai，部署于《火影忍者手游》；提出 Heterogeneous League Training（HELT），只用 13% 的角色训练就能泛化到全部角色。
- Nguyen & Driessens, *For How Long Should We Be Punching? Learning Action Duration in Fighting Games*，**arXiv:2605.20911**（Computers and Games 2026）。以 SF2 为例，让智能体同时学"做什么"和"做多久"，并直接讨论了"逐帧决策等于帧级完美反射、对人类不现实"的问题。
- Van Nguyen, Khan et al., DareFightingICE 竞赛论文：**arXiv:2203.01556**、**arXiv:2403.02687**（标题和编号来自检索结果，未逐篇打开 `[部分核实]`）。
- 综述：*A Comprehensive Review of Multi-Agent Reinforcement Learning in Video Games*，**arXiv:2509.03682**（IEEE Transactions on Games, 2025）。不是格斗专项综述。
- *Mitigating Cowardice for Reinforcement Learning*（IEEE CoG 2022）。链接 https://ieee-cog.org/2022/assets/papers/paper_111.pdf 取自 linyiLYi README，作者和 DOI `[未核实]`。

---

## 4. 街机 ROM 的 RAM 状态读取

| 方式 | 机制 | 要点 |
|---|---|---|
| **MAME Lua API** | `manager.machine.devices[":maincpu"].spaces["program"]` 取地址空间，然后 `space:read_u8(addr)` / `read_u16` / `read_i32` / `read_u64` 等读取；`space:install_read_tap(start, end, name, callback)` 可以在读访问时被动回调（来源：https://docs.mamedev.org/luascript/ref-mem.html ） | 不用改 MAME 源码；当前 MAME 0.289（2026-07-30）。每帧回调和输入注入要另查 `emu` / `ioport` 相关 API，本次没有逐条核实 |
| **MAME 调试器 cheat 搜索** | `cheatinit` 快照内存 → `cheatnext` 按增减或等值筛选 → `cheatlist` 导出 XML（形如 `<action>:maincpu.pb@0x00B85=0x03</action>`）（来源：https://docs.mamedev.org/debugger/cheats.html ） | 给新游戏找血量、坐标、计时器地址的标准方法 |
| **MAME cheat 数据库（社区 Pugsy's cheat.7z）** | 社区维护的 XML 金手指集合，里面常有"无限血量"等条目，可以反推血量地址 | 官网 mamecheat.co.uk 本次访问返回 403，版本和覆盖范围 `[未核实]`。用前需在调试器里验证地址和类型 |
| **stable-retro `data.json`** | `{"health": {"address": 16744514, "type": ">i2"}}`，地址是模拟器 RAM 数组的偏移；`scenario.json` 用这些变量定义奖励和结束条件；Integration UI 支持搜索和改值验证 | 文档给了类型陷阱的排查方法（`>d2` 和 `>d4`、有无符号、找到的是副本还是真地址） |
| **DIAMBRA 内置 RAM 状态** | 观测字典里直接给出 `stage`、`timer`，以及 P1/P2 的 `side`、`wins`、`character`、`health`，加游戏特有项（如 sfiii3n 的 `stun_bar`、`super_bar`） | 不用自己找地址；但字段固定，没有坐标、帧数据、招式状态（samsh5sp 例外，有 latest move/attack） |
| **MAMEToolkit** | 修改版 MAME 的 Lua console 加 FIFO，用 `Address('0x02068D0B','s8')` 声明地址 | 停更，只作参考 |

**RAM 读取对训练的意义**
1. **奖励**：几乎所有格斗 RL 都用血量差做稠密奖励（linyiLYi、FightLadder、stable-retro 的 MKII 场景），没有 RAM 就只能用 OCR 读血条。
2. **回合和结束判定、跳过菜单**：靠 `round` / `wins` / `continuetimer` 等变量。
3. **观测**：RAM 状态可以直接作为低维观测（坐标、硬直、招式 ID），样本效率远高于像素输入。但这也是"信息不对称"的来源：人类看不到对手的内部帧计数器，RAM 观测会让 AI 获得额外信息。FightLadder 原文 "Same as human players, the agent is not allowed to access the [complete state]"。**公平性实验里应限制 RAM 观测只包含人类在屏幕上可见的信息**，或者只用像素。
4. **评估和分析**：可以统计受击、防御、出招分布，用来检测"怂"（cowardice）和退化策略。

---

## 5. "RL 必然无敌"这个说法的诚实评估

### 5.1 帧级完美反应是"不公平优势"，不是"更聪明"

- 60Hz 游戏一帧约 16.7ms。逐帧决策的 RL 智能体反应时间只有 1–2 帧（17–33ms）。Firoiu 2017 自己承认这是主要批评："2 frames (33ms), compared to over 200ms for humans"。
- 人类视觉反应约 250ms（Firoiu 2018 和 OpenAI Five 都引用了这个数字）。B&S 实测职业选手平均约 230ms。换算成帧：**12 帧（200ms）可视为人类下限，15 帧（250ms）约为普通人**，依据是 Firoiu 2018 的原文设定。
- 格斗游戏圈常说"人类对特定招式的反应约 15–20 帧" `[未核实：没有找到同行评审来源；只有 Firoiu 2018 的 12/15 帧设定可作学术引用]`。
- 因此，**不限制延迟的胜利只能证明"反射快"**，B&S 和 Firoiu 2018 都把延迟作为公平性前提。

### 5.2 加上人类延迟后，"超人"结论明显变弱

| 工作 | 无延迟或低延迟 | 人类级延迟 |
|---|---|---|
| Firoiu 2017（Melee） | 2 帧：对 10 名高排名选手占优 | 6–10 帧：性能急剧下降 |
| Firoiu 2018（Melee） | — | 12–14 帧加预测模型：对英国头号选手 2–3 胜 5 负，未胜出 |
| B&S（NCSOFT） | — | 230ms：对 5 名职业选手总胜率 62%，Blind Match 3/7 |
| Phillip / slippi-ai | — | 18 帧以上：对部分顶尖选手占优、对部分落败（二手比分） |
| GT Sophy（赛车） | 10Hz 决策 | 加延迟后的结果 `[部分核实]` |

所以**超人表现确实存在，但只在特定条件下得到证实**：大规模自博弈、有人类回放数据（Phillip），或者游戏本身让反应速度没那么关键（B&S 的 0.1s 决策粒度和 aggressive 风格）。没有任何一篇工作证明"在人类级延迟下，RL 能稳定击败所有顶尖人类"。

### 5.3 对 CPU 赢不等于对人赢

- linyiLYi 的 100% 胜率是对**单一存档、单一 CPU** 的过拟合，作者自己写明泛化差。
- Firoiu 2017：只对内置 AI 训练的智能体"连低水平竞技玩家都构不成挑战"。内置 AI 的模式固定，容易被利用。

### 5.4 可被利用性：强不等于不可被针对

- FightLadder：所有主流竞争性 MARL 算法（IPPO、FSP、PSRO、联赛）训练出的街霸智能体，都能被单智能体 PPO 利用者打出超过 0.5 的胜率，人类用"防御姿态加适时下段踢"就能稳定取胜。
- KataGo：超人围棋 AI 被对抗策略以超过 97% 的胜率击败，人类学会后也能复现。
- Gleave 2019：自博弈训练的策略对"乱动"的对抗策略很脆弱。
- 结论：**"能赢某个分布的对手"和"不可被利用"是两个指标**。宣称"无敌"至少要报告"对专门训练的利用者"的胜率。

### 5.5 自博弈和联赛是必要条件，但不充分

- 只对 CPU 训练会过拟合（linyiLYi、Firoiu 2017）。朴素自博弈会出现循环克制和遗忘（PSRO 论文提出的 joint-policy correlation 就是为此）。联赛和 PSRO 能提高 Elo、降低可被利用性，但 FightLadder 显示它们离纳什均衡仍很远。
- 格斗游戏本身有强烈的非传递性（打、投、防的克制循环），FootsiesGym 论文专门把它作为研究对象。这意味着"一个策略打遍天下"在理论上就不成立，理想目标是混合策略。

### 5.6 RAM 读取是双刃剑

- 好处是能提供稠密奖励和低维观测，训练快几个数量级。
- 坏处是 RAM 观测可能包含屏幕上看不到的信息（内部计数器、对手指令缓冲区）。即使延迟限制到人类水平，信息优势仍会让"公平"打折扣。公平实验应**只用像素，或者只用人类可见的 RAM 字段**，并在论文里写明。

---

## 6. 可信路线

### 6.1 约束先行

1. **观测延迟**：智能体在 t 时刻只能看到 t−d 时刻的观测。主实验取 d = 12 帧（200ms），敏感性分析取 d ∈ {0, 6, 12, 15, 18} 帧，与 Firoiu 2018、B&S（230ms）、Phillip（18 帧以上）对齐。实现方式：在环境包装器里维护观测队列。FootsiesGym 有现成的 `action_delay` 可以直接对照。
2. **动作频率 / APM 上限**：决策间隔 ≥ 4–6 帧（10–15 次/秒），或在滑动窗口内限制非 no-op 动作数（参照 AlphaStar 的 22 次每 5 秒），并统计实际 APM 和人类对照。OpenAI Five 的 7.5Hz 和 B&S 的 10Hz 都是先例。
3. **信息对等**：只用像素，或者只用人类可见的 RAM 字段（血、气、计时、位置）；不读对手指令缓冲区和内部帧计数器。
4. **预测模型**：在延迟下引入前向预测（Firoiu 2018 的方法：p = d 时最好），否则性能可能直接崩掉。

### 6.2 训练

- 用自博弈加联赛（主智能体、主利用者、联赛利用者）或 PSRO，不要只对 CPU 训练。
- 角色、关卡、存档随机化，避免重蹈 linyiLYi 单存档过拟合的覆辙。
- 平台选择：
  - stable-retro 选 `MortalKombatII-Genesis-v0`：RAM 变量最全，有双人存档；
  - 或 DIAMBRA 的 `sfiii3n` / `kof98umh`：街机原版，2P 现成；
  - 研究延迟算法本身可以先在 FootsiesGym 上做（快、向量化、可分析）。
- 算力：stable-retro 和 FootsiesGym 都没有 Windows 原生支持，适合放到 Linux GPU 服务器上用任务队列跑；DIAMBRA 在服务器上也需要 Docker。

### 6.3 评估（三类对手，缺一不可）

| 对手 | 指标 | 说明 |
|---|---|---|
| **脚本 AI / 游戏内 CPU** | 各难度、各角色的胜率，通关率 | 只是健全性检查，不能用来宣称"超人" |
| **人类** | 分段（新手、中级、高手）胜率，带 95% CI；固定延迟设置并公开 | 盲测（人类不知道对面是 AI）；记录对局录像；人类有适应期，所以要报告前 N 局和后 N 局的变化 |
| **针对性利用者** | 冻结目标策略，用 PPO 训练最优反应，报告利用者收敛后的胜率（即 FightLadder 的可被利用性近似） | 再加"人类利用者"：给人类充分时间寻找套路。**只有利用者胜率接近 0.5 时才能谈"不可被利用"** |

- 还要报告：同一模型在 d = 0 和 d = 12 帧下的表现差距，量化"反射优势"占了多少。
- 判定标准：只有在人类级延迟、APM 上限和信息对等的条件下，同时满足"对人类高手胜率显著高于 50%"和"利用者胜率不高"，才能说"在该游戏中达到超人水平"。否则如实写"在 X 条件下对 Y 对手胜率 Z"。

---

## 7. 未核实或部分核实清单

| 条目 | 状态 | 说明 |
|---|---|---|
| DIAMBRA Docker 镜像当前能否拉取、竞赛平台是否运营 | `[未核实]` | 仓库自 2024-06 起停更 |
| FootsiesGym 接口属于 PettingZoo 还是 RLlib | `[未核实]` | README 只能看出是多智能体 dict 风格 |
| Ray RLlib Footsies 示例的当前位置 | `[部分核实]` | 只在第三方镜像见到，主分支路径 404 |
| DareFightingICE 2025 获奖名单、2026 "≤7B" 限制 | `[部分核实]` | 来自检索摘要；2026 获奖名单已在官方页核实 |
| DareFightingICE 竞赛论文 arXiv:2203.01556 / 2403.02687 | `[部分核实]` | 只核对了检索结果中的标题和编号 |
| Phillip 对 Moky、Zain 的具体比分 | `[部分核实]` | 只有 Manifold 二手来源 |
| GT Sophy 自然反应 23–30ms 及加延迟实验结果 | `[部分核实]` | Nature 原文需登录，未读到 |
| AlphaStar 2019-01 版平均延迟 350ms、APM 280 | `[部分核实]` | 新闻转述 |
| 格斗游戏"人类反应 15–20 帧"的说法 | `[未核实]` | 改用 Firoiu 2018 的 12/15 帧设定 |
| MAME cheat 数据库（Pugsy）版本和覆盖范围 | `[未核实]` | 官网返回 403 |
| *Mitigating Cowardice for RL* 的作者和 DOI | `[未核实]` | 只有 PDF 链接 |
| Ikemen GO / MUGEN 的成型 RL 环境 | `[未核实]` | 检索无结果，不能断言不存在 |
| MAME Lua 每帧回调、输入注入 API 细节 | `[未核实]` | 只核实了内存读取部分 |

> 注：上表中部分条目没有继续追查；补查时优先打开表中给出的一手链接。

---

## 附：一手来源索引

- DIAMBRA：https://docs.diambra.ai/ ，https://docs.diambra.ai/envs/ ，https://docs.diambra.ai/envs/games/ ，https://github.com/diambra/arena ，https://pypi.org/project/diambra-arena/ ，arXiv:2210.10595
- stable-retro：https://github.com/Farama-Foundation/stable-retro ，`docs/supported_games.md`，`docs/integration.md`，https://pypi.org/project/stable-retro/
- MAMEToolkit：https://github.com/M-J-Murray/MAMEToolkit
- MAME：https://docs.mamedev.org/luascript/ref-mem.html ，https://docs.mamedev.org/debugger/cheats.html ，https://github.com/mamedev/mame/releases
- FightingICE：https://github.com/TeamFightingICE/FightingICE ，https://www.ice.ci.ritsumei.ac.jp/~ftgaic/index-R.html ，https://pypi.org/project/pyftg/
- FootsiesGym：https://github.com/como-research/FootsiesGym ，arXiv:2607.06514 ；FOOTSIES：https://github.com/hifight/Footsies
- linyiLYi：https://github.com/linyiLYi/street-fighter-ai
- FightLadder：arXiv:2406.02081 ，https://github.com/wenzhe-li/FightLadder
- slippi-ai：https://github.com/vladfi1/slippi-ai
- 论文：arXiv:1904.03821（DOI 10.1109/TG.2021.3049539），arXiv:1702.06230，arXiv:1810.07286，arXiv:1912.06680，arXiv:1905.10615，arXiv:2211.00241，arXiv:1711.00832，arXiv:1805.02070，arXiv:2211.02759，arXiv:2406.01103，arXiv:2605.20911，arXiv:2509.03682；Nature DOI 10.1038/s41586-021-04357-7（GT Sophy），10.1038/s41586-019-1724-z（AlphaStar）
- AlphaStar 博客：https://deepmind.google/discover/blog/alphastar-grandmaster-level-in-starcraft-ii-using-multi-agent-reinforcement-learning/
