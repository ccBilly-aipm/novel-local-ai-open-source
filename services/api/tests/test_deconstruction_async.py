import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.entities import Character, Foreshadowing, Novel


class AsyncDeconMockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        prompt = payload.get("messages", [{}])[0].get("content", "")

        if "AGENT: decon_characters" in prompt:
            # 每块都返回同名角色 → reduce 应去重为一条
            content = json.dumps(
                {"characters": [{"name": "周明", "role": "主角", "description": "记忆档案员", "confidence": 0.8, "evidence": "出场"}]},
                ensure_ascii=False,
            )
        elif "AGENT: decon_meta" in prompt:
            content = json.dumps(
                {"meta_items": [{"genre": "悬疑", "logline": "删除记忆的人发现自己被改写", "premise": "记忆与真实", "confidence": 0.8, "evidence": "整体"}]},
                ensure_ascii=False,
            )
        elif "AGENT: decon_setup_payoff" in prompt:
            content = json.dumps(
                {"items": [{"setup": "主角口袋里的旧照片", "payoff": "结尾揭示照片是伪造", "status": "open", "confidence": 0.7, "evidence": "照片"}]},
                ensure_ascii=False,
            )
        elif "AGENT: decon_style_fingerprint" in prompt:
            content = json.dumps(
                {"style_items": [{"summary": "冷峻短句，克制叙述", "narrative_voice": "疏离", "confidence": 0.9, "evidence": "通篇"}]},
                ensure_ascii=False,
            )
        else:
            content = json.dumps({"unexpected": True})

        body = json.dumps(
            {
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 30, "completion_tokens": 20},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def _start_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), AsyncDeconMockHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _bootstrap(client, port):
    project = client.post("/api/projects", json={"name": "异步拆解"}).json()
    novel = client.post("/api/novels", json={"project_id": project["id"], "title": "目标新作"}).json()
    provider = client.post(
        "/api/model-providers",
        json={
            "name": "Async Decon Mock",
            "provider_type": "openai_compatible",
            "base_url": "http://127.0.0.1:{}/v1".format(port),
            "model": "async-decon-mock",
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


def test_async_deconstruction_map_reduce_and_accept():
    server = _start_server()
    try:
        with TestClient(app) as client:
            _project, novel, provider = _bootstrap(client, server.server_address[1])
            novel_id = novel["id"]
            # 多块原文：三章各约 1500 字
            source = (
                "第一章\n" + "甲" * 1500
                + "\n\n第二章\n" + "乙" * 1500
                + "\n\n第三章\n" + "丙" * 1500
            )

            created = client.post(
                "/api/novels/{}/deconstruction-runs".format(novel_id),
                json={
                    "provider_id": provider["id"],
                    "source_text": source,
                    "dimensions": ["characters", "meta", "setup_payoff", "style_fingerprint"],
                    # 显式小分块确保多块；max_parallel 走并发逐维度路径（验证并发下跨块去重仍正确）。
                    "options": {"chunk_tokens": 1000, "max_parallel": 2},
                },
            )
            assert created.status_code == 202, created.text
            run_id = created.json()["id"]
            assert created.json()["chunk_count"] == 0 or created.json()["status"] == "pending"

            run = _wait_completed(client, novel_id, run_id)
            assert run["status"] == "completed", run
            assert run["chunk_count"] >= 3  # 多块
            assert run["candidate_count"] >= 4

            candidates = client.get(
                "/api/novels/{}/story-engineering/candidates".format(novel_id)
            ).json()
            by_type = {}
            for c in candidates:
                by_type.setdefault(c["record_type"], []).append(c)

            # reduce 去重：多块同名角色 → 只剩一条 character 候选
            assert len(by_type.get("staged_decon_characters", [])) == 1
            # 单条维度（meta/style）reduce 后只剩一条
            assert len(by_type.get("staged_decon_meta", [])) == 1
            assert len(by_type.get("staged_decon_style_fingerprint", [])) == 1
            assert len(by_type.get("staged_decon_setup_payoff", [])) >= 1

            def accept(rt):
                cid = by_type[rt][0]["id"]
                resp = client.post("/api/story-engineering/candidates/{}/accept".format(cid))
                assert resp.status_code == 200, resp.text

            accept("staged_decon_characters")
            accept("staged_decon_meta")
            accept("staged_decon_setup_payoff")
            accept("staged_decon_style_fingerprint")

            with SessionLocal() as db:
                assert db.query(Character).filter(Character.novel_id == novel_id, Character.name == "周明").count() == 1
                fresh = db.get(Novel, novel_id)
                assert "记忆" in fresh.synopsis  # meta logline 落入简介
                assert "冷峻" in fresh.style_guide  # 文风指纹落入风格指南
                assert db.query(Foreshadowing).filter(Foreshadowing.novel_id == novel_id).count() >= 1
    finally:
        server.shutdown()
        server.server_close()
