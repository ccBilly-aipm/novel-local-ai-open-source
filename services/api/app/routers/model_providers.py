import subprocess
import time
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.entities import ModelProvider
from app.providers.adapters import get_adapter
from app.schemas.entities import (
    ModelProviderCreate,
    ModelProviderOut,
    ModelProviderUpdate,
    LocalModelInventory,
    LMStudioActionRequest,
    LMStudioActionResult,
    ProviderTestResult,
)
from app.services.common import dumps, get_or_404
from app.services.local_model_inventory import (
    build_local_model_inventory,
    sync_local_model_providers,
)


router = APIRouter(prefix="/model-providers", tags=["model-providers"])
LM_STUDIO_CLI = Path.home() / ".lmstudio" / "bin" / "lms"


@router.post("", response_model=ModelProviderOut, status_code=status.HTTP_201_CREATED)
def create_provider(payload: ModelProviderCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude={"default_options"})
    provider = ModelProvider(**data, default_options_json=dumps(payload.default_options))
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return provider


@router.get("", response_model=List[ModelProviderOut])
def list_providers(db: Session = Depends(get_db)):
    return list(db.scalars(select(ModelProvider).order_by(ModelProvider.created_at)).all())


@router.get("/local-inventory", response_model=LocalModelInventory)
def local_inventory(db: Session = Depends(get_db)):
    return build_local_model_inventory(db)


@router.post("/sync-local", response_model=List[ModelProviderOut])
def sync_local_providers(db: Session = Depends(get_db)):
    return sync_local_model_providers(db)


def run_lm_studio(args, timeout=900):
    if not LM_STUDIO_CLI.exists():
        return LMStudioActionResult(ok=False, message="未找到 LM Studio CLI")
    try:
        completed = subprocess.run(
            [str(LM_STUDIO_CLI)] + args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (completed.stdout + "\n" + completed.stderr).strip()
        return LMStudioActionResult(
            ok=completed.returncode == 0,
            message="操作成功" if completed.returncode == 0 else "LM Studio 操作失败",
            output=output[-4000:],
        )
    except subprocess.TimeoutExpired:
        return LMStudioActionResult(ok=False, message="LM Studio 操作超时")
    except OSError as exc:
        return LMStudioActionResult(ok=False, message=str(exc))


@router.post("/lm-studio/server/start", response_model=LMStudioActionResult)
def start_lm_studio_server():
    return run_lm_studio(["server", "start", "--bind", "127.0.0.1", "-p", "1234"], timeout=60)


@router.post("/lm-studio/models/load", response_model=LMStudioActionResult)
def load_lm_studio_model(payload: LMStudioActionRequest):
    start_result = run_lm_studio(["server", "start", "--bind", "127.0.0.1", "-p", "1234"], timeout=60)
    if not start_result.ok and "already" not in start_result.output.lower():
        return start_result
    identifier = payload.identifier.strip() or payload.model_key
    return run_lm_studio(
        [
            "load",
            payload.model_key,
            "--context-length",
            str(payload.context_length),
            "--identifier",
            identifier,
            "--yes",
        ]
    )


@router.post("/lm-studio/models/unload", response_model=LMStudioActionResult)
def unload_lm_studio_model(payload: LMStudioActionRequest):
    return run_lm_studio(["unload", payload.identifier.strip() or payload.model_key], timeout=120)


@router.patch("/{provider_id}", response_model=ModelProviderOut)
def update_provider(
    provider_id: str,
    payload: ModelProviderUpdate,
    db: Session = Depends(get_db),
):
    provider = get_or_404(db, ModelProvider, provider_id, "Model provider")
    data = payload.model_dump(exclude_unset=True)
    if "default_options" in data:
        provider.default_options_json = dumps(data.pop("default_options"))
    for key, value in data.items():
        setattr(provider, key, value)
    db.commit()
    db.refresh(provider)
    return provider


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider(provider_id: str, db: Session = Depends(get_db)):
    provider = get_or_404(db, ModelProvider, provider_id, "Model provider")
    db.delete(provider)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{provider_id}/test", response_model=ProviderTestResult)
def test_provider(provider_id: str, db: Session = Depends(get_db)):
    provider = get_or_404(db, ModelProvider, provider_id, "Model provider")
    started = time.perf_counter()
    try:
        result = get_adapter(provider).generate_text(
            "只回复 OK 两个字母，不要解释。",
            {"max_tokens": 512, "temperature": 0},
        )
        latency = int((time.perf_counter() - started) * 1000)
        provider.last_test_status = "ok"
        provider.last_test_message = result.text[:300]
        db.commit()
        return ProviderTestResult(
            ok=True,
            message="Connection and generation succeeded",
            latency_ms=latency,
            response_preview=result.text[:300],
        )
    except Exception as exc:
        latency = int((time.perf_counter() - started) * 1000)
        provider.last_test_status = "failed"
        provider.last_test_message = str(exc)
        db.commit()
        return ProviderTestResult(ok=False, message=str(exc), latency_ms=latency)
