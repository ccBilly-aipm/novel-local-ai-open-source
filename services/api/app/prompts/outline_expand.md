把章节目标扩展成 2 至 6 个顺序场景。每个场景必须推动目标。只输出合法 JSON。

故事与章节上下文：
{{context}}

输出格式：
{
  "scenes": [
    {
      "order_index": 1,
      "title": "场景名",
      "goal": "本场景改变什么",
      "outline_content": "发生的行动、冲突和结果",
      "character_ids": ["角色 ID"],
      "location_id": null
    }
  ]
}
