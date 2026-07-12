import json
from typing import Any, Callable, Dict

import httpx

from app.models.entities import ModelProvider
from app.providers.base import ModelAdapter, ModelResult
from app.services.common import loads


def merged_options(provider: ModelProvider, options: Dict[str, Any]) -> Dict[str, Any]:
    merged = loads(provider.default_options_json, {})
    merged.update(options or {})
    merged.pop("context_budget", None)
    return merged


class OpenAICompatibleAdapter(ModelAdapter):
    supports_stream = True

    def __init__(self, provider: ModelProvider):
        self.provider = provider

    def generate_text(self, prompt: str, options: Dict[str, Any]) -> ModelResult:
        settings = merged_options(self.provider, options)
        base_url = self.provider.base_url.rstrip("/")
        url = "{}/chat/completions".format(base_url)
        headers = {"Content-Type": "application/json"}
        if self.provider.api_key:
            headers["Authorization"] = "Bearer {}".format(self.provider.api_key)
        payload = {
            "model": self.provider.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": settings.pop("temperature", 0.7),
            "max_tokens": settings.pop("max_tokens", 1800),
            **settings,
        }
        with httpx.Client(timeout=self.provider.timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("Provider response does not contain choices")
        message = choices[0].get("message") or {}
        text = message.get("content")
        if text is None:
            text = choices[0].get("text", "")
        if not str(text or "").strip():
            reasoning = message.get("reasoning_content") or message.get("reasoning")
            finish_reason = choices[0].get("finish_reason", "")
            if reasoning:
                raise ValueError(
                    "Model used the output budget for reasoning but returned no final content "
                    "(finish_reason={}). Increase max_tokens or disable thinking in the model preset.".format(
                        finish_reason or "unknown"
                    )
                )
            raise ValueError("Provider returned an empty assistant response")
        usage = data.get("usage") or {}
        return ModelResult(
            text=str(text).strip(),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            raw=data,
        )

    def generate_text_stream(
        self,
        prompt: str,
        options: Dict[str, Any],
        on_delta: Callable[[str], None],
    ) -> ModelResult:
        settings = merged_options(self.provider, options)
        base_url = self.provider.base_url.rstrip("/")
        headers = {"Content-Type": "application/json"}
        if self.provider.api_key:
            headers["Authorization"] = "Bearer {}".format(self.provider.api_key)
        payload = {
            "model": self.provider.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": settings.pop("temperature", 0.7),
            "max_tokens": settings.pop("max_tokens", 1800),
            "stream": True,
            **settings,
        }
        chunks = []
        usage = {}
        finish_reason = ""
        with httpx.Client(timeout=self.provider.timeout_seconds) as client:
            with client.stream(
                "POST",
                "{}/chat/completions".format(base_url),
                headers=headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "text/event-stream" not in content_type:
                    response.read()
                    data = response.json()
                    choices = data.get("choices") or []
                    message = choices[0].get("message") or {} if choices else {}
                    text = str(message.get("content") or (choices[0].get("text", "") if choices else ""))
                    if text:
                        on_delta(text)
                    usage = data.get("usage") or {}
                    return ModelResult(
                        text=text.strip(),
                        input_tokens=usage.get("prompt_tokens"),
                        output_tokens=usage.get("completion_tokens"),
                        raw=data,
                    )
                for line in response.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data_text = line[5:].strip()
                    if data_text == "[DONE]":
                        break
                    try:
                        event = json.loads(data_text)
                    except json.JSONDecodeError:
                        continue
                    choices = event.get("choices") or []
                    if choices:
                        choice = choices[0]
                        delta = choice.get("delta") or {}
                        text = delta.get("content")
                        if text is None:
                            text = choice.get("text", "")
                        if text:
                            text = str(text)
                            chunks.append(text)
                            on_delta(text)
                        finish_reason = choice.get("finish_reason") or finish_reason
                    usage = event.get("usage") or usage
        text = "".join(chunks).strip()
        if not text:
            raise ValueError("Provider returned an empty streamed assistant response")
        return ModelResult(
            text=text,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            raw={"stream": True, "finish_reason": finish_reason, "usage": usage},
        )


class OllamaAdapter(ModelAdapter):
    supports_stream = True

    def __init__(self, provider: ModelProvider):
        self.provider = provider

    def generate_text(self, prompt: str, options: Dict[str, Any]) -> ModelResult:
        settings = merged_options(self.provider, options)
        base_url = self.provider.base_url.rstrip("/")
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]
        payload = {
            "model": self.provider.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": settings,
        }
        with httpx.Client(timeout=self.provider.timeout_seconds) as client:
            response = client.post("{}/api/chat".format(base_url), json=payload)
            response.raise_for_status()
            data = response.json()
        text = (data.get("message") or {}).get("content", "")
        return ModelResult(
            text=str(text).strip(),
            input_tokens=data.get("prompt_eval_count"),
            output_tokens=data.get("eval_count"),
            raw=data,
        )

    def generate_text_stream(
        self,
        prompt: str,
        options: Dict[str, Any],
        on_delta: Callable[[str], None],
    ) -> ModelResult:
        settings = merged_options(self.provider, options)
        base_url = self.provider.base_url.rstrip("/")
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]
        payload = {
            "model": self.provider.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "options": settings,
        }
        chunks = []
        final = {}
        with httpx.Client(timeout=self.provider.timeout_seconds) as client:
            with client.stream("POST", "{}/api/chat".format(base_url), json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    event = json.loads(line)
                    text = str((event.get("message") or {}).get("content", ""))
                    if text:
                        chunks.append(text)
                        on_delta(text)
                    final = event
        text = "".join(chunks).strip()
        if not text:
            raise ValueError("Ollama returned an empty streamed response")
        return ModelResult(
            text=text,
            input_tokens=final.get("prompt_eval_count"),
            output_tokens=final.get("eval_count"),
            raw={"stream": True, "done_reason": final.get("done_reason", "")},
        )


class LMStudioAdapter(ModelAdapter):
    supports_stream = True

    def __init__(self, provider: ModelProvider):
        self.provider = provider

    def generate_text(self, prompt: str, options: Dict[str, Any]) -> ModelResult:
        settings = merged_options(self.provider, options)
        force_no_think = bool(settings.pop("force_no_think", False))
        settings.pop("reasoning", None)
        if not force_no_think:
            return OpenAICompatibleAdapter(self.provider).generate_text(prompt, options)

        base_url = self.provider.base_url.rstrip("/")
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]
        max_tokens = settings.pop("max_output_tokens", settings.pop("max_tokens", 2400))
        chatml_prompt = (
            "<|im_start|>system\n"
            "你是本地小说创作助手。严格执行用户要求，只输出可直接使用的最终结果。"
            "<|im_end|>\n"
            "<|im_start|>user\n"
            "{}"
            "<|im_end|>\n"
            "<|im_start|>assistant\n"
            "<think>\n\n</think>\n\n"
        ).format(prompt)
        payload = {
            "model": self.provider.model,
            "prompt": chatml_prompt,
            "stream": False,
            "max_tokens": max_tokens,
            "temperature": settings.pop("temperature", 0.7),
            "stop": ["<|im_end|>"],
            **settings,
        }
        with httpx.Client(timeout=self.provider.timeout_seconds) as client:
            response = client.post("{}/v1/completions".format(base_url), json=payload)
            response.raise_for_status()
            data = response.json()
        choices = data.get("choices") or []
        text = str(choices[0].get("text", "") if choices else "").strip()
        if not text:
            raise ValueError("LM Studio returned an empty text completion")
        usage = data.get("usage") or {}
        return ModelResult(
            text=text,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            raw=data,
        )

    def generate_text_stream(
        self,
        prompt: str,
        options: Dict[str, Any],
        on_delta: Callable[[str], None],
    ) -> ModelResult:
        settings = merged_options(self.provider, options)
        force_no_think = bool(settings.pop("force_no_think", False))
        if not force_no_think:
            return OpenAICompatibleAdapter(self.provider).generate_text_stream(
                prompt,
                options,
                on_delta,
            )
        base_url = self.provider.base_url.rstrip("/")
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]
        max_tokens = settings.pop("max_output_tokens", settings.pop("max_tokens", 2400))
        settings.pop("reasoning", None)
        chatml_prompt = (
            "<|im_start|>system\n"
            "你是本地小说创作助手。严格执行用户要求，只输出可直接使用的最终结果。"
            "<|im_end|>\n"
            "<|im_start|>user\n{}<|im_end|>\n"
            "<|im_start|>assistant\n<think>\n\n</think>\n\n"
        ).format(prompt)
        payload = {
            "model": self.provider.model,
            "prompt": chatml_prompt,
            "stream": True,
            "max_tokens": max_tokens,
            "temperature": settings.pop("temperature", 0.7),
            "stop": ["<|im_end|>"],
            **settings,
        }
        chunks = []
        usage = {}
        finish_reason = ""
        with httpx.Client(timeout=self.provider.timeout_seconds) as client:
            with client.stream(
                "POST",
                "{}/v1/completions".format(base_url),
                json=payload,
            ) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "text/event-stream" not in content_type:
                    response.read()
                    data = response.json()
                    choices = data.get("choices") or []
                    text = str(choices[0].get("text", "") if choices else "")
                    if text:
                        on_delta(text)
                    usage = data.get("usage") or {}
                    return ModelResult(
                        text=text.strip(),
                        input_tokens=usage.get("prompt_tokens"),
                        output_tokens=usage.get("completion_tokens"),
                        raw=data,
                    )
                for line in response.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data_text = line[5:].strip()
                    if data_text == "[DONE]":
                        break
                    event = json.loads(data_text)
                    choices = event.get("choices") or []
                    choice = choices[0] if choices else {}
                    text = str(choice.get("text", ""))
                    if text:
                        chunks.append(text)
                        on_delta(text)
                    finish_reason = choice.get("finish_reason") or finish_reason
                    usage = event.get("usage") or usage
        text = "".join(chunks).strip()
        if not text:
            raise ValueError("LM Studio returned an empty streamed text completion")
        return ModelResult(
            text=text,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            raw={"stream": True, "finish_reason": finish_reason, "usage": usage},
        )


class KoboldCppAdapter(ModelAdapter):
    def __init__(self, provider: ModelProvider):
        self.provider = provider

    def generate_text(self, prompt: str, options: Dict[str, Any]) -> ModelResult:
        if self.provider.base_url.rstrip("/").endswith("/v1"):
            return OpenAICompatibleAdapter(self.provider).generate_text(prompt, options)
        settings = merged_options(self.provider, options)
        payload = {
            "prompt": prompt,
            "max_length": settings.pop("max_tokens", settings.pop("max_length", 1800)),
            "temperature": settings.pop("temperature", 0.7),
            "top_p": settings.pop("top_p", 0.9),
            **settings,
        }
        url = "{}/api/v1/generate".format(self.provider.base_url.rstrip("/"))
        with httpx.Client(timeout=self.provider.timeout_seconds) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
        results = data.get("results") or []
        if not results:
            raise ValueError("KoboldCpp response does not contain results")
        return ModelResult(text=str(results[0].get("text", "")).strip(), raw=data)


def get_adapter(provider: ModelProvider) -> ModelAdapter:
    provider_type = provider.provider_type.lower()
    if provider_type == "lm_studio":
        return LMStudioAdapter(provider)
    if provider_type == "ollama":
        return OllamaAdapter(provider)
    if provider_type == "koboldcpp":
        return KoboldCppAdapter(provider)
    if provider_type in {
        "llama_cpp",
        "omlx",
        "text_generation_webui",
        "openai_compatible",
        "cloud_openai_compatible",
    }:
        return OpenAICompatibleAdapter(provider)
    raise ValueError("Unsupported provider type: {}".format(provider.provider_type))
