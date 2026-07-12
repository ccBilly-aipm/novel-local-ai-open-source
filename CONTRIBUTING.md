# Contributing to Novel Local AI

感谢你改进 Novel Local AI。这个项目优先保证本地数据安全、版本可追溯和旧流程兼容，功能数量排在这些约束之后。

## 开始之前

1. 阅读 `AGENTS.md`、`PROJECT_HANDOFF.md` 和与改动相关的测试。
2. 在 Issue 中说明问题、预期行为和最小改动范围。
3. 不要上传用户小说正文、模型权重、数据库、日志、API Key 或本机绝对路径。
4. 大型架构改动请先讨论；优先提交小而可验证的 PR。

## 本地开发

```bash
cd services/api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
alembic upgrade head

cd ../../apps/web
npm install
```

## 提交前验证

```bash
cd services/api
.venv/bin/pytest

cd ../../apps/web
npm run build

cd ../..
git diff --check
git ls-files | rg '(\.db($|-)|\.sqlite|\.env($|\.)|\.log$)'
```

当前没有浏览器 E2E。涉及审批、自动提交、恢复或模型配置的 PR，请在描述中列出手动回归步骤。

## PR 要求

- 解释用户可见变化、数据库影响和回滚方式。
- 新增行为应有测试；修复 bug 时优先先补失败用例。
- 数据模型变化必须有 Alembic migration，不要只依赖 `create_all()`。
- 不破坏旧 `POST /api/chapters/{chapter_id}/generate`。
- 不删除或原地改写历史 `ChapterVersion`。
- 所有模型调用和工作流步骤继续保留审计日志。
- 结构化模型输出继续经过 Pydantic/JsonGuard。

## 许可证

提交 Contribution 即表示你有权提交该内容，并同意其按 Apache License 2.0 发布。不要复制许可证不兼容或来源不明的第三方代码。
