import json
import re
from dataclasses import dataclass
from typing import Optional


class DraftTextGuardError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class DraftTextResult:
    content_markdown: str
    warning: str = ""
    extraction_mode: str = "plain_text"


def _extract_legacy_json(text: str) -> Optional[DraftTextResult]:
    cleaned = str(text or "").strip()
    try:
        payload = json.loads(cleaned)
        if isinstance(payload, dict) and isinstance(payload.get("draft_markdown"), str):
            return DraftTextResult(
                content_markdown=payload["draft_markdown"],
                warning="LEGACY_DRAFT_JSON_EXTRACTED",
                extraction_mode="valid_json",
            )
    except json.JSONDecodeError:
        pass

    marker = re.search(r'"draft_markdown"\s*:\s*', cleaned)
    if marker is None:
        return None
    remainder = cleaned[marker.end():].lstrip()
    if remainder.startswith('"'):
        try:
            value, _end = json.JSONDecoder().raw_decode(remainder)
            if isinstance(value, str):
                return DraftTextResult(
                    content_markdown=value,
                    warning="DRAFT_JSON_FALLBACK_USED",
                    extraction_mode="invalid_json_field",
                )
        except json.JSONDecodeError:
            pass

    boundary = re.search(
        r'",?\s*"(?:scene_breakdown|self_notes|chapter_id)"\s*:',
        remainder,
        flags=re.DOTALL,
    )
    candidate = remainder[:boundary.start()] if boundary else remainder
    candidate = candidate.strip().lstrip('"').rstrip().rstrip("},").rstrip('"').strip()
    if not candidate:
        return None
    candidate = candidate.replace(r"\n", "\n").replace(r"\"", '"').replace(r"\\", "\\")
    return DraftTextResult(
        content_markdown=candidate,
        warning="DRAFT_JSON_FALLBACK_USED",
        extraction_mode="invalid_json_field",
    )


class DraftTextGuard:
    def __init__(self, min_characters: int = 20):
        self.min_characters = min_characters

    def validate(self, text: str) -> DraftTextResult:
        raw = str(text or "").strip()
        if not raw:
            raise DraftTextGuardError("EMPTY_CONTENT", "Draft writer returned empty content")

        extracted = _extract_legacy_json(raw)
        result = extracted or DraftTextResult(content_markdown=raw)
        content = result.content_markdown.strip()
        lowered = content.lower()

        if not content:
            raise DraftTextGuardError("EMPTY_CONTENT", "Draft writer returned empty content")
        if len(content) < self.min_characters:
            raise DraftTextGuardError(
                "TOO_SHORT",
                "Draft writer returned only {} characters; expected at least {}".format(
                    len(content),
                    self.min_characters,
                ),
            )
        refusal_prefixes = (
            "抱歉",
            "对不起",
            "我无法",
            "作为ai",
            "作为一个ai",
            "i'm sorry",
            "i am sorry",
            "i can't",
            "i cannot",
        )
        if lowered.startswith(refusal_prefixes):
            raise DraftTextGuardError("MODEL_REFUSAL", "Model refused to write the chapter draft")
        error_prefixes = ("error:", "exception:", "model error", "provider error", "模型错误", "服务错误")
        if lowered.startswith(error_prefixes):
            raise DraftTextGuardError("INVALID_DRAFT_TEXT", "Model returned an error message instead of fiction")
        leak_markers = (
            "AGENT: draft_writer",
            "AGENT: revision_writer",
            "章节 ID：",
            "硬规则：",
            "只输出章节正文 Markdown",
        )
        if any(marker in content for marker in leak_markers):
            raise DraftTextGuardError("PROMPT_LEAK", "Draft contains prompt or system instruction text")
        if "```" in content:
            raise DraftTextGuardError("INVALID_DRAFT_TEXT", "Draft must not be wrapped in a code fence")
        if extracted is None and content.startswith("{") and '"draft_markdown"' in content:
            raise DraftTextGuardError(
                "INVALID_DRAFT_TEXT",
                "Malformed draft JSON wrapper could not be safely converted to chapter text",
            )

        result.content_markdown = content
        return result
