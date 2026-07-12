# 故事地图前端交付报告（阶段 2）

> 分支：`feat/story-map-ui`（接在 `feat/story-map-api` 之后）｜ 工单来源：`docs/34_story_map_master_plan.md` §6.2
> 技术域：React 18 + TS + Vite + Tailwind + D3（模块化按需引入）。

## 1. 新增 / 改动文件树

```
apps/web/src/features/storymap/
  StoryMapPage.tsx        页面壳：四视图 tab + 主画布 + 常驻详情面板 + 图例 + 提取入口
  SelectionContext.tsx    全局联动状态（hovered/selected），切 tab 保留 selected
  useStoryMapData.ts       GET /novels/{id}/story-map 数据 hook + refetch
  useZoom.ts               d3-zoom 行为封装（缩放/平移/双击复位）
  theme.ts                 8 色人物色板 + 5 色关系色 + viz 状态色 + EntityRef 类型
  TimelineView.tsx         V1 时间线（章节主轴 + 伏笔弧线 + 叙事/故事双模式）
  CharacterGraphView.tsx   V2 人物力导向图（半径∝出场、主角六边形环、章节滑块回放）
  ThreadWeaveView.tsx      V3 织线图（泳道网格 + curveMonotoneX 连线 + 伏笔菱形）
  StatsDashboard.tsx       V4 仪表盘（字数柱线/连续性趋势/伏笔计数环/出场热力图）
  DetailPanel.tsx          常驻右侧详情面板（摘要 / 实体卡 + 内联编辑 + 删除 + 跳转）
  EntityForm.tsx           事件/情节线/伏笔通用表单（POST 新建 / PATCH 编辑）
  ManualAddMenu.tsx        「＋手动添加」下拉
  ExtractDialog.tsx        AI 提取对话框（范围/Provider → 轮询进度 → 候选接受/忽略/批量）
  Legend.tsx / EmptyState.tsx  图例行 / 空态引导卡
apps/web/e2e/storymap.spec.ts   Playwright 冒烟
apps/web/playwright.config.ts
```

改动：`App.tsx`（projectViews +storymap）、`ProjectWorkspaceShell.tsx`（tab「故事地图」在「章节」后 + 渲染）、
`types.ts`（故事地图类型）、`index.css`（E2 光晕过渡）、`tailwind.config.js`（viz 语义色）、
`vite.config.ts`（VITE_API_TARGET 代理覆盖）、`package.json`（d3 依赖 + e2e 脚本）。

## 2. 技术选型落实

- 新依赖仅限 D3 模块化：`d3-selection / d3-zoom / d3-force / d3-scale / d3-shape / d3-array`（精确版本，见 package.json）
  + 对应 `@types/*`。未引入 ECharts / 路由库 / 状态库。bundle 从 96KB → 131KB gz（D3 约 +35KB gz，符合预期）。
- D3 只负责 zoom 行为 / force 仿真 / 比例尺 / 路径生成器；DOM 由 React JSX 出 SVG，force tick 更新坐标 state。

## 3. 每视图完成度

| 视图 | 完成 | 说明 |
|---|---|---|
| V1 时间线 | ✅ | 章节等距主轴、同章纵向堆叠、按第一人物着色、伏笔埋设→回收贝塞尔弧（未回收虚线/超期红）、叙事/故事双模式、未锚定泳道、zoom |
| V2 人物网络 | ✅ | d3-force、半径∝√出场、主角六边形环、边按关系类型着色、悬停一跳邻居高亮其余淡出、底部章节滑块回放、unmatched 提示、zoom |
| V3 织线图 | ✅ | 泳道网格（thread 行 + 独立伏笔行）、curveMonotoneX 结点连线、resolved 线淡化延伸、伏笔菱形按状态着色、悬停列头淡金条 + 联动、zoom |
| V4 仪表盘 | ✅ | 字数柱+移动平均、连续性分数折线（空态文案）、伏笔计数环（超期红）、人物×章节热力图（点格跳人物网络） |
| 详情面板 | ✅ | 无选中显示统计摘要 + 伏笔健康度；选中显示实体卡 + 关联 chips（点击跳转）+ 内联编辑（PATCH）+ 删除（二次确认） |
| 提取 UI | ✅ | 范围（全部/自选）、Provider 选择、进度条轮询、候选按类型分组显示 confidence/evidence、单条接受/忽略 + 「全部接受高置信≥0.7」 |
| 空态 | ✅ | 无任何事件/线/伏笔/关系时画布区显示引导卡（AI 提取主按钮 + 手动添加），不显示空坐标系 |

## 4. 联动矩阵（hover/click X → 高亮哪些视图的什么）

- hover **人物**（V2/详情）→ 时间线高亮该人物的事件点；人物网络高亮其一跳邻居。
- hover/click **章节**（V1 轴/V3 列头）→ V3 该列淡金背景条 + SelectionContext 广播。
- click **事件/情节线/伏笔** → 右侧详情面板渲染实体卡，关联 chips 可点击跳到对应视图并选中。
- 热力图点格 → 选中该人物 + 跳人物网络视图。
- 切 tab 保留 selected（联动状态跨 tab 保留）。

## 5. 构建与 E2E 结果

- `npm run build`（tsc --noEmit + vite build）：0 错误。
- 后端回归 `pytest`：80 passed（前端任务未碰后端）。
- Playwright E2E（`apps/web/e2e/storymap.spec.ts`）：**通过**——四视图切换、SVG 有节点、hover/click、提取对话框可开。
  在独立端口（前端 :5199 → 后端 :8099）跑，避开本机部署副本占用的 :5173/:8000（详见运行与测试指南）。
- 四视图真机截图已人工核对（时间线/人物网络/织线图/仪表盘均正确渲染，暖纸质主题一致）。

## 6. 性能实测（造数脚本）

200 章 / 50 人物 / 300 事件 / 20 情节线下的首屏渲染：时间线 149ms、人物网络 592ms（含力仿真收敛）、
织线图 28ms、仪表盘 55ms。SVG 完全扛得住该量级，印证「D3 自绘 + SVG，不引入 canvas/ECharts」的选型。

## 7. 视觉与对比度

- 全程沿用 `.panel/.label/.btn/bg-paper/moss/ink` token，未改全局主题。
- 新增语义色写进 tailwind：`viz.open`(#b45309)/`viz.resolved`(#38564a)/`viz.overdue`(#b3261e)。
- 人物 8 色板均为深色调，纸底（#ebe5d9/#f5f1e8）上标签文字对比度 ≥4.5:1、大图形元素 ≥3:1；
  节点内白字 + 深色填充保证可读。空态/加载态/错误态三态齐全，出错给 refetch 重试。

## 8. 已知限制与回滚

- 未引入 `d3-transition`：双击复位为即时（CSS transition 承担节点光晕/淡出的平滑感），排列切换用 CSS 过渡。
- resolved thread 的「回收后变淡」用一段淡色虚线延伸示意，非逐段裁剪（务实近似）。
- 回滚：分支 `feat/story-map-ui` 各 T* 一笔 commit，`git revert` 即可；纯前端 additive（新页面 + 新依赖 + 路由 tab），不改既有页面行为。
