# 产品路线

## MVP / V0.1

- 本地 Web UI、项目/小说/章节/角色/世界规则 CRUD
- 小说总纲、章节目标与正文编辑
- 模型 provider 配置、连接测试和统一生成接口
- SQLite 串行 WritingTask 队列，失败可重试，等待任务可暂停
- Token 预算上下文构建器
- 章节生成、摘要、人物状态建议、轻量审稿
- GenerationRun 全记录与 Markdown 导出

验收核心：不依赖云服务，使用本地 HTTP 模型完成至少两章连续生成，第二章 prompt 包含
第一章人工确认后的正文摘要。

## V0.2

- 场景大纲编辑器与按场景生成
- 地点、时间线、剧情线、伏笔的完整 CRUD
- 上下文命中解释与手动钉选
- prompt 版本回滚、provider 参数预设
- 生成中取消（需要 provider 流式请求和连接中断）
- SQLite migration、macOS Keychain 密钥存储、自动备份
- 导入结构明确的 Markdown/TXT 项目

## V0.3

- Tauri 桌面封装、安装包和本地服务生命周期管理
- 流式生成、差异对比、章节版本历史
- 批量章节任务与可恢复队列
- 更完整的一致性检查和结构化状态确认界面

## 未来 RAG

先用章节摘要、角色和规则做 baseline。只有当真实项目证明显式上下文召回不足时，再加入
Chroma、LanceDB 或 FAISS。检索单元优先使用“场景/事件卡”，而不是任意字符切块；界面必须
显示召回来源并允许作者排除错误记忆。

## 未来 GraphRAG

在时间线、人物关系和事件查询已经形成稳定 schema 后，再评估 Kuzu、NetworkX 或其他图
存储。GraphRAG 只应服务明确问题，例如“角色 A 在当前时间点知道哪些事实”，不应成为默认
生成链路的强依赖。

## 未来多 Agent

可增加独立的连续性、节奏、角色声音和事实核查 reviewer。各 reviewer 只产生结构化建议，
由用户选择是否进入 revision。自动修订必须保存 patch 和新版本，不能覆盖原稿。

## 未来 Tauri

Web 工作流稳定后封装 Tauri。桌面层负责启动/停止 FastAPI、选择数据目录、Keychain、
自动更新和日志收集；React 业务组件保持不变。
