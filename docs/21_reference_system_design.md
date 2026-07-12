# Reference System 设计

## 1. 目标

让用户显式选择生成参考，而不是把整本小说正文加入上下文。

## 2. 优先级

- P0：章节、章节版本。
- P1：角色、世界规则、选中文本。
- P2：伏笔、风格样本、用户笔记。

本轮只实现 P0。

## 3. 数据模型

`ReferencePack` 保存一次 Run 的引用快照。P0 使用 JSON items，避免过早增加多张表。

每项包含：

```json
{
  "reference_id": "chapter-or-version-id",
  "type": "chapter",
  "title": "第 2 章",
  "reason": "参考战斗节奏",
  "summary": "已有章节摘要",
  "selected_excerpt": "受预算裁剪的片段",
  "constraints": ["不得改变已确认时间线"],
  "source_version_id": null,
  "token_estimate": 500
}
```

## 4. 构建规则

1. 验证引用对象属于当前 project/novel。
2. 章节优先使用 `Chapter.summary`；没有摘要时最多截取有限正文。
3. 版本使用指定不可变 `ChapterVersion` 的有限片段。
4. 记录来源 ID、标题、目的、内容 hash 和 token estimate。
5. Context Builder 只加载本次 `ReferencePack`，不扫描全部章节全文。
6. Reference Pack 使用独立预算，超长时按用户选择顺序裁剪。

## 5. API

```text
GET  /api/projects/{project_id}/references/search?q=
POST /api/projects/{project_id}/reference-packs
GET  /api/projects/{project_id}/reference-packs/{pack_id}
```

新单章自动入口也可内联提交 reference selections，后端先生成 Pack 再创建 Run。

## 6. 前端

- 输入 `@关键词` 搜索章节和版本。
- 选择后以 chip 展示。
- chip 可填写参考目的并可移除。
- 启动前显示引用类型、标题和估算 token。

P0 不实现富文本光标级 mention；使用明确的搜索输入和 chip，避免重写编辑器。
