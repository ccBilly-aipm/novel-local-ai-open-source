from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


@dataclass
class ModelResult:
    text: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    raw: Optional[Dict[str, Any]] = None


class ModelAdapter:
    supports_stream = False

    def generate_text(self, prompt: str, options: Dict[str, Any]) -> ModelResult:
        raise NotImplementedError

    def generate_text_stream(
        self,
        prompt: str,
        options: Dict[str, Any],
        on_delta: Callable[[str], None],
    ) -> ModelResult:
        result = self.generate_text(prompt, options)
        if result.text:
            on_delta(result.text)
        return result
