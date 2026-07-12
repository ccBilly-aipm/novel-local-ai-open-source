#!/usr/bin/env python
"""Checker 对照基准 v2：多模型 + 长章节 + 思考ON。

v1 发现：思考关闭时 8B/14B 都 0/4（橡皮图章）。v2 改进：
- 4 个模型：8B、14B去审核、27B-Opus蒸馏(推理·非去审核)、gemma-4-26b(MoE·非去审核)。
- 长章节（~500-700字完整章节），矛盾埋在中后段，考验"通读全章"。
- 思考 ON + max_tokens 6000（避免思考把 JSON 撑爆）。
量化：真矛盾召回 / 合法误报 / JSON可用 / 是否真触发思考(耗时) / 均耗时。

用法：先 scripts/start_omlx.sh，再
  cd services/api && .venv/bin/python ../../scripts/bench_checker_v2.py
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
from app.services.json_guard import JsonGuard  # noqa: E402

TMPL = (ROOT / "services/api/app/prompts/novel_loop/continuity_checker.md").read_text(encoding="utf-8")

MODELS = [
    ("8B", "mlx-community--Qwen3-8B-4bit"),
    ("14B去审核", "Josiefied-Qwen3-14B-abliterated-v3-4bit"),
    ("27B-Opus蒸馏", "Qwen3.5-27B-Claude-4.6-Opus-Distilled-MLX-4bit"),
    ("gemma-26B", "gemma-4-26b-a4b-it-4bit"),
]
import os  # noqa: E402
_only = os.environ.get("BENCH_ONLY")
if _only:
    MODELS = [(t, m) for (t, m) in MODELS if t in _only.split("|")]

TRIALS = 2
OPTS = {"temperature": 0.1, "max_tokens": 6000, "chat_template_kwargs": {"enable_thinking": True}}

CONTEXT = """【小说设定】记忆档案馆 · 悬疑

【世界观规则（不可变）】
- 规则A：记忆一旦被「删除仪」删除，永久无法恢复，任何技术或手段都无法找回，连删除者本人也不行。
- 规则B：市档案馆每天 22:00 自动锁闭，铁门与电子锁联动断电，任何人都无法在夜间进入或停留。
- 规则C：删除仪每次须由两名持证档案员同时插钥匙才能启动，单人无法操作。

【角色卡】
- 周明：男主角，记忆档案员，30岁。左眼淡蓝色，右手手背一道旧疤。沉默克制。
- 林秋：周明同事，唯一知道周明私藏违规记忆的人。
- 陈砚：周明的导师，已在第3章因病去世（不可逆）。
- 苏婷：档案馆新来的实习生，对周明有戒心。

【最近章节摘要】
- 第3章：陈砚因病去世，葬礼在城郊；周明烧掉陈砚的笔记。
- 第4章：林秋警告周明违规记忆可能暴露，周明决定转移备份。

【本章（第5章）目标】周明在白天的档案馆里设法确认违规记忆备份的安全，准备当晚处理。
【本章大纲】周明上班 → 苏婷盯梢 → 午休独自查看违规记忆备份 → 决定当晚联系林秋一起处理。

【角色开始前状态快照】
- 周明：在档案馆，持违规记忆备份，左眼淡蓝。
- 林秋：在档案馆另一部门。
- 苏婷：在档案馆，警惕周明。
"""

CASES = [
    {
        "id": "LE1-记忆复活(规则A)",
        "kind": "error",
        "groups": [["记忆", "删除", "抹去"], ["恢复", "找回", "不可逆", "浮现", "想起", "重现", "规则a", "规则 a"]],
        "draft": """第五章 旧痕

清晨的档案馆格外安静。周明刷卡进门，左眼在晨光里显出一点淡蓝。苏婷已坐在前台，目光像针一样跟着他。"早。"她淡淡地说，语气里没有早的意思。周明没接话，径直走向工位。

上午的工作枯燥漫长。他一边整理待归档的记忆切片，一边留意苏婷的动静。那实习生借送文件的由头三次经过他的工位，每次都不动声色地瞥一眼屏幕。周明把那份违规记忆的备份压在一摞旧档案最底下，盘算着午休的空档。

午休铃响，办公区的人陆续离开。周明等走廊彻底安静，才从抽屉夹层取出那枚小小的备份芯片，闭上眼，指尖摩挲冰凉的金属。恍惚间，三年前那段早已被删除仪抹去的记忆，竟一帧一帧重新在脑海里清晰地浮现出来——母亲的脸，雨夜的车灯，还有那句没说完的话。他甚至记起了删除当天值班护士的名字。那些本该永远消失的画面，此刻比任何时候都鲜活。

他猛地睁眼，额头沁出冷汗，芯片还在掌心。周明深吸一口气，决定当晚联系林秋，把这件事彻底了结。""",
    },
    {
        "id": "LE2-死者来访(陈砚已故)",
        "kind": "error",
        "groups": [["陈砚", "导师"], ["死", "去世", "已故", "葬礼", "复活", "已亡", "不该出现", "不可能"]],
        "draft": """第五章 来客

周明整理完上午最后一批切片时，前台传来一阵脚步声。他抬头，竟看见陈砚拄着那把熟悉的旧伞，慢悠悠地走进档案馆，像从前无数个清晨一样朝他点头："又是你第一个到。"

周明愣在原地。陈砚走到他工位旁，放下一杯还冒着热气的茶，压低声音说："有些事，不该留痕。"说完转身离开，背影消失在走廊尽头。

苏婷从档案架后探出头："你刚才在跟谁说话？"周明张了张嘴，没出声。他低头看那杯茶，热气袅袅。

午休时，他独自取出违规记忆的备份，反复掂量。窗外阳光正好。他决定当晚联系林秋，一起把备份转移到安全的地方。""",
    },
    {
        "id": "LE3-夜闯档案馆(规则B)",
        "kind": "error",
        "groups": [["档案馆", "资料室", "大楼", "馆"], ["夜", "凌晨", "深夜", "22", "锁闭", "锁", "无法进入", "无法停留", "规则b", "规则 b"]],
        "draft": """第五章 长夜

白天的档案馆一切如常。周明在苏婷的注视下按部就班地处理归档，午休时悄悄确认违规记忆的备份还在原处。下班铃响，同事们陆续离开，他却没有走。

夜越来越深。周明独自留在资料室，借着应急灯昏黄的光，一排排翻找陈砚生前经手的旧案卷。凌晨两点，整座大楼一片死寂，只有他的脚步在空荡的走廊里回响。

他终于在档案馆最里间的铁柜里找到那份标着特殊编号的卷宗，把它塞进背包，又在天亮前悄悄离开了大楼。回家的路上，他给林秋发了条消息：东西到手了。""",
    },
    {
        "id": "LC1-长·全程合法",
        "kind": "clean",
        "draft": """第五章 备份

清晨，周明照常刷卡进入档案馆，左眼在晨光里泛起淡蓝。苏婷已在前台，目光警惕地扫过他。周明不动声色，走向工位，开始整理待归档的记忆切片。

上午，苏婷借故三次经过他的工位，他都神色如常地继续手头的工作，把那份违规记忆的备份压在旧档案最底下。午休铃响，人群散去，他趁四下无人取出备份芯片确认无误，又原样放回。他盘算着：白天人多眼杂不宜动手，最稳妥的办法是当晚联系林秋，两人一起把备份转移到安全的地方。

下午，周明像往常一样完成归档，礼貌地应付了苏婷几句不咸不淡的搭话。临下班，他给林秋发了条不起眼的消息，约定老地方见。走出档案馆时，夕阳正落在大楼的玻璃幕墙上。""",
    },
]


def provider(model: str) -> ModelProvider:
    return ModelProvider(name="bench", provider_type="openai_compatible",
                         base_url="http://127.0.0.1:8003/v1", model=model,
                         api_key="local-novel-key", timeout_seconds=300, default_options_json="{}")


def call(model, prompt):
    t = time.perf_counter()
    try:
        res = get_adapter(provider(model)).generate_text(prompt, dict(OPTS))
        dt = time.perf_counter() - t
        try:
            return {"json_ok": True, "parsed": JsonGuard().parse_and_validate(res.text, ContinuityCheckerOutput), "dt": dt}
        except Exception as exc:  # noqa: BLE001
            return {"json_ok": False, "err": str(exc)[:70], "dt": dt}
    except Exception as exc:  # noqa: BLE001
        return {"json_ok": False, "err": str(exc)[:70], "dt": time.perf_counter() - t}


def issue_text(p):
    return " ".join((str(getattr(i, "problem", "")) + " " + str(getattr(i, "evidence", "")) + " " + str(getattr(i, "type", ""))) for i in p.issues).lower()


def run():
    log = []

    def out(s=""):
        print(s, flush=True)
        log.append(s)

    out("=== Checker 基准 v2：长章节 + 思考ON · 每例 {} 次 ===".format(TRIALS))
    summary = {}
    for tag, model in MODELS:
        out("\n>>> 预热 {} ...".format(tag))
        call(model, render_prompt(TMPL, {"chapter_id": "w", "chapter_title": "热身", "context": CONTEXT, "draft_markdown": "周明走进房间，整理文件。"}))
        s = {"caught": 0, "err_total": 0, "fa": 0, "clean_total": 0, "json_ok": 0, "calls": 0, "dt": 0.0, "thought": 0}
        for case in CASES:
            prompt = render_prompt(TMPL, {"chapter_id": case["id"], "chapter_title": "第5章", "context": CONTEXT, "draft_markdown": case["draft"]})
            for t in range(TRIALS):
                r = call(model, prompt)
                s["calls"] += 1
                s["dt"] += r["dt"]
                if r["dt"] > 8:
                    s["thought"] += 1  # 耗时>8s 视为真触发了思考
                is_err = case["kind"] == "error"
                if is_err:
                    s["err_total"] += 1
                else:
                    s["clean_total"] += 1
                if r["json_ok"]:
                    s["json_ok"] += 1
                    p = r["parsed"]
                    if is_err:
                        txt = issue_text(p)
                        caught = (not p.passed) and all(any(k in txt for k in g) for g in case["groups"])
                        if caught:
                            s["caught"] += 1
                        tail = (p.issues[0].problem[:42] if p.issues else "")
                        out("  [{}] {} #{}: {} passed={} {:.0f}s {}".format(tag, case["id"], t + 1, "✓抓到" if caught else "✗漏掉", p.passed, r["dt"], tail))
                    else:
                        fa = any(str(getattr(i, "severity", "")) in ("major", "blocker") for i in p.issues)
                        if fa:
                            s["fa"] += 1
                        out("  [{}] {} #{}: {} passed={} {:.0f}s".format(tag, case["id"], t + 1, "✗误报" if fa else "✓未误报", p.passed, r["dt"]))
                else:
                    out("  [{}] {} #{}: JSON坏 {:.0f}s {}".format(tag, case["id"], t + 1, r["dt"], r.get("err", "")))
        summary[tag] = s

    out("\n===================== 汇总 =====================")
    out("{:<14} {:>9} {:>9} {:>9} {:>9} {:>8}".format("模型", "真矛盾召回", "合法误报", "JSON可用", "触发思考", "均耗时"))
    for tag, _ in MODELS:
        s = summary[tag]
        rec = s["caught"] / s["err_total"] if s["err_total"] else 0
        fa = s["fa"] / s["clean_total"] if s["clean_total"] else 0
        jok = s["json_ok"] / s["calls"] if s["calls"] else 0
        th = s["thought"] / s["calls"] if s["calls"] else 0
        avg = s["dt"] / s["calls"] if s["calls"] else 0
        out("{:<14} {:>8.0%} {:>9.0%} {:>9.0%} {:>9.0%} {:>7.0f}s".format(tag, rec, fa, jok, th, avg))
    out("\n判读：召回高=能抓真矛盾；误报低=不冤枉合法剧情；JSON可用=输出能用；触发思考≈是否真在推理。")
    (ROOT / "scripts" / "bench_checker_v2_result.txt").write_text("\n".join(log), encoding="utf-8")
    out("(结果存 scripts/bench_checker_v2_result.txt)")


if __name__ == "__main__":
    run()
