# 训练与数据采集 API

目前提供环境、可见观测、动作编码、存档和回放；没有模型、学习算法或模型服务。

## 进程内接口

```python
import random
from backend.env import WarChestEnv, decode_action, public_action, replay

env = WarChestEnv(42, setup="random", player_count=2,
                 max_decisions=2000, record_trace=True, verify=True)
picker = random.Random(7)  # 仅为接口演示的随机选择器

while not env.done:
    actor = env.decision_player
    obs = env.observe(actor)                 # 只给该席位看得到的信息
    codes = env.legal_action_codes()         # 该局面全部合法候选
    code = picker.choice(codes)
    visible_event = {"actor": actor, **public_action(code)}
    result = env.step(code, expected_revision=obs["revision"])
    # 用 visible_event 更新其他席位的公共历史；暗弃支付币已脱敏。

trace = env.export_trace()                   # 受信任的离线日志，包含隐藏状态
final_game = replay(trace)                   # 检验每步动作、随机结果摘要、终局标签
```

运行 `python -m backend.cli` 可通过 JSON Lines 控制一个持续驻留的环境，无需在每步启动 Python，也无需经过 HTTP。

```json
{"op":"reset","seed":42,"max_decisions":2000,"options":{"setup":"draft","player_count":2}}
{"op":"observe"}
```

每行返回 `{ "ok": true, "result": ... }` 或错误对象。`observe` 返回当前决策方的私有观测和可读 `candidates`；从返回结果取 `code` 和 `revision` 后提交：

```json
{"op":"step","action_code":123,"expected_revision":0}
```

上面的 `123` 只是语法示例，必须替换为当前候选中的实际编码。非法或过期行动保持状态不变。`export_trace` 在 CLI 中只允许结束或截断后的对局，避免 LLM 对弈期间读取隐藏状态。

## 决策，而不是固定交替

`StepResult.actor` 是本步执行者；`decision_player` 是下一决策席位。两者可能相同，也可能在防御阶段切到对手，或切到触发能力的队友。不能写死每步奖励取反，不能假设一步总消耗手币，也不能把特殊决策当成新一轮普通行动。

自然胜利时每个获胜队席位 `+1`，失败队 `-1`，平时全零。达到 `max_decisions` 只设置 `truncated=True`，不设置自然终局或胜方，不伪造零价值和棋标签；训练器未来需要自行处理 bootstrap。步数包括选兵、额外操纵及防御选择。

截断后保留真实的下一决策席位和局面供 bootstrap 使用，但不再返回可提交候选，`step` 会拒绝继续推进；需要 `reset` 开始下一条采样。

## 观测边界

`schema_version=1`、`ruleset_version=base-1`。

- 棋盘、据点列表、队伍、出手顺序、先手与本轮争夺状态、轮次。
- 当前阶段和脱敏后的结算栈，包括步兵尚未行动的单位、攻击来源等公共上下文。
- 所有席位公开阵容、供应、移除区、袋/手/弃币数量、公开弃币。
- 查看者自己的手币计数、袋币计数、自己的弃币；不提供抽币顺序。
- 牧师强制币仅对其使用者公开；非决策者的合法候选为空。
- 不提供对手的隐藏手币、袋币构成、暗弃身份、随机种子和随机状态。

环境本身不维护每个策略的记忆。采集器应保存观测历史和 `public_action(code)`，并只把动作的公开部分广播给其他策略。原始编码包含暗弃支付币身份，**不可直接广播给其他策略**。`record_trace=True` 的完整日志也不能作为对弈输入。

这是不完全信息、带随机抽币的环境。内部快照、`clone()` 和回放是受信任工具；从真实快照直接搜索，会读取真实隐藏状态和未来随机流，不能把这种结果误称为公平策略表现。未来信息集搜索应按当前玩家知识重新采样隐状态。

## 紧凑数值观测

`env.observe_packed(seat)` 与字典观测共用信息边界，返回不可变 `PackedObservation`，无需 NumPy 或模型依赖。`schema_version=1`，可直接用 `numpy.frombuffer(..., dtype=uint8)` 读取三个字节区；这只是传输格式，不限定后续网络架构。

- `context`：查看席位、下一席位（自然结束为零）、先手席位、先手已转移标记、阶段编号、轮次、胜利目标、胜利队伍、卫队版本、人数、revision。
- `board`：按 `COORDS[1:]` 固定 47 行，每行 5 字节，依次为有效格/据点 bit flags（1/2）、据点队伍、单位所有席位、兵种、增援币数。双人未使用的外侧格有效标志为零。
- `players`：每席 69 字节，席位顺序同 `turn_order`。前四字节是队伍、袋/手/弃币数量；随后为 16 个阵容标志、16 个供应数、16 个移除数、17 个公开弃币数。
- `own`：17 个手币数、17 个袋币数、17 个自己的弃币总数。
- `pending`：每项为阶段编号、该选择的席位、起点、终点、可见币编号、零至两个剩余步兵位置。其他席位的强制抽币编号为零。
- `legal_action_codes`：仅当前查看者有权使用的候选。`truncated` 单列。

席位编号从 `turn_order` 的 1 开始；南/北队伍为 1/2；兵种/币、坐标使用模块常量表；阶段使用 `PHASES`。空值为零。玩家名、展示文本和已发生事件字符串不放进这些缓冲区，公共历史仍由采集器保存。

## 动作编码

`action_encoding_version=1`。候选为可放入 `uint64` 的整数，无 HMAC、字符串 JSON 或 HTTP 依赖。

| 位段 | 内容 |
| --- | --- |
| 0–4 | `OPS` 操作编号 |
| 5–9 | 支付币编号 |
| 10–15 | `src` |
| 16–21 | `dst` |
| 22–27 | `aux` |
| 28–32 | 招募/选兵编号 |

坐标表为 `COORDS=(None,*sorted(FULL_HEXS))`，币表为 `COINS=('',*KINDS,'royal')`；编号在双、四人之间相同。`decode_action` 可恢复语义。编码不是固定离散输出头的数组下标；建议以后对可变长度候选评分。批处理时为候选补齐长度，并另外提供 padding mask。可选项已经合法，不必再建立包含数十亿空槽的全空间 mask。

`aux` 在轻骑兵中是路径中点，在冲锋中是攻击目标，在指挥中是指挥者位置。不要用一个统一的“第二目标”解释其所有语义。

## 快照与回放

`backend.state.snapshot/restore/dumps/loads` 使用带版本的 JSON，包含全部币区、随机状态和结算栈；不用 pickle。`clone()` 复制所有可变状态和随机流，可用于调试、分支验证。修改导出的快照不影响原环境。

每条回放记录执行席位、完整语义动作、版本和状态摘要。重放逐步检查合法性、摘要及终局标签。摘要忽略展示文本，但涵盖随机状态和规则状态。跨规则版本不直接兼容。

网页对局同样在 SQLite 中记录初始状态和每个决策。结束后，已加入席位可以访问 `GET /api/v1/games/{id}/replay` 导出同一种回放格式；进行中返回 409。此前版本创建的旧存档，从升级时保存的局面开始记录后续回放。

## 性能路径

`WarChestEnv.step` 校验当前 revision 和合法候选，之后走内部执行路径，避免重复生成合法动作。`verify=True` 在每步增加完整不变量检查；验证过的批量模拟可关闭。观测、完整日志、状态摘要均按需生成；默认不记录展示事件、不记录轨迹，避免把 JSON 和历史复制塞进每步模拟。

一个实例由一个工作进程独占。CPU 并行使用多个独立进程和不同种子，进程之间批量传输采样；不要多线程同时修改同一个环境。当前没有假称可并行的批量封装，也没有额外模型依赖。
