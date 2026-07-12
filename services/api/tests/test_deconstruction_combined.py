import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.entities import CreativeRun

# 合并抽取：一次调用产出全部维度的完整 JSON（每块返回相同内容 → 跨块 reduce 应去重）。
COMBINED = {
    "characters": [{"name": "周明", "role": "主角", "description": "记忆档案员", "confidence": 0.8, "evidence": "出场"}],
    "world_rules": [{"name": "记忆可删除", "category": "technology", "description": "可删改他人记忆", "cost": "人格残缺", "priority": 85, "confidence": 0.9, "evidence": "设定"}],
    "timeline": [{"title": "发现记忆被改", "story_time": "第三天", "description": "档案库比对", "characters": ["周明"], "confidence": 0.8, "evidence": "转折"}],
    "plot_threads": [{"name": "追查真相", "description": "主线", "status": "open", "resolution": "", "confidence": 0.85, "evidence": "贯穿"}],
    "meta_items": [{"genre": "悬疑", "logline": "删除记忆的人发现被改写", "premise": "记忆与真实", "confidence": 0.8, "evidence": "整体"}],
    "beats": [{"name": "开场钩子", "description": "发现异常", "position": "opening", "confidence": 0.7, "evidence": "首段"}],
    "items": [{"setup": "旧照片", "payoff": "伪造", "status": "open", "confidence": 0.7, "evidence": "照片"}],
    "themes": [{"name": "记忆与身份", "description": "自我认同", "motifs": "镜子", "confidence": 0.8, "evidence": "通篇"}],
    "pov_items": [{"person": "第一人称", "viewpoint_character": "周明", "notes": "限制视角", "confidence": 0.7, "evidence": "叙述"}],
    "style_items": [{"summary": "冷峻短句", "narrative_voice": "疏离", "confidence": 0.9, "evidence": "通篇"}],
}


class CombinedMockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        prompt = payload.get("messages", [{}])[0].get("content", "")
        content = json.dumps(COMBINED if "AGENT: decon_combined" in prompt else {"unexpected": True}, ensure_ascii=False)
        body = json.dumps(
            {"choices": [{"message": {"role": "assistant", "content": content}}], "usage": {"prompt_tokens": 40, "completion_tokens": 60}}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def _start_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), CombinedMockHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _wait_completed(client, novel_id, run_id):
    deadline = time.time() + 25
    while time.time() < deadline:
        run = client.get("/api/novels/{}/deconstruction-runs/{}".format(novel_id, run_id)).json()
        if run["status"] in {"completed", "failed"}:
            return run
        time.sleep(0.05)
    raise AssertionError("拆解任务未在期限内完成")


def test_combined_extraction_one_call_per_chunk_and_parallel():
    server = _start_server()
    try:
        with TestClient(app) as client:
            project = client.post("/api/projects", json={"name": "合并拆解"}).json()
            novel = client.post("/api/novels", json={"project_id": project["id"], "title": "目标新作"}).json()
            provider = client.post(
                "/api/model-providers",
                json={
                    "name": "Combined Mock",
                    "provider_type": "openai_compatible",
                    "base_url": "http://127.0.0.1:{}/v1".format(server.server_address[1]),
                    "model": "combined-mock",
                    "timeout_seconds": 5,
                },
            ).json()
            novel_id = novel["id"]
            source = "第一章\n" + "甲" * 1500 + "\n\n第二章\n" + "乙" * 1500 + "\n\n第三章\n" + "丙" * 1500

            created = client.post(
                "/api/novels/{}/deconstruction-runs".format(novel_id),
                json={
                    "provider_id": provider["id"],
                    "source_text": source,
                    "dimensions": ["characters", "worldbuilding", "timeline", "plot_threads", "meta", "structure", "setup_payoff", "theme", "pov", "style_fingerprint"],
                    "options": {"merge_dimensions": True, "max_parallel": 3, "chunk_tokens": 1000},
                },
            )
            assert created.status_code == 202, created.text
            run_id = created.json()["id"]

            run = _wait_completed(client, novel_id, run_id)
            assert run["status"] == "completed", run
            chunk_count = run["chunk_count"]
            assert chunk_count >= 3  # 仍走多块
            # 分组合并：10 维 / 每组 4 = 3 组；total_units == 块数 × 组数（而不是 维度×块 的 10×）
            assert run["total_units"] == chunk_count * 3

            candidates = client.get("/api/novels/{}/story-engineering/candidates".format(novel_id)).json()
            by_type = {}
            for c in candidates:
                by_type.setdefault(c["record_type"], []).append(c)

            # 10 个维度各恰好 1 条（跨块 reduce 去重）
            for rt in [
                "staged_decon_characters", "staged_decon_worldbuilding", "staged_decon_timeline",
                "staged_decon_plot_threads", "staged_decon_meta", "staged_decon_structure",
                "staged_decon_setup_payoff", "staged_decon_theme", "staged_decon_pov",
                "staged_decon_style_fingerprint",
            ]:
                assert len(by_type.get(rt, [])) == 1, (rt, by_type.get(rt))

            # 关键：每块按 3 组各调用一次（operation=decon_combined），调用数 == 块数×3，而非 10×块
            with SessionLocal() as db:
                combined_calls = db.query(CreativeRun).filter(
                    CreativeRun.novel_id == novel_id, CreativeRun.operation == "decon_combined"
                ).count()
                assert combined_calls == chunk_count * 3, combined_calls
                # 没有逐维度调用
                per_dim = db.query(CreativeRun).filter(
                    CreativeRun.novel_id == novel_id, CreativeRun.operation == "decon_characters"
                ).count()
                assert per_dim == 0

            # 候选可正常接受（沿用同一套 accept 接口）
            cid = by_type["staged_decon_worldbuilding"][0]["id"]
            resp = client.post("/api/story-engineering/candidates/{}/accept".format(cid))
            assert resp.status_code == 200, resp.text
    finally:
        server.shutdown()
        server.server_close()


class FallbackMockHandler(BaseHTTPRequestHandler):
    """合并调用返回截断的非法 JSON；逐维度调用返回正常 → 验证回退路径。"""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        prompt = payload.get("messages", [{}])[0].get("content", "")
        if "AGENT: decon_combined" in prompt:
            content = '{ "characters": [ {"name": "周明"'  # 截断，非法 JSON
        elif "AGENT: decon_characters" in prompt:
            content = json.dumps({"characters": [{"name": "周明", "confidence": 0.8, "evidence": "x"}]}, ensure_ascii=False)
        elif "AGENT: decon_worldbuilding" in prompt:
            content = json.dumps({"world_rules": [{"name": "记忆可删除", "confidence": 0.8, "evidence": "x"}]}, ensure_ascii=False)
        else:
            content = json.dumps({"unexpected": True})
        body = json.dumps(
            {"choices": [{"message": {"role": "assistant", "content": content}}], "usage": {"prompt_tokens": 30, "completion_tokens": 20}}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def test_combined_falls_back_to_per_dimension_on_parse_failure():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FallbackMockHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with TestClient(app) as client:
            project = client.post("/api/projects", json={"name": "回退测试"}).json()
            novel = client.post("/api/novels", json={"project_id": project["id"], "title": "目标"}).json()
            provider = client.post(
                "/api/model-providers",
                json={"name": "Fallback Mock", "provider_type": "openai_compatible",
                      "base_url": "http://127.0.0.1:{}/v1".format(server.server_address[1]),
                      "model": "fallback-mock", "timeout_seconds": 5},
            ).json()
            novel_id = novel["id"]
            created = client.post(
                "/api/novels/{}/deconstruction-runs".format(novel_id),
                json={"provider_id": provider["id"], "source_text": "周明是记忆档案员，档案局可删除记忆。",
                      "dimensions": ["characters", "worldbuilding"],
                      "options": {"merge_dimensions": True, "max_parallel": 1}},
            )
            assert created.status_code == 202, created.text
            run = _wait_completed(client, novel_id, created.json()["id"])
            assert run["status"] == "completed", run

            candidates = client.get("/api/novels/{}/story-engineering/candidates".format(novel_id)).json()
            kinds = {c["record_type"] for c in candidates}
            # 合并失败但回退逐维度 → 两个维度的候选都拿到了，没有整块丢失
            assert "staged_decon_characters" in kinds
            assert "staged_decon_worldbuilding" in kinds

            with SessionLocal() as db:
                # 合并调用失败被记录
                assert db.query(CreativeRun).filter(
                    CreativeRun.novel_id == novel_id, CreativeRun.operation == "decon_combined", CreativeRun.status == "failed"
                ).count() >= 1
                # 回退的逐维度调用成功
                assert db.query(CreativeRun).filter(
                    CreativeRun.novel_id == novel_id, CreativeRun.operation == "decon_characters", CreativeRun.status == "completed"
                ).count() >= 1
    finally:
        server.shutdown()
        server.server_close()


def test_decon_item_coerces_list_to_string():
    """本地模型把字符串字段返回成数组时，应宽松拼接而非整条校验失败丢维度。"""
    from app.schemas.deconstruction import DeconCharacter, DeconTheme

    t = DeconTheme(name="身份", motifs=["镜子", "面具"], confidence=0.8)
    assert t.motifs == "镜子、面具"
    c = DeconCharacter(name="周明", personality=["谨慎", "隐忍"])
    assert c.personality == "谨慎、隐忍"
    # 正常字符串不受影响
    assert DeconTheme(name="x", motifs="单一母题").motifs == "单一母题"
