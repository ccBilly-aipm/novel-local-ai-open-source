根据角色卡和章节正文，提出人物状态更新。不要把推测当事实。只输出合法 JSON。

角色卡：
{{characters}}

章节正文：
{{chapter_content}}

输出格式：
{
  "updates": [
    {
      "character_id": "角色 ID",
      "character_name": "角色名",
      "changes": {"位置": "新值", "身体": "新值", "情绪": "新值", "已知信息": ["事实"]},
      "evidence": "正文中的简短依据",
      "confidence": 0.0
    }
  ]
}
