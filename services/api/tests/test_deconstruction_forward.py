import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.entities import CanonState, Character, PlotThread, TimelineEvent, WorldRule


class DeconMockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        prompt = payload.get("messages", [{}])[0].get("content", "")

        if "AGENT: decon_characters" in prompt:
            content = json.dumps(
                {
                    "characters": [
                        {
                            "name": "周明",
                            "role": "主角",
                            "description": "记忆档案员",
                            "personality": "谨慎",
                            "goals": "查清童年真相",
                            "arc": "从顺从到反抗",
                            "relationships": "与上司对立",
                            "confidence": 0.8,
                            "evidence": "原文多次出场",
                        }
                    ]
                },
                ensure_ascii=False,
            )
        elif "AGENT: decon_worldbuilding" in prompt:
            content = json.dumps(
                {
                    "world_rules": [
                        {
                            "name": "记忆可删除",
                            "category": "technology",
                            "description": "档案局可删除并改写他人记忆",
                            "cost": "被删者人格残缺",
                            "priority": 85,
                            "confidence": 0.9,
                            "evidence": "设定核心",
                        }
                    ]
                },
                ensure_ascii=False,
            )
        elif "AGENT: decon_timeline" in prompt:
            content = json.dumps(
                {
                    "timeline": [
                        {
                            "title": "周明发现童年记忆被改",
                            "story_time": "故事第三天",
                            "description": "在档案库比对到异常",
                            "characters": ["周明"],
                            "confidence": 0.8,
                            "evidence": "关键转折",
                        }
                    ]
                },
                ensure_ascii=False,
            )
        elif "AGENT: decon_plot_threads" in prompt:
            content = json.dumps(
                {
                    "plot_threads": [
                        {
                            "name": "追查童年真相",
                            "description": "主角逐步揭开自己记忆被篡改的主线",
                            "status": "open",
                            "resolution": "",
                            "confidence": 0.85,
                            "evidence": "贯穿全篇",
                        }
                    ]
                },
                ensure_ascii=False,
            )
        else:
            content = json.dumps({"unexpected": True})

        body = json.dumps(
            {
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 40},
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
    server = ThreadingHTTPServer(("127.0.0.1", 0), DeconMockHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _bootstrap(client, port):
    project = client.post("/api/projects", json={"name": "拆解测试"}).json()
    novel = client.post(
        "/api/novels", json={"project_id": project["id"], "title": "目标新作"}
    ).json()
    provider = client.post(
        "/api/model-providers",
        json={
            "name": "Decon Mock",
            "provider_type": "openai_compatible",
            "base_url": "http://127.0.0.1:{}/v1".format(port),
            "model": "decon-mock",
            "timeout_seconds": 5,
        },
    ).json()
    return project, novel, provider


def test_deconstruction_end_to_end():
    server = _start_server()
    try:
        with TestClient(app) as client:
            _project, novel, provider = _bootstrap(client, server.server_address[1])
            novel_id = novel["id"]

            run = client.post(
                "/api/novels/{}/deconstruction/run".format(novel_id),
                json={
                    "provider_id": provider["id"],
                    "source_text": "周明是档案局的记忆档案员。某天他在档案库发现自己的童年记忆被人改写过。",
                    "dimensions": ["characters", "worldbuilding", "timeline", "plot_threads"],
                },
            )
            assert run.status_code == 200, run.text
            candidates = run.json()
            kinds = {c["record_type"] for c in candidates}
            assert kinds == {
                "staged_decon_characters",
                "staged_decon_worldbuilding",
                "staged_decon_timeline",
                "staged_decon_plot_threads",
            }
            for c in candidates:
                assert c["status"] == "staged"

            # 生成阶段不落库
            with SessionLocal() as db:
                assert db.query(Character).filter(Character.novel_id == novel_id).count() == 0

            by_type = {c["record_type"]: c for c in candidates}

            def accept(record_type):
                resp = client.post(
                    "/api/story-engineering/candidates/{}/accept".format(by_type[record_type]["id"])
                )
                assert resp.status_code == 200, resp.text
                assert resp.json()["applied"] is True

            accept("staged_decon_characters")
            accept("staged_decon_worldbuilding")
            accept("staged_decon_timeline")
            accept("staged_decon_plot_threads")

            with SessionLocal() as db:
                assert db.query(Character).filter(Character.novel_id == novel_id, Character.name == "周明").count() == 1
                assert db.query(WorldRule).filter(WorldRule.novel_id == novel_id, WorldRule.name == "记忆可删除").count() == 1
                events = list(db.query(TimelineEvent).filter(TimelineEvent.novel_id == novel_id))
                assert any(e.title == "周明发现童年记忆被改" for e in events)
                threads = list(db.query(PlotThread).filter(PlotThread.novel_id == novel_id))
                assert any(t.name == "追查童年真相" for t in threads)
                # 世界规则的 cost 应拼进 description
                rule = db.query(WorldRule).filter(WorldRule.novel_id == novel_id).first()
                assert "代价" in rule.description
                # 不污染 Canon
                canon = db.query(CanonState).filter(CanonState.novel_id == novel_id).first()
                assert canon.character_states_json == "{}"

            # reject 一个新生成的候选不落库
            run2 = client.post(
                "/api/novels/{}/deconstruction/run".format(novel_id),
                json={
                    "provider_id": provider["id"],
                    "source_text": "另一段原文：林氏家族掌控记忆交易。",
                    "dimensions": ["plot_threads"],
                },
            ).json()
            reject = client.post(
                "/api/story-engineering/candidates/{}/reject".format(run2[0]["id"])
            )
            assert reject.status_code == 200, reject.text
            assert reject.json()["status"] == "rejected"
    finally:
        server.shutdown()
        server.server_close()
