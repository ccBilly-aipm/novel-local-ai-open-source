import json
import re
from pathlib import Path
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import PromptTemplate


PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"

# 全部提示词注册表：key -> (相对 prompts/ 的文件, 显示名, 说明)。
# 运行时一律走 load_prompt(db, key)：DB 有 active 模板则用 DB（提示词页可编辑覆盖），否则读文件兜底。
# 这样这页就能"管全部提示词"，而不只是旧版 6 个。
PROMPT_REGISTRY: Dict[str, Dict[str, str]] = {
    # —— 旧版生产（Legacy WritingTask 管线 chapter_pipeline）——
    "chapter_generation": {"file": "chapter_generation.md", "name": "章节生成（旧）", "description": "根据预算上下文和章节目标生成正文。"},
    "chapter_summary": {"file": "chapter_summary.md", "name": "章节摘要（旧）", "description": "抽取章节摘要、事件、冲突和伏笔。"},
    "character_state_update": {"file": "character_state_update.md", "name": "人物状态更新（旧）", "description": "生成待人工确认的人物状态变更。"},
    "chapter_review": {"file": "chapter_review.md", "name": "章节审稿（旧）", "description": "检查目标、人物、时间线、重复、剧情和风格。"},
    "continuity_check": {"file": "continuity_check.md", "name": "一致性检查（旧）", "description": "独立检查 canon 冲突。"},
    "outline_expand": {"file": "outline_expand.md", "name": "场景大纲扩展（旧）", "description": "把章节大纲扩展为顺序场景。"},
    # —— Loop 循环（新版状态机 agents）——
    "loop_draft_writer": {"file": "novel_loop/draft_writer.md", "name": "Loop·正文起草", "description": "Loop 写作：生成章节草稿正文。"},
    "loop_revision_writer": {"file": "novel_loop/revision_writer.md", "name": "Loop·正文修订", "description": "Loop 修订：按检查意见重写章节。"},
    "loop_continuity_checker": {"file": "novel_loop/continuity_checker.md", "name": "Loop·一致性检查", "description": "Loop 检查：连续性 / 冲突诊断。"},
    "loop_state_extractor": {"file": "novel_loop/state_extractor.md", "name": "Loop·状态抽取", "description": "Loop 状态：抽取人物状态变更候选。"},
    # —— 拆解（逆向工程）——
    "decon_characters": {"file": "deconstruction/characters_map.md", "name": "拆解·人物线", "description": "从参考小说抽取人物原型卡。"},
    "decon_worldbuilding": {"file": "deconstruction/worldbuilding_map.md", "name": "拆解·世界观", "description": "抽取世界规则。"},
    "decon_timeline": {"file": "deconstruction/timeline_map.md", "name": "拆解·时间线", "description": "抽取时间线事件。"},
    "decon_plot_threads": {"file": "deconstruction/plot_threads_map.md", "name": "拆解·情节线", "description": "抽取情节线。"},
    "decon_meta": {"file": "deconstruction/meta_map.md", "name": "拆解·定位", "description": "抽取题材 / 定位 / logline。"},
    "decon_structure": {"file": "deconstruction/structure_map.md", "name": "拆解·结构", "description": "抽取结构节拍。"},
    "decon_setup_payoff": {"file": "deconstruction/setup_payoff_map.md", "name": "拆解·伏笔", "description": "抽取伏笔-回收。"},
    "decon_theme": {"file": "deconstruction/theme_map.md", "name": "拆解·主题", "description": "抽取主题与母题。"},
    "decon_pov": {"file": "deconstruction/pov_map.md", "name": "拆解·视角", "description": "抽取叙事视角。"},
    "decon_style_fingerprint": {"file": "deconstruction/style_fingerprint_map.md", "name": "拆解·文风指纹", "description": "抽取可复刻的文风指纹。"},
    "decon_combined": {"file": "deconstruction/combined_map.md", "name": "拆解·合并抽取", "description": "一次产出多维度（合并模式）。"},
    "decon_critique": {"file": "deconstruction/_critique.md", "name": "拆解·审校 CRITIQUE", "description": "对去重候选逐条裁决 keep / drop。"},
    "decon_refine": {"file": "deconstruction/_refine.md", "name": "拆解·精炼 REFINE", "description": "标注可迁移层级 + 仿写可复用度。"},
    # —— 故事工程 / 仿写 ——
    "se_framework": {"file": "story_engineering/framework.md", "name": "故事工程·框架", "description": "从想法生成故事框架。"},
    "se_characters": {"file": "story_engineering/characters.md", "name": "故事工程·人物", "description": "从想法生成人物。"},
    "se_world_rules": {"file": "story_engineering/world_rules.md", "name": "故事工程·世界规则", "description": "从想法生成世界规则。"},
    "se_chapter_plan": {"file": "story_engineering/chapter_plan.md", "name": "故事工程·章节计划", "description": "从想法生成章节计划。"},
    "se_pastiche": {"file": "story_engineering/pastiche_framework.md", "name": "故事工程·仿写框架", "description": "基于已采纳设定生成原创仿写框架（含 surface/pattern/signature 三层迁移教义）。"},
}

# 旧版 6 个的输出 schema（仅展示用）；其余给通用占位。
_LEGACY_SCHEMAS = {
    "chapter_generation": {"type": "string"},
    "chapter_summary": {"type": "object", "required": ["summary", "key_events", "unresolved_conflicts", "foreshadowing"]},
    "character_state_update": {"type": "object", "required": ["updates"]},
    "chapter_review": {"type": "object", "required": ["score", "suggestions"]},
    "continuity_check": {"type": "object", "required": ["issues"]},
    "outline_expand": {"type": "object", "required": ["scenes"]},
}


def seed_prompt_templates(db: Session) -> None:
    """把注册表里全部提示词种入 DB（仅当缺失时新增，保留用户已有编辑）。"""
    created = False
    for key, meta in PROMPT_REGISTRY.items():
        existing = db.scalar(select(PromptTemplate).where(PromptTemplate.key == key))
        if existing is not None:
            continue
        path = PROMPT_DIR / meta["file"]
        try:
            text = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            continue  # 文件缺失就跳过，不阻断启动
        db.add(
            PromptTemplate(
                key=key,
                name=meta["name"],
                description=meta["description"],
                template_text=text,
                output_schema_json=json.dumps(_LEGACY_SCHEMAS.get(key, {}), ensure_ascii=False),
                active=True,
            )
        )
        created = True
    if created:
        db.commit()


def load_prompt(db: Session, key: str) -> str:
    """统一加载：DB 有 active 模板用 DB（提示词页可编辑覆盖），否则读注册表文件兜底。

    这样所有提示词（旧版 / Loop / 拆解 / 故事工程）都能在提示词页里编辑并立即生效，
    DB 缺失（如新部署种入前）时回退到打包的 .md，绝不因 DB 没有就报错。"""
    template = db.scalar(
        select(PromptTemplate).where(PromptTemplate.key == key, PromptTemplate.active.is_(True))
    )
    if template is not None:
        return template.template_text
    meta = PROMPT_REGISTRY.get(key)
    if meta is None:
        raise ValueError("Unknown prompt key: {}".format(key))
    return (PROMPT_DIR / meta["file"]).read_text(encoding="utf-8")


def get_template(db: Session, key: str) -> PromptTemplate:
    template = db.scalar(
        select(PromptTemplate).where(PromptTemplate.key == key, PromptTemplate.active.is_(True))
    )
    if template is None:
        raise ValueError("Active prompt template not found: {}".format(key))
    return template


def render_template(template_text: str, variables: Dict[str, Any]) -> str:
    pattern = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

    def replace(match):
        value = variables.get(match.group(1), "")
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, indent=2)
        return str(value)

    return pattern.sub(replace, template_text)
