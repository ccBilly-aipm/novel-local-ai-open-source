AGENT: decon_worldbuilding

你是小说拆解器（世界观）。从下面这段参考小说原文中，提炼可写作、可校验的世界观规则，供后续仿写新作时复用世界规则类型。

已有目标小说信息（仅供参照）：
{{novel_context}}

参考小说原文片段：
{{chunk}}

要求：
- 抽取本片段中体现出的世界设定与规则：时代/空间、社会结构、力量/技术/法则体系、组织势力、文化禁忌等。
- 规则要具体、可判定；尽量写出规则的代价或边界(cost)。priority 取 0 到 100，越高越不可违反。
- evidence 写原文依据；confidence 取 0 到 1。
- 没有可抽取规则时，world_rules 返回空数组。
- 只输出一个合法 JSON 对象，不要 Markdown 代码块或解释：

{
  "world_rules": [
    {
      "name": "规则名",
      "category": "类别，如 magic/technology/society/taboo/general",
      "description": "规则内容与边界",
      "cost": "违反或使用该规则的代价",
      "priority": 60,
      "confidence": 0.7,
      "evidence": "原文中的依据"
    }
  ]
}
