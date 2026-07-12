# 阶段 3 交付报告 —— 云模型接入（DeepSeek / 小米 MiMo / MiniMax / SiliconFlow）

> 分支：`feat/cloud-model-presets` ｜ 工单来源：`docs/34_story_map_master_plan.md` §6.3
> 目标：在「设置 → 模型」里两下接入四家云服务，同时不改变「本地优先」立场。

## 1. 改动文件清单

| 文件 | 改动 |
|---|---|
| `services/api/app/providers/adapters.py` | `OpenAICompatibleAdapter` 的 `generate_text` / `generate_text_stream` 支持 `token_param` 可选键；`LMStudioAdapter` / `KoboldCppAdapter` 自建 payload 分支主动 pop 掉该键防泄漏 |
| `services/api/tests/test_adapter_token_param.py`（新增） | 两个用例：缺省=旧行为、`token_param="max_completion_tokens"` 时改名 |
| `apps/web/src/components/ModelSettings.tsx` | 预设 key 与 provider_type 解耦；新增四个云端预设 + 「云端服务」分组；模型 datalist、DeepSeek 旧名警告、Key 安全提示、MiniMax token_param |
| `README.md` | 新增「云端 API（可选）」小节（四行表 + 定位） |
| `docs/USER_GUIDE.md` | §4 新增「云端 API（可选）」小节 |
| `CHANGELOG.md` | 新增 1.1.0 目标条目（云端预设 + token_param） |

## 2. 关键实现

### T1 adapter `token_param`（additive，零回归）
- `token_param = str(settings.pop("token_param", "max_tokens") or "max_tokens")`，payload 中用该名装
  `max_tokens` 的值；`token_param` 本身被 pop，不进入请求体。
- **默认路径**（未设 `token_param`）→ key 仍为 `"max_tokens"`，payload 与旧行为逐字节一致。
- MiniMax 已弃用 `max_tokens`，预设内置 `token_param: "max_completion_tokens"`，无需用户干预。

### T2 前端预设（最易犯错点已规避）
- 预设结构新增 `providerType` / `cloud` / `defaultModel` / `suggestedModels`；表单新增 `presetKey`
  字段，与后端 `provider_type` 彻底解耦。
- **发给后端的 `provider_type` 一律是既有合法值**：四个云端预设都映射 `cloud_openai_compatible`，
  不新增后端 `provider_type`，不动 `get_adapter()` 分发——冒烟已验证四家均落库正确、不抛
  `Unsupported provider type`。
- 已有 Provider 反推所属预设：优先按 `base_url` 精确匹配云端预设，匹配不到退回 `provider_type`。
- DeepSeek 旧模型名（`deepseek-chat` / `deepseek-reasoner`）+ base_url 命中 `api.deepseek.com` → 表单内联红字警告。
- 模型输入框 `<datalist>` 提供主力/便宜两档建议；API Key 输入框下「仅存本机、勿分享」提示。

### T3 文档
- README / USER_GUIDE 均新增「云端 API（可选）」小节，四家 base_url / 模型 / 拿 Key 入口，强调本地优先。

## 3. 测试结果

- 后端 `pytest`：**基线 70 → 现在 72**（新增 2 个 token_param 用例），全绿。
- 前端 `npm run build`（tsc --noEmit + vite build）：0 错误。

## 4. 冒烟结果

- 通过 TestClient 模拟前端提交：四个云端预设建 Provider 均落库
  `provider_type=cloud_openai_compatible`，模型名默认值正确。
- 无 Key 的「测试连接」对 MiniMax 返回 `ok=False` + 真实 `401 Unauthorized`（HTTP 200 包裹，未崩溃）。
- **真机验证**：本会话未提供任何真实 API Key，故未做真机「测试连接 + 20 字生成」；上述为无 Key 的
  优雅失败验证。用户填入真实 Key 后可自行在页面「测试真实生成」验收。

## 5. 已知限制

- 各家 JSON mode / `response_format` 行为差异未逐一验证——本项目 JSON 靠提示词约束 + `JsonGuard`，
  写作主链路不依赖 `response_format`，不阻塞。
- MiMo 多轮工具调用官方 bug（issue #44）：本项目为纯文本补全 + JSON，不受影响（预设备注已写明）。
- Key 仍明文存本地 SQLite（既有事实，README 已声明）；Keychain 迁移是 roadmap 独立事项，本阶段不做。

## 6. 回滚方式

- 分支 `feat/cloud-model-presets` 两笔提交：`git revert` 任一或两笔即可。
- 无 migration、无 schema 变化、无数据库影响；纯 additive（adapter 可选键 + 前端预设 + 文档）。
