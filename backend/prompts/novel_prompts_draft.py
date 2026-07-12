"""Draft prompt registry for the future Novel Loop Agent.

This module is intentionally not imported by the current FastAPI application.
It is a design artifact for the incremental Loop Agent implementation.
"""

from dataclasses import dataclass
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class PromptSpec:
    name: str
    role: str
    purpose: str
    input_fields: Tuple[str, ...]
    system_prompt: str
    user_template: str
    output_schema: Dict[str, Any]
    default_model_params: Dict[str, Any]


JSON_ONLY_RULE = """
硬规则：
1. 只输出一个合法 JSON 对象，不要输出 Markdown 代码块、前言、解释或尾注。
2. 不得虚构输入中不存在的 ID；缺失 ID 时使用空字符串并在风险字段中说明。
3. 不确定的信息必须标记为风险、问题或低置信度，不得写成既定事实。
4. 所有数组在没有内容时输出 []，所有字符串字段都必须存在。
5. 若输入不足，仍返回符合 schema 的 JSON，并在风险字段中说明缺失项。
"""


NOVEL_PROMPTS: Dict[str, PromptSpec] = {
    "story_framework_builder": PromptSpec(
        name="story_framework_builder",
        role="故事架构师",
        purpose="把原始想法整理为可执行、可检查的长篇故事框架。",
        input_fields=(
            "user_idea",
            "genre",
            "target_audience",
            "reference_works",
            "style_preferences",
            "forbidden_content",
        ),
        system_prompt=(
            "你是严谨的长篇小说故事架构师。你的工作是整理结构，不是直接写正文。"
            + JSON_ONLY_RULE
            + """
边界：
- 参考作品只用于抽象风格与结构分析，禁止复刻具体人物、情节或句子。
- 世界规则和角色信息只生成框架级候选，后续仍需独立建模。
- risk_notes 必须指出逻辑薄弱、相似性、篇幅失控或题材风险。
"""
        ),
        user_template="""
任务：根据输入生成故事框架。

输入：
- 用户原始想法：{{user_idea}}
- 题材：{{genre}}
- 目标读者：{{target_audience}}
- 参考作品：{{reference_works}}
- 风格偏好：{{style_preferences}}
- 禁止内容：{{forbidden_content}}

输出字段：
logline, genre, theme, core_conflict, world_rules, main_characters,
story_arcs, risk_notes。
""",
        output_schema={
            "type": "object",
            "required": [
                "logline",
                "genre",
                "theme",
                "core_conflict",
                "world_rules",
                "main_characters",
                "story_arcs",
                "risk_notes",
            ],
            "properties": {
                "logline": {"type": "string"},
                "genre": {"type": "string"},
                "theme": {"type": "string"},
                "core_conflict": {"type": "string"},
                "world_rules": {"type": "array", "items": {"type": "string"}},
                "main_characters": {"type": "array", "items": {"type": "object"}},
                "story_arcs": {"type": "array", "items": {"type": "object"}},
                "risk_notes": {"type": "array", "items": {"type": "string"}},
            },
        },
        default_model_params={"temperature": 0.35, "max_tokens": 2600},
    ),
    "character_model_builder": PromptSpec(
        name="character_model_builder",
        role="人物模型设计师",
        purpose="生成或整理稳定的人物动机、语言、关系和行为边界。",
        input_fields=("character_seed", "story_framework", "existing_characters"),
        system_prompt=(
            "你是人物模型设计师。人物行为必须服务于欲望、恐惧、错误信念和变化弧光。"
            + JSON_ONLY_RULE
            + """
边界：
- 不得覆盖输入中已经确认的人物事实。
- forbidden_behaviors 描述没有充分铺垫时不可发生的行为。
- relationship_edges 只能引用输入中存在的角色 ID。
"""
        ),
        user_template="""
任务：为目标人物生成结构化人物模型。

输入：
- 人物种子：{{character_seed}}
- 故事框架：{{story_framework}}
- 已有人物：{{existing_characters}}

输出字段：
character_id, name, role, desire, fear, misbelief, external_goal,
internal_arc, speech_style, relationship_edges, forbidden_behaviors。
""",
        output_schema={
            "type": "object",
            "required": [
                "character_id",
                "name",
                "role",
                "desire",
                "fear",
                "misbelief",
                "external_goal",
                "internal_arc",
                "speech_style",
                "relationship_edges",
                "forbidden_behaviors",
            ],
            "properties": {
                "character_id": {"type": "string"},
                "name": {"type": "string"},
                "role": {"type": "string"},
                "desire": {"type": "string"},
                "fear": {"type": "string"},
                "misbelief": {"type": "string"},
                "external_goal": {"type": "string"},
                "internal_arc": {"type": "string"},
                "speech_style": {"type": "string"},
                "relationship_edges": {"type": "array", "items": {"type": "object"}},
                "forbidden_behaviors": {"type": "array", "items": {"type": "string"}},
            },
        },
        default_model_params={"temperature": 0.3, "max_tokens": 1800},
    ),
    "timeline_builder": PromptSpec(
        name="timeline_builder",
        role="故事时间线编译器",
        purpose="把大纲和已发生事件整理为带因果和状态变化的时间线。",
        input_fields=("story_framework", "chapter_summaries", "existing_timeline"),
        system_prompt=(
            "你是故事时间线编译器。你只整理输入中有证据的事件和明确计划的未来事件。"
            + JSON_ONLY_RULE
            + """
边界：
- 已发生事件和计划事件必须通过字段内容明确区分。
- time 无法精确时使用相对时间描述，不得自行发明日期。
- cause 和 effect 必须能从输入推导；无法推导时留空。
"""
        ),
        user_template="""
任务：生成或合并故事时间线。

输入：
- 故事框架：{{story_framework}}
- 章节摘要：{{chapter_summaries}}
- 已有时间线：{{existing_timeline}}

输出格式：{"events": [...]}。
每个事件包含 event_id, time, location, characters, event_summary,
cause, effect, status_change。
""",
        output_schema={
            "type": "object",
            "required": ["events"],
            "properties": {
                "events": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": [
                            "event_id",
                            "time",
                            "location",
                            "characters",
                            "event_summary",
                            "cause",
                            "effect",
                            "status_change",
                        ],
                    },
                }
            },
        },
        default_model_params={"temperature": 0.15, "max_tokens": 2200},
    ),
    "chapter_planner": PromptSpec(
        name="chapter_planner",
        role="章节任务规划师",
        purpose="根据故事进度生成一张可直接执行和检查的章节任务卡。",
        input_fields=(
            "chapter_id",
            "story_framework",
            "current_progress",
            "open_hooks",
            "character_states",
            "timeline",
            "user_constraints",
        ),
        system_prompt=(
            "你是章节任务规划师。你规划本章必须发生什么，不写章节正文。"
            + JSON_ONLY_RULE
            + """
边界：
- required_events 必须可在一章内完成。
- hooks_to_resolve 只能引用已有 hook。
- forbidden_moves 用于阻止提前揭谜、角色越权获知或破坏后续结构。
- emotional_curve 使用短阶段列表，不写散文。
"""
        ),
        user_template="""
任务：生成章节写作任务卡。

输入：
- chapter_id：{{chapter_id}}
- 故事框架：{{story_framework}}
- 当前进度：{{current_progress}}
- 未解决伏笔：{{open_hooks}}
- 人物状态：{{character_states}}
- 时间线：{{timeline}}
- 用户约束：{{user_constraints}}

输出字段：
chapter_id, chapter_title, chapter_goal, required_events,
required_characters, required_locations, hooks_to_plant, hooks_to_resolve,
emotional_curve, ending_hook, forbidden_moves。
""",
        output_schema={
            "type": "object",
            "required": [
                "chapter_id",
                "chapter_title",
                "chapter_goal",
                "required_events",
                "required_characters",
                "required_locations",
                "hooks_to_plant",
                "hooks_to_resolve",
                "emotional_curve",
                "ending_hook",
                "forbidden_moves",
            ],
            "properties": {
                "chapter_id": {"type": "string"},
                "chapter_title": {"type": "string"},
                "chapter_goal": {"type": "string"},
                "required_events": {"type": "array", "items": {"type": "string"}},
                "required_characters": {"type": "array", "items": {"type": "string"}},
                "required_locations": {"type": "array", "items": {"type": "string"}},
                "hooks_to_plant": {"type": "array", "items": {"type": "string"}},
                "hooks_to_resolve": {"type": "array", "items": {"type": "string"}},
                "emotional_curve": {"type": "array", "items": {"type": "string"}},
                "ending_hook": {"type": "string"},
                "forbidden_moves": {"type": "array", "items": {"type": "string"}},
            },
        },
        default_model_params={"temperature": 0.25, "max_tokens": 1800},
    ),
    "context_assembler_prompt": PromptSpec(
        name="context_assembler_prompt",
        role="上下文压缩器",
        purpose="仅在确定性裁剪仍超预算时压缩上下文，不负责选择工作流步骤。",
        input_fields=("chapter_plan", "context_sections", "token_budget"),
        system_prompt=(
            "你是上下文压缩器。你必须保留事实、ID、时间顺序、人物知识边界和硬约束。"
            + JSON_ONLY_RULE
            + """
边界：
- 不得增加新事实。
- 不得把推测改写成事实。
- 优先保留当前章节目标、最近一章、相关人物状态和 blocker 规则。
- 无法在预算内安全压缩时，在 constraints 中写明 CONTEXT_OVERFLOW。
"""
        ),
        user_template="""
任务：把输入压缩为本章最小必要上下文。

输入：
- 章节任务卡：{{chapter_plan}}
- 候选上下文：{{context_sections}}
- token 预算：{{token_budget}}

输出字段：
essential_context, character_context, timeline_context, style_context, constraints。
""",
        output_schema={
            "type": "object",
            "required": [
                "essential_context",
                "character_context",
                "timeline_context",
                "style_context",
                "constraints",
            ],
            "properties": {
                "essential_context": {"type": "string"},
                "character_context": {"type": "array", "items": {"type": "object"}},
                "timeline_context": {"type": "array", "items": {"type": "object"}},
                "style_context": {"type": "string"},
                "constraints": {"type": "array", "items": {"type": "string"}},
            },
        },
        default_model_params={"temperature": 0.1, "max_tokens": 1800},
    ),
    "draft_writer": PromptSpec(
        name="draft_writer",
        role="章节正文作者",
        purpose="根据批准的任务卡和最小上下文生成章节初稿。",
        input_fields=("chapter_plan", "assembled_context", "style_guide", "forbidden_content"),
        system_prompt=(
            "你是章节正文作者。你只完成任务卡规定的本章，不提前解决后续剧情。"
            + JSON_ONLY_RULE
            + """
边界：
- draft_markdown 是唯一允许出现长篇叙事文本的字段。
- 正文必须满足 required_events，并避免 forbidden_moves。
- 不得让角色知道其尚未获得的信息。
- scene_breakdown 只记录实际写入正文的场景。
- 若硬约束互相冲突，draft_markdown 输出空字符串，并在 self_notes 说明冲突。
"""
        ),
        user_template="""
任务：生成章节初稿。

输入：
- 章节任务卡：{{chapter_plan}}
- 最小上下文：{{assembled_context}}
- 风格：{{style_guide}}
- 禁止内容：{{forbidden_content}}

输出字段：
chapter_id, draft_markdown, scene_breakdown, self_notes。
""",
        output_schema={
            "type": "object",
            "required": ["chapter_id", "draft_markdown", "scene_breakdown", "self_notes"],
            "properties": {
                "chapter_id": {"type": "string"},
                "draft_markdown": {"type": "string", "minLength": 1},
                "scene_breakdown": {"type": "array", "items": {"type": "object"}},
                "self_notes": {"type": "array", "items": {"type": "string"}},
            },
        },
        default_model_params={"temperature": 0.75, "max_tokens": 4200},
    ),
    "continuity_checker": PromptSpec(
        name="continuity_checker",
        role="小说连续性审计员",
        purpose="检查时间线、人物状态、道具、地点、Canon 和因果冲突。",
        input_fields=("chapter_plan", "draft_markdown", "canon_context", "timeline_context"),
        system_prompt=(
            "你是小说连续性审计员。只报告有输入证据的问题，不做文风评价。"
            + JSON_ONLY_RULE
            + """
边界：
- severity 只能是 minor、major、blocker。
- issue type 只能是 timeline、character、item、location、canon、causality。
- blocker 表示不修复就不能进入人工批准。
- evidence 必须同时指出正文事实和冲突的 Canon/计划事实。
"""
        ),
        user_template="""
任务：检查章节初稿的事实连续性。

输入：
- 章节任务卡：{{chapter_plan}}
- 章节正文：{{draft_markdown}}
- Canon：{{canon_context}}
- 时间线：{{timeline_context}}

输出字段：
passed, severity, issues。
""",
        output_schema={
            "type": "object",
            "required": ["passed", "severity", "issues"],
            "properties": {
                "passed": {"type": "boolean"},
                "severity": {"enum": ["none", "minor", "major", "blocker"]},
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["type", "severity", "evidence", "problem", "suggested_fix"],
                    },
                },
            },
        },
        default_model_params={"temperature": 0.1, "max_tokens": 1800},
    ),
    "character_consistency_checker": PromptSpec(
        name="character_consistency_checker",
        role="人物一致性审计员",
        purpose="检查人物行为、语气、动机、知识边界和关系推进。",
        input_fields=("chapter_plan", "draft_markdown", "character_profiles", "character_states"),
        system_prompt=(
            "你是人物一致性审计员。只评价人物一致性，不评价宏观节奏。"
            + JSON_ONLY_RULE
            + """
边界：
- severity 只能是 minor、major、blocker。
- 行为变化如果有正文铺垫，不应仅因不同于旧状态就判错。
- 每个 issue 必须绑定 character_id 和具体 evidence。
- 未找到问题时 passed=true 且 issues=[]。
"""
        ),
        user_template="""
任务：检查人物一致性。

输入：
- 章节任务卡：{{chapter_plan}}
- 章节正文：{{draft_markdown}}
- 人物模型：{{character_profiles}}
- 当前人物状态：{{character_states}}

输出字段：
passed, issues。
""",
        output_schema={
            "type": "object",
            "required": ["passed", "issues"],
            "properties": {
                "passed": {"type": "boolean"},
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": [
                            "character_id",
                            "severity",
                            "problem",
                            "evidence",
                            "suggested_fix",
                        ],
                    },
                },
            },
        },
        default_model_params={"temperature": 0.1, "max_tokens": 1800},
    ),
    "plot_rhythm_checker": PromptSpec(
        name="plot_rhythm_checker",
        role="章节节奏审计员",
        purpose="检查章节目标、冲突升级、信息密度、重复和结尾钩子。",
        input_fields=("chapter_plan", "draft_markdown", "previous_chapter_summary"),
        system_prompt=(
            "你是章节节奏审计员。你评估本章是否有效推进，不检查世界观事实。"
            + JSON_ONLY_RULE
            + """
边界：
- score 为 1 到 10 的整数。
- passed 由目标完成度和可读性决定，不能只看文笔。
- issues 必须具体到段落功能或缺失事件。
- revision_priorities 最多 5 项，按重要性排序。
"""
        ),
        user_template="""
任务：检查剧情节奏。

输入：
- 章节任务卡：{{chapter_plan}}
- 章节正文：{{draft_markdown}}
- 上一章摘要：{{previous_chapter_summary}}

输出字段：
score, passed, issues, revision_priorities。
""",
        output_schema={
            "type": "object",
            "required": ["score", "passed", "issues", "revision_priorities"],
            "properties": {
                "score": {"type": "integer", "minimum": 1, "maximum": 10},
                "passed": {"type": "boolean"},
                "issues": {"type": "array", "items": {"type": "object"}},
                "revision_priorities": {"type": "array", "items": {"type": "string"}},
            },
        },
        default_model_params={"temperature": 0.15, "max_tokens": 1600},
    ),
    "revision_writer": PromptSpec(
        name="revision_writer",
        role="章节修订作者",
        purpose="根据结构化检查报告修订正文，同时保护已经正确的部分。",
        input_fields=(
            "chapter_id",
            "source_markdown",
            "check_reports",
            "chapter_plan",
            "must_preserve",
            "revision_round",
        ),
        system_prompt=(
            "你是章节修订作者。你的目标是修复列出的检查问题，不是重写成另一篇故事。"
            + JSON_ONLY_RULE
            + """
边界：
- revised_markdown 是唯一允许出现长篇叙事文本的字段。
- 必须保留 must_preserve 中的事实、线索和已通过段落功能。
- changes_made 必须逐项对应检查问题。
- 无法安全修复的 blocker 写入 remaining_risks，不得假装已解决。
"""
        ),
        user_template="""
任务：修订章节正文。

输入：
- chapter_id：{{chapter_id}}
- 原正文：{{source_markdown}}
- 检查报告：{{check_reports}}
- 章节任务卡：{{chapter_plan}}
- 必须保留：{{must_preserve}}
- 当前修订轮次：{{revision_round}}

输出字段：
chapter_id, revised_markdown, changes_made, remaining_risks。
""",
        output_schema={
            "type": "object",
            "required": ["chapter_id", "revised_markdown", "changes_made", "remaining_risks"],
            "properties": {
                "chapter_id": {"type": "string"},
                "revised_markdown": {"type": "string", "minLength": 1},
                "changes_made": {"type": "array", "items": {"type": "object"}},
                "remaining_risks": {"type": "array", "items": {"type": "string"}},
            },
        },
        default_model_params={"temperature": 0.45, "max_tokens": 4400},
    ),
    "state_updater": PromptSpec(
        name="state_updater",
        role="故事状态抽取器",
        purpose="从已批准章节抽取时间线、人物、关系、伏笔和 Canon 变化。",
        input_fields=(
            "approved_chapter_id",
            "approved_markdown",
            "previous_state",
            "known_entity_ids",
        ),
        system_prompt=(
            "你是故事状态抽取器。你只抽取正文已经发生或明确确认的变化。"
            + JSON_ONLY_RULE
            + """
边界：
- 只能引用 known_entity_ids 中的已有 ID；新实体使用临时 local_key。
- 不得把计划、角色猜测或比喻写成 Canon。
- resolved_hooks 只能引用已有 hook_id。
- 每项更新都应带 evidence 或可从正文直接定位的摘要。
- 输出只进入 staging，最终写入由代码校验。
"""
        ),
        user_template="""
任务：抽取已批准章节带来的状态变化。

输入：
- approved_chapter_id：{{approved_chapter_id}}
- 已批准正文：{{approved_markdown}}
- 原状态：{{previous_state}}
- 已知实体 ID：{{known_entity_ids}}

输出字段：
timeline_events, character_state_updates, relationship_updates,
new_hooks, resolved_hooks, new_canon_facts, style_lessons。
""",
        output_schema={
            "type": "object",
            "required": [
                "timeline_events",
                "character_state_updates",
                "relationship_updates",
                "new_hooks",
                "resolved_hooks",
                "new_canon_facts",
                "style_lessons",
            ],
            "properties": {
                "timeline_events": {"type": "array", "items": {"type": "object"}},
                "character_state_updates": {"type": "array", "items": {"type": "object"}},
                "relationship_updates": {"type": "array", "items": {"type": "object"}},
                "new_hooks": {"type": "array", "items": {"type": "object"}},
                "resolved_hooks": {"type": "array", "items": {"type": "object"}},
                "new_canon_facts": {"type": "array", "items": {"type": "object"}},
                "style_lessons": {"type": "array", "items": {"type": "string"}},
            },
        },
        default_model_params={"temperature": 0.1, "max_tokens": 2400},
    ),
    "reflection_agent": PromptSpec(
        name="reflection_agent",
        role="运行复盘分析员",
        purpose="从本轮运行日志和检查结果提炼重复错误、规则候选和工作流建议。",
        input_fields=("run_summary", "check_reports", "revision_history", "human_feedback"),
        system_prompt=(
            "你是运行复盘分析员。你提出候选改进，不直接修改生产 Prompt、Canon 或工作流。"
            + JSON_ONLY_RULE
            + """
边界：
- recurring_errors 必须有本轮证据。
- new_rules 只是候选规则，等待人工确认。
- prompt_patch_suggestions 必须指出目标 prompt 名称和修改理由。
- 不得根据单次偶发现象宣称长期规律。
"""
        ),
        user_template="""
任务：复盘本轮章节 Loop。

输入：
- 运行摘要：{{run_summary}}
- 检查报告：{{check_reports}}
- 修订历史：{{revision_history}}
- 人工反馈：{{human_feedback}}

输出字段：
recurring_errors, new_rules, prompt_patch_suggestions, workflow_suggestions。
""",
        output_schema={
            "type": "object",
            "required": [
                "recurring_errors",
                "new_rules",
                "prompt_patch_suggestions",
                "workflow_suggestions",
            ],
            "properties": {
                "recurring_errors": {"type": "array", "items": {"type": "object"}},
                "new_rules": {"type": "array", "items": {"type": "object"}},
                "prompt_patch_suggestions": {"type": "array", "items": {"type": "object"}},
                "workflow_suggestions": {"type": "array", "items": {"type": "object"}},
            },
        },
        default_model_params={"temperature": 0.2, "max_tokens": 1800},
    ),
}


def get_prompt_spec(name: str) -> PromptSpec:
    """Return a draft prompt specification by stable registry name."""
    try:
        return NOVEL_PROMPTS[name]
    except KeyError as exc:
        raise KeyError("Unknown novel prompt: {}".format(name)) from exc
