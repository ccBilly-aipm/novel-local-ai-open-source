对照 canon 检查章节事实一致性。只输出合法 JSON。

Canon：
{{context}}

章节正文：
{{chapter_content}}

输出格式：
{
  "issues": [
    {"type": "character|timeline|world|knowledge", "severity": "low|medium|high", "detail": "问题", "evidence": "依据"}
  ]
}
