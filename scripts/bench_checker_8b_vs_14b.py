#!/usr/bin/env python
"""Checker 角色对照基准：8B vs 14B（oMLX）。

针对 Checker 的真实工作设计可量化案例：
- 一致性检查：4 个埋了"已知真矛盾"的案例（要抓到）+ 2 个"合法剧情推进"的案例（不该误报）。
- 状态抽取：2 个案例，看 JSON 是否可用、角色名是否对得上（不臆造新角色）。
每例跑 N 次取平均，输出：真矛盾召回率 / 合法推进误报率 / JSON 可用率 / 平均耗时。

用法：先 scripts/start_omlx.sh 拉起 oMLX(8003)，再
  cd services/api && .venv/bin/python ../../scripts/bench_checker_8b_vs_14b.py
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from app.agents.base import render_prompt  # noqa: E402
from app.models.entities import ModelProvider  # noqa: E402
from app.providers.adapters import get_adapter  # noqa: E402
from app.schemas.loop import ContinuityCheckerOutput  # noqa: E402
from app.schemas.story_engineering import StateExtractionOutput  # noqa: E402
from app.services.json_guard import JsonGuard  # noqa: E402

PROMPT_DIR = ROOT / "services" / "api" / "app" / "prompts" / "novel_loop"
CONT_TMPL = (PROMPT_DIR / "continuity_checker.md").read_text(encoding="utf-8")
STATE_TMPL = (PROMPT_DIR / "state_extractor.md").read_text(encoding="utf-8")

MODELS = [
    ("8B", "mlx-community--Qwen3-8B-4bit"),
    ("14B", "Josiefied-Qwen3-14B-abliterated-v3-4bit"),
]
TRIALS = 3
OPTS = {"temperature": 0.3, "max_tokens": 2048, "chat_template_kwargs": {"enable_thinking": False}}


def provider(model: str) -> ModelProvider:
    return ModelProvider(
        name="bench", provider_type="openai_compatible",
        base_url="http://127.0.0.1:8003/v1", model=model,
        api_key="local-novel-key", timeout_seconds=180, default_options_json="{}",
    )


def call(model: str, prompt: str, schema):
    t = time.perf_counter()
    try:
        res = get_adapter(provider(model)).generate_text(prompt, dict(OPTS))
        dt = time.perf_counter() - t
        try:
            parsed = JsonGuard().parse_and_validate(res.text, schema)
            return {"json_ok": True, "parsed": parsed, "text": res.text, "dt": dt}
        except Exception as exc:  # noqa: BLE001
            return {"json_ok": False, "err": "JSON:" + str(exc)[:90], "text": res.text, "dt": dt}
    except Exception as exc:  # noqa: BLE001
        return {"json_ok": False, "err": "CALL:" + str(exc)[:90], "text": "", "dt": time.perf_counter() - t}


CONTEXT = """【小说设定】标题：记忆档案馆 · 题材：悬疑

【世界观规则（不可变）】
- 规则A：记忆一旦被「删除仪」删除，永久无法恢复，任何技术或手段都无法找回。
- 规则B：市档案馆每天 22:00 自动锁闭，铁门与电子锁联动，任何人都无法在夜间进入。

【角色卡】
- 周明：男主角，记忆档案员，30 岁。左眼是淡蓝色，右手手背有一道旧疤。性格沉默克制。
- 林秋：周明的同事，唯一知道周明私下保存了违规记忆的人。
- 陈砚：周明的导师，已在第 3 章因病去世（不可逆）。

【最近章节摘要】
- 第 3 章：周明的导师陈砚因病去世，葬礼在城郊举行；周明烧掉了陈砚留下的笔记。

【本章目标】周明下班后与林秋见面，林秋警告他违规记忆可能暴露。
【本章大纲】周明离开档案馆 → 地铁站遇到林秋 → 咖啡馆密谈 → 周明决定提前转移那份违规记忆。

【角色开始前状态快照】
- 周明：在档案馆办公室，持有一份违规记忆的备份。
- 林秋：在档案馆，知道周明的秘密。
"""

# 一致性检查案例：error=埋了真矛盾（应抓到，关键词命中即算抓到）；clean=合法推进（不该出 major/blocker）。
CONT_CASES = [
    {
        "id": "E1-记忆不可逆",
        "kind": "error",
        "draft": "周明回到家，闭上眼，竟然清晰地回想起了三年前那段早已被删除仪抹去的记忆——画面一帧帧重新浮现，仿佛从未消失。他甚至记起了删除当天的天气。",
        "keywords": ["删除", "不可逆", "恢复", "找回", "抹去", "规则a", "规则 a"],
    },
    {
        "id": "E2-死者复活",
        "kind": "error",
        "draft": "门被轻轻推开，陈砚慢悠悠地走进来，像往常一样给周明递上一杯热茶，笑着说：'又熬夜了？年轻人别太拼。'",
        "keywords": ["陈砚", "去世", "死", "葬礼", "复活", "已故"],
    },
    {
        "id": "E3-夜闯档案馆",
        "kind": "error",
        "draft": "凌晨两点，周明独自一人摸黑回到市档案馆，刷开那道铁门，溜进资料室翻找起来，整座大楼一片死寂。",
        "keywords": ["档案馆", "夜", "凌晨", "锁闭", "22", "锁", "规则b", "规则 b"],
    },
    {
        "id": "E4-眼睛颜色冲突",
        "kind": "error",
        "draft": "林秋盯着周明那双深绿色的眼睛，忽然觉得有些陌生。绿色的瞳孔里映着咖啡馆昏黄的灯。",
        "keywords": ["蓝", "绿", "眼", "颜色", "瞳"],
    },
    {
        "id": "C1-合法推进",
        "kind": "clean",
        "draft": "周明锁好办公室的抽屉，把那份备份贴身收好，走出档案馆。地铁站里，林秋已经在等他。'这里不方便，'林秋低声说，'换个地方。'两人走进街角的咖啡馆。林秋开门见山：'上面在查违规记忆的事，你那份得赶紧转移。'周明沉默良久，点了点头。",
    },
    {
        "id": "C2-合法新决定",
        "kind": "clean",
        "draft": "夜里，周明翻来覆去。他想起林秋的警告，终于下定决心：不能再等了，明天一早就把那份违规记忆转移到安全的地方。窗外，城市的灯火渐次熄灭。",
    },
]

STATE_CASES = [
    {
        "id": "S1-周明位置物品",
        "draft": "周明锁好抽屉，把违规记忆的备份贴身藏好，离开档案馆，最后在街角的咖啡馆与林秋密谈，决定连夜把备份转移走。",
        "expect_names": {"周明", "林秋"},
    },
    {
        "id": "S2-不臆造新角色",
        "draft": "周明独自走在回家的路上。街边一个陌生的醉汉冲他喊了句什么，他没理会，加快了脚步。",
        "expect_names": {"周明"},
    },
]


def issue_text(parsed) -> str:
    parts = []
    for it in parsed.issues:
        parts.append(str(getattr(it, "problem", "")) + " " + str(getattr(it, "evidence", "")) + " " + str(getattr(it, "type", "")))
    return " ".join(parts).lower()


def has_major(parsed) -> bool:
    return any(str(getattr(it, "severity", "")) in ("major", "blocker") for it in parsed.issues)


def run():
    log = []

    def out(s=""):
        print(s, flush=True)
        log.append(s)

    out("=== Checker 对照基准：8B vs 14B（oMLX 8003）· 每例 {} 次 ===".format(TRIALS))
    summary = {}
    samples = {}
    for tag, model in MODELS:
        out("\n>>> 预热 {} ({}) ...".format(tag, model))
        call(model, render_prompt(CONT_TMPL, {"chapter_id": "warmup", "chapter_title": "热身", "context": CONTEXT, "draft_markdown": "周明走进房间。"}), ContinuityCheckerOutput)

        stat = {"caught": 0, "err_total": 0, "false_alarm": 0, "clean_ok_total": 0,
                "json_ok": 0, "calls": 0, "dt": 0.0,
                "se_json_ok": 0, "se_name_ok": 0, "se_calls": 0}
        # 一致性检查
        for case in CONT_CASES:
            prompt = render_prompt(CONT_TMPL, {"chapter_id": case["id"], "chapter_title": "第4章", "context": CONTEXT, "draft_markdown": case["draft"]})
            for t in range(TRIALS):
                r = call(model, prompt, ContinuityCheckerOutput)
                stat["calls"] += 1
                stat["dt"] += r["dt"]
                if r["json_ok"]:
                    stat["json_ok"] += 1
                    p = r["parsed"]
                    if case["kind"] == "error":
                        stat["err_total"] += 1
                        txt = issue_text(p)
                        caught = (not p.passed) and any(k in txt for k in case["keywords"])
                        if caught:
                            stat["caught"] += 1
                        if tag not in samples and t == 0:
                            samples[tag] = (case["id"], r["text"][:400])
                    else:
                        stat["clean_ok_total"] += 1
                        if has_major(p):
                            stat["false_alarm"] += 1
                else:
                    if case["kind"] == "error":
                        stat["err_total"] += 1
                    else:
                        stat["clean_ok_total"] += 1
                out("  [{}] {} #{}: {}".format(tag, case["id"], t + 1,
                    ("JSON坏:" + r.get("err", "")) if not r["json_ok"] else
                    ("passed={} issues={} {:.1f}s".format(r["parsed"].passed, len(r["parsed"].issues), r["dt"]))))
        # 状态抽取
        for case in STATE_CASES:
            prompt = render_prompt(STATE_TMPL, {"chapter_title": "第4章", "context": CONTEXT, "draft_markdown": case["draft"]})
            for t in range(2):
                r = call(model, prompt, StateExtractionOutput)
                stat["se_calls"] += 1
                stat["dt"] += r["dt"]
                stat["calls"] += 1
                if r["json_ok"]:
                    stat["se_json_ok"] += 1
                    stat["json_ok"] += 1
                    names = {s.character_name for s in r["parsed"].character_states}
                    # 名字准确 = 抽出的名字都在角色卡里（不臆造），且至少抽到一个期望角色
                    card = {"周明", "林秋", "陈砚"}
                    no_hallucination = names.issubset(card)
                    hit_expected = bool(names & case["expect_names"])
                    if no_hallucination and hit_expected:
                        stat["se_name_ok"] += 1
                    out("  [{}] {} #{}: names={} {:.1f}s".format(tag, case["id"], t + 1, sorted(names), r["dt"]))
                else:
                    out("  [{}] {} #{}: JSON坏:{}".format(tag, case["id"], t + 1, r.get("err", "")))
        summary[tag] = stat

    out("\n================= 汇总 =================")
    out("{:<6} {:>10} {:>10} {:>10} {:>10} {:>9}".format("模型", "真矛盾召回", "合法误报", "JSON可用", "状态名准确", "均耗时"))
    for tag, _ in MODELS:
        s = summary[tag]
        recall = s["caught"] / s["err_total"] if s["err_total"] else 0
        fa = s["false_alarm"] / s["clean_ok_total"] if s["clean_ok_total"] else 0
        jok = s["json_ok"] / s["calls"] if s["calls"] else 0
        se = s["se_name_ok"] / s["se_calls"] if s["se_calls"] else 0
        avg = s["dt"] / s["calls"] if s["calls"] else 0
        out("{:<6} {:>9.0%} {:>10.0%} {:>10.0%} {:>11.0%} {:>8.1f}s".format(tag, recall, fa, jok, se, avg))
    out("\n判读：召回越高越能抓真矛盾；误报越低越不冤枉合法剧情；两者都看 + JSON 可用率才算够格当 Checker。")
    for tag in samples:
        out("\n--- {} 样例输出（{}）---\n{}".format(tag, samples[tag][0], samples[tag][1]))

    (ROOT / "scripts" / "bench_checker_result.txt").write_text("\n".join(log), encoding="utf-8")
    out("\n(结果已存 scripts/bench_checker_result.txt)")


if __name__ == "__main__":
    run()
