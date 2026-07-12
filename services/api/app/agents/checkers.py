from sqlalchemy.orm import Session

from app.agents.base import AgentOutputMode, AgentSpec, PromptSpec, StructuredAgent
from app.models.entities import Chapter, ModelProvider
from app.models.loop_entities import ChapterLoopRun, ChapterVersion, RunStep
from app.schemas.loop import ContinuityCheckerOutput
from app.schemas.story_engineering import StateExtractionOutput
from app.workflow.policies import CONTINUITY_DEFAULTS, agent_options


class ContinuityCheckerAgent(StructuredAgent):
    name = "continuity_checker"
    prompt_file = "continuity_checker.md"
    output_schema = ContinuityCheckerOutput
    spec = AgentSpec(
        name=name,
        prompt=PromptSpec(prompt_file, AgentOutputMode.JSON_SCHEMA),
        output_schema=ContinuityCheckerOutput,
    )

    def __init__(self, db: Session):
        super().__init__(db)

    def run(
        self,
        loop_run: ChapterLoopRun,
        step: RunStep,
        chapter: Chapter,
        version: ChapterVersion,
        provider: ModelProvider,
        context: str,
        overrides,
    ) -> ContinuityCheckerOutput:
        prompt = self.prompt(
            {
                "chapter_id": chapter.id,
                "chapter_title": chapter.title,
                "context": context,
                "draft_markdown": version.content_markdown,
            }
        )
        return self.call(
            loop_run,
            step,
            provider,
            prompt,
            agent_options(CONTINUITY_DEFAULTS, overrides),
        )


class StateChangeExtractorAgent(StructuredAgent):
    name = "state_extractor"
    prompt_file = "state_extractor.md"
    output_schema = StateExtractionOutput
    spec = AgentSpec(
        name=name,
        prompt=PromptSpec(prompt_file, AgentOutputMode.JSON_SCHEMA),
        output_schema=StateExtractionOutput,
    )

    def __init__(self, db: Session):
        super().__init__(db)

    def run(
        self,
        loop_run: ChapterLoopRun,
        step: RunStep,
        chapter: Chapter,
        version: ChapterVersion,
        provider: ModelProvider,
        context: str,
        overrides,
    ) -> StateExtractionOutput:
        prompt = self.prompt(
            {
                "chapter_title": chapter.title,
                "context": context,
                "draft_markdown": version.content_markdown,
            }
        )
        return self.call(
            loop_run,
            step,
            provider,
            prompt,
            agent_options(CONTINUITY_DEFAULTS, overrides),
        )
