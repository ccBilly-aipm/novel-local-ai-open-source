"""三轮循环 P0：CRITIQUE（审校）+ REFINE（精炼/分层）的 happy-path 与托底护栏。

桩按 prompt 里的 AGENT 标记 + 维度标签分流，模拟真实模型：
- characters：抽到 2 个角色 → 审校 drop 掉次要的 1 个 → 精炼给存活者标层级/复用度。
- theme：抽到 2 个主题 → 审校把两个都判 drop → 失灵护栏拦截 → 两条都保留。
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.auto_entities import StoryMemoryRecord
from app.services.common import loads


class RefineMockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        prompt = payload.get("messages", [{}])[0].get("content", "")

        if "AGENT: decon_characters" in prompt:
            content = json.dumps(
                {"characters": [
                    {"name": "周明", "role": "主角", "description": "记忆档案员", "confidence": 0.9, "evidence": "开篇出场"},
                    {"name": "李雷", "role": "路人", "description": "", "confidence": 0.4, "evidence": ""},
                ]},
                ensure_ascii=False,
            )
        elif "AGENT: decon_theme" in prompt:
            content = json.dumps(
                {"themes": [
                    {"name": "记忆与真实", "description": "删除记忆是否抹掉真实", "confidence": 0.8, "evidence": "通篇"},
                    {"name": "身份", "description": "被改写者还是不是自己", "confidence": 0.7, "evidence": "通篇"},
                ]},
                ensure_ascii=False,
            )
        elif "AGENT: decon_critique" in prompt and "维度：人物" in prompt:
            # 保留主角周明（ref0），淘汰无证据的次要角色李雷（ref1）
            content = json.dumps(
                {"verdicts": [
                    {"ref": 0, "verdict": "keep", "reason": "主角，证据具体"},
                    {"ref": 1, "verdict": "drop", "reason": "路人，无证据"},
                ]},
                ensure_ascii=False,
            )
        elif "AGENT: decon_critique" in prompt and "维度：主题" in prompt:
            # 故意全判 drop → 失灵护栏应拦下、两条都留
            content = json.dumps(
                {"verdicts": [
                    {"ref": 0, "verdict": "drop", "reason": "x"},
                    {"ref": 1, "verdict": "drop", "reason": "x"},
                ]},
                ensure_ascii=False,
            )
        elif "AGENT: decon_refine" in prompt and "维度：人物" in prompt:
            content = json.dumps(
                {"items": [{"ref": 0, "layer": "signature", "reuse_score": 9, "reuse_note": "复刻主角弧光"}]},
                ensure_ascii=False,
            )
        elif "AGENT: decon_refine" in prompt and "维度：主题" in prompt:
            content = json.dumps(
                {"items": [
                    {"ref": 0, "layer": "signature", "reuse_score": 8, "reuse_note": "母题复刻"},
                    {"ref": 1, "layer": "pattern", "reuse_score": 7, "reuse_note": "身份反转套路"},
                ]},
                ensure_ascii=False,
            )
        else:
            content = json.dumps({"unexpected": True})

        body = json.dumps(
            {"choices": [{"message": {"role": "assistant", "content": content}}],
             "usage": {"prompt_tokens": 30, "completion_tokens": 20}}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def _start_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), RefineMockHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _bootstrap(client, port):
    project = client.post("/api/projects", json={"name": "精炼测试"}).json()
    novel = client.post("/api/novels", json={"project_id": project["id"], "title": "目标新作"}).json()
    provider = client.post(
        "/api/model-providers",
        json={
            "name": "Refine Mock",
            "provider_type": "openai_compatible",
            "base_url": "http://127.0.0.1:{}/v1".format(port),
            "model": "refine-mock",
            "timeout_seconds": 5,
        },
    ).json()
    return project, novel, provider


def _wait_completed(client, novel_id, run_id):
    deadline = time.time() + 25
    while time.time() < deadline:
        run = client.get("/api/novels/{}/deconstruction-runs/{}".format(novel_id, run_id)).json()
        if run["status"] in {"completed", "failed"}:
            return run
        time.sleep(0.05)
    raise AssertionError("拆解任务未在期限内完成")


def _by_type_status(novel_id):
    """直接读库，按 (record_type, status) 归类该小说的候选。"""
    out = {}
    with SessionLocal() as db:
        rows = db.query(StoryMemoryRecord).filter(StoryMemoryRecord.novel_id == novel_id).all()
        for r in rows:
            out.setdefault((r.record_type, r.status), []).append(r)
    return out


def test_critique_drops_and_refine_annotates_with_misfire_guard():
    server = _start_server()
    try:
        with TestClient(app) as client:
            _project, novel, provider = _bootstrap(client, server.server_address[1])
            novel_id = novel["id"]
            source = "第一章\n" + "甲" * 400  # 小文本 → 单块，便于断言

            created = client.post(
                "/api/novels/{}/deconstruction-runs".format(novel_id),
                json={
                    "provider_id": provider["id"],
                    "source_text": source,
                    "dimensions": ["characters", "theme"],
                    "options": {},  # refine 默认开
                },
            )
            assert created.status_code == 202, created.text
            run = _wait_completed(client, novel_id, created.json()["id"])
            assert run["status"] == "completed", run
            assert run["error_code"] == "", run  # 精炼成功，不应标 PARTIAL

            buckets = _by_type_status(novel_id)

            # 人物：审校淘汰 1 条（李雷→discarded），存活 1 条（周明→staged）
            staged_chars = buckets.get(("staged_decon_characters", "staged"), [])
            discarded_chars = buckets.get(("staged_decon_characters", "discarded"), [])
            assert len(staged_chars) == 1
            assert len(discarded_chars) == 1
            assert loads(staged_chars[0].content_json, {})["name"] == "周明"
            assert loads(discarded_chars[0].content_json, {})["name"] == "李雷"
            # 淘汰理由记入 metadata（审计可追溯，非静默吞）
            assert loads(discarded_chars[0].metadata_json, {}).get("critique", {}).get("verdict") == "drop"

            # 精炼：存活的周明被标了层级与复用度，写进 content_json
            zhou = loads(staged_chars[0].content_json, {})
            assert zhou["layer"] == "signature"
            assert zhou["reuse_score"] == 9.0
            assert "复刻" in zhou["reuse_note"]

            # 主题：审校全判 drop → 失灵护栏拦下 → 两条都保留为 staged，且都被精炼标注
            staged_themes = buckets.get(("staged_decon_theme", "staged"), [])
            assert len(staged_themes) == 2
            assert buckets.get(("staged_decon_theme", "discarded"), []) == []
            layers = sorted(loads(t.content_json, {}).get("layer", "") for t in staged_themes)
            assert layers == ["pattern", "signature"]

            # candidate_count 排除 discarded：周明 + 两个主题 = 3（李雷不计）
            assert run["candidate_count"] == 3, run

            # 托底·可逆：把被 AI 误杀的李雷恢复为待采纳 → 回到 staged、清掉审校痕迹、可再采纳
            cid = discarded_chars[0].id
            resp = client.post("/api/story-engineering/candidates/{}/restore".format(cid))
            assert resp.status_code == 200, resp.text
            assert resp.json()["status"] == "staged"
            after = _by_type_status(novel_id)
            assert len(after.get(("staged_decon_characters", "staged"), [])) == 2  # 周明 + 恢复的李雷
            assert after.get(("staged_decon_characters", "discarded"), []) == []
            restored = next(r for r in after[("staged_decon_characters", "staged")]
                            if loads(r.content_json, {})["name"] == "李雷")
            assert "critique" not in loads(restored.metadata_json, {})
            # 恢复后可正常采纳
            assert client.post("/api/story-engineering/candidates/{}/accept".format(cid)).status_code == 200
    finally:
        server.shutdown()
        server.server_close()


def test_refine_disabled_keeps_baseline_only():
    """options.refine=false → 跳过审校/精炼，候选保持 map-reduce 基线，无 layer 标注。"""
    server = _start_server()
    try:
        with TestClient(app) as client:
            _project, novel, provider = _bootstrap(client, server.server_address[1])
            novel_id = novel["id"]
            source = "第一章\n" + "甲" * 400

            created = client.post(
                "/api/novels/{}/deconstruction-runs".format(novel_id),
                json={
                    "provider_id": provider["id"],
                    "source_text": source,
                    "dimensions": ["characters"],
                    "options": {"refine": False},
                },
            )
            assert created.status_code == 202, created.text
            run = _wait_completed(client, novel_id, created.json()["id"])
            assert run["status"] == "completed", run

            buckets = _by_type_status(novel_id)
            # 关掉精炼：两个角色都还在 staged（无审校淘汰），且无 layer 标注
            staged = buckets.get(("staged_decon_characters", "staged"), [])
            assert len(staged) == 2
            assert buckets.get(("staged_decon_characters", "discarded"), []) == []
            for r in staged:
                assert "layer" not in loads(r.content_json, {})
    finally:
        server.shutdown()
        server.server_close()
