# MVP 验收记录

验收日期：2026-06-11

## 自动化

- 后端：`pytest`，2 项通过。
- 覆盖：项目/小说/角色/世界规则/章节 CRUD、上下文预览、OpenAI-compatible 模拟模型、
  串行生成、自动摘要、审稿、GenerationRun、CanonState 和 Markdown 导出。
- 前端：`npm run build` 通过。
- 依赖：`npm audit --audit-level=moderate` 为 0 个已知漏洞。

## 真实本地模型

使用本机 llama.cpp：

```text
Base URL: http://127.0.0.1:18081/v1
Model: qwen2.5-coder-0.5b-q4km
```

验证结果：

- Provider 测试成功，响应 `OK`。
- 真实章节生成任务完成。
- 自动章节摘要任务完成。
- 两次调用均保存 prompt、response、tokens、耗时与状态。
- 小输出预算导致 JSON 截断时，系统能提取已完成的 `summary` 字段；自动摘要现使用独立
  `max_tokens >= 384`，避免继承章节生成的极小输出限制。

该 0.5B coder 模型仅用于接口闭环，不代表小说质量建议。实际写作应配置更适合中文叙事、
且上下文窗口与输出预算匹配的 GGUF 模型。

## 浏览器验收

在本地 Web UI 中完成：

- 创建项目与小说。
- 创建章节，填写目标、大纲和人工正文并保存。
- 创建角色卡与 JSON 当前状态。
- 查看上下文预览。
- 查看并测试 llama.cpp provider，页面返回成功状态。
- 浏览器控制台无 warning/error。

## 本地模型盘点

模型设置页包含动态“本地模型中心”，扫描 GGUF、Ollama manifests、MLX 与 Hugging Face
缓存，并显示：

- 当前实际运行的模型。
- 已安装、运行中、辅助模型和未完成下载。
- 针对 64GB Apple Silicon 的用途建议与参数建议。
- 推荐模型的一键 Provider 配置草案。

2026-06-11 本机盘点结论：当前运行 Qwen2.5-Coder-0.5B Q4_K_M；正式章节写作优先使用
已安装的 Ollama `qwen3.5:27b` Q4_K_M；完整的 MLX Qwen3 8B 权重适合摘要与状态任务，
但需要先安装并启动 MLX-LM 服务。
