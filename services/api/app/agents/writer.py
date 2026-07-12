from sqlalchemy.orm import Session

from app.agents.base import AgentOutputMode, AgentSpec, PromptSpec, TextAgent
from app.models.entities import Chapter, ModelProvider
from app.models.loop_entities import ChapterLoopRun, RunStep
from app.schemas.loop import DraftWriterOutput
from app.workflow.policies import DRAFT_DEFAULTS, agent_options


class DraftWriterAgent(TextAgent):
    name = "draft_writer"
    prompt_file = "draft_writer.md"
    spec = AgentSpec(
        name=name,
        prompt=PromptSpec(prompt_file, AgentOutputMode.TEXT_STREAM),
    )

    def __init__(self, db: Session):
        super().__init__(db)

    def run(
        self,
        loop_run: ChapterLoopRun,
        step: RunStep,
        chapter: Chapter,
        provider: ModelProvider,
        context: str,
        overrides,
    ) -> DraftWriterOutput:
        prompt = self.prompt(
            {
                "chapter_id": chapter.id,
                "chapter_title": chapter.title,
                "chapter_goal": chapter.outline.goal if chapter.outline else "",
                "chapter_outline": chapter.outline.outline_content if chapter.outline else "",
                "context": context,
            }
        )
        result = self.call_text(
            loop_run,
            step,
            provider,
            prompt,
            agent_options(DRAFT_DEFAULTS, overrides),
        )
        return DraftWriterOutput(
            chapter_id=chapter.id,
            draft_markdown=result.content_markdown,
            scene_breakdown=[],
            self_notes=[result.warning] if result.warning else [],
        )


class RevisionWriterAgent(TextAgent):
    name = "revision_writer"
    prompt_file = "revision_writer.md"
    spec = AgentSpec(
        name=name,
        prompt=PromptSpec(prompt_file, AgentOutputMode.TEXT_STREAM),
    )

    def run(
        self,
        loop_run: ChapterLoopRun,
        step: RunStep,
        chapter: Chapter,
        provider: ModelProvider,
        context: str,
        previous_draft: str,
        feedback: str,
        overrides,
    ) -> DraftWriterOutput:
        prompt = self.prompt(
            {
                "chapter_id": chapter.id,
                "chapter_title": chapter.title,
                "chapter_goal": chapter.outline.goal if chapter.outline else "",
                "chapter_outline": chapter.outline.outline_content if chapter.outline else "",
                "context": context,
                "previous_draft": previous_draft,
                "feedback": feedback,
            }
        )
        result = self.call_text(
            loop_run,
            step,
            provider,
            prompt,
            agent_options(DRAFT_DEFAULTS, overrides),
        )
        return DraftWriterOutput(
            chapter_id=chapter.id,
            draft_markdown=result.content_markdown,
            scene_breakdown=[],
            self_notes=[result.warning] if result.warning else [],
        )
