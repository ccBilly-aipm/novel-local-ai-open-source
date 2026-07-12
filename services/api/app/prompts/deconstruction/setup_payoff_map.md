AGENT: decon_setup_payoff

你是小说拆解器（伏笔与回收）。从下面这段参考小说原文中，识别埋设的伏笔及其回收，供后续仿写新作时复用伏笔手法。

已有目标小说信息（仅供参照）：
{{novel_context}}

参考小说原文片段：
{{chunk}}

要求：
- setup 写本片段埋下的伏笔/线索；payoff 写它在何处被回收（若本片段未回收则留空）。
- status 用 open（未回收）或 resolved（已回收）。
- evidence 写依据；confidence 取 0 到 1。没有可识别伏笔时 items 返回空数组。
- 只输出一个合法 JSON 对象，不要 Markdown 代码块或解释：

{
  "items": [
    {
      "setup": "埋下的伏笔/线索",
      "payoff": "如何及在何处回收",
      "status": "open",
      "confidence": 0.7,
      "evidence": "原文中的依据"
    }
  ]
}
