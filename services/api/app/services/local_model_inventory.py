import json
import os
import platform
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import ModelProvider


HOME = Path.home()
GGUF_ROOTS = [
    HOME / "Downloads" / "llama.cpp-models",
    HOME / "models",
    HOME / "Models",
]
OLLAMA_MANIFEST_ROOT = HOME / ".ollama" / "models" / "manifests"
OLLAMA_BLOB_ROOT = HOME / ".ollama" / "models" / "blobs"
HF_HUB_ROOT = HOME / ".cache" / "huggingface" / "hub"
OMLX_ROOT = HOME / ".omlx"
OMLX_MODELS_ROOT = OMLX_ROOT / "models"
LM_STUDIO_ROOT = HOME / ".lmstudio"
LM_STUDIO_MODELS_ROOT = LM_STUDIO_ROOT / "models"
LM_STUDIO_CLI = LM_STUDIO_ROOT / "bin" / "lms"


def size_label(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024 or unit == "TB":
            return "{:.1f} {}".format(value, unit) if unit in {"GB", "TB"} else "{:.0f} {}".format(value, unit)
        value /= 1024
    return "{} B".format(size_bytes)


def safe_file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def safe_tree_size(root: Path) -> int:
    total = 0
    try:
        for path in root.rglob("*"):
            if path.is_file() and not path.is_symlink():
                total += safe_file_size(path)
    except OSError:
        return total
    return total


def run_text(command: List[str]) -> str:
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def system_hardware() -> Dict[str, Any]:
    memory_bytes = 0
    try:
        memory_bytes = int(run_text(["sysctl", "-n", "hw.memsize"]) or 0)
    except ValueError:
        pass
    disk = shutil.disk_usage(HOME)
    chip = run_text(["sysctl", "-n", "machdep.cpu.brand_string"]) or platform.machine()
    return {
        "chip": chip,
        "memory_gb": round(memory_bytes / (1024 ** 3)) if memory_bytes else 0,
        "disk_free_gb": round(disk.free / (1024 ** 3)),
        "platform": platform.platform(),
    }


def recommendation_for(name: str, state: str, source: str) -> Dict[str, Any]:
    lower = name.lower()
    if state == "incomplete":
        return {
            "level": "unavailable",
            "label": "不可用",
            "tasks": [],
            "reason": "下载未完成，不能加载。",
            "setup": "删除残留或重新完成下载。",
            "options": {},
        }
    if any(term in lower for term in ["whisper"]):
        return {
            "level": "auxiliary",
            "label": "辅助模型",
            "tasks": ["语音转写"],
            "reason": "这是语音识别模型，不负责小说正文。",
            "setup": "只在未来加入语音输入时使用。",
            "options": {},
        }
    if any(term in lower for term in ["bge-", "minilm", "sentence-transformers", "embedding"]):
        return {
            "level": "auxiliary",
            "label": "辅助模型",
            "tasks": ["向量检索", "未来 RAG"],
            "reason": "这是嵌入/检索模型，不能生成小说正文。",
            "setup": "第二阶段实现 RAG 时再接入。",
            "options": {},
        }
    if source == "LM Studio" and any(term in lower for term in ["35b-a3b", "40b"]):
        review_focused = any(term in lower for term in ["reasoning", "thinking", "opus"])
        return {
            "level": "primary",
            "label": "LM Studio 主模型",
            "tasks": ["复杂审稿", "故事框架"] if review_focused else ["章节正文", "故事框架", "角色与世界观"],
            "reason": (
                "本机已有的大型精选模型。名称显示它偏推理/思考，优先用于规划和审稿；具体中文小说质量仍需固定样稿实测。"
                if review_focused
                else "本机已有的 35B-A3B/40B 模型，适合高质量生成候选；微调来源复杂，需用固定样稿比较稳定性。"
            ),
            "setup": "先在模型页加载到 LM Studio，再创建或选择 1234/v1 Provider。建议从 16K 上下文开始。",
            "options": {
                "temperature": 0.75 if review_focused else 0.82,
                "top_p": 0.95,
                "max_tokens": 3200,
                "context_budget": 16000,
            },
        }
    if source == "LM Studio" and "27b" in lower:
        return {
            "level": "secondary",
            "label": "LM Studio 均衡模型",
            "tasks": ["章节正文", "大纲扩展", "摘要与审稿"],
            "reason": "27B 模型在 64GB 统一内存上更易保留上下文和响应速度，适合先做日常主力候选。",
            "setup": "在 LM Studio 加载后创建 Provider；先比较 Q4/Q5 或 MLX 版本的速度、内存与文风。",
            "options": {
                "temperature": 0.8,
                "top_p": 0.95,
                "max_tokens": 3200,
                "context_budget": 16000,
            },
        }
    if "qwen3.5" in lower and ("27b" in lower or "27.8b" in lower):
        return {
            "level": "primary",
            "label": "首选主模型",
            "tasks": ["章节正文", "续写改写", "复杂结构分析", "高质量审稿"],
            "reason": "本机已安装的最强文本模型；27.8B Q4_K_M 与 64GB 统一内存匹配。",
            "setup": "通过 Ollama 按需启动。正文建议 12K-20K 上下文，审稿降低温度。",
            "options": {
                "writing": {"temperature": 0.8, "top_p": 0.95, "max_tokens": 3200},
                "review": {"temperature": 0.2, "top_p": 0.9, "max_tokens": 1200},
                "context_budget": 16000,
            },
        }
    if "qwen3" in lower and "8b" in lower:
        return {
            "level": "secondary",
            "label": "快速副模型",
            "tasks": ["章节摘要", "人物状态", "大纲扩展", "轻量审稿"],
            "reason": "8B 4-bit 速度与质量平衡，适合高频结构化任务。",
            "setup": "权重完整，但当前缺少 MLX-LM 服务；安装运行时或改用 GGUF/Ollama 版本。",
            "options": {
                "temperature": 0.2,
                "max_tokens": 1000,
                "context_budget": 10000,
            },
        }
    if "0.5b" in lower:
        return {
            "level": "test",
            "label": "仅联调",
            "tasks": ["连接测试", "短格式验证"],
            "reason": "参数量过小且是 Coder 模型，无法承担稳定的中文小说正文。",
            "setup": "保留为快速健康检查，不建议用于正式章节。",
            "options": {"temperature": 0, "max_tokens": 64, "context_budget": 1024},
        }
    if "coder" in lower:
        return {
            "level": "test",
            "label": "不建议写作",
            "tasks": ["代码或格式任务"],
            "reason": "Coder 模型的训练重点不是叙事文本。",
            "setup": "小说写作优先改用通用 Instruct 模型。",
            "options": {},
        }
    return {
        "level": "candidate",
        "label": "待实测",
        "tasks": ["通用生成"],
        "reason": "已发现本地权重，但尚未建立小说质量基准。",
        "setup": "先进行 2-3 章固定大纲对比测试，再决定用途。",
        "options": {},
    }


def _model_profile(name: str, size_bytes: int, details: Dict[str, Any]) -> Dict[str, Any]:
    lower = name.lower()
    size_gib = size_bytes / (1024 ** 3) if size_bytes else 0
    if size_gib and size_gib < 18:
        recommended_context = 32768
    elif size_gib and size_gib < 26:
        recommended_context = 24576
    elif size_gib:
        recommended_context = 16384
    else:
        recommended_context = 8192
    if "0.5b" in lower:
        recommended_context = 4096

    context_overhead = 0.8 if recommended_context <= 8192 else 1.5 if recommended_context <= 16384 else 2.5
    runtime_low = max(1, int(size_gib * 1.10 + context_overhead + 2.5 + 0.999))
    runtime_high = max(runtime_low + 1, int(runtime_low * 1.18 + 0.999))

    is_qwen36 = "qwen3.6" in lower or "qwopus3.6" in lower
    is_reasoning = any(term in lower for term in ["reasoning", "thinking", "qwopus", "opus"])
    if is_qwen36 and is_reasoning:
        default_options: Dict[str, Any] = {
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 20,
            "min_p": 0.0,
            "presence_penalty": 0.0,
            "repetition_penalty": 1.0,
            "max_tokens": 8192,
        }
        defaults_source = "Qwen3.6 官方 thinking 参数；本应用将输出上限保守设为 8K"
    elif is_qwen36 or "qwen3.5" in lower:
        default_options = {
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 20,
            "min_p": 0.0,
            "presence_penalty": 1.5,
            "repetition_penalty": 1.0,
            "max_tokens": 8192,
            "force_no_think": True,
        }
        defaults_source = "Qwen3.6 官方 non-thinking 参数；本应用将输出上限保守设为 8K"
    elif "0.5b" in lower:
        default_options = {"temperature": 0, "max_tokens": 128}
        defaults_source = "仅用于本地连接健康检查"
    else:
        default_options = {
            "temperature": 0.8,
            "top_p": 0.95,
            "max_tokens": 8192,
        }
        defaults_source = "模型卡未提供统一小说参数，采用应用保守长文本基线"

    repository = str(details.get("repository") or "")
    return {
        "recommended_context_length": recommended_context,
        "recommended_output_tokens": int(default_options.get("max_tokens", 8192)),
        "runtime_memory_gb_estimate": "{}-{} GB".format(runtime_low, runtime_high),
        "runtime_memory_note": "按本机 64GB 统一内存、模型权重、运行时开销和推荐上下文估算；实际值受并发与 KV cache 影响。",
        "default_options": default_options,
        "defaults_source": defaults_source,
        "model_card_url": "https://huggingface.co/{}".format(repository) if "/" in repository else "",
    }


def provider_template(
    name: str,
    source: str,
    profile: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    lower = name.lower()
    defaults = dict((profile or {}).get("default_options") or {})
    if source == "LM Studio":
        return {
            "name": "LM Studio · {}".format(name),
            "provider_type": "lm_studio",
            "base_url": "http://127.0.0.1:1234/v1",
            "model": name,
            "default_options": defaults or {"temperature": 0.8, "top_p": 0.95, "max_tokens": 8192},
            "timeout_seconds": 900,
            "enabled": True,
        }
    if source == "oMLX":
        defaults.pop("force_no_think", None)
        if "qwen" in lower and not any(term in lower for term in ["reasoning", "thinking", "qwopus", "opus"]):
            defaults["chat_template_kwargs"] = {"enable_thinking": False}
        return {
            "name": "oMLX · {}".format(name),
            "provider_type": "omlx",
            # oMLX 服务端口是 8003（8000 是本应用 api 自己的端口，写成 8000 会连到 api 上必失败）。
            "base_url": "http://127.0.0.1:8003/v1",
            "model": name,
            "default_options": defaults or {"temperature": 0.8, "top_p": 0.95, "max_tokens": 8192},
            "timeout_seconds": 900,
            "enabled": True,
        }
    if source == "ollama":
        defaults.pop("force_no_think", None)
        return {
            "name": "Ollama · {}".format(name),
            "provider_type": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "model": name,
            "default_options": {
                **(defaults or {"temperature": 0.8, "top_p": 0.95, "max_tokens": 8192}),
                "num_ctx": int((profile or {}).get("recommended_context_length") or 16384),
            },
            "timeout_seconds": 600,
            "enabled": True,
        }
    if source == "llama.cpp" and "qwen2.5-coder-0.5b" in lower:
        return {
            "name": "本机 llama.cpp",
            "provider_type": "llama_cpp",
            "base_url": "http://127.0.0.1:18081/v1",
            "model": "qwen2.5-coder-0.5b-q4km",
            "default_options": defaults or {"temperature": 0, "max_tokens": 128},
            "timeout_seconds": 120,
            "enabled": True,
        }
    return None


def make_model(
    *,
    model_id: str,
    name: str,
    source: str,
    model_format: str,
    size_bytes: int,
    path: str,
    state: str,
    current: bool = False,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    enriched_details = dict(details or {})
    profile = _model_profile(name, size_bytes, enriched_details)
    enriched_details.update(profile)
    recommendation = recommendation_for(name, state, source)
    if recommendation["level"] not in {"auxiliary", "unavailable"}:
        recommendation["options"] = {
            **profile["default_options"],
            "context_budget": profile["recommended_context_length"],
        }
    return {
        "id": model_id,
        "name": name,
        "source": source,
        "format": model_format,
        "size_bytes": size_bytes,
        "size_label": size_label(size_bytes),
        "path": path,
        "state": state,
        "current": current,
        "usable": state in {"running", "installed"} and recommendation["level"] not in {"auxiliary"},
        "recommendation": recommendation,
        "details": enriched_details,
        "provider_template": provider_template(name, source, profile),
    }


def loaded_models() -> Dict[str, str]:
    loaded: Dict[str, str] = {}
    endpoints = {
        "llama.cpp": "http://127.0.0.1:18081/v1/models",
        "ollama": "http://127.0.0.1:11434/api/tags",
        "oMLX": "http://127.0.0.1:8003/v1/models",
    }
    for source, url in endpoints.items():
        try:
            response = httpx.get(url, timeout=1.5)
            response.raise_for_status()
            data = response.json()
            items = data.get("models", []) if source == "ollama" else data.get("data", [])
            for item in items:
                name = str(item.get("id") or item.get("name") or item.get("model") or "")
                if name:
                    loaded[name] = source
        except Exception:
            continue
    return loaded


def lm_studio_json(command: List[str]) -> List[Dict[str, Any]]:
    if not LM_STUDIO_CLI.exists():
        return []
    try:
        completed = subprocess.run(
            [str(LM_STUDIO_CLI)] + command,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if completed.returncode != 0:
            return []
        data = json.loads(completed.stdout or "[]")
        return data if isinstance(data, list) else []
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return []


def scan_lm_studio() -> List[Dict[str, Any]]:
    disk_models = lm_studio_json(["ls", "--json"])
    loaded_entries = lm_studio_json(["ps", "--json"])
    loaded_names = {
        str(
            item.get("identifier")
            or item.get("modelKey")
            or item.get("model")
            or item.get("path")
            or ""
        ).lower()
        for item in loaded_entries
    }
    loaded_contexts = {
        str(item.get("identifier") or item.get("modelKey") or "").lower(): item.get("contextLength")
        for item in loaded_entries
    }
    result: List[Dict[str, Any]] = []
    server_running = False
    try:
        server_running = httpx.get("http://127.0.0.1:1234/v1/models", timeout=1).is_success
    except Exception:
        pass
    for item in disk_models:
        if item.get("type") != "llm":
            continue
        model_key = str(item.get("modelKey") or item.get("displayName") or item.get("path") or "")
        path_value = str(item.get("path") or "")
        current = any(
            loaded_name
            and (
                loaded_name == model_key.lower()
                or model_key.lower() in loaded_name
                or path_value.lower() in loaded_name
            )
            for loaded_name in loaded_names
        )
        quantization = item.get("quantization") or {}
        quantization_name = str(quantization.get("name") or "")
        if not quantization_name:
            match = re.search(r"(Q[2-8](?:_[A-Z0-9]+)+)", path_value.upper())
            quantization_name = match.group(1) if match else ""
        model = make_model(
            model_id="lmstudio:{}".format(model_key),
            name=model_key,
            source="LM Studio",
            model_format=str(item.get("format") or "local").upper(),
            size_bytes=int(item.get("sizeBytes") or 0),
            path=str(LM_STUDIO_MODELS_ROOT / path_value),
            state="running" if current else "installed",
            current=current,
            details={
                "display_name": item.get("displayName", ""),
                "publisher": item.get("publisher", ""),
                "parameters": item.get("paramsString", ""),
                "architecture": item.get("architecture", ""),
                "quantization": quantization_name,
                "quantization_bits": quantization.get("bits"),
                "max_context_length": item.get("maxContextLength"),
                "vision": bool(item.get("vision")),
                "tool_use": bool(item.get("trainedForToolUse")),
                "service_running": server_running,
                "loaded": current,
                "loaded_context_length": loaded_contexts.get(model_key.lower()) if current else None,
                "repository": path_value.split("/", 2)[0] + "/" + path_value.split("/", 2)[1]
                if path_value.count("/") >= 1
                else "",
            },
        )
        if model["provider_template"]:
            model["provider_template"]["model"] = model_key
        result.append(model)
    return result


def scan_gguf(loaded: Dict[str, str]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    seen = set()
    for root in GGUF_ROOTS:
        try:
            files = list(root.rglob("*.gguf")) if root.exists() else []
        except OSError:
            files = []
        for path in files:
            resolved = str(path)
            if resolved in seen:
                continue
            seen.add(resolved)
            name = path.stem
            current = any(
                loaded_name.lower() in name.lower() or "qwen2.5-coder-0.5b" in name.lower()
                and "qwen2.5-coder-0.5b" in loaded_name.lower()
                for loaded_name, source in loaded.items()
                if source == "llama.cpp"
            )
            result.append(
                make_model(
                    model_id="gguf:{}".format(resolved),
                    name=name,
                    source="llama.cpp",
                    model_format="GGUF",
                    size_bytes=safe_file_size(path),
                    path=resolved,
                    state="running" if current else "installed",
                    current=current,
                    details={"quantization": name.split("-")[-1] if "-" in name else ""},
                )
            )
        try:
            incomplete = list(root.rglob("*.incomplete")) if root.exists() else []
        except OSError:
            incomplete = []
        for path in incomplete:
            try:
                relative_parts = path.relative_to(root).parts
                incomplete_name = relative_parts[0] if relative_parts else path.name
            except ValueError:
                incomplete_name = path.name
            result.append(
                make_model(
                    model_id="incomplete:{}".format(path),
                    name=incomplete_name,
                    source="llama.cpp",
                    model_format="GGUF",
                    size_bytes=safe_file_size(path),
                    path=str(path),
                    state="incomplete",
                )
            )
    return result


def scan_ollama(loaded: Dict[str, str]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    if not OLLAMA_MANIFEST_ROOT.exists():
        return result
    try:
        manifests = [path for path in OLLAMA_MANIFEST_ROOT.rglob("*") if path.is_file()]
    except OSError:
        return result
    for manifest_path in manifests:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        parts = manifest_path.relative_to(OLLAMA_MANIFEST_ROOT).parts
        if len(parts) < 3:
            continue
        name = "{}:{}".format(parts[-2], parts[-1])
        size_bytes = sum(int(layer.get("size", 0)) for layer in manifest.get("layers", []))
        config: Dict[str, Any] = {}
        digest = str((manifest.get("config") or {}).get("digest", "")).replace("sha256:", "")
        if digest:
            try:
                config = json.loads((OLLAMA_BLOB_ROOT / "sha256-{}".format(digest)).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        current = any(
            loaded_name == name or loaded_name.startswith(name + ":")
            for loaded_name, source in loaded.items()
            if source == "ollama"
        )
        result.append(
            make_model(
                model_id="ollama:{}".format(name),
                name=name,
                source="ollama",
                model_format=str(config.get("model_format", "GGUF")).upper(),
                size_bytes=size_bytes,
                path=str(manifest_path),
                state="running" if current else "installed",
                current=current,
                details={
                    "parameter_size": config.get("model_type", ""),
                    "quantization": config.get("file_type", ""),
                    "family": config.get("model_family", ""),
                    "service_running": any(source == "ollama" for source in loaded.values()),
                },
            )
        )
    return result


def hf_source_and_name(directory_name: str) -> Dict[str, str]:
    clean = directory_name.replace("models--", "", 1)
    parts = clean.split("--")
    return {
        "source": "MLX" if "mlx" in parts[0].lower() else "Hugging Face",
        "name": "/".join(parts),
    }


def scan_huggingface() -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    if not HF_HUB_ROOT.exists():
        return result
    try:
        model_dirs = [path for path in HF_HUB_ROOT.glob("models--*") if path.is_dir()]
    except OSError:
        return result
    for model_dir in model_dirs:
        identity = hf_source_and_name(model_dir.name)
        name = identity["name"]
        lower = name.lower()
        if not any(
            term in lower
            for term in ["qwen", "llama", "mistral", "gemma", "deepseek", "whisper", "sentence-transformers", "bge"]
        ):
            continue
        snapshots = model_dir / "snapshots"
        complete = False
        model_format = "cache"
        try:
            for path in snapshots.rglob("*") if snapshots.exists() else []:
                if path.suffix.lower() in {".safetensors", ".gguf", ".bin", ".npz"} and path.exists():
                    complete = True
                    model_format = "MLX safetensors" if identity["source"] == "MLX" else "safetensors"
                    break
        except OSError:
            pass
        result.append(
            make_model(
                model_id="hf:{}".format(model_dir.name),
                name=name,
                source=identity["source"],
                model_format=model_format,
                size_bytes=safe_tree_size(model_dir / "blobs"),
                path=str(model_dir),
                state="installed" if complete else "incomplete",
                details={
                    "runtime_ready": False if identity["source"] == "MLX" and "qwen" in lower else None,
                },
            )
        )
    return result


def scan_omlx() -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    if not OMLX_MODELS_ROOT.exists():
        return result
    try:
        model_dirs = [path for path in OMLX_MODELS_ROOT.iterdir() if path.is_dir()]
    except OSError:
        return result
    for model_dir in model_dirs:
        if model_dir.name.endswith("_backup"):
            continue
        config_path = model_dir / "config.json"
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        weights = list(model_dir.glob("*.safetensors"))
        if not weights:
            continue
        text_config = config.get("text_config") or {}
        quantization = config.get("quantization") or {}
        result.append(
            make_model(
                model_id="omlx:{}".format(model_dir.name),
                name=model_dir.name,
                source="oMLX",
                model_format="MLX safetensors",
                size_bytes=safe_tree_size(model_dir),
                path=str(model_dir),
                state="installed",
                details={
                    "architecture": config.get("model_type", ""),
                    "quantization": "{}bit".format(quantization.get("bits")) if quantization.get("bits") else "",
                    "quantization_bits": quantization.get("bits"),
                    "max_context_length": text_config.get("max_position_embeddings"),
                    "service_running": False,
                    "repository": model_dir.name.replace("__", "/"),
                },
            )
        )
    return result


def scan_runtime_only(loaded: Dict[str, str], existing: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    existing_names = [model["name"].lower() for model in existing]
    for name, source in loaded.items():
        lower = name.lower()
        matched = any(
            lower in existing_name
            or existing_name in lower
            or "qwen2.5-coder-0.5b" in lower and "qwen2.5-coder-0.5b" in existing_name
            for existing_name in existing_names
        )
        if matched:
            continue
        endpoint = "http://127.0.0.1:18081/v1" if source == "llama.cpp" else "http://127.0.0.1:11434"
        result.append(
            make_model(
                model_id="runtime:{}:{}".format(source, name),
                name=name,
                source=source,
                model_format="API runtime",
                size_bytes=0,
                path=endpoint,
                state="running",
                current=True,
                details={"discovered_from": "running service"},
            )
        )
    return result


def apply_configured_provider_status(
    providers: List[ModelProvider],
    existing: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    additions: List[Dict[str, Any]] = []
    for provider in providers:
        if not provider.enabled or provider.last_test_status != "ok":
            continue
        if "127.0.0.1:1234" in provider.base_url or "localhost:1234" in provider.base_url:
            # LM Studio has a reliable live `lms ps` signal; do not treat an old
            # connection test as proof that a model is still loaded.
            continue
        provider_name = provider.model.lower()
        expected_source = (
            "ollama"
            if provider.provider_type == "ollama"
            else "llama.cpp"
            if provider.provider_type == "llama_cpp"
            else None
        )
        match = next(
            (
                model
                for model in existing
                if model["state"] != "incomplete"
                and model["recommendation"]["level"] != "unavailable"
                and (expected_source is None or model["source"].lower() == expected_source)
                and (
                    provider_name in model["name"].lower()
                    or model["name"].lower() in provider_name
                    or "qwen2.5-coder-0.5b" in provider_name
                    and "qwen2.5-coder-0.5b" in model["name"].lower()
                )
            ),
            None,
        )
        if match:
            match["current"] = True
            match["state"] = "running"
            match["details"]["configured_provider"] = provider.name
            continue
        source = "ollama" if provider.provider_type == "ollama" else "llama.cpp" if provider.provider_type == "llama_cpp" else provider.provider_type
        additions.append(
            make_model(
                model_id="provider:{}".format(provider.id),
                name=provider.model,
                source=source,
                model_format="Configured API",
                size_bytes=0,
                path=provider.base_url,
                state="running",
                current=True,
                details={"configured_provider": provider.name, "last_test_status": provider.last_test_status},
            )
        )
    return additions


def sort_models(models: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    order = {
        "primary": 0,
        "secondary": 1,
        "test": 2,
        "candidate": 3,
        "auxiliary": 4,
        "unavailable": 5,
    }
    return sorted(
        models,
        key=lambda item: (
            0 if item["current"] else 1,
            order.get(item["recommendation"]["level"], 9),
            -item["size_bytes"],
        ),
    )


def build_local_model_inventory(db: Session) -> Dict[str, Any]:
    providers = list(db.scalars(select(ModelProvider).order_by(ModelProvider.created_at)).all())
    loaded = loaded_models()
    discovered = (
        scan_lm_studio()
        + scan_omlx()
        + scan_gguf(loaded)
        + scan_ollama(loaded)
        + scan_huggingface()
    )
    discovered += scan_runtime_only(loaded, discovered)
    discovered += apply_configured_provider_status(providers, discovered)
    models = sort_models(discovered)
    current = next((model for model in models if model["current"]), None)
    return {
        "scanned_at": datetime.utcnow().isoformat() + "Z",
        "hardware": system_hardware(),
        "current_model": current,
        "models": models,
        "configured_providers": [
            {
                "id": provider.id,
                "name": provider.name,
                "provider_type": provider.provider_type,
                "model": provider.model,
                "enabled": provider.enabled,
                "last_test_status": provider.last_test_status,
            }
            for provider in providers
        ],
        "summary": {
            "total": len(models),
            "generative": sum(1 for model in models if model["usable"]),
            "auxiliary": sum(1 for model in models if model["recommendation"]["level"] == "auxiliary"),
            "incomplete": sum(1 for model in models if model["state"] == "incomplete"),
            "recommended_primary": next(
                (model["name"] for model in models if model["recommendation"]["level"] == "primary"),
                None,
            ),
        },
        "usage_profiles": [
            {
                "name": "正式章节写作",
                "model": "qwen3.6-27b-crack",
                "why": "当前已加载的 27B MXFP4 模型，14GB 权重，适合 64GB Mac 上的日常长文写作。",
                "settings": "temperature 0.7 · top_p 0.8 · top_k 20 · context 32K · output 8K · thinking off",
            },
            {
                "name": "复杂审稿与修订",
                "model": "35B-A3B Q4/Q5",
                "why": "MoE 模型更适合结构分析；优先选择 Q4/Q5，避免 Q6 在长上下文下挤占统一内存。",
                "settings": "temperature 0.1-0.3 · context 16K-24K · output 2K-4K",
            },
            {
                "name": "连接健康检查",
                "model": "Qwen2.5-Coder-0.5B",
                "why": "启动快，但不应用于正式小说内容。",
                "settings": "temperature 0 · context 1K · output 8-64",
            },
        ],
    }


def sync_local_model_providers(db: Session) -> List[ModelProvider]:
    inventory = build_local_model_inventory(db)
    providers = list(db.scalars(select(ModelProvider).order_by(ModelProvider.created_at)).all())
    by_runtime_model = {
        (provider.provider_type, provider.base_url.rstrip("/"), provider.model): provider
        for provider in providers
    }
    changed = False
    for model in inventory["models"]:
        template = model.get("provider_template")
        if not template or model["state"] == "incomplete":
            continue
        key = (
            str(template["provider_type"]),
            str(template["base_url"]).rstrip("/"),
            str(template["model"]),
        )
        provider = by_runtime_model.get(key)
        options_json = json.dumps(template.get("default_options") or {}, ensure_ascii=False)
        if provider is None:
            provider = ModelProvider(
                name=str(template["name"]),
                provider_type=key[0],
                base_url=str(template["base_url"]),
                model=key[2],
                default_options_json=options_json,
                timeout_seconds=int(template.get("timeout_seconds") or 900),
                enabled=bool(template.get("enabled", True)),
            )
            db.add(provider)
            providers.append(provider)
            by_runtime_model[key] = provider
            changed = True
            continue
        # Only refresh records created from the inventory template. Hand-edited
        # provider names are treated as user-owned and are left untouched.
        if provider.name == template["name"]:
            provider.default_options_json = options_json
            provider.timeout_seconds = int(template.get("timeout_seconds") or provider.timeout_seconds)
            provider.enabled = True
            changed = True
    if changed:
        db.commit()
    return list(db.scalars(select(ModelProvider).order_by(ModelProvider.created_at)).all())
