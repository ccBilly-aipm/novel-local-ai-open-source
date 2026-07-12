AGENT: decon_plot_threads

你是小说拆解器（情节线）。从下面这段参考小说原文中，识别正在推进的故事线/情节线（主线与支线），供后续仿写新作时复用结构骨架。

已有目标小说信息（仅供参照）：
{{novel_context}}

参考小说原文片段：
{{chunk}}

要求：
- 识别本片段中体现的情节线：每条线是一组围绕同一目标/冲突推进的事件。
- description 概括这条线的冲突与推进；status 用 open（未解决）或 resolved（已解决）；若已解决，resolution 写如何收束。
- evidence 写原文依据；confidence 取 0 到 1。
- 没有可识别情节线时，plot_threads 返回空数组。
- 只输出一个合法 JSON 对象，不要 Markdown 代码块或解释：

{
  "plot_threads": [
    {
      "name": "情节线名称",
      "description": "这条线的冲突与推进",
      "status": "open",
      "resolution": "若已解决，如何收束",
      "confidence": 0.7,
      "evidence": "原文中的依据"
    }
  ]
}
