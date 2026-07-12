import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import ModelProvider


LM_STUDIO_CLI = Path.home() / ".lmstudio" / "bin" / "lms"
OMLX_CLI = Path.home() / ".omlx" / "bin" / "omlx"


class ProviderUnavailableError(RuntimeError):
    code = "PROVIDER_UNAVAILABLE"

    def __init__(self, message: str, attempts: List[str]):
        super().__init__(message)
        self.attempts = attempts


@dataclass
class ProviderResolution:
    provider: ModelProvider
    attempts: List[str]
    fallback_from_id: Optional[str] = None


def provider_socket_available(provider: ModelProvider, timeout: float = 0.5) -> bool:
    parsed = urlparse(provider.base_url)
    host = parsed.hostname
    if not host:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def provider_model_available(provider: ModelProvider) -> bool:
    if not provider_socket_available(provider):
        return False
    provider_type = provider.provider_type.lower()
    try:
        with httpx.Client(timeout=2) as client:
            if provider_type == "ollama":
                base_url = provider.base_url.rstrip("/")
                if base_url.endswith("/v1"):
                    base_url = base_url[:-3]
                data = client.get("{}/api/tags".format(base_url)).json()
                names = {
                    str(item.get("name") or item.get("model") or "")
                    for item in data.get("models", [])
                }
                return provider.model in names
            if provider_type in {"lm_studio", "llama_cpp", "omlx"}:
                base_url = provider.base_url.rstrip("/")
                if not base_url.endswith("/v1"):
                    base_url += "/v1"
                data = client.get("{}/models".format(base_url)).json()
                names = {
                    str(item.get("id") or item.get("model") or item.get("name") or "")
                    for item in (data.get("data") or data.get("models") or [])
                }
                return provider.model in names
    except (httpx.HTTPError, ValueError, TypeError):
        return False
    return True


def _run(args: List[str], timeout: int) -> str:
    completed = subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = (completed.stdout + "\n" + completed.stderr).strip()
    if completed.returncode != 0:
        raise RuntimeError(output or "command exited with {}".format(completed.returncode))
    return output[-1000:]


def _wait_available(provider: ModelProvider, seconds: int = 20) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if provider_model_available(provider):
            return True
        time.sleep(0.5)
    return False


def attempt_local_recovery(provider: ModelProvider, context_budget: int) -> List[str]:
    attempts = []
    provider_type = provider.provider_type.lower()
    looks_like_lm_studio = (
        provider_type == "lm_studio"
        or "lm studio" in provider.name.lower()
        or urlparse(provider.base_url).port == 1234
    )
    try:
        if looks_like_lm_studio:
            if not LM_STUDIO_CLI.exists():
                return ["LM Studio CLI not found"]
            attempts.append("starting LM Studio local server")
            _run(
                [str(LM_STUDIO_CLI), "server", "start", "--bind", "127.0.0.1", "-p", "1234"],
                60,
            )
            attempts.append("loading LM Studio model {}".format(provider.model))
            _run(
                [
                    str(LM_STUDIO_CLI),
                    "load",
                    provider.model,
                    "--context-length",
                    str(max(4096, min(131072, context_budget))),
                    "--identifier",
                    provider.model,
                    "--yes",
                ],
                900,
            )
        elif provider_type == "ollama":
            attempts.append("starting Ollama application")
            _run(["open", "-gja", "Ollama"], 30)
        elif provider_type == "omlx":
            if not OMLX_CLI.exists():
                return ["oMLX CLI not found"]
            attempts.append("starting oMLX multi-model server")
            _run([str(OMLX_CLI), "start", "--timeout", "60"], 90)
        elif provider_type == "llama_cpp" and urlparse(provider.base_url).port == 18081:
            attempts.append("restarting managed llama.cpp service")
            _run(
                ["launchctl", "kickstart", "-k", "gui/{}/com.novel-local-ai.llama".format(
                    subprocess.check_output(["id", "-u"], text=True).strip()
                )],
                30,
            )
        else:
            attempts.append("no managed start command for {}".format(provider.provider_type))
            return attempts
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        attempts.append("recovery failed: {}".format(exc))
        return attempts

    if _wait_available(provider):
        attempts.append("provider became reachable")
    else:
        attempts.append("provider still unreachable after recovery")
    return attempts


def resolve_provider(
    db: Session,
    preferred: ModelProvider,
    context_budget: int,
) -> ProviderResolution:
    if provider_model_available(preferred):
        return ProviderResolution(provider=preferred, attempts=["selected provider reachable"])

    attempts = ["selected provider {} is unreachable".format(preferred.name)]
    attempts.extend(attempt_local_recovery(preferred, context_budget))
    if provider_model_available(preferred):
        preferred.last_test_status = "ok"
        preferred.last_test_message = "Recovered automatically before Loop run"
        db.flush()
        return ProviderResolution(provider=preferred, attempts=attempts)

    preferred.last_test_status = "failed"
    preferred.last_test_message = "; ".join(attempts)[-1000:]
    candidates = list(
        db.scalars(
            select(ModelProvider).where(
                ModelProvider.enabled.is_(True),
                ModelProvider.id != preferred.id,
            )
        ).all()
    )
    candidates.sort(
        key=lambda item: (
            item.last_test_status != "ok",
            item.provider_type not in {"lm_studio", "llama_cpp", "ollama"},
            item.created_at,
        )
    )
    for candidate in candidates:
        if provider_model_available(candidate):
            candidate.last_test_status = "ok"
            candidate.last_test_message = "Selected as automatic local fallback"
            attempts.append("fallback provider selected: {}".format(candidate.name))
            db.flush()
            return ProviderResolution(
                provider=candidate,
                attempts=attempts,
                fallback_from_id=preferred.id,
            )
    db.flush()
    raise ProviderUnavailableError(
        "所选本地模型服务未启动，自动恢复失败，也没有其他在线的本地 Provider。",
        attempts,
    )
