#!/usr/bin/env python3
"""拆解性能基准：通过部署版 app(:8000) 驱动真实 oMLX 模型，对比三种模式。

模式：
  A 逐维度(基线)   merge off, 串行  -> 10 维 × N 块 次调用
  B 合并-串行       merge on,  串行  -> N 块 次调用（每块一次抽全部维度）
  C 合并-并发x3     merge on,  并发3 -> N 块 次调用，块间并发

度量：墙钟耗时、实际块数、模型调用次数(creative_runs)、各维度候选数。
结果写 /tmp/bench_result.json，并在结束删除基准用的临时 project。
"""
import json
import os
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8000/api"
DB = os.getenv(
    "NOVEL_AI_BENCH_DB",
    str(Path.home() / "Library/Application Support/NovelLocalAI/data/novel_local_ai.db"),
)
ALL10 = ["characters", "worldbuilding", "timeline", "plot_threads", "meta",
         "structure", "setup_payoff", "theme", "pov", "style_fingerprint"]
PER_RUN_TIMEOUT = 600


def req(method, path, body=None, timeout=620):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read() or b"null")


def find_provider():
    for p in req("GET", "/model-providers"):
        if "8003" in p["base_url"] and "Qwen3-8B" in p["name"]:
            return p
    raise SystemExit("找不到 oMLX Qwen3-8B provider")


def ro(query, args=()):
    con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
    try:
        return con.execute(query, args).fetchall()
    finally:
        con.close()


def sample_text(n):
    rows = ro("SELECT source_text FROM deconstruction_runs ORDER BY created_at DESC LIMIT 1")
    return (rows[0][0] or "")[:n] if rows else ""


def calls_for(novel_id):
    return dict(ro("SELECT operation, count(*) FROM creative_runs WHERE novel_id=? GROUP BY operation", (novel_id,)))


def run_mode(project_id, provider, text, dims, options, label):
    novel = req("POST", "/novels", {"project_id": project_id, "title": "bench-" + label})
    t0 = time.time()
    created = req("POST", "/novels/%s/deconstruction-runs" % novel["id"],
                  {"provider_id": provider["id"], "source_text": text, "dimensions": dims, "options": options})
    rid = created["id"]
    run = created
    while run["status"] not in ("completed", "failed"):
        if time.time() - t0 > PER_RUN_TIMEOUT:
            return {"label": label, "status": "TIMEOUT", "secs": round(time.time() - t0, 1), "novel": novel["id"]}
        time.sleep(1.0)
        run = req("GET", "/novels/%s/deconstruction-runs/%s" % (novel["id"], rid))
    dt = round(time.time() - t0, 1)
    cands = req("GET", "/novels/%s/story-engineering/candidates" % novel["id"])
    by = {}
    for c in cands:
        by[c["record_type"]] = by.get(c["record_type"], 0) + 1
    return {"label": label, "status": run["status"], "secs": dt, "chunks": run["chunk_count"],
            "total_units": run["total_units"], "candidates": run["candidate_count"],
            "calls": calls_for(novel["id"]), "by_type": by, "error": run.get("error", ""), "novel": novel["id"]}


def main():
    p = find_provider()
    text = sample_text(7000)
    print("provider:", p["name"], "| model:", p["model"], "| sample chars:", len(text)); sys.stdout.flush()
    project = req("POST", "/projects", {"name": "perf-bench-decon"})
    THINK = {"chat_template_kwargs": {"enable_thinking": False}, "temperature": 0.3}

    print("warmup (载入模型)..."); sys.stdout.flush()
    w = run_mode(project["id"], p, text[:1500], ["meta"],
                 {**THINK, "chunk_tokens": 20000, "max_tokens": 1200, "merge_dimensions": True}, "warmup")
    print("warmup:", w["status"], w["secs"], "s", w.get("error", "")); sys.stdout.flush()

    modes = [
        ("A-逐维度串行", ALL10, {**THINK, "chunk_tokens": 3500, "max_tokens": 1800, "max_parallel": 1}),
        ("B-逐维度并行x3", ALL10, {**THINK, "chunk_tokens": 3500, "max_tokens": 1800, "max_parallel": 3}),
        ("C-逐维度并行x6", ALL10, {**THINK, "chunk_tokens": 3500, "max_tokens": 1800, "max_parallel": 6}),
    ]
    results = []
    for label, dims, opt in modes:
        r = run_mode(project["id"], p, text, dims, opt, label)
        results.append(r)
        print("DONE", label, "->", r["status"], r["secs"], "s | chunks", r.get("chunks"),
              "| total_calls", sum((r.get("calls") or {}).values()), "| cands", r.get("candidates"),
              "|", r.get("error", "")); sys.stdout.flush()

    base = next((x for x in results if x["label"].startswith("A") and x["status"] == "completed"), None)
    print("\n==== 结果汇总 ====")
    for r in results:
        spd = ("%.1fx" % (base["secs"] / r["secs"])) if base and r.get("secs") and r["status"] == "completed" else "-"
        print("%-14s %-10s %7ss  chunks=%s units=%s calls=%s cands=%s 提速=%s" % (
            r["label"], r["status"], r.get("secs"), r.get("chunks"), r.get("total_units"),
            sum((r.get("calls") or {}).values()), r.get("candidates"), spd))

    json.dump(results, open("/tmp/bench_result.json", "w"), ensure_ascii=False, indent=2)
    # 清理基准临时数据
    try:
        req("DELETE", "/projects/%s" % project["id"])
        print("\n已删除基准临时 project:", project["id"])
    except Exception as exc:
        print("清理失败(可手动删 perf-bench-decon):", exc)
    print("详细结果: /tmp/bench_result.json")


if __name__ == "__main__":
    main()
