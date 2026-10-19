# War Chest 后端 → 前端视图协议 v1

当前实现为基础版双人/四人服务。2026-10-18 扩展字段与入口如下；既有视图结构继续兼容。

- `GET /api/v1/rules`：16 兵种名称、能力说明、棋币数和规则版本。
- `POST /api/v1/dev/games`：可选 `setup`（recommended/random/draft/gaugamela/bannockburn/crecy）、`player_count`（2/4）、`seed`、`rosters`、`initiative`、`draft_first`、`royal_guard_version`（默认 original）。返回全部席位的 `join_urls`。
- `GET /api/v1/games/{id}/replay`：已加入席位在自然终局后导出完整私有回放；进行中 409。
- `GameView` 增加 `ruleset_version`、`viewer_team_id`、`winner_team_id`、`player_count`；`PlayerView` 增加 `team_id`、`is_ally`，单位增加 `team_id`。`owner_id` 在单位上表示具体席位，在据点上表示队伍；渲染时不能混用。
- 四人席位为 south/north/south2/north2，队伍为 south/north；以 `winner_team_id` 解释胜利。旧的 `winner_player_id` 保留同一队伍标识供旧双人客户端兼容。
- 阵容项增加只作展示的 `description`。新动作标签/分组由服务器下发，选兵和额外行动不需要手牌也能提交。
- SQLite 在同一事务内写入局面和动作日志，成功后才替换内存状态。缓存以 revision 失效。当前本地服务仅使用一个服务工作进程；多进程模拟使用独立的 `WarChestEnv`。
- 游戏 Cookie 和席位记录会恢复；数据库路径可由 `WARCHEST_DB` 指定，默认 `backend/data/games.sqlite3`。

后端必须提供**当前授权玩家**可见的展示快照，不允许前端获得完整 `GameState` 后自己删字段。参考 `src/types.ts` 的全部数据类型。

## GET `/api/v1/games/{game_id}/view`

- 认证：服务端 Session Cookie；`credentials: include`；鉴权失败 `401`/`403`。
- 数据：`GameView` 顶级对象，`schema_version=1`、`game_id`、递增 `revision`、`ruleset_label`、`status`、`winner_player_id`、`viewer_player_id`、`decision_player_id`、`initiative_player_id`、`round`、`phase_label`、`instruction`。
- `board: HexView[]`：仅有效/明确标注为blocked的格子。每格拥有引擎提供的稳定 `id`, `q`, `r`, `terrain`, `owner_id`, `unit`。`q,r` 仅用于 SVG 坐标渲染，不能作为游戏规则坐标计算的依据。
- `players: PlayerView[]`：双方公开资料、控制数、单位名录与公开总数（包括 `board_unit_count`，由后端权威计算）。不可知的资源数量请给 `null`，不要传隐藏对象。
- `hand: HandCoinView[]`：**当前授权玩家**的可见手牌；每枚有唯一展示ID。对手手牌只通过公开的 `hand_count` 表示。
- `legal_actions: ActionView[]`：引擎针对**当前查看者**生成的全部合法选项（不是根据全局状态把“敌方合法动作”也发过来），非己方决策时应为空数组。每个动作的 `id` 是不透明令牌；`payment_coin_type`、`source_hex_id`、`target_hex_ids`、`highlight_hex_ids` 只作展示和筛选；不用于裁判。
- `events: GameEventView[]`：后端按隐私规则裁剪的公开游戏事件。
- 响应必须 `Cache-Control: no-store`。

## POST `/api/v1/games/{game_id}/actions`

请求：

```json
{ "action_id": "opaque-server-action-token", "expected_revision": 42 }
```

响应成功：

```json
{ "view": { "schema_version": 1, "game_id": "g-1", "revision": 43, "...": "完整GameView其他字段" } }
```

注意：示例中的 `...` 只是文档占位符，实际响应必须包含所有 `GameView` 必填字段。

后端应在事务内完成以下检查：

1. 检查调用者登录身份和对局席位。
2. 检查本局确实仍可行动，且当前 `decision_player_id` 与会话身份一致。
3. `expected_revision` 与实际版本严格一致，否则 `409`，状态不变。
4. `action_id` 必须在该玩家、该局面版本对应的引擎 `legal_actions` 内，绝不相信前端 `source/destination` 或支付类型。
5. 在服务端执行整个状态机步骤，处理抽币、自动事件、强制决策与胜负。
6. 原子性写入新状态和递增版本，重新生成**脱敏** `GameView` 并作为响应。
7. `POST` 需防CSRF（例如SameSite严格Cookie、Origin/CSRF令牌检查），并配合正确的服务端权限检查。

## 前端只做呈现

- 点击棋币：在**后端已返回**的 `legal_actions` 中按 `payment_coin_type` 切换列表可视范围。
- 点击格子：高亮格子、展示该格子现有视图信息，以及与之关联的服务器已给的行动候选。
- 点击具体行动：记下已有不透明ID。
- 点击执行：发送 `action_id`、`expected_revision`，只在后端成功返回后换局面。
- 服务器决定合法动作的起点、目标高亮和阶段标题；UI不要凭兵种、距离、方向、牌数推导合法性。
- 不假定轮流行动。战术子步骤和防守选择都由后端作为新的 `decision_player_id` 和 `legal_actions` 返回。
- 后端未提供的字段、规则或能力，UI只能显示“未知/等待”，不能补全逻辑。

## 强制验收

- **无规则代码**：在 `src/` 中检查不得出现决定移动/攻击/抽币/终局/先手的计算逻辑。
- **隐私**：用两个不同玩家账号分别访问同一个game，抓包核实两份视图未包含对方隐藏手牌、暗弃币、真实袋中顺序，不能仅视觉遮挡。
- **并发**：模拟同时请求和网络乱序、双击执行、409冲突，前端不得展示比已接收版本更旧的状态，也不应重复提交。
- **动作完整**：所有来自后端的合法动作都能按其ID显示、被选中并提交，不应该依靠硬编码兵种或9种行动枚举过滤未知的新类型。
- **阶段**：骑兵复合战术、牧师抽币、皇家卫队防御抉择、步兵双操纵等全部由后端提供中间视图和新Action IDs；验证前端无需改规则逻辑。
- **演示模式**：离线静态模式不会调用POST且UI明确显示“静态预览”。连接失败也不会悄悄回退到演示棋局。
- **回放**：后端同一revision必须向相同玩家返回稳定、完整、可重建的视图。
- **浏览器**：桌面Chrome和移动宽屏均能显示棋盘、手牌、行动列表，SVG坐标与点击目标一致。
