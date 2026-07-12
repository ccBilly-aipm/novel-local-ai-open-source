from typing import Any, Dict


DRAFT_DEFAULTS: Dict[str, Any] = {
    "temperature": 0.7,
    "max_tokens": 8192,
}

# 检查 / 状态抽取默认参数。实测结论（长章节四案例基准）：
# - 思考(enable_thinking)是连续性检查的命门——关掉则 0 召回（橡皮图章）。
#   这里强制开启，且因 merged_options 中"调用时 options 覆盖 provider 默认"，
#   会盖掉 provider 烘焙的 enable_thinking:false（如去审核模型的默认配置）。
# - max_tokens 给足，避免推理链未结束就被截断导致无 JSON 产出（gemma 在 6000 才勉强）。
CONTINUITY_DEFAULTS: Dict[str, Any] = {
    "temperature": 0.1,
    "max_tokens": 6000,
    "chat_template_kwargs": {"enable_thinking": True},
}


def agent_options(defaults: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(defaults)
    result.update(overrides or {})
    result.pop("context_budget", None)
    return result
