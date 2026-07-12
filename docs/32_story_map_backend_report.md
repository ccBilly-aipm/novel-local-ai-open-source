# 故事地图后端交付报告（阶段 1）

> 分支：`feat/story-map-api` ｜ 工单来源：`docs/34_story_map_master_plan.md` §6.1
> 范围：只做后端——故事地图数据接口 + AI 提取管线。不碰前端页面。

## 1. 设计要点

可视化的**数据地基已存在**（`TimelineEvent` / `PlotThread` / `Foreshadowing` /
`Character.relationships_json` / `CanonState`），本阶段补齐三样东西：

1. **读接口**：一次拉齐聚合 payload（解析后数组，前端拿到即用）+ 少量手动 CRUD。
2. **数据填充管线**：AI 逐章提取 → staging → 人工接受（机制照抄 `story_engineering` /
   `deconstruction` 的 `staged_*` record_type 模式）。
3. **一次 additive migration**：给 `TimelineEvent` 加可空 `story_order`，并在**新** record_type
   的接受逻辑里修复旧路径丢关联的缺陷（旧行为完全不动）。

## 2. 新增接口清单

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/novels/{novel_id}/story-map` | 聚合读：chapters / characters / timeline_events / plot_threads / foreshadowing / relationships / unmatched / stats |
| GET/POST/PATCH/DELETE | `/api/novels/{id}/timeline-events`、`/api/timeline-events`、`/api/timeline-events/{id}` | 时间线事件手动 CRUD |
| GET/POST/PATCH/DELETE | `/api/novels/{id}/plot-threads`、`/api/plot-threads`、`/api/plot-threads/{id}` | 情节线手动 CRUD |
| GET/POST/PATCH/DELETE | `/api/novels/{id}/foreshadowing`、`/api/foreshadowing`、`/api/foreshadowing/{id}` | 伏笔手动 CRUD |
| POST | `/api/novels/{id}/story-map/extract` | AI 提取：入队后台逐章提取，返回 run（202） |
| GET | `/api/novels/{id}/story-map/extract-runs`、`/{run_id}` | 提取进度轮询 |

候选的**列表/接受/拒绝/恢复复用既有 story-engineering 接口**
（`/novels/{id}/story-engineering/candidates`、`/story-engineering/candidates/{id}/accept|reject|restore`），
record_type 为 `staged_storymap_event` / `_relationship` / `_thread` / `_foreshadow`。

## 3. 关键实现

### T1 迁移
- `TimelineEvent.story_order`（可空 Integer）；`TimelineEventOut` 同步加字段。
- 新表 `story_map_extract_runs`（镜像 `deconstruction_runs`）。
- migration `d4e5f6a7b809`（revises `b2c3d4e5f6a7`），只 add_column + create_table，配 downgrade；
  已在一次性 DB 验证 upgrade head 与 downgrade -1，旧数据不受影响。

### T3 聚合与归一化
- `relationships[]` = 全体 `Character.relationships_json` 归一化为
  `[{source_id,target_id,type,description,mutual}]`：key 精确匹配现有人物 name → 取 id；
  匹配不到进 `unmatched[]`（原样返回，不丢不猜）；值为字符串 → `type=other`，值为对象 → 取
  type/description；type 不在 `family/ally/enemy/romance/other` 一律折入 other（原类型留描述）。
- `presence_chapters`：从 `ChapterOutline.character_ids_json` + `TimelineEvent.character_ids_json`
  聚合去重升序。
- `stats.foreshadow_counts.overdue`：planted 章距最新已提交章 > 20 且未回收。
- 空小说各字段空数组，HTTP 200。

### T4 提取管线
- `StoryMapExtractRunner` + `story_map_extract_queue`（进程内线程队列，`recover_pending` 孤儿清理）。
- 逐章：`get_adapter().generate_text`（低温度 0.2）→ `JsonGuard + StoryMapExtractionOutput`
  → 写 staging（带 chapter_id 锚点 + confidence/evidence）；每章记 `CreativeRun` 审计。
- 单章失败记录后继续下一章，最终标 `error_code=PARTIAL`；无模型服务时**优雅失败**（见冒烟）。
- 提取 prompt 注入 `known_characters` / `known_threads`，防止重复创建同名线/人物。

### T4.4 接受逻辑（新路径修复丢关联）
- event → `TimelineEvent`：character_names 精确匹配 → 正确写 `character_ids_json`（匹配不到留描述尾部
  「（涉及：…）」）；chapter 锚点写 `chapter_id`；story_order 写入。
- relationship → 更新源人物 `relationships_json`，value 统一写对象 `{type,description}`（读侧兼容字符串）。
- thread → 同名则 append 章节锚点到 `related_chapter_ids_json`（去重），否则新建。
- foreshadow → planted 新建（planted_chapter_id=锚点）；resolved 在未回收伏笔中按 description
  包含匹配，命中则置 resolved+resolved_chapter_id，找不到则新建已回收记录并在 notes 注明。

## 4. 测试结果

- 后端 `pytest`：**基线 70 → 现在 80**（新增 `tests/test_story_map.py` 10 个用例），全绿。
- 覆盖：story_order 往返、CRUD+404、聚合归一化/presence/overdue/空小说 200、提取合法/非法 JSON
  （staging 落库 + CreativeRun 审计 + 非法走失败语义）、accept 各新 record_type（名字→id 解析、
  同名 thread 合并、伏笔回收匹配）。
- 前端 `npm run build` 仍通过（本阶段未动前端，等价回归）。

## 5. 冒烟结果（uvicorn + httpx，对已迁移的一次性 DB）

- `GET /story-map` 返回 200 与完整字段（空小说）。
- 三实体 CRUD POST 均 201。
- `POST /story-map/extract`（provider 指向不可达端口）→ run 优雅失败：`status=completed`、
  `error_code=PARTIAL`、`processed=1/1`、`candidates=0`，run.error 记录 `503`——**不崩溃、留失败记录**
  （本身就是一个验收点）；随后聚合 GET 仍 200。

## 6. 数据库影响与回滚

- migration revision `d4e5f6a7b809`；回滚方式：`alembic downgrade -1`（一次性库）或以备份恢复用户库。
- 纯 additive：新列可空、新表、新路由、新文件；无既有字段/接口重命名或删除。

## 7. 已知限制与决策

- `story_time` 仍是自由文本不参与排序；排序主轴用章节 order_index + 可空 `story_order`（方案意图）。
- overdue 阈值 V1 定死 20 章（`OVERDUE_GAP`），不做配置（方案 §7.3 未决小项）。
- relationship 接受时若**源人物不存在**，不臆造新建人物，返回提示保留候选信息（先落数据、不丢、可撤销原则）。
- 提取为逐章串行（未做并发/分块）：单章 60000 字截断输入；符合「先打通、可靠优先」。
