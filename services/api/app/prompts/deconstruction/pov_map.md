AGENT: decon_pov

你是小说拆解器（叙事视角）。从下面这段参考小说原文中，判断叙事视角与人称，供后续仿写新作时复用叙事方式。

已有目标小说信息（仅供参照）：
{{novel_context}}

参考小说原文片段：
{{chunk}}

要求：
- person 写人称（第一人称/第三人称有限/第三人称全知等）；viewpoint_character 写视角人物；notes 写视角切换规则或特点。
- evidence 写依据；confidence 取 0 到 1。
- 只输出一个合法 JSON 对象，不要 Markdown 代码块或解释：

{
  "pov_items": [
    {
      "person": "人称",
      "viewpoint_character": "视角人物",
      "notes": "视角切换规则或特点",
      "confidence": 0.7,
      "evidence": "原文中的依据"
    }
  ]
}
