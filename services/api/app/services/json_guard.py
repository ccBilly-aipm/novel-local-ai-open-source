import json
import re
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError


SchemaT = TypeVar("SchemaT", bound=BaseModel)


class JsonGuardError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def strip_json_fence(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def extract_first_json_object(text: str) -> str:
    cleaned = strip_json_fence(text)
    start = cleaned.find("{")
    if start < 0:
        return cleaned
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(cleaned)):
        character = cleaned[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return cleaned[start:index + 1]
    return cleaned[start:]


class JsonGuard:
    def parse_and_validate(self, text: str, schema: Type[SchemaT]) -> SchemaT:
        cleaned = extract_first_json_object(text)
        if not cleaned:
            raise JsonGuardError("EMPTY_MODEL_OUTPUT", "Model returned an empty structured response")
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise JsonGuardError(
                "JSON_PARSE_ERROR",
                "Model output is not valid JSON: {}".format(exc),
            ) from exc
        try:
            return schema.model_validate(payload)
        except ValidationError as exc:
            raise JsonGuardError(
                "SCHEMA_VALIDATION_ERROR",
                "Model JSON failed Pydantic validation: {}".format(exc),
            ) from exc
