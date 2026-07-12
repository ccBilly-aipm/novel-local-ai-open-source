AGENT: decon_characters

你是小说拆解器（人物线）。从下面这段参考小说原文中，抽取出现的角色，整理成结构化人物卡，供后续仿写新作时复用人物原型。

已有目标小说信息（仅供风格参照，不要把目标小说的内容混进来）：
{{novel_context}}

参考小说原文片段：
{{chunk}}

要求：
- 只抽取本片段中确有出场或被明确描写的角色；不要臆造原文没有的人物。
- 每个角色尽量给出：定位(role)、外在设定(description)、性格(personality)、欲望/目标(goals)、人物弧光(arc)、关系(relationships)。本片段信息不足的字段留空字符串。
- evidence 写原文中的简短依据；confidence 取 0 到 1。
- 没有可抽取角色时，characters 返回空数组。
- 只输出一个合法 JSON 对象，不要 Markdown 代码块或解释：

{
  "characters": [
    {
      "name": "角色名",
      "role": "定位，如主角/对手/导师",
      "description": "外在设定与背景",
      "personality": "性格与行为模式",
      "goals": "欲望与目标",
      "arc": "人物弧光：从何处到何处",
      "relationships": "与其他角色的关系",
      "confidence": 0.7,
      "evidence": "原文中的依据"
    }
  ]
}
