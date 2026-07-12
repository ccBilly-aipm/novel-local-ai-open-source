import { defineConfig } from "@playwright/test";

// 故事地图前端 E2E 冒烟。需要后端(:8000)与前端(:5173)已在运行；
// 详见 docs/AI_RUN_AND_TEST_GUIDE.md「故事地图 E2E」一节。
export default defineConfig({
  testDir: "./e2e",
  timeout: 60000,
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    // 前端地址可用 E2E_BASE 覆盖（避开部署副本占用的 :5173）。
    baseURL: process.env.E2E_BASE || "http://127.0.0.1:5173",
    headless: true,
  },
});
