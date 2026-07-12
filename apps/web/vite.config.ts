import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// API 代理目标默认 :8000；可用 VITE_API_TARGET 覆盖（E2E 用独立端口时用得上）。
// 经 process.env 读取；此处不依赖 @types/node，用最小声明避免引入额外类型依赖。
declare const process: { env: Record<string, string | undefined> };
const apiTarget = process.env.VITE_API_TARGET || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": apiTarget,
    },
  },
});
