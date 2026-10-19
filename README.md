# 战争之匣 · 基础版游戏与训练环境

[![Tests and build](https://github.com/Alexlin23/war-chest/actions/workflows/ci.yml/badge.svg)](https://github.com/Alexlin23/war-chest/actions/workflows/ci.yml)

已把首局 8 兵种样机扩展为基础版 16 兵种，支持双人、四人组队、随机/自选阵容、选兵和三组历史阵容。没有实现模型或 DLC。

## Windows 上开始游戏

需要 Python 3.11+、Node.js 18+。在此目录打开 PowerShell：

```powershell
.\start.ps1
```

首次运行安装依赖，之后启动前后端。打开 **http://localhost:5173/**，选择人数和阵容，创建对局。

每位玩家使用独立浏览器会话打开自己的席位链接；同一会话的 Cookie 只保留最近加入的席位。可使用不同浏览器、独立用户配置或无痕会话。收藏席位链接即可继续对局。

选择手牌或棋盘格筛选行动，选定具体行动后点击「执行行动」。特殊能力会显示独立决策，例如卫队防御、牧师用币、步兵协同。兵种面板含能力说明。

按 Ctrl+C 停止两个服务。游戏、席位和行动记录保存在 `backend/data/games.sqlite3`，重启可继续。若端口 8000/5173 已被使用，启动器会提示先停止已有服务。

若 PowerShell 当前策略禁止运行脚本，可在两个终端分别手动启动：

```powershell
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

```powershell
npm ci
npm run dev -- --host 127.0.0.1
```

WSL 也可继续使用 `start-backend.sh` 和 `start-frontend.sh`。静态展示为 `http://localhost:5173/?demo=1`。

## 实现范围

- 基础版全部 16 兵种及其能力，棋币守恒、先手、循环抽币、即时胜利。
- 双人 37 格/10 据点，四人 47 格/14 据点；队伍控制、共享部署、队友指挥。
- 推荐、随机、自选、轮流选兵，以及高加米拉/班诺克本/克雷西阵容。
- 特殊效果暂停与恢复，不能假设每步双方交替或每步消耗一枚手币。
- 私有玩家视图、签名动作、版本冲突和并发重复提交保护。
- SQLite 原子保存局面与行动；完整回放在对局结束后才允许玩家导出。
- 进程内环境、JSON Lines 接口、紧凑数值观测、独立克隆和可校验回放。

皇家卫队默认使用**原始基础版**能力；修订版是显式接口选项，会被单独记录。规则来源、边缘解释和验证范围见 [规则记录](docs/rules.md)。

## 训练 API

```python
from backend.env import WarChestEnv

env = WarChestEnv(42, setup="random", max_decisions=2000)
obs = env.observe()
code = env.legal_action_codes()[0]  # 仅演示；以后由策略选择
result = env.step(code, expected_revision=obs["revision"])
```

批量模拟不经过 HTTP 或数据库；观测和轨迹按需生成。详见 [接口说明](docs/training-api.md)、[LLM 冷启动训练设想](docs/training-plan.md) 和 [性能记录](docs/performance.md)。

## 验证

```powershell
python -m pytest backend/tests -q
npm test
npm run build
python -m backend.benchmark --steps 200000 --repeats 3 --players 2
```

测试覆盖逐兵种能力、连锁结算、双/四人完整胜局、隐藏信息、并发、存档恢复、API 完整对局和回放一致性。浏览器验证和具体结果见 [验证记录](docs/VALIDATION.md)。

## 主要文件

- `backend/engine.py`：唯一规则来源。
- `backend/env.py`：训练和采集接口，不依赖 Web 或模型库。
- `backend/state.py`：JSON 快照、动作序列化和状态摘要。
- `backend/storage.py`、`backend/api.py`：本地游戏服务与存档。
- `backend/cli.py`：持续驻留的 JSON Lines 工具接口。
- `src/`：开局、棋盘、手牌、能力说明和行动选择界面。

当前是本机游戏/研发服务，使用一个服务工作进程；没有公网账户、匹配或多人房间管理平台。任意采样步数上限只表示截断，不冒充官方和棋。规则已按官方资料核对并有回归测试，尚无独立规则引擎做穷尽差分验证。
