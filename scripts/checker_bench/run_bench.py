#!/usr/bin/env python
"""Checker 分级基准运行器（逐级递增、增量更新页面）。

读 cases.json(对抗审查产出的分级用例) + candidates.py(候选模型)，按轮次跑，
把结果增量合并进 apps/web/src/data/checkerBench.json（前端「模型测试」栏直接读），
并把逐次调用明细存 results.json。模型推理在本机单卡串行（并行必 OOM）。

环境变量：
  ROUND=r1            只跑某一轮（默认跑 cases.json 里出现的所有轮）；可逗号分隔 r1,r2
  SERVICE=oMLX        只跑某个服务的候选（oMLX / "LM Studio"）
  BENCH_ONLY=27B      候选 label 子串过滤（多个用 | 分隔）

用法：
  cd services/api && ROUND=r1 SERVICE=oMLX .venv/bin/python ../../scripts/checker_bench/run_bench.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))
sys.path.insert(0, str(HERE))

from app.agents.base import render_prompt  # noqa: E402
from app.models.entities import ModelProvider  # noqa: E402
from app.providers.adapters import get_adapter  # noqa: E402
from app.schemas.loop import ContinuityCheckerOutput  # noqa: E402
from app.services.json_guard import JsonGuard  # noqa: E402
from candidates import CANDIDATES  # noqa: E402

TMPL = (ROOT / "services/api/app/prompts/novel_loop/continuity_checker.md").read_text(encoding="utf-8")
CASES_JSON = HERE / "cases.json"
UI_JSON = ROOT / "apps/web/src/data/checkerBench.json"
RESULTS_JSON = HERE / "results.json"

TRIALS = 2
THINK_S = 8.0  # 耗时 > 8s 视为真触发了思考
OPTS = {"temperature": 0.1, "max_tokens": 6000, "chat_template_kwargs": {"enable_thinking": True}}

ROUND_FILTER = [r.strip() for r in os.environ.get("ROUND", "").split(",") if r.strip()]
SERVICE_FILTER = os.environ.get("SERVICE", "").strip()
ONLY = [s for s in os.environ.get("BENCH_ONLY", "").split("|") if s]


def provider(c):
    return ModelProvider(
        name="bench", provider_type="openai_compatible",
        base_url=c["base_url"], model=c["model"], api_key=c["api_key"],
        timeout_seconds=600, default_options_json="{}",
    )


def _omlx_post(base_url, path, api_key):
    url = base_url.rstrip("/") + path
    req = urllib.request.Request(url, data=b"", method="POST",
                                 headers={"Authorization": "Bearer " + api_key})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:  # noqa: BLE001
        return None


def _omlx_get(base_url, path, api_key):
    url = base_url.rstrip("/") + path
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + api_key})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


def unload_all_omlx():
    """卸载 oMLX 上所有已加载模型，腾出显存（每个模型必须独占加载，否则 507）。"""
    base = "http://127.0.0.1:8003/v1"
    key = "local-novel-key"
    st = _omlx_get(base, "/models/status", key)
    if not st:
        return
    for m in st.get("models", []):
        if m.get("loaded"):
            mid = urllib.parse.quote(m["id"], safe="")
            code = _omlx_post(base, "/models/{}/unload".format(mid), key)
            print("  · 卸载 {} -> {}".format(m["id"], code), flush=True)
    time.sleep(2)  # 给显存回收一点时间


def unload(c):
    if c["service"] != "oMLX":
        return
    mid = urllib.parse.quote(c["model"], safe="")
    _omlx_post(c["base_url"], "/models/{}/unload".format(mid), c["api_key"])
    time.sleep(2)


import subprocess  # noqa: E402

LMS_CLI = str(Path.home() / ".lmstudio" / "bin" / "lms")


def lms_unload_all():
    try:
        subprocess.run([LMS_CLI, "unload", "--all"], timeout=60, capture_output=True)
    except Exception:  # noqa: BLE001
        pass
    time.sleep(3)


def lms_load(model):
    """用项目验证过的方式加载 LM Studio 模型，并以 model 名作 identifier 便于 OpenAI 端点寻址。"""
    try:
        r = subprocess.run(
            [LMS_CLI, "load", model, "--context-length", "16384", "--identifier", model, "--yes"],
            timeout=900, capture_output=True, text=True,
        )
        if r.returncode != 0:
            print("  · lms load 失败：{}".format((r.stderr or r.stdout or "")[:120].strip()), flush=True)
        return r.returncode == 0
    except Exception as exc:  # noqa: BLE001
        print("  · lms load 异常：{}".format(str(exc)[:100]), flush=True)
        return False


def ensure_loaded(c):
    """LM Studio 需先卸载其它再显式加载目标；oMLX 在请求时自动加载。返回是否就绪。"""
    if c["service"] == "LM Studio":
        lms_unload_all()
        print("  · 加载 LM Studio 模型 {} …".format(c["model"]), flush=True)
        return lms_load(c["model"])
    return True


def release(c):
    """测完释放：oMLX 卸载该模型；LM Studio 卸载全部。"""
    if c["service"] == "oMLX":
        unload(c)
    elif c["service"] == "LM Studio":
        lms_unload_all()


def call(c, prompt):
    t = time.perf_counter()
    try:
        res = get_adapter(provider(c)).generate_text(prompt, dict(OPTS))
        dt = time.perf_counter() - t
        try:
            return {"json_ok": True, "parsed": JsonGuard().parse_and_validate(res.text, ContinuityCheckerOutput), "dt": dt}
        except Exception as exc:  # noqa: BLE001
            return {"json_ok": False, "err": str(exc)[:90], "dt": dt}
    except Exception as exc:  # noqa: BLE001
        return {"json_ok": False, "err": str(exc)[:90], "dt": time.perf_counter() - t, "call_err": True}


def issue_text(p):
    return " ".join(
        (str(getattr(i, "problem", "")) + " " + str(getattr(i, "evidence", "")) + " " + str(getattr(i, "type", "")))
        for i in p.issues
    ).lower()


def has_major(p):
    return any(str(getattr(i, "severity", "")) in ("major", "blocker") for i in p.issues) or not p.passed


def verdict_of(row):
    """按已跑出的轮次给判定（None 的轮不参与）。"""
    r1, r2, r3, r4, fa = row.get("r1"), row.get("r2"), row.get("r3"), row.get("r4"), row.get("fa", 0)
    if r1 is None:
        return "pending"
    if r1 < 80 or fa > 25:
        return "fail"
    if r2 is not None and r2 < 80:
        return "weak"
    if r3 is not None and r3 < 60:
        return "weak"
    return "pass"


def load_ui():
    return json.loads(UI_JSON.read_text(encoding="utf-8"))


def save_ui(ui):
    UI_JSON.write_text(json.dumps(ui, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    data = json.loads(CASES_JSON.read_text(encoding="utf-8"))
    context = data["context"]
    cases = data["cases"]
    rounds_present = [r for r in ["r1", "r2", "r3", "r4", "clean"] if any(c["round"] == r for c in cases)]
    run_rounds = ROUND_FILTER or rounds_present
    # clean 永远跟跑（误报是每轮判定的一部分）
    run_error_rounds = [r for r in run_rounds if r != "clean"]
    run_clean = "clean" in run_rounds or bool(run_error_rounds)

    cands = CANDIDATES
    if SERVICE_FILTER:
        cands = [c for c in cands if c["service"] == SERVICE_FILTER]
    if ONLY:
        cands = [c for c in cands if any(o in c["label"] for o in ONLY)]

    print("=== Checker 分级基准 · 轮次 {} · 服务 {} · {} 个候选 ===".format(
        run_rounds, SERVICE_FILTER or "全部", len(cands)), flush=True)

    # 开跑前总是清空 oMLX 驻留（即便本轮只测 LM Studio，也要腾出共享内存，否则两运行时叠加会 OOM）。
    print(">>> 开跑前清空 oMLX 驻留模型…", flush=True)
    unload_all_omlx()

    detail = []
    if RESULTS_JSON.exists():
        try:
            detail = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            detail = []

    for c in cands:
        label = c["label"]
        print("\n>>> {} ({} · {})".format(label, c["service"], c["model"]), flush=True)
        if not ensure_loaded(c):
            print("  加载失败 → 跳过(标 error)", flush=True)
            ui = load_ui()
            _upsert(ui, c, {}, note_err="LM Studio 加载失败")
            save_ui(ui)
            release(c)
            continue
        print("  预热…", flush=True)
        warm = call(c, render_prompt(TMPL, {"chapter_id": "w", "chapter_title": "热身", "context": context, "draft_markdown": "周明走进房间，整理文件。"}))
        if warm.get("call_err"):
            print("  预热失败：{} → 跳过(标 error)".format(warm.get("err")), flush=True)
            ui = load_ui()
            _upsert(ui, c, {}, note_err=warm.get("err"))
            save_ui(ui)
            release(c)
            unload_all_omlx()  # 预热失败也可能残留半加载，强清
            continue

        per_round = {}   # round -> [caught_bool ...] for error rounds
        clean_fa = []    # false alarm bools
        calls = json_ok = thought = 0
        dt_sum = 0.0
        for case in cases:
            rnd = case["round"]
            if rnd == "clean":
                if not run_clean:
                    continue
            elif rnd not in run_error_rounds:
                continue
            prompt = render_prompt(TMPL, {"chapter_id": case["id"], "chapter_title": "第5章", "context": context, "draft_markdown": case["draft"]})
            for t in range(TRIALS):
                r = call(c, prompt)
                calls += 1
                dt_sum += r["dt"]
                if r["dt"] > THINK_S:
                    thought += 1
                rec = {"label": label, "round": rnd, "case": case["id"], "trial": t + 1, "dt": round(r["dt"], 1), "json_ok": r["json_ok"]}
                if r["json_ok"]:
                    json_ok += 1
                    p = r["parsed"]
                    if case["kind"] == "error":
                        txt = issue_text(p)
                        groups = case.get("keyword_groups", [])
                        caught = (not p.passed) and bool(groups) and all(any(k.lower() in txt for k in g) for g in groups)
                        per_round.setdefault(rnd, []).append(caught)
                        rec["caught"] = caught
                        rec["passed"] = p.passed
                        print("  [{}] {} #{}: {} {:.0f}s".format(rnd, case["id"], t + 1, "✓抓到" if caught else "✗漏掉", r["dt"]), flush=True)
                    else:
                        fa = has_major(p)
                        clean_fa.append(fa)
                        rec["false_alarm"] = fa
                        print("  [{}] {} #{}: {} {:.0f}s".format(rnd, case["id"], t + 1, "✗误报" if fa else "✓未误报", r["dt"]), flush=True)
                else:
                    if case["kind"] == "error":
                        per_round.setdefault(rnd, []).append(False)
                    else:
                        clean_fa.append(False)
                    rec["err"] = r.get("err", "")
                    print("  [{}] {} #{}: JSON坏 {:.0f}s {}".format(rnd, case["id"], t + 1, r["dt"], r.get("err", "")), flush=True)
                detail.append(rec)

        scores = {}
        for rnd, arr in per_round.items():
            scores[rnd] = round(100 * sum(arr) / len(arr)) if arr else None
        fa_rate = round(100 * sum(clean_fa) / len(clean_fa)) if clean_fa else 0
        agg = {
            "scores": scores,
            "fa": fa_rate,
            "jsonOk": round(100 * json_ok / calls) if calls else 0,
            "thinking": round(100 * thought / calls) if calls else 0,
            "latencyS": round(dt_sum / calls) if calls else 0,
        }
        ui = load_ui()
        _upsert(ui, c, agg)
        save_ui(ui)
        RESULTS_JSON.write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("  → {} 本轮：{} fa={}% json={}% think={}% {}s".format(
            label, scores, fa_rate, agg["jsonOk"], agg["thinking"], agg["latencyS"]), flush=True)
        release(c)  # 测完即卸载，给下一个模型腾显存（oMLX 卸该模型 / LM Studio 卸全部）

    print("\n=== 完成。结果已写入 {} ===".format(UI_JSON), flush=True)


def _upsert(ui, c, agg, note_err=None):
    rows = ui.setdefault("rows", [])
    row = next((r for r in rows if r["label"] == c["label"]), None)
    if row is None:
        row = {"label": c["label"], "service": c["service"], "paramB": c["param_b"], "category": c["category"],
               "r1": None, "r2": None, "r3": None, "r4": None, "jsonOk": 0, "latencyS": 0, "thinking": 0, "fa": 0,
               "verdict": "pending", "note": c.get("note", "")}
        rows.append(row)
    row["service"] = c["service"]
    row["paramB"] = c["param_b"]
    row["category"] = c["category"]
    if note_err:
        row["verdict"] = "fail"
        row["note"] = "加载/调用失败：{}".format(note_err)[:80]
    else:
        for rnd, v in agg["scores"].items():
            row[rnd] = v
        row["fa"] = agg["fa"]
        row["jsonOk"] = agg["jsonOk"]
        row["thinking"] = agg["thinking"]
        row["latencyS"] = agg["latencyS"]
        row["verdict"] = verdict_of(row)
        extra = " · 误报{}%".format(agg["fa"]) if agg["fa"] else ""
        row["note"] = (c.get("note", "") + extra).strip(" ·")
    # 从排队列表移除
    ui["queued"] = [q for q in ui.get("queued", []) if c["label"].split(" · ")[0] not in q and c["model"] not in q]
    ui["generatedAt"] = data_date()


def data_date():
    # 避免 Date.now 类不可用问题：用环境注入或固定占位，外部部署时更新
    return os.environ.get("BENCH_DATE", "2026-06-14")


if __name__ == "__main__":
    main()
