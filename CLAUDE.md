# Claude Code 项目入口

本文件只作为兼容入口。任何 AI Agent 开始工作前，必须先完整阅读根目录的
[`AGENTS.md`](AGENTS.md)，再按其中的阅读顺序查看当前状态、架构、测试和风险文档。

当前 Git 基线版本为 `v1.0.0`。项目处于可本地运行的 MVP 3 原型阶段，已经包含单章 Loop、
人工审批、AI 自动修订/提交、多章生产线、Reference Pack、最小 Story Memory、正向故事工程和
反向拆解 P0。不要依据早期 `docs/01` 到 `docs/08` 中的历史结论判断当前实现。

必须保留的兼容性约束：

1. 不破坏 `POST /api/chapters/{chapter_id}/generate`。
2. 不删除旧 `WritingTask`、`GenerationRun`、`chapter_pipeline.py`。
3. 不覆盖或删除历史 `ChapterVersion`。
4. 所有模型调用和工作流步骤必须保留日志。
5. 模型 JSON 输出必须经过 Pydantic 校验，错误不得静默成功。
6. 数据库迁移和部署同步必须遵循 `AGENTS.md` 的数据安全规则。
