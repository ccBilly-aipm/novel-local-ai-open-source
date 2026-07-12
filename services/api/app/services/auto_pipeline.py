from datetime import datetime
from typing import Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.auto_entities import AutoRunPolicy, RevisionPlan
from app.models.entities import Chapter
from app.models.loop_entities import ChapterLoopRun, ChapterVersion, ModelCall
from app.schemas.loop import ContinuityCheckerOutput
from app.services.common import dumps, loads
from app.services.version_manager import ChapterVersionManager


AUTO_MODES = {"ai_auto_revise", "ai_auto_commit", "full_autonomous"}
AUTO_COMMIT_MODES = {"ai_auto_commit", "full_autonomous"}
HARD_PAUSE_TYPES = {"canon", "character"}


def issue_requires_pause(issue) -> bool:
    severity = issue.severity if hasattr(issue, "severity") else issue.get("severity")
    issue_type = issue.type if hasattr(issue, "type") else issue.get("type")
    must_pause = issue.must_pause if hasattr(issue, "must_pause") else issue.get("must_pause")
    auto_fixable = issue.auto_fixable if hasattr(issue, "auto_fixable") else issue.get("auto_fixable")
    return severity == "blocker" or (
        bool(must_pause)
        and issue_type in HARD_PAUSE_TYPES
        and not bool(auto_fixable)
    )


def policy_for_run(db: Session, run_id: str) -> AutoRunPolicy:
    return db.scalar(select(AutoRunPolicy).where(AutoRunPolicy.run_id == run_id))


def create_revision_plan(
    db: Session,
    run: ChapterLoopRun,
    policy: AutoRunPolicy,
    report: ContinuityCheckerOutput,
) -> RevisionPlan:
    fixes = [
        {
            "issue_id": issue.issue_id,
            "instruction": issue.suggested_fix,
            "preserve": ["未被该问题指出的既有事实和有效段落"],
            "change": issue.affected_sections or [issue.problem],
            "avoid": ["引入新的 Canon 事实", "扩大未要求修改的范围"],
            "checker_auto_fixable": issue.auto_fixable,
            "must_pause": issue.must_pause,
        }
        for issue in report.issues
        if not issue_requires_pause(issue)
    ]
    plan = RevisionPlan(
        project_id=run.project_id,
        novel_id=run.novel_id,
        chapter_id=run.chapter_id,
        run_id=run.id,
        target_version_id=run.current_version_id,
        goals_json=dumps(["逐项修复连续性报告中的全部非 blocker 问题"]),
        fixes_json=dumps(fixes),
        risk_notes_json=dumps(
            ["修订后必须重新运行 Continuity Checker", "不得覆盖旧 ChapterVersion"]
        ),
        metadata_json=dumps({"report_severity": report.severity}),
    )
    db.add(plan)
    policy.revision_rounds += 1
    run.revision_parent_version_id = run.current_version_id
    run.revision_feedback = (
        "按以下 RevisionPlan 修订全文。保留未涉及内容，只修复列出问题：\n{}"
    ).format(dumps(fixes))
    db.commit()
    db.refresh(plan)
    return plan


def next_state_after_check(
    policy: AutoRunPolicy,
    report: ContinuityCheckerOutput,
) -> Tuple[str, str]:
    if policy is None or policy.mode in {"manual_review", "ai_review_suggest"}:
        return "WAIT_HUMAN_APPROVAL", ""

    threshold = loads(policy.auto_commit_threshold_json, {})
    blocker = any(issue_requires_pause(issue) for issue in report.issues)
    major = any(issue.severity == "major" for issue in report.issues)
    revisable = bool(report.issues) and all(
        not issue_requires_pause(issue)
        for issue in report.issues
    )

    if not report.passed and not report.issues:
        return "PAUSED", "Checker did not pass but returned no actionable issues"
    if blocker:
        return "PAUSED", "Continuity Checker reported a blocker"
    if major and not threshold.get("allow_major", False):
        revision_limit = min(
            policy.max_revision_rounds_per_chapter,
            policy.stop_on_major_after_rounds,
        )
        if revisable and policy.revision_rounds < revision_limit:
            return "BUILD_REVISION_PLAN", ""
        return "PAUSED", "Major issues remain after allowed revision rounds"
    if (
        report.issues
        and revisable
        and policy.revision_rounds < policy.max_revision_rounds_per_chapter
    ):
        return "BUILD_REVISION_PLAN", ""
    if policy.mode in AUTO_COMMIT_MODES:
        return "AUTO_COMMITTING", ""
    return "WAIT_HUMAN_APPROVAL", ""


def resume_state_for_paused_run(
    run: ChapterLoopRun,
    policy: AutoRunPolicy,
) -> str:
    report_data = loads(run.continuity_report_json, {})
    if (
        policy
        and policy.mode in AUTO_MODES
        and run.current_version_id
        and report_data.get("issues")
        and not any(
            issue_requires_pause(issue)
            for issue in report_data.get("issues", [])
        )
        and policy.revision_rounds < policy.max_revision_rounds_per_chapter
    ):
        return "BUILD_REVISION_PLAN"
    return "ASSEMBLE_CONTEXT"


def extend_revision_budget_for_resume(
    run: ChapterLoopRun,
    policy: AutoRunPolicy,
    additional_rounds: int,
) -> bool:
    if not policy or additional_rounds <= 0 or policy.mode not in AUTO_MODES:
        return False
    report_data = loads(run.continuity_report_json, {})
    issues = report_data.get("issues") or []
    if (
        not run.current_version_id
        or not issues
        or any(
            issue_requires_pause(issue)
            for issue in issues
        )
        or policy.revision_rounds < policy.max_revision_rounds_per_chapter
    ):
        return False
    policy.max_revision_rounds_per_chapter += additional_rounds
    return True


def validate_auto_commit(
    db: Session,
    run: ChapterLoopRun,
    policy: AutoRunPolicy,
) -> ChapterVersion:
    version = db.get(ChapterVersion, run.current_version_id)
    if version is None or version.run_id != run.id or version.chapter_id != run.chapter_id:
        raise ValueError("Current ChapterVersion is missing or does not belong to run")
    report = ContinuityCheckerOutput.model_validate(loads(run.continuity_report_json, {}))
    threshold = loads(policy.auto_commit_threshold_json, {})
    if any(issue_requires_pause(issue) for issue in report.issues):
        raise ValueError("Auto Commit is forbidden while blocker issues remain")
    if not threshold.get("allow_major", False) and any(
        issue.severity == "major" for issue in report.issues
    ):
        raise ValueError("Auto Commit threshold forbids major issues")
    writer_calls = db.scalar(
        select(func.count())
        .select_from(ModelCall)
        .where(
            ModelCall.run_id == run.id,
            ModelCall.agent_name.in_(["draft_writer", "revision_writer"]),
            ModelCall.status == "completed",
        )
    )
    checker_calls = db.scalar(
        select(func.count())
        .select_from(ModelCall)
        .where(
            ModelCall.run_id == run.id,
            ModelCall.agent_name == "continuity_checker",
            ModelCall.status == "completed",
        )
    )
    if not writer_calls or not checker_calls:
        raise ValueError("Auto Commit requires completed Writer and Checker logs")
    return version


def commit_version(
    db: Session,
    run: ChapterLoopRun,
    policy: AutoRunPolicy,
) -> dict:
    version = validate_auto_commit(db, run, policy)
    chapter = db.get(Chapter, run.chapter_id)
    if chapter is None:
        raise ValueError("Chapter does not exist")

    backup_id = None
    if chapter.content.strip() and chapter.content != version.content_markdown:
        backup = ChapterVersionManager(db).append_version(
            chapter_id=chapter.id,
            run_id=run.id,
            content_markdown=chapter.content,
            kind="pre_auto_commit_backup",
        )
        backup_id = backup.id
    changed = chapter.content != version.content_markdown
    chapter.content = version.content_markdown
    if changed:
        chapter.version += 1
    chapter.status = "approved"
    run.approved_version_id = version.id
    run.decision_feedback = "AI Auto Commit policy threshold passed"
    run.decided_at = datetime.utcnow()
    db.commit()
    return {
        "approved_version_id": version.id,
        "backup_version_id": backup_id,
        "chapter_content_updated": changed,
        "chapter_version": chapter.version,
    }
