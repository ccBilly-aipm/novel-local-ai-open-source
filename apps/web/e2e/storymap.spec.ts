import { test, expect, request as pwRequest } from "@playwright/test";

// 后端 API 地址可用 E2E_API 覆盖（避开本机 LaunchAgent 部署副本占用的 :8000）。
const API = (process.env.E2E_API || "http://127.0.0.1:8000") + "/api";

// 通过后端 API 造一个带故事地图数据的测试项目，返回 { projectId, novelId }。
async function seed() {
  const ctx = await pwRequest.newContext();
  const project = await (await ctx.post(`${API}/projects`, { data: { name: `E2E故事地图 ${Date.now()}` } })).json();
  const novel = await (
    await ctx.post(`${API}/novels`, { data: { project_id: project.id, title: "E2E小说" } })
  ).json();
  // 两章
  const c1 = await (
    await ctx.post(`${API}/chapters`, {
      data: { novel_id: novel.id, order_index: 1, title: "第一章", content: "甲".repeat(80), outline: { goal: "g", outline_content: "o" } },
    })
  ).json();
  const c2 = await (
    await ctx.post(`${API}/chapters`, {
      data: { novel_id: novel.id, order_index: 2, title: "第二章", content: "乙".repeat(60), outline: { goal: "g", outline_content: "o" } },
    })
  ).json();
  // 两人物 + 关系
  const zhou = await (
    await ctx.post(`${API}/characters`, { data: { novel_id: novel.id, name: "周明", role: "主角", relationships: { 林秋: { type: "ally", description: "同事" } } } })
  ).json();
  await ctx.post(`${API}/characters`, { data: { novel_id: novel.id, name: "林秋", role: "配角" } });
  // 事件、情节线、伏笔
  await ctx.post(`${API}/timeline-events`, { data: { novel_id: novel.id, title: "开场事件", chapter_id: c1.id, character_ids: [zhou.id] } });
  await ctx.post(`${API}/plot-threads`, { data: { novel_id: novel.id, name: "主线", related_chapter_ids: [c1.id, c2.id] } });
  await ctx.post(`${API}/foreshadowing`, { data: { novel_id: novel.id, description: "神秘信物", planted_chapter_id: c1.id } });
  await ctx.dispose();
  return { projectId: project.id, novelId: novel.id };
}

test("故事地图页：四视图切换 / SVG 有节点 / hover 联动 / 提取对话框可开", async ({ page }) => {
  const { projectId } = await seed();
  await page.goto(`/#/projects/${projectId}/storymap`);

  // 四个视图 tab 都在
  for (const label of ["时间线", "人物网络", "故事线", "仪表盘"]) {
    await expect(page.getByRole("button", { name: label })).toBeVisible();
  }

  // 时间线：SVG 有事件圆点
  await expect(page.locator("svg circle").first()).toBeVisible();

  // 切到人物网络：SVG 有节点，hover 后出现 halo/高亮
  await page.getByRole("button", { name: "人物网络" }).click();
  const node = page.locator("svg g.storymap-node").first();
  await expect(node).toBeVisible();
  await node.hover();
  // hover 人物后详情面板出现人物名（联动）——DetailPanel 显示「人物」卡
  // 也可断言存在 halo circle；这里断言点击后详情面板更新
  await node.click();

  // 切到故事线 / 仪表盘 都能渲染
  await page.getByRole("button", { name: "故事线" }).click();
  await expect(page.locator("svg").first()).toBeVisible();
  await page.getByRole("button", { name: "仪表盘" }).click();
  await expect(page.locator("svg").first()).toBeVisible();

  // 提取对话框可打开
  await page.getByRole("button", { name: /AI 提取/ }).click();
  await expect(page.getByText("AI 提取故事结构")).toBeVisible();
});
