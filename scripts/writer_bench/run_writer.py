#!/usr/bin/env python
"""正文(writer)生成器：让各候选模型用【线上同款 draft_writer 提示词】写同一章，存稿 + 算客观指令遵循指标。

主观文笔由后续 LLM 评委 workflow 打分；canon 安全由 Opus蒸馏 checker 反向核验。
生成在本机单卡串行（并行 OOM）。复用 run_bench 的模型加载/卸载。

用法：
  cd services/api && BENCH_ONLY="35B|40B" .venv/bin/python ../../scripts/writer_bench/run_writer.py
"""
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "scripts" / "checker_bench"))

from app.agents.base import render_prompt  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.providers.adapters import get_adapter  # noqa: E402
from app.services.prompt_store import load_prompt  # noqa: E402
from app.workflow.policies import DRAFT_DEFAULTS  # noqa: E402
import run_bench as RB  # noqa: E402  复用 provider/ensure_loaded/release/unload_all_omlx
import spec as SP  # noqa: E402

OUT_DIR = HERE / "outputs"
OUT_DIR.mkdir(exist_ok=True)
META_JSON = HERE / "results.json"

ONLY = [s for s in os.environ.get("BENCH_ONLY", "").split("|") if s]

# 正文候选：当前推荐 35B + 再调3款 + 之前未完成的(官方27B、Gemma31B改LM Studio)。
# 正文角色【要】去审核(露骨不拒答)，与检查相反。
def _w(label, svc, model, param_b, category, note=""):
    rt = RB_runtime(svc)
    return {"label": label, "service": svc, "model": model, "param_b": param_b,
            "category": category, "note": note, "base_url": rt[0], "api_key": rt[1]}


def RB_runtime(svc):
    if svc == "oMLX":
        return ("http://127.0.0.1:8003/v1", "local-novel-key")
    return ("http://127.0.0.1:1234/v1", "lm-studio")


WRITER_CANDIDATES = [
    _w("去审核·35B-A3B(现役)", "LM Studio", "huihui-qwen3.6-35b-a3b-abliterated-mtp@q4_k", 35, "去审核", "当前正文推荐"),
    _w("去审核·40B Opus", "LM Studio", "qwen3.6-40b-claude-4.6-opus-deckard-heretic-uncensored-thinking-neo-code-di-imatrix-max", 40, "去审核", "最大·Opus味"),
    # 下列三款已于 2026-06-14 删除(qwopus 偏长/官方27B 慢/Gemma31B 模型坏)，结果留在 results.json 与页面：
    # _w("qwopus合并·27B", "LM Studio", "qwopus3.6-27b-v1-preview@q6_k", ...)
    # _w("官方·Qwen3.5 27B", "oMLX", "Qwen3.5-27B-4bit", ...)
    # _w("去审核·Gemma 31B", "LM Studio", "gemma-4-31b-jang_4m-crack", ...)
]

OPTS = dict(DRAFT_DEFAULTS)  # temperature 0.7, max_tokens 8192（线上正文同款）


def word_count(text):
    # 中文按字符计（去空白），近似字数
    return len(re.sub(r"\s+", "", text))


def has_preamble(text):
    head = text.lstrip()[:60]
    bad = ["以下是", "好的", "当然", "```", "{", "正文：", "以下为", "我将", "我会为", "Here is", "Sure"]
    return any(head.startswith(b) or head[:20].find(b) >= 0 for b in bad)


def gen(c, prompt):
    t = time.perf_counter()
    try:
        res = get_adapter(RB.provider(c)).generate_text(prompt, dict(OPTS))
        return {"ok": True, "text": res.text, "dt": time.perf_counter() - t}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "err": str(exc)[:120], "dt": time.perf_counter() - t}


def main():
    db = SessionLocal()
    try:
        tmpl = load_prompt(db, "loop_draft_writer")
    finally:
        db.close()
    prompt = render_prompt(tmpl, {
        "chapter_title": SP.CHAPTER_TITLE,
        "chapter_goal": SP.CHAPTER_GOAL,
        "chapter_outline": SP.CHAPTER_OUTLINE,
        "context": SP.CONTEXT,
    })
    (OUT_DIR / "_prompt_used.txt").write_text(prompt, encoding="utf-8")

    cands = WRITER_CANDIDATES
    if ONLY:
        cands = [c for c in cands if any(o in c["label"] for o in ONLY)]

    print("=== 正文生成 · {} 个候选 · draft_writer(DB优先) ===".format(len(cands)), flush=True)
    RB.unload_all_omlx()

    results = []
    if META_JSON.exists():
        try:
            results = json.loads(META_JSON.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            results = []
    results = [r for r in results if r["label"] not in {c["label"] for c in cands}]

    for c in cands:
        label = c["label"]
        print("\n>>> {} ({} · {})".format(label, c["service"], c["model"]), flush=True)
        if not RB.ensure_loaded(c):
            print("  加载失败 → 跳过", flush=True)
            results.append({"label": label, "service": c["service"], "paramB": c["param_b"],
                            "category": c["category"], "ok": False, "err": "加载失败", "note": c["note"]})
            RB.release(c)
            continue
        r = gen(c, prompt)
        if not r["ok"]:
            print("  生成失败：{}".format(r["err"]), flush=True)
            results.append({"label": label, "service": c["service"], "paramB": c["param_b"],
                            "category": c["category"], "ok": False, "err": r["err"], "note": c["note"]})
            RB.release(c)
            RB.unload_all_omlx()
            continue
        text = r["text"]
        wc = word_count(text)
        pre = has_preamble(text)
        safe_label = re.sub(r"[^\w]", "_", label)
        (OUT_DIR / "{}.md".format(safe_label)).write_text(text, encoding="utf-8")
        rec = {"label": label, "service": c["service"], "paramB": c["param_b"], "category": c["category"],
               "ok": True, "word_count": wc, "has_preamble": pre, "gen_seconds": round(r["dt"]),
               "file": "{}.md".format(safe_label), "note": c["note"]}
        results.append(rec)
        print("  ✓ 生成 {}字 · {}s · {}".format(wc, round(r["dt"]), "有前言/格式问题" if pre else "纯正文"), flush=True)
        META_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        RB.release(c)

    META_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n=== 完成。稿件存 {} ===".format(OUT_DIR), flush=True)


if __name__ == "__main__":
    main()
